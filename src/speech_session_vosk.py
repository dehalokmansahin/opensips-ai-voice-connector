"""
Module for full-duplex speech interaction using Vosk for Speech-to-Text (STT)
and Piper for Text-to-Speech (TTS).

This module provides `SmartSpeech`, an AIEngine implementation that integrates
Vosk and Piper services. It handles real-time audio processing, voice activity
detection (VAD), STT transcription, and TTS response generation. The system is
designed for applications like voice assistants or interactive voice response
systems.

Key Components:
- `SmartSpeech`: The main class orchestrating the STT/TTS pipeline. It manages
                 the overall session, user interaction flow, and communication
                 with external STT/TTS services.
- `AudioProcessor`: Processes raw incoming audio (expected in PCMU format) into a
                    format suitable for STT (16kHz, 16-bit PCM mono). This includes
                    decoding, resampling, normalization, and noise reduction.
- `VADProcessor`: Buffers processed audio and applies Voice Activity Detection
                  to identify speech segments, controlling when audio is sent to
                  the STT engine.
- `TranscriptHandler`: Manages partial and final transcripts received from the
                       STT service, providing the most current recognized text.
- `TTSProcessor`: Generates speech audio from text using a Piper TTS client,
                  processes this audio (e.g., resampling to the desired output rate),
                  and queues it for playback. Handles barge-in to interrupt TTS
                  when user speech is detected.

The system is designed to be asynchronous, leveraging `asyncio` for concurrent
operations such as receiving user audio, streaming to STT, receiving transcripts,
and generating/playing TTS audio.
"""
from codec import get_codecs, PCMU, UnsupportedCodec # For SDP parsing and codec handling
from vad_detector import VADDetector # Silero VAD wrapper
from config import Config # For application configuration
import torch # For tensor operations, primarily in audio processing
import asyncio # For asynchronous programming
from ai import AIEngine # Base class for AI engine implementations
from queue import Empty, Queue # For synchronous queue (rtp_queue for TTS output)
import json # For STT message parsing (Vosk primarily)
import logging # For application logging
from typing import Any, Callable, Awaitable, Optional, Tuple # For type hinting
from vosk_client import VoskClient # Client for Vosk STT server
import torchaudio # For audio resampling and transformations
import time # For timing VAD buffer flushes, etc.
from pcmu_decoder import PCMUDecoder # For decoding PCMU audio
import websockets # For Vosk WebSocket communication (used by VoskClient)
# import traceback # Unused: logging with exc_info=True is generally preferred
import audioop  # For mu-law encoding/decoding if needed (TTS output to PCMU)
import random  # For simulated LLM responses (placeholder)
from piper_client import PiperClient # Client for Piper TTS server

class AudioProcessor:
    """
    Handles audio processing for speech recognition.

    This class takes raw audio bytes (expected in PCMU format, 8kHz),
    decodes them, performs cleaning (NaN/Inf removal), normalization,
    resampling to a target sample rate (e.g., 16kHz for STT), and
    converts the audio to both a PyTorch tensor and 16-bit PCM byte format.
    """
    
    def __init__(self, target_sample_rate: int = 16000, debug: bool = False, session_id: str = ""):
        """
        Initializes the AudioProcessor.

        Args:
            target_sample_rate: The desired sample rate for the output audio, typically 16000 Hz for STT.
            debug: If True, enables detailed debug logging for audio processing steps.
            session_id: An identifier for the current session, used for contextual logging.
        """
        self.target_sample_rate: int = target_sample_rate
        self.debug: bool = debug
        self.session_id: str = session_id
        
        self.pcmu_decoder: PCMUDecoder = PCMUDecoder()
        self.resampler: torchaudio.transforms.Resample = torchaudio.transforms.Resample(
            orig_freq=8000,  # PCMU is typically 8kHz
            new_freq=self.target_sample_rate
        )
        logging.info(f"{self.session_id}AudioProcessor initialized for target sample rate {self.target_sample_rate}Hz.")

    def tensor_to_bytes(self, tensor: torch.Tensor) -> bytes:
        """
        Converts a float32 audio tensor to 16-bit PCM bytes (little-endian).

        The input tensor is expected to contain audio samples in the range [-1.0, 1.0].
        Values outside this range will be clamped. The tensor is then scaled to the
        int16 range [-32768, 32767] and converted to raw bytes.

        Args:
            tensor: A PyTorch float32 audio tensor (1D).
            
        Returns:
            Audio data as a byte string in 16-bit PCM format.
        """
        # Ensure tensor values are within the expected float range [-1.0, 1.0]
        clamped_tensor = torch.clamp(tensor, -1.0, 1.0)
        # Scale to int16 range, convert type, then to bytes
        # Note: .numpy().tobytes() uses the system's native endianness, usually little-endian.
        return (clamped_tensor * 32767.0).to(torch.int16).numpy().tobytes() # Max int16 is 32767
    
    def process_bytes_audio(self, audio: bytes) -> Tuple[Optional[torch.Tensor], Optional[bytes]]:
        """
        Processes raw PCMU audio bytes into a resampled float32 tensor and 16-bit PCM bytes.

        The pipeline includes:
        1. Decoding PCMU bytes to float32 PCM NumPy array.
        2. Converting NumPy array to a PyTorch tensor.
        3. Cleaning the tensor (removing NaN/Inf values).
        4. Normalizing audio levels if too quiet.
        5. Resampling the audio to the target sample rate.
        6. Converting the final resampled tensor to 16-bit PCM bytes.

        Args:
            audio: Raw audio bytes, expected in PCMU (G.711 mu-law) format.
            
        Returns:
            tuple: A tuple containing:
                - resampled_tensor (torch.Tensor | None): The processed and resampled audio
                  as a float32 PyTorch tensor, or None if processing failed.
                - audio_bytes (bytes | None): The processed audio converted to 16-bit PCM bytes,
                  suitable for STT engines, or None if processing failed.
        """
        if len(audio) == 0:
            logging.warning(f"{self.session_id}Received empty audio bytes. Skipping processing.")
            return None, None
            
        if self.debug:
            logging.debug(f"{self.session_id}Raw input audio: {len(audio)} bytes")
        
        try:
            # Step 1: Decode PCMU bytes to a float32 NumPy array (8kHz)
            # Note: pcmu_decoder.decode returns a NumPy array.
            pcm32_samples_np = self.pcmu_decoder.decode(audio) 

            if pcm32_samples_np is None or pcm32_samples_np.size == 0:
                logging.warning(f"{self.session_id}PCMU decoder returned empty result. Skipping processing.")
                return None, None
            
            if self.debug:
                logging.debug(f"{self.session_id}Decoded PCMU to float32 PCM samples: count={len(pcm32_samples_np)}")
            
            # Step 2: Convert float32 NumPy array to a float32 PyTorch tensor
            audio_tensor = torch.from_numpy(pcm32_samples_np)
            if self.debug:
                logging.debug(f"{self.session_id}Converted NumPy to 8kHz PyTorch tensor: shape={audio_tensor.shape}, dtype={audio_tensor.dtype}, min={audio_tensor.min():.4f}, max={audio_tensor.max():.4f}")
            
            # Step 3: Clean tensor by removing NaN or Inf values
            audio_tensor = self._clean_tensor(audio_tensor)
            
            # Step 4: Normalize audio levels, especially for very quiet audio
            audio_tensor = self._normalize_audio(audio_tensor)
            
            # Step 5: Resample the audio tensor from 8kHz to the target sample rate (e.g., 16kHz)
            resampled_tensor = self.resampler(audio_tensor.unsqueeze(0)).squeeze(0)
            if self.debug:
                logging.debug(f"{self.session_id}Resampled tensor to {self.target_sample_rate}Hz: shape={resampled_tensor.shape}, dtype={resampled_tensor.dtype}, min={resampled_tensor.min():.4f}, max={resampled_tensor.max():.4f}")
            
            if resampled_tensor.shape[0] == 0:
                logging.warning(f"{self.session_id}Resampling resulted in an empty tensor. Skipping.")
                return None, None
            
            # Step 6: Convert the final float32 resampled tensor to 16-bit PCM bytes
            audio_bytes_out = self.tensor_to_bytes(resampled_tensor)
            
            if self.debug:
                logging.debug(f"{self.session_id}Final processed audio bytes length: {len(audio_bytes_out)}")
            
            return resampled_tensor, audio_bytes_out
            
        except Exception as e:
            logging.error(f"{self.session_id}Error processing audio bytes: {e}", exc_info=True)
            return None, None
    
    def _clean_tensor(self, tensor: torch.Tensor) -> torch.Tensor:
        """
        Cleans an audio tensor by replacing NaN or Inf values.

        NaN values are replaced with 0.0.
        Positive infinity values are replaced with 0.99.
        Negative infinity values are replaced with -0.99.

        Args:
            tensor: The input PyTorch audio tensor.
            
        Returns:
            torch.Tensor: The cleaned audio tensor.
        """
        if torch.isnan(tensor).any() or torch.isinf(tensor).any():
            if self.debug:
                logging.debug(f"{self.session_id}Audio tensor contains NaN or Inf values. Cleaning tensor.")
            return torch.nan_to_num(tensor, nan=0.0, posinf=0.99, neginf=-0.99)
        return tensor
    
    def _normalize_audio(self, tensor: torch.Tensor) -> torch.Tensor:
        """
        Normalizes audio levels, particularly for very quiet audio.

        If the maximum absolute amplitude of the tensor is below a threshold (0.005),
        a gain is applied to boost the audio level. The gain is capped to avoid
        excessive amplification.

        Args:
            tensor: The input PyTorch audio tensor.
            
        Returns:
            torch.Tensor: The (potentially) normalized audio tensor.
        """
        audio_max = torch.max(torch.abs(tensor))
        
        if audio_max < 0.005: 
            gain = min(0.2 / (audio_max + 1e-10), 5.0) 
            tensor = tensor * gain
            if self.debug:
                logging.debug(f"{self.session_id}Applied normalization with gain: {gain:.2f}")
        
        return tensor

class VADProcessor:
    """
    Manages Voice Activity Detection (VAD) state and audio buffering.

    This class buffers incoming audio chunks (already processed into 16-bit PCM)
    and, once a configurable buffer duration is reached, passes the complete
    buffer to an underlying `VADDetector` instance (e.g., Silero VAD).
    It maintains a state (`speech_active`) based on consecutive speech/silence
    determinations from the VAD detector, implementing thresholds for speech
    start and end detection. This helps in smoothing out VAD decisions and
    controlling when audio is forwarded to the STT engine.
    """
    
    def __init__(self, 
                 vad_detector: VADDetector, 
                 target_sample_rate: int, 
                 vad_buffer_chunk_ms: int = 750, 
                 speech_detection_threshold: int = 1, # Default changed from 3 in original to 1
                 silence_detection_threshold: int = 1, # Default changed from 10 in original to 1
                 debug: bool = False, 
                 session_id: str = ""):
        """
        Initializes the VADProcessor.

        Args:
            vad_detector: An instance of a VAD detector (e.g., `VADDetector` wrapping Silero).
            target_sample_rate: The sample rate of the audio being processed (e.g., 16000 Hz).
                                This is used to calculate buffer duration in milliseconds.
            vad_buffer_chunk_ms: Duration of audio (in ms) to buffer before passing to `vad_detector`.
            speech_detection_threshold: Number of consecutive `vad_detector` speech chunks
                                        required to trigger the `speech_active` state.
            silence_detection_threshold: Number of consecutive `vad_detector` silence chunks
                                         required to deactivate the `speech_active` state.
            debug: If True, enables detailed debug logging for VAD processing.
            session_id: An identifier for the current session, used for contextual logging.
        """
        self.vad: VADDetector = vad_detector
        self.target_sample_rate: int = target_sample_rate
        self.vad_buffer_chunk_ms: int = vad_buffer_chunk_ms
        self.speech_detection_threshold: int = speech_detection_threshold
        self.silence_detection_threshold: int = silence_detection_threshold
        self.debug: bool = debug
        self.session_id: str = session_id
        
        self._vad_buffer: bytearray = bytearray()  # Buffer for storing incoming audio bytes
        self._vad_buffer_size_samples: int = 0     # Current size of the buffer in audio samples
        self._last_buffer_flush_time: float = time.time() # Timestamp of the last buffer processing
        self._vad_buffer_locks: asyncio.Lock = asyncio.Lock() # Lock for concurrent access to buffer
        
        self.consecutive_speech_packets: int = 0 # Counter for consecutive speech chunks
        self.consecutive_silence_packets: int = 0 # Counter for consecutive silence chunks
        self.speech_active: bool = False  # Overall VAD state: True if speech is ongoing
        
        # New: Add speech timing tracking for timeout detection
        self.speech_start_time: float = 0.0  # When current speech started
        self.last_speech_activity_time: float = 0.0  # Last time any speech was detected
        self.speech_timeout_seconds: float = 10.0  # Maximum speech duration before forcing final
        self.silence_timeout_seconds: float = 3.0   # Maximum silence after speech before forcing final
        
        logging.info(
            f"{self.session_id}VADProcessor initialized: "
            f"ChunkMs={self.vad_buffer_chunk_ms}, SpeechThresh={self.speech_detection_threshold}, "
            f"SilenceThresh={self.silence_detection_threshold}"
        )
    
    def reset_vad_state(self, preserve_buffer: bool = False) -> None:
        """
        Resets the VAD state counters and optionally clears the audio buffer.

        Args:
            preserve_buffer: If True, keeps the current audio buffer. If False, clears it.
        """
        logging.info(
            f"{self.session_id}VAD state reset. Speech was {'active' if self.speech_active else 'inactive'}. "
            f"Buffer {'preserved' if preserve_buffer else 'cleared'}."
        )
        
        # Reset state counters
        self.consecutive_speech_packets = 0
        self.consecutive_silence_packets = 0
        
        # Reset speech timing
        self.speech_start_time = 0.0
        self.last_speech_activity_time = time.time()
        
        # Optionally clear buffer
        if not preserve_buffer:
            self._vad_buffer.clear()
            self._vad_buffer_size_samples = 0
            self._last_buffer_flush_time = time.time()
        
        # Important: Set speech_active to False after resetting counters but before any new processing
        self.speech_active = False

    async def add_audio(self, audio_bytes: bytes, num_samples: int) -> Tuple[bool, bool, Optional[bytes]]:
        """
        Adds audio data to the internal buffer and processes it for VAD if the buffer reaches `vad_buffer_chunk_ms`.

        Args:
            audio_bytes: The raw audio data (16-bit PCM bytes) to add to the buffer.
            num_samples: The number of audio samples represented by `audio_bytes`.

        Returns:
            A tuple (was_processed, is_speech, processed_buffer_bytes):
            - `was_processed` (bool): True if a full buffer chunk was processed for VAD, False otherwise.
            - `is_speech` (bool): If `was_processed` is True, this indicates if the processed chunk
                                  (or overall VAD state) determined speech. Otherwise, it's False.
            - `processed_buffer_bytes` (Optional[bytes]): If `was_processed` is True, this contains
                                                          the audio bytes of the processed chunk.
                                                          Otherwise, it's None.
        """
        async with self._vad_buffer_locks: 
            self._vad_buffer.extend(audio_bytes)
            self._vad_buffer_size_samples += num_samples
            
            # Calculate current buffer duration in milliseconds
            buffer_duration_ms = (self._vad_buffer_size_samples / self.target_sample_rate) * 1000
            
            # If buffer duration meets or exceeds the configured chunk size, process it
            if buffer_duration_ms >= self.vad_buffer_chunk_ms:
                if self.debug:
                    logging.debug(
                        f"{self.session_id}VAD buffer reached {buffer_duration_ms:.2f}ms "
                        f"(threshold {self.vad_buffer_chunk_ms}ms), processing for VAD."
                    )
                # Process the buffered audio for VAD
                is_speech_decision, processed_chunk_bytes = await self._process_buffer()
                return True, is_speech_decision, processed_chunk_bytes # Buffer was processed
                
            return False, False, None # Buffer not yet full enough to process
    
    async def _process_buffer(self) -> Tuple[bool, bytes]:
        """
        Processes the current VAD buffer using the VAD detector.

        This is called when the buffer reaches its configured chunk size.
        It applies VAD to the buffered audio and updates the speech state based on
        consecutive speech/silence detection thresholds.

        Returns:
            A tuple containing:
            - is_speech_in_current_chunk: Whether speech was detected in this chunk
            - buffer_bytes: The audio bytes that were processed (for forwarding to STT)
        """
        if self.debug:
            logging.debug(f"{self.session_id}VAD processing buffer of {len(self._vad_buffer)} bytes.")
        
        # Create a tensor from the buffer for VAD analysis
        buffer_bytes = bytes(self._vad_buffer) # Copy buffer data before clearing
        audio_tensor = torch.frombuffer(buffer_bytes, dtype=torch.int16).float() / 32768.0 # Normalize to [-1, 1]
        
        # Clear buffer after copying
        self._vad_buffer.clear()
        self._vad_buffer_size_samples = 0
        self._last_buffer_flush_time = time.time()
        
        # Apply VAD to determine if speech is present in this chunk
        is_speech_in_current_chunk = self.vad.is_speech(audio_tensor)
        
        current_time = time.time()
        
        # Update consecutive counters based on VAD result
        if is_speech_in_current_chunk:
            self.consecutive_speech_packets += 1
            self.consecutive_silence_packets = 0 # Reset silence counter
            self.last_speech_activity_time = current_time
            if self.speech_start_time == 0.0:
                self.speech_start_time = current_time
                
            if self.debug:
                logging.debug(
                    f"{self.session_id}VAD detected speech in chunk "
                    f"(consecutive_speech={self.consecutive_speech_packets})"
                )
                
            # Check if we should activate speech state
            if self.consecutive_speech_packets >= self.speech_detection_threshold and not self.speech_active:
                self.speech_active = True
                self.speech_start_time = current_time
                logging.info(
                    f"{self.session_id}Speech started (VAD active) after "
                    f"{self.consecutive_speech_packets} consecutive speech chunk(s)."
                )
        else: # Current chunk is silent
            self.consecutive_silence_packets += 1
            self.consecutive_speech_packets = 0 # Reset speech counter
            
            if self.debug and self.speech_active:
                logging.debug(
                    f"{self.session_id}VAD detected silence in chunk while speech was active "
                    f"(consecutive_silence={self.consecutive_silence_packets})"
                )
            
            # Check if we should deactivate speech state
            if self.consecutive_silence_packets >= self.silence_detection_threshold and self.speech_active:
                self.speech_active = False
                self.speech_start_time = 0.0
                logging.info(
                    f"{self.session_id}Speech ended (VAD inactive) after "
                    f"{self.consecutive_silence_packets} consecutive silence chunk(s)."
                )
        
        # Determine if this chunk should be sent to STT:
        # Send if the current chunk itself contains speech, OR if speech is already generally active
        # (e.g., to capture trailing audio after speech ends but before silence threshold is fully met).
        send_chunk_to_stt = is_speech_in_current_chunk or self.speech_active
        
        if self.debug:
            logging.debug(
                f"{self.session_id}VAD decision: speech_in_chunk={is_speech_in_current_chunk}, "
                f"speech_active={self.speech_active}, send_to_stt={send_chunk_to_stt}"
            )

        return send_chunk_to_stt, buffer_bytes

    def has_speech_timeout(self) -> bool:
        """Check if speech has been going on too long and should be forced to end."""
        if not self.speech_active or self.speech_start_time == 0.0:
            return False
        
        current_time = time.time()
        speech_duration = current_time - self.speech_start_time
        return speech_duration > self.speech_timeout_seconds

    def has_silence_timeout(self) -> bool:
        """Check if silence after speech has gone on too long."""
        if self.speech_active or self.last_speech_activity_time == 0.0:
            return False
        
        current_time = time.time()
        silence_duration = current_time - self.last_speech_activity_time
        return silence_duration > self.silence_timeout_seconds

    async def process_final_buffer(self) -> Tuple[bool, Optional[bytes]]:
        """
        Processes any remaining audio in the VAD buffer.
        
        This is typically called at the end of an audio stream to ensure any
        lingering audio data is processed for VAD.

        Returns:
            A tuple (is_speech, processed_buffer_bytes):
            - `is_speech` (bool): True if the final processed chunk (or overall VAD state)
                                  determined speech. False if no data or no speech.
            - `processed_buffer_bytes` (Optional[bytes]): The audio bytes of the final
                                                          processed chunk, or None if no data.
        """
        async with self._vad_buffer_locks: 
            if len(self._vad_buffer) > 0:
                if self.debug:
                    buffer_duration_ms = (self._vad_buffer_size_samples / self.target_sample_rate) * 1000
                    logging.debug(
                        f"{self.session_id}Processing remaining VAD buffer: "
                        f"{buffer_duration_ms:.2f} ms ({self._vad_buffer_size_samples} samples)."
                    )
                # Process the remaining audio in the buffer
                is_speech_decision, processed_chunk_bytes = await self._process_buffer()
                return is_speech_decision, processed_chunk_bytes
            
        if self.debug:
            logging.debug(f"{self.session_id}No remaining VAD buffer to process.")
        return False, None # No buffer to process

class TranscriptHandler:
    """
    Manages STT (Speech-to-Text) transcript data.

    This class stores the last partial and final transcripts received from the
    STT service. It provides callbacks (`on_partial_transcript`, `on_final_transcript`)
    that can be set by other components to react to transcript updates.
    It also offers a method to retrieve the most definitive available transcript.
    """
    
    def __init__(self, session_id: str = ""):
        """
        Initializes the TranscriptHandler.

        Args:
            session_id: An identifier for the current session, used for contextual logging.
        """
        self.last_partial_transcript: str = ""
        self.last_final_transcript: str = ""
        self.last_partial_timestamp: float = 0.0  # When the last partial was received
        self.partial_unchanged_duration: float = 0.0  # How long the partial has been unchanged
        # Callbacks for transcript updates:
        self.on_partial_transcript: Optional[Callable[[str], Awaitable[None]]] = None
        self.on_final_transcript: Optional[Callable[[str], Awaitable[None]]] = None
        self.session_id: str = session_id
        logging.info(f"{self.session_id}TranscriptHandler initialized.")
    
    async def handle_message(self, message: str) -> bool:
        """
        Processes an incoming message (JSON string) from the STT service.

        Parses the message, updates `last_partial_transcript` and/or
        `last_final_transcript`, and triggers the respective callbacks if set.

        Args:
            message: The JSON message string from the STT service.
                     Expected to contain 'partial' or 'text' (final) fields.

        Returns:
            True if the message was successfully processed, False otherwise
            (e.g., JSON decode error).
        """
        try:
            response = json.loads(message) # Parse the JSON message
            current_time = time.time()
            
            # Handle partial transcript
            if "partial" in response:
                partial_text = response.get("partial", "").strip() # Get partial text, strip whitespace
                
                # Check if partial transcript has changed
                if partial_text != self.last_partial_transcript:
                    self.last_partial_transcript = partial_text
                    self.last_partial_timestamp = current_time
                    self.partial_unchanged_duration = 0.0
                    
                    if partial_text: # Log non-empty partials
                        logging.info(f"{self.session_id}Partial transcript: \"{partial_text}\"")
                    if self.on_partial_transcript and partial_text: # Trigger callback if set and text exists
                        await self.on_partial_transcript(partial_text)
                else:
                    # Partial hasn't changed, update duration
                    self.partial_unchanged_duration = current_time - self.last_partial_timestamp
            
            # Handle final transcript
            if "text" in response:
                final_text = response.get("text", "").strip() # Get final text, strip whitespace
                if final_text: # Process only if final text is non-empty
                    self.last_final_transcript = final_text
                    # Reset partial tracking since we got a final
                    self.last_partial_timestamp = 0.0
                    self.partial_unchanged_duration = 0.0
                    
                    # It's common for final results to also update the last partial,
                    # ensuring consistency if no further partials arrive.
                    if final_text != self.last_partial_transcript:
                        self.last_partial_transcript = final_text 

                    logging.info(f"{self.session_id}Final transcript: \"{final_text}\"")
                    if self.on_final_transcript: # Trigger callback if set
                        # Run final transcript callback as a separate task to avoid blocking
                        # the message handling loop if the callback is slow.
                        asyncio.create_task(self.on_final_transcript(final_text))
                    
            return True # Message processed successfully
                
        except json.JSONDecodeError:
            logging.error(f"{self.session_id}Invalid JSON response from STT: {message[:100]}...")
            return False
        except Exception as e:
            logging.error(f"{self.session_id}Error processing STT transcript message: {str(e)}", exc_info=True)
            return False

    def has_stale_partial(self, max_unchanged_seconds: float = 2.0) -> bool:
        """
        Checks if the current partial transcript has been unchanged for too long.
        
        Args:
            max_unchanged_seconds: Maximum time (in seconds) a partial can remain unchanged.
            
        Returns:
            True if there's a stale partial that should be promoted to final.
        """
        if not self.last_partial_transcript or self.last_partial_timestamp == 0.0:
            return False
        
        return self.partial_unchanged_duration >= max_unchanged_seconds

    def clear_transcripts(self) -> None:
        """Clears all transcript data and resets timing."""
        self.last_partial_transcript = ""
        self.last_final_transcript = ""
        self.last_partial_timestamp = 0.0
        self.partial_unchanged_duration = 0.0
    
    def get_final_transcript(self) -> str:
        """
        Retrieves the most definitive transcript available.

        It prioritizes the last final transcript. If no final transcript is
        available, it falls back to the last partial transcript. If neither is
        available, it returns an empty string.

        Returns:
            The most definitive transcript string.
        """
        if self.last_final_transcript:
            if self.debug_logging_enabled(): 
                 logging.debug(f"{self.session_id}Returning final transcript: \"{self.last_final_transcript[:70]}...\"")
            return self.last_final_transcript
        elif self.last_partial_transcript:
            if self.debug_logging_enabled():
                logging.debug(f"{self.session_id}No final transcript, returning partial: \"{self.last_partial_transcript[:70]}...\"")
            return self.last_partial_transcript
        else:
            if self.debug_logging_enabled():
                logging.debug(f"{self.session_id}No transcript (final or partial) available, returning empty string.")
            return ""

    def debug_logging_enabled(self) -> bool:
        """Helper to check if DEBUG level logging is enabled for the current logger."""
        return logging.getLogger().isEnabledFor(logging.DEBUG)

class TTSProcessor:
    """
    Handles Text-to-Speech (TTS) audio generation, processing, and queuing.

    This class interfaces with a Piper TTS client to synthesize speech from text.
    It manages the TTS audio stream, resamples it to the desired output rate
    (e.g., 8kHz for RTP/PCMU), converts it to PCMU format, and queues the
    resulting audio packets into an RTP queue for playback. It also supports
    interruption (barge-in) to stop TTS playback when user speech is detected.
    """
    def __init__(self, 
                 rtp_queue: Queue, # Note: This is stdlib queue.Queue, not asyncio.Queue
                 tts_server_host: str, 
                 tts_server_port: int, 
                 tts_voice: str,
                 tts_target_output_rate: int = 8000, 
                 session_id: str = "", 
                 debug: bool = False):
        """
        Initializes the TTSProcessor.

        Args:
            rtp_queue: The queue where processed TTS audio packets (PCMU) will be placed.
            tts_server_host: Hostname or IP address of the Piper TTS server.
            tts_server_port: Port number of the Piper TTS server.
            tts_voice: The voice to be used for TTS generation (specific to Piper server).
            tts_target_output_rate: The target sample rate for the output audio (e.g., 8000 Hz for PCMU).
            session_id: An identifier for the current session, used for contextual logging.
            debug: If True, enables detailed debug logging for TTS processing.
        """
        self.rtp_queue: Queue = rtp_queue # Synchronous queue for RTP audio packets
        self.tts_server_host: str = tts_server_host
        self.tts_server_port: int = tts_server_port
        self.tts_voice: str = tts_voice
        self.tts_target_output_rate: int = tts_target_output_rate # e.g., 8000 Hz for PCMU
        self.session_id: str = session_id
        self.debug: bool = debug

        self.tts_resampler: Optional[torchaudio.transforms.Resample] = None
        # Piper default output is 22050 Hz, 16-bit mono PCM
        self.tts_input_rate: int = 22050 
        self.tts_processing_lock: asyncio.Lock = asyncio.Lock() # Ensures one TTS generation at a time
        self._interrupt_event: asyncio.Event = asyncio.Event() # For barge-in support

        logging.info(
            f"{self.session_id}TTSProcessor initialized: Voice='{self.tts_voice}', "
            f"TargetRate={self.tts_target_output_rate}Hz, PiperHost={self.tts_server_host}:{self.tts_server_port}"
        )

    def interrupt(self) -> None:
        """
        Signals this TTSProcessor to stop its current playback and clears the RTP audio queue.
        
        This method is thread-safe as `asyncio.Event.set()` is thread-safe and
        `queue.Queue.get_nowait()` is used for draining.
        """
        if self.debug:
            logging.debug(f"{self.session_id}TTSProcessor: Interrupt signal received.")
        self._interrupt_event.set() # Signal any ongoing generation to stop
        
        # Drain the RTP queue of any pending TTS packets
        drained_count = 0
        while not self.rtp_queue.empty():
            try:
                self.rtp_queue.get_nowait() # Non-blocking get
                drained_count += 1
            except Empty: # Should not happen if rtp_queue.empty() is false, but good practice
                break 
        if drained_count > 0 and self.debug:
            logging.debug(f"{self.session_id}TTSProcessor: Drained {drained_count} packets from RTP queue during interruption.")

    async def generate_and_queue_tts_audio(self, text_to_speak: str) -> None:
        """
        Generates TTS audio from `text_to_speak`, processes it, and queues it into `rtp_queue`.

        The process involves:
        1. Connecting to the Piper TTS server.
        2. Synthesizing speech for the given text.
        3. Receiving audio chunks from Piper.
        4. For each chunk: resampling (if necessary), converting to PCMU, and packetizing.
        5. Putting packets into the `rtp_queue`.
        This method can be interrupted by calling `self.interrupt()`.

        Args:
            text_to_speak: The text string to be synthesized into speech.
        """
        self._interrupt_event.clear() # Clear interruption flag at the start of a new generation

        # Ensure only one TTS generation process runs at a time for this instance
        async with self.tts_processing_lock:
            if self.debug:
                logging.debug(f"{self.session_id}TTSProcessor: Generating audio for text: \"{text_to_speak[:70]}...\"")
            
            # Check if an interruption was signaled right before acquiring the lock or starting
            if self._interrupt_event.is_set():
                logging.info(f"{self.session_id}TTSProcessor: TTS generation cancelled at entry due to prior interrupt signal.")
                return

            # Drain RTP queue of any old TTS audio from a previous, possibly un-cancelled, run.
            # This is a safeguard. Normal interruption should handle queue draining.
            if not self.rtp_queue.empty():
                q_size = self.rtp_queue.qsize()
                logging.info(f"{self.session_id}TTSProcessor: Draining {q_size} stale packets from RTP queue before new TTS playback.")
                while not self.rtp_queue.empty():
                    try: self.rtp_queue.get_nowait()
                    except Empty: break
            
            tts_success = False
            piper_client: Optional[PiperClient] = None # Ensure defined for finally block
            
            try:
                # Check for interruption again after initial queue drain and before connecting to Piper
                if self._interrupt_event.is_set():
                    logging.info(f"{self.session_id}TTSProcessor: TTS generation cancelled before Piper connection due to interrupt.")
                    return

                piper_client = PiperClient(
                    server_host=self.tts_server_host,
                    server_port=self.tts_server_port,
                    session_id=self.session_id # Pass session ID for Piper client logging
                )
                
                cumulative_pcmu_bytes = bytearray() # Buffer for PCMU bytes before packetization
                rtp_chunk_size_bytes = 160 # Standard for G.711 PCMU in 20ms RTP packets
                first_audio_chunk_received = True # Flag to initialize resampler on first audio chunk
                
                # Define the callback for handling audio chunks from PiperClient
                async def on_audio_chunk_received(audio_bytes_from_piper: bytes):
                    nonlocal cumulative_pcmu_bytes, first_audio_chunk_received
                    
                    # If interruption is signaled, stop processing and raise CancelledError
                    # This will be caught by the main try/except block around piper_client.process_stream
                    if self._interrupt_event.is_set():
                        logging.info(f"{self.session_id}TTSProcessor: Interruption detected in on_audio callback.")
                        raise asyncio.CancelledError("TTS interrupted by user (on_audio_chunk_received)")

                    try:
                        # Initialize resampler on the first audio chunk if sample rates differ
                        if first_audio_chunk_received:
                            first_audio_chunk_received = False
                            if self.tts_input_rate != self.tts_target_output_rate:
                                if self.debug: 
                                    logging.debug(f"{self.session_id}TTSProcessor: Initializing TTS resampler: {self.tts_input_rate}Hz -> {self.tts_target_output_rate}Hz")
                                self.tts_resampler = torchaudio.transforms.Resample(
                                    orig_freq=self.tts_input_rate, 
                                    new_freq=self.tts_target_output_rate
                                )
                            elif self.debug:
                                logging.debug(f"{self.session_id}TTSProcessor: TTS input rate matches target output rate ({self.tts_target_output_rate}Hz). No resampling needed.")
                        
                        # Process the audio chunk: bytes (s16le) -> tensor -> resample (optional) -> clamp -> bytes (s16le) -> PCMU
                        input_tensor = torch.frombuffer(bytearray(audio_bytes_from_piper), dtype=torch.int16).float() / 32768.0
                        
                        processed_tensor = self.tts_resampler(input_tensor.unsqueeze(0)).squeeze(0) if self.tts_resampler else input_tensor
                        clamped_tensor = torch.clamp(processed_tensor, -1.0, 1.0)
                        # Convert float tensor back to 16-bit PCM bytes
                        pcm_s16le_bytes = (clamped_tensor * 32767.0).to(torch.int16).numpy().tobytes()
                        
                        # Convert 16-bit linear PCM to PCMU (mu-law)
                        pcmu_chunk_bytes = audioop.lin2ulaw(pcm_s16le_bytes, 2) # 2 is for 16-bit width
                        cumulative_pcmu_bytes.extend(pcmu_chunk_bytes)
                        
                        # Packetize PCMU bytes into RTP chunk sizes and queue them
                        while len(cumulative_pcmu_bytes) >= rtp_chunk_size_bytes:
                            if self._interrupt_event.is_set(): # Check before putting into queue
                                logging.info(f"{self.session_id}TTSProcessor: Interruption detected before queueing RTP chunk.")
                                raise asyncio.CancelledError("TTS interrupted by user (before RTP queueing)")
                            
                            rtp_payload = cumulative_pcmu_bytes[:rtp_chunk_size_bytes]
                            self.rtp_queue.put_nowait(bytes(rtp_payload)) # Add to synchronous queue
                            if self.debug: 
                                logging.debug(f"{self.session_id}TTSProcessor: Queued {len(rtp_payload)} bytes of TTS audio for RTP.")
                            cumulative_pcmu_bytes = cumulative_pcmu_bytes[rtp_chunk_size_bytes:]
                            await asyncio.sleep(0.001) # Briefly yield control to allow other tasks to run
                            
                    except asyncio.CancelledError: # Propagate cancellation if it originated here or above
                        raise
                    except Exception as audio_processing_error:
                        logging.error(f"{self.session_id}TTSProcessor: Error processing TTS audio chunk: {audio_processing_error}", exc_info=True)
                
                # Define simple callbacks for PiperClient stream events
                async def on_stream_start(data): logging.info(f"{self.session_id}TTSProcessor: Piper TTS stream starting: {data.get('message')}")
                async def on_stream_end(data): nonlocal tts_success; tts_success = True; logging.info(f"{self.session_id}TTSProcessor: Piper TTS stream complete: {data.get('message')}")
                async def on_stream_error(data): logging.error(f"{self.session_id}TTSProcessor: Error from Piper TTS stream: {data.get('message')}")
                
                # Connect to Piper server
                if await piper_client.connect():
                    # Check for interruption before making the synthesis call
                    if self._interrupt_event.is_set():
                        logging.info(f"{self.session_id}TTSProcessor: TTS generation cancelled before Piper synthesize call due to interrupt.")
                        # No need to return here, finally block will close piper_client
                    else:
                        # Start synthesis and process the audio stream
                        if await piper_client.synthesize(text_to_speak, voice=self.tts_voice):
                            await piper_client.process_stream(
                                on_start=on_stream_start,
                                on_audio=on_audio_chunk_received,
                                on_end=on_stream_end,
                                on_error=on_stream_error
                            )
                
                # After stream processing, handle any remaining bytes in cumulative_pcmu_bytes
                if not self._interrupt_event.is_set() and cumulative_pcmu_bytes: 
                    if self.debug: 
                        logging.debug(f"{self.session_id}TTSProcessor: Processing {len(cumulative_pcmu_bytes)} remaining TTS PCMU bytes.")
                    # Pad the final payload if it's smaller than rtp_chunk_size_bytes
                    # Using silence byte 0xFF for PCMU
                    final_payload = bytes(cumulative_pcmu_bytes).ljust(rtp_chunk_size_bytes, b'\xff') 
                    self.rtp_queue.put_nowait(final_payload)
                    if self.debug: 
                        logging.debug(f"{self.session_id}TTSProcessor: Queued final {len(final_payload)} bytes of TTS audio (padded).")
                
                # Log success or failure based on tts_success flag and interrupt status
                if tts_success and not self._interrupt_event.is_set():
                    logging.info(f"{self.session_id}TTSProcessor: Successfully generated and queued audio for: \"{text_to_speak[:70]}...\"")
                elif self._interrupt_event.is_set():
                    logging.info(f"{self.session_id}TTSProcessor: TTS generation for \"{text_to_speak[:70]}...\" was interrupted.")
                    tts_success = False # Ensure correct state if interrupted
                else: # Not interrupted, but tts_success is False (e.g., Piper connection or synthesis error)
                    logging.warning(f"{self.session_id}TTSProcessor: TTS generation did not complete successfully for: \"{text_to_speak[:70]}...\"")
            
            except asyncio.CancelledError: # Catch cancellation of the generate_and_queue_tts_audio task itself
                logging.info(f"{self.session_id}TTSProcessor: TTS generation task was cancelled (likely by SmartSpeech barge-in).")
                tts_success = False
                self._interrupt_event.set() # Ensure event is set if task is cancelled externally
            except Exception as e: # Catch any other unexpected errors during TTS processing
                logging.error(f"{self.session_id}TTSProcessor: Unexpected error during TTS processing: {e}", exc_info=True)
                tts_success = False # Ensure correct state on error
            finally:
                # Always ensure Piper client is closed if it was initialized and connected
                if piper_client and piper_client.is_connected:
                    await piper_client.close()
                if self._interrupt_event.is_set():
                     logging.info(f"{self.session_id}TTSProcessor: TTS processing finished. Interruption signal was active.")

class SmartSpeech(AIEngine):
    """
    Orchestrates full-duplex speech interaction using Vosk for STT and Piper for TTS.

    This class, derived from `AIEngine`, manages the entire lifecycle of a speech
    session. It initializes and coordinates helper classes for audio input processing
    (`AudioProcessor`), voice activity detection (`VADProcessor`), STT transcript
    handling (`TranscriptHandler`), and TTS audio generation/playback (`TTSProcessor`).

    Key functionalities include:
    - Starting and stopping the STT engine (Vosk client connection).
    - Processing incoming audio packets: PCMU decoding, resampling, VAD.
    - Sending audio to Vosk based on VAD decisions.
    - Receiving and handling partial and final transcripts from Vosk.
    - Managing TTS generation in response to final transcripts (simulated LLM interaction).
    - Implementing barge-in: interrupting TTS playback when user speech is detected.
    - Handling session closure and resource cleanup.
    """
    
    def __init__(self, call: Any, cfg: Config): # Type for 'call' can be more specific if known
        """
        Initializes the SmartSpeech engine for a given call.

        Args:
            call: The call object, expected to have attributes like `b2b_key` (optional),
                  `rtp` (the output RTP queue for TTS audio), `sdp` (for codec negotiation),
                  and `client_addr`/`client_port` for logging.
            cfg: The application configuration object.
        """
        self.cfg: Config = Config.get("SmartSpeech", cfg) # Get Vosk-specific configuration
        
        # Session identification for logging
        self.b2b_key: Optional[str] = call.b2b_key if hasattr(call, 'b2b_key') else None
        self.session_id: str = f"[Session:{self.b2b_key}] " if self.b2b_key else "[Session:Unknown] "
        
        self.queue: Queue = call.rtp # RTP queue for outgoing TTS audio (PCMU packets)
        
        self._load_config()      # Load specific parameters from config
        self._init_components(call) # Initialize helper components
        
        self.receive_task: Optional[asyncio.Task] = None # Task for receiving Vosk transcripts
        self.tts_task: Optional[asyncio.Task] = None     # Task for TTS generation
        self.timeout_monitor_task: Optional[asyncio.Task] = None  # Task for monitoring VAD timeouts
        self._is_closing: bool = False                   # Flag to indicate session closure is in progress
        self.is_tts_active: bool = False                 # <<< ADDED: Flag to indicate TTS is actively playing
        
        # Barge-in timing control
        self.barge_in_speech_start_time: float = 0.0     # When continuous speech started during TTS
        self.barge_in_pending: bool = False              # Whether barge-in is being considered
        
        self._setup_logging() # Configure logging level based on settings
        
        logging.info(f"{self.session_id}SmartSpeech engine initialized. VAD Bypass: {self.bypass_vad}, Barge-in threshold: {self.barge_in_threshold_seconds}s")

    def _load_config(self) -> None:
        """Loads STT, VAD, and TTS configurations from the application config."""
        # Vosk STT Server settings
        self.vosk_server_url: str = self.cfg.get("url", "url", "ws://localhost:2700")
        self.websocket_timeout: float = self.cfg.get("websocket_timeout", "websocket_timeout", 5.0)
        self.target_sample_rate: int = int(self.cfg.get("sample_rate", "sample_rate", 16000)) # For STT
        self.channels: int = self.cfg.get("channels", "channels", 1) # Audio channels for STT
        self.send_eof: bool = self.cfg.get("send_eof", "send_eof", True) # Send EOF to Vosk
        self.debug: bool = self.cfg.get("debug", "debug", False) # General debug flag for this session
        
        # VAD settings
        self.bypass_vad: bool = self.cfg.get("bypass_vad", "bypass_vad", False)
        self.vad_threshold: float = self.cfg.get("vad_threshold", "vad_threshold", 0.25)
        self.vad_min_speech_ms: int = self.cfg.get("vad_min_speech_ms", "vad_min_speech_ms", 150)
        self.vad_min_silence_ms: int = self.cfg.get("vad_min_silence_ms", "vad_min_silence_ms", 450)
        self.vad_buffer_chunk_ms: int = self.cfg.get("vad_buffer_chunk_ms", "vad_buffer_chunk_ms", 600)
        # self.vad_buffer_max_seconds: float = self.cfg.get("vad_buffer_max_seconds", "vad_buffer_max_seconds", 2.0) # Currently unused
        self.speech_detection_threshold: int = self.cfg.get("speech_detection_threshold", "speech_detection_threshold", 1)
        self.silence_detection_threshold: int = self.cfg.get("silence_detection_threshold", "silence_detection_threshold", 1)
        
        # New timeout settings for robust transcript handling
        self.speech_timeout_seconds: float = self.cfg.get("speech_timeout_seconds", "speech_timeout_seconds", 10.0)
        self.silence_timeout_seconds: float = self.cfg.get("silence_timeout_seconds", "silence_timeout_seconds", 3.0)
        self.stale_partial_timeout_seconds: float = self.cfg.get("stale_partial_timeout_seconds", "stale_partial_timeout_seconds", 2.5)
            
        # Barge-in control settings
        self.barge_in_threshold_seconds: float = self.cfg.get("barge_in_threshold_seconds", "barge_in_threshold_seconds", 1.5)
            
        # Piper TTS Server settings
        self.tts_server_host_cfg: str = self.cfg.get("host", "TTS_HOST", "localhost")
        self.tts_server_port_cfg: int = int(self.cfg.get("port", "TTS_PORT", 8000))
        self.tts_voice_cfg: str = self.cfg.get("voice", "TTS_VOICE", "tr_TR-fahrettin-medium")
        self.tts_target_output_rate_cfg: int = 8000  # TTS output target rate (e.g., for PCMU)
        
        logging.info(f"{self.session_id}Vosk STT URL: {self.vosk_server_url}, Target STT Rate: {self.target_sample_rate}Hz")
        logging.info(
            f"{self.session_id}TTS Config: Host={self.tts_server_host_cfg}:{self.tts_server_port_cfg}, "
            f"Voice={self.tts_voice_cfg}, Target Output Rate={self.tts_target_output_rate_cfg}Hz"
        )
        logging.info(
            f"{self.session_id}VAD Config: Bypass={self.bypass_vad}, Threshold={self.vad_threshold}, "
            f"MinSpeechMs={self.vad_min_speech_ms}, MinSilenceMs={self.vad_min_silence_ms}, "
            f"BufferChunkMs={self.vad_buffer_chunk_ms}, SpeechDetectThresh={self.speech_detection_threshold}, "
            f"SilenceDetectThresh={self.silence_detection_threshold}"
        )
        logging.info(
            f"{self.session_id}Timeout Config: SpeechTimeout={self.speech_timeout_seconds}s, "
            f"SilenceTimeout={self.silence_timeout_seconds}s, StalePartialTimeout={self.stale_partial_timeout_seconds}s"
        )
        logging.info(
            f"{self.session_id}Barge-in Config: Threshold={self.barge_in_threshold_seconds}s"
        )

    def _init_components(self, call: Any) -> None:
        """Initializes all processing components (Audio, VAD, Transcript, TTS, Vosk client)."""
        self.call: Any = call # Store call object
        self.client_addr: Tuple[str, int] = call.client_addr
        self.client_port: int = call.client_port # For logging purposes
        self.codec: PCMU = self.choose_codec(call.sdp) # Determine audio codec from SDP
        
        # Audio Processor for input audio (PCMU -> PCM for STT)
        self.audio_processor: AudioProcessor = AudioProcessor(
            target_sample_rate=self.target_sample_rate,
            debug=self.debug,
            session_id=self.session_id
        )
        
        # VAD Detector instance (e.g., Silero VAD)
        vad_detector_instance = VADDetector(
            sample_rate=self.target_sample_rate, # VAD model operates on resampled audio
            threshold=self.vad_threshold,
            min_speech_duration_ms=self.vad_min_speech_ms,
            min_silence_duration_ms=self.vad_min_silence_ms
        )
        
        # VAD Processor to manage VAD state and buffering
        self.vad_processor: VADProcessor = VADProcessor(
            vad_detector=vad_detector_instance,
            target_sample_rate=self.target_sample_rate,
            vad_buffer_chunk_ms=self.vad_buffer_chunk_ms,
            speech_detection_threshold=self.speech_detection_threshold,
            silence_detection_threshold=self.silence_detection_threshold,
            debug=self.debug,
            session_id=self.session_id
        )
        
        # Configure timeout values for VAD processor
        self.vad_processor.speech_timeout_seconds = self.speech_timeout_seconds
        self.vad_processor.silence_timeout_seconds = self.silence_timeout_seconds
        
        # If VAD is bypassed, VADProcessor is always in "speech active" mode
        if self.bypass_vad:
            self.vad_processor.speech_active = True
            logging.info(f"{self.session_id}VAD is bypassed. All audio will be sent to STT.")
        
        # Transcript Handler to manage STT results
        self.transcript_handler: TranscriptHandler = TranscriptHandler(session_id=self.session_id)
        
        # Vosk Client for STT communication
        self.vosk_client: VoskClient = VoskClient(self.vosk_server_url, timeout=self.websocket_timeout)
        
        # TTS Processor for generating speech output
        self.tts_processor: TTSProcessor = TTSProcessor(
            rtp_queue=self.queue, # Output queue for TTS audio packets
            tts_server_host=self.tts_server_host_cfg,
            tts_server_port=self.tts_server_port_cfg,
            tts_voice=self.tts_voice_cfg,
            tts_target_output_rate=self.tts_target_output_rate_cfg,
            session_id=self.session_id,
            debug=self.debug
        )
        
        # Set the callback in TranscriptHandler for when a final transcript is ready
        self.transcript_handler.on_final_transcript = self._handle_final_transcript
        logging.info(f"{self.session_id}All SmartSpeech components initialized.")

    def _setup_logging(self) -> None:
        """Configures the logging level for the session based on the debug flag."""
        # Note: BasicConfig should ideally be called once at application startup.
        # If called multiple times, it might not behave as expected unless `force=True` (Python 3.8+)
        # is used, or if handlers are manually managed.
        # For simplicity here, we assume it's okay or handled by a higher-level logger setup.
        # logging.basicConfig(level=logging.INFO) # Avoid re-calling basicConfig if already set
        if self.debug:
            logging.getLogger().setLevel(logging.DEBUG) # Set global log level to DEBUG if self.debug is true
            logging.debug(f"{self.session_id}Debug logging enabled for SmartSpeech session.")
        else:
            # If not debug, ensure global level isn't stuck at DEBUG from a previous session
            # This depends on how logging is managed globally. A dedicated logger per session might be better.
            # For now, this assumes a shared root logger.
            pass # logging.getLogger().setLevel(logging.INFO) # Or set to a configured default

    def choose_codec(self, sdp: str) -> PCMU: # Assuming PCMU is the only supported/chosen one
        """
        Chooses a supported audio codec from the SDP offer.

        Currently, it iterates through codecs in the SDP and selects the first
        instance of PCMU (payload type 0).

        Args:
            sdp: The Session Description Protocol (SDP) string from the call.

        Returns:
            A PCMU codec object if found.

        Raises:
            UnsupportedCodec: If PCMU (payload type 0) is not found in the SDP.
        """
        codecs = get_codecs(sdp)
        for c in codecs:
            if c.payloadType == 0: # PCMU typically has payload type 0
                logging.info(f"{self.session_id}PCMU codec selected based on SDP.")
                return PCMU(c) # Return an instance of PCMU codec wrapper
        raise UnsupportedCodec(f"{self.session_id}No supported codec (PCMU/0) found in SDP.")

    async def start(self) -> bool:
        """
        Starts the SmartSpeech engine for the session.

        This involves connecting to the Vosk STT server, sending initial configuration,
        and starting the task to receive transcripts.

        Returns:
            True if successfully started, False otherwise (e.g., connection to Vosk failed).
        """
        logging.info(f"{self.session_id}SmartSpeech engine starting...")
        self._is_closing = False # Reset closing flag on start
        
        try:
            # Connect to Vosk server
            if not await self.vosk_client.connect():
                logging.error(f"{self.session_id}Failed to connect to Vosk server. Cannot start SmartSpeech engine.")
                return False
            
            # Send initial configuration to Vosk (e.g., sample rate)
            vosk_config = { "config": { "sample_rate": self.target_sample_rate, "num_channels": self.channels } }
            if not await self.vosk_client.send(vosk_config):
                logging.error(f"{self.session_id}Failed to send initial config to Vosk. Disconnecting.")
                await self.vosk_client.disconnect()
                return False
                
            # Start the background task to receive and process transcripts from Vosk
            self.receive_task = asyncio.create_task(self.receive_transcripts(), name=f"VoskReceive-{self.session_id}")
            
            # Start the timeout monitoring task to handle speech timeouts
            if not self.bypass_vad:
                self.timeout_monitor_task = asyncio.create_task(self._monitor_vad_timeouts(), name=f"VADTimeout-{self.session_id}")
            
            logging.info(f"{self.session_id}SmartSpeech engine started successfully. Listening for transcripts.")
            return True
            
        except Exception as e:
            logging.error(f"{self.session_id}Error during SmartSpeech engine start: {e}", exc_info=True)
            if self.vosk_client and self.vosk_client.is_connected:
                await self.vosk_client.disconnect() # Attempt cleanup
            return False

    async def _monitor_vad_timeouts(self) -> None:
        """
        Monitors VAD timeouts and generates final transcripts when needed.
        
        This task runs in the background and checks for speech/silence timeouts.
        When a timeout is detected, it forces a final transcript generation using
        the current partial transcript if available.
        """
        try:
            while not self._is_closing:
                await asyncio.sleep(0.5)  # Check every 500ms
                
                if not self.vad_processor or not self.transcript_handler:
                    continue
                
                # Check for speech timeout (speech going too long)
                if self.vad_processor.has_speech_timeout():
                    logging.warning(f"{self.session_id}Speech timeout detected. Forcing final transcript generation.")
                    await self._force_final_transcript("Speech timeout")
                    continue
                
                # Check for silence timeout (silence after speech going too long)
                if self.vad_processor.has_silence_timeout():
                    logging.info(f"{self.session_id}Silence timeout detected. Forcing final transcript generation.")
                    await self._force_final_transcript("Silence timeout")
                    continue
                
                # Check for stale partial transcripts (partial unchanged for too long)
                if self.transcript_handler.has_stale_partial(max_unchanged_seconds=self.stale_partial_timeout_seconds):
                    logging.info(f"{self.session_id}Stale partial transcript detected. Promoting to final.")
                    await self._force_final_transcript("Stale partial")
                    continue
                    
        except asyncio.CancelledError:
            logging.info(f"{self.session_id}VAD timeout monitor task cancelled.")
        except Exception as e:
            logging.error(f"{self.session_id}Error in VAD timeout monitor: {e}", exc_info=True)

    async def _force_final_transcript(self, reason: str) -> None:
        """
        Forces generation of a final transcript using the current partial transcript.
        
        This is called when timeouts are detected and Vosk hasn't provided a final transcript.
        
        Args:
            reason: The reason for forcing the transcript (for logging).
        """
        try:
            if not self.transcript_handler.last_partial_transcript:
                logging.info(f"{self.session_id}No partial transcript available for forced final ({reason}).")
                # Reset VAD state even if no partial available
                if not self.bypass_vad:
                    self.vad_processor.reset_vad_state(preserve_buffer=False)
                return
            
            partial_text = self.transcript_handler.last_partial_transcript.strip()
            if not partial_text:
                logging.info(f"{self.session_id}Partial transcript is empty for forced final ({reason}).")
                # Reset VAD state and clear partial
                if not self.bypass_vad:
                    self.vad_processor.reset_vad_state(preserve_buffer=False)
                self.transcript_handler.clear_transcripts()
                return
            
            # Check minimum length threshold
            if len(partial_text) < 2:
                logging.info(f"{self.session_id}Partial transcript too short for forced final ({reason}): \"{partial_text}\"")
                if not self.bypass_vad:
                    self.vad_processor.reset_vad_state(preserve_buffer=False)
                self.transcript_handler.clear_transcripts()
                return
            
            logging.info(f"{self.session_id}Forcing final transcript from partial due to {reason}: \"{partial_text}\"")
            
            # Set the partial as final and trigger the callback
            self.transcript_handler.last_final_transcript = partial_text
            
            # Reset VAD state to prepare for new speech
            if not self.bypass_vad:
                self.vad_processor.reset_vad_state(preserve_buffer=False)
            
            # Clear transcript timing to prevent double triggering
            self.transcript_handler.clear_transcripts()
            
            # Trigger the final transcript callback
            if self.transcript_handler.on_final_transcript:
                asyncio.create_task(self.transcript_handler.on_final_transcript(partial_text))
            
        except Exception as e:
            logging.error(f"{self.session_id}Error forcing final transcript: {e}", exc_info=True)

    async def stop(self) -> bool:
        """
        Stops the SmartSpeech engine components related to STT.

        This method sends an EOF signal to the Vosk server (if enabled and connected),
        disconnects from the Vosk server, and cancels the transcript receiving task.
        It's primarily for STT shutdown, while `close` handles full session cleanup.

        Returns:
            True if STT components were stopped successfully, False otherwise.
        """
        logging.info(f"{self.session_id}Stopping SmartSpeech STT components.")
        
        try:
            # Send EOF to Vosk server to finalize transcription if connected and enabled
            await self._send_eof_if_enabled()
            
            # Disconnect from Vosk server if connected
            if self.vosk_client.is_connected:
                try:
                    await self.vosk_client.disconnect()
                    logging.info(f"{self.session_id}Disconnected from Vosk server during stop sequence.")
                except Exception as e_disconnect:
                    logging.error(f"{self.session_id}Error disconnecting Vosk client during stop: {e_disconnect}", exc_info=True)
            
            # Cancel the transcript receiving task
            await self._cancel_receive_task() 
            
            logging.info(f"{self.session_id}SmartSpeech STT components stopped successfully.")
            return True
        except Exception as e:
            logging.error(f"{self.session_id}Error stopping SmartSpeech STT components: {e}", exc_info=True)
            return False

    async def _manage_task(self, task: Optional[asyncio.Task], timeout: float = 2.0) -> bool:
        """
        Manages an asyncio task with timeout, cancellation, and logging.

        Args:
            task: The asyncio.Task to manage.
            timeout: How long to wait for the task to complete before cancelling.

        Returns:
            True if the task completed (or was already done), False if it timed out or an error occurred.
        """
        if not task or task.done():
            return True # Nothing to manage or already completed

        task_name = task.get_name() if hasattr(task, 'get_name') else "Unnamed Task"
        try:
            await asyncio.wait_for(task, timeout=timeout)
            return True # Task completed within timeout
        except asyncio.TimeoutError:
            logging.warning(f"{self.session_id}Task '{task_name}' timed out after {timeout}s. Cancelling.")
            task.cancel()
            try:
                await task # Await cancellation
            except asyncio.CancelledError:
                logging.info(f"{self.session_id}Task '{task_name}' was successfully cancelled after timeout.")
            except Exception as e_cancel:
                logging.error(f"{self.session_id}Error awaiting cancellation of task '{task_name}': {e_cancel}", exc_info=True)
            return False
        except asyncio.CancelledError: # If the task was cancelled by something else before wait_for
            logging.info(f"{self.session_id}Task '{task_name}' was already cancelled externally.")
            # Ensure it's fully awaited if it was cancelled but not yet awaited by the canceller
            if not task.done(): # Should be done if CancelledError was raised from await task
                 try: await task
                 except asyncio.CancelledError: pass # Expected
            return True # Treat as "managed"
        except Exception as e_wait:
            logging.error(f"{self.session_id}Unexpected error managing task '{task_name}': {e_wait}", exc_info=True)
            if not task.done(): # If an unexpected error didn't terminate it, try to cancel
                task.cancel()
                try: await task
                except asyncio.CancelledError: pass 
                except Exception as e_final_cancel:
                    logging.error(f"{self.session_id}Error during final cancellation attempt of task '{task_name}': {e_final_cancel}", exc_info=True)
            return False

    async def _cancel_receive_task(self) -> None:
        """Cancels and awaits the Vosk transcript receiving task (`self.receive_task`)."""
        if self.receive_task:
            if self.debug:
                logging.debug(f"{self.session_id}Cancelling Vosk transcript receive_task.")
            if not await self._manage_task(self.receive_task, timeout=1.0): 
                logging.warning(f"{self.session_id}Vosk receive_task did not complete cleanly after cancellation request.")
            self.receive_task = None # Clear the task reference
        elif self.debug:
            logging.debug(f"{self.session_id}Vosk receive_task is None, no cancellation needed.")

    async def _send_eof_if_enabled(self) -> None:
        """Sends an EOF signal to the Vosk server if `self.send_eof` is True and connected."""
        if self.send_eof and self.vosk_client and self.vosk_client.is_connected:
            try:
                logging.debug(f"{self.session_id}Sending EOF signal to Vosk server.")
                await self.vosk_client.send_eof() # VoskClient's send_eof already handles the JSON part
            except Exception as e: # Catch exceptions from VoskClient.send_eof or underlying websocket
                logging.error(f"{self.session_id}Error sending EOF to Vosk: {e}", exc_info=True)

    async def send(self, audio: bytes) -> None:
        """
        Processes and sends an incoming audio chunk for STT.

        This method is called by the RTP media server (or equivalent) with raw
        audio bytes (expected PCMU). It performs:
        1. Audio processing (PCMU decode, resample, normalize) via `AudioProcessor`.
        2. VAD processing (if not bypassed) via `VADProcessor`.
        3. If VAD indicates speech, the audio is sent to the Vosk server via `VoskClient`.
           This step also handles TTS barge-in if user speech is detected during TTS playback.

        Args:
            audio: Raw audio bytes (e.g., from an RTP packet, typically PCMU).
        """
        if self._is_closing: 
            logging.warning(f"{self.session_id}Attempted to send audio while session is closing. Skipping.")
            return

        if not self.vosk_client or not self.vosk_client.is_connected:
            logging.warning(f"{self.session_id}Vosk client not connected. Cannot send audio.")
            return
            
        try:
            if not isinstance(audio, bytes):
                logging.warning(f"{self.session_id}Unexpected audio type received: {type(audio)}, expected bytes. Skipping.")
                return

            # Process the raw audio (e.g., decode PCMU, resample)
            resampled_tensor, processed_audio_bytes_for_stt = self.audio_processor.process_bytes_audio(audio)
            
            if processed_audio_bytes_for_stt is None: # Processing might fail or return no data
                return # Error already logged by AudioProcessor
                
            # Pass processed audio to VAD (or directly to STT if VAD is bypassed)
            await self._handle_processed_audio(resampled_tensor, processed_audio_bytes_for_stt)
                
        except Exception as e:
            logging.error(f"{self.session_id}Unhandled error in SmartSpeech.send method: {e}", exc_info=True)

    async def _handle_processed_audio(self, 
                                      tensor: Optional[torch.Tensor], 
                                      audio_bytes_for_stt: bytes) -> None:
        """
        Handles audio after initial processing (e.g., resampling).

        If VAD is bypassed, sends audio directly to STT. Otherwise, adds audio
        to `VADProcessor`. If VAD signals speech start, interrupts any ongoing TTS
        (barge-in) and then sends VAD-processed audio to STT.

        Args:
            tensor: The audio tensor corresponding to `audio_bytes_for_stt`. Used by VADProcessor
                    if VAD is not bypassed, for deriving number of samples. Can be None if
                    AudioProcessor failed to produce a tensor but still provided bytes.
            audio_bytes_for_stt: The 16-bit PCM audio bytes ready for STT or VAD.
        """
        if self.debug: 
            logging.debug(f"{self.session_id}Handling processed audio chunk: {len(audio_bytes_for_stt)} bytes for STT/VAD.")
        
        if self.bypass_vad:
            # VAD is bypassed, send audio directly to Vosk STT server
            if self.debug: 
                hex_preview = ' '.join([f'{b:02x}' for b in audio_bytes_for_stt[:20]])
                logging.debug(f"{self.session_id}Sending audio directly to STT (VAD bypassed): len={len(audio_bytes_for_stt)}, preview_hex={hex_preview}")
            
            if not self.is_tts_active: # <<< MODIFIED: Check TTS status
                if self.vosk_client and self.vosk_client.is_connected:
                    await self.vosk_client.send_audio(audio_bytes_for_stt)
                else:
                    logging.warning(f"{self.session_id}Vosk client not available for sending audio (VAD bypassed).")
            elif self.debug:
                logging.debug(f"{self.session_id}TTS is active, discarding direct audio to prevent echo transcription (VAD bypassed).")
        else: # VAD is active
            num_samples = tensor.shape[0] if tensor is not None else len(audio_bytes_for_stt) // 2 
            
            was_vad_buffer_processed, is_speech_in_vad_chunk, vad_output_buffer_bytes = \
                await self.vad_processor.add_audio(audio_bytes_for_stt, num_samples)
                
            current_time = time.time()

            # 1. Start or continue barge-in timing if user speaks during active TTS
            if self.is_tts_active and is_speech_in_vad_chunk and not self.barge_in_pending:
                self.barge_in_pending = True
                self.barge_in_speech_start_time = current_time
                logging.info(f"{self.session_id}User speech detected during TTS. Starting barge-in timer ({self.barge_in_threshold_seconds}s threshold). Current TTS active: {self.is_tts_active}")

            # 2. Process barge-in if pending and threshold met
            if self.barge_in_pending and is_speech_in_vad_chunk: # User is currently speaking and barge-in was initiated
                speech_duration = current_time - self.barge_in_speech_start_time
                if speech_duration >= self.barge_in_threshold_seconds:
                    logging.info(f"{self.session_id}Sustained user speech ({speech_duration:.2f}s). Triggering barge-in. TTS active: {self.is_tts_active}")
                    
                    if self.is_tts_active and self.tts_task and not self.tts_task.done():
                        self.tts_processor.interrupt() 
                        self.tts_task.cancel()
                        try:
                            await self.tts_task 
                        except asyncio.CancelledError:
                            logging.info(f"{self.session_id}TTS task successfully cancelled due to sustained barge-in.")
                        except Exception as e_cancel:
                            logging.error(f"{self.session_id}Error awaiting cancelled TTS task during barge-in: {e_cancel}", exc_info=True)
                        self.tts_task = None
                    # Ensure TTS active flag is false AFTER attempting to stop TTS, regardless of its prior state when barge-in threshold met.
                    self.is_tts_active = False 
                    
                    self.transcript_handler.clear_transcripts()
                    logging.info(f"{self.session_id}Partial transcripts cleared due to barge-in.")

                    if not self.bypass_vad:
                        self.vad_processor.reset_vad_state(preserve_buffer=False)
                        logging.info(f"{self.session_id}VAD state reset due to barge-in. Listening for new user utterance.")
                    
                    self.barge_in_pending = False # Barge-in completed
                    self.barge_in_speech_start_time = 0.0
                    vad_output_buffer_bytes = None # Consumed by barge-in, don't send this chunk to STT
                else:
                    logging.info(f"{self.session_id}User speech continues during TTS, duration {speech_duration:.2f}s < threshold {self.barge_in_threshold_seconds}s. Barge-in pending. TTS active: {self.is_tts_active}")
            
            # 3. Reset barge-in if user stops speaking *before* threshold is met
            elif self.barge_in_pending and not is_speech_in_vad_chunk:
                speech_duration_at_stop = current_time - self.barge_in_speech_start_time
                logging.info(f"{self.session_id}User speech stopped during barge-in pending (duration: {speech_duration_at_stop:.2f}s). Resetting barge-in state as threshold not met. TTS active: {self.is_tts_active}")
                self.barge_in_pending = False
                self.barge_in_speech_start_time = 0.0
                # If TTS had already finished by itself before this point, is_tts_active would be false.
                # If TTS is still (or was just) active, the VAD audio here (silence) shouldn't be sent to STT if is_tts_active is true.

            # 4. Send audio to STT if applicable (VAD output, no active TTS, not consumed by barge-in)
            if was_vad_buffer_processed and vad_output_buffer_bytes: # vad_output_buffer_bytes might be None if barge-in consumed it
                if not self.is_tts_active: 
                    if self.debug: 
                        hex_preview_vad = ' '.join([f'{b:02x}' for b in vad_output_buffer_bytes[:20]])
                        logging.debug(
                            f"{self.session_id}Sending VAD output buffer to STT: "
                            f"len={len(vad_output_buffer_bytes)}, preview_hex={hex_preview_vad}"
                        )
                    if self.vosk_client and self.vosk_client.is_connected:
                        await self.vosk_client.send_audio(vad_output_buffer_bytes)
                    else:
                        logging.warning(f"{self.session_id}Vosk client not available for sending VAD audio.")
                elif self.debug and vad_output_buffer_bytes: # TTS is active, but VAD still produced something
                    logging.debug(f"{self.session_id}TTS is active, discarding VAD output buffer to prevent echo transcription.")
            
            # Handle case where speech stops during barge-in pending (reset barge-in state)
            # This needs to be after the main barge-in check.
            if was_vad_buffer_processed and not is_speech_in_vad_chunk and self.barge_in_pending:
                speech_duration_at_stop = time.time() - self.barge_in_speech_start_time
                logging.info(f"{self.session_id}Speech ended during barge-in pending (duration: {speech_duration_at_stop:.2f}s). Resetting barge-in state as threshold not met.")
                self.barge_in_pending = False

            # Yield control briefly to allow other tasks to run
            if not self._is_closing:
                await asyncio.sleep(0)  # Allow other coroutines to run
            # Additional cases for logging or specific actions based on VAD output:
            # elif was_vad_buffer_processed and not is_speech_in_vad_chunk:
            #     if self.debug: logging.debug(f"{self.session_id}VAD processed a silent chunk.")
            # else: # was_vad_buffer_processed is False
            #     if self.debug: logging.debug(f"{self.session_id}VAD buffer is still accumulating audio.")


    async def receive_transcripts(self) -> None:
        """
        Continuously receives and processes STT results from the Vosk server.

        This method runs as a background task (`self.receive_task`). It listens for
        messages from `VoskClient.receive_result()`, handles potential WebSocket
        connection issues (including reconnection attempts), and passes valid
        transcript messages to `TranscriptHandler.handle_message()`.
        The loop terminates if the session is closing or if reconnection fails repeatedly.
        """
        try:
            reconnect_attempts = 0
            max_reconnect_attempts = 5  # Max attempts before giving up
            
            while not self._is_closing: # Loop until session closure is signaled
                try:
                    if not self.vosk_client or not self.vosk_client.is_connected:
                        # Attempt to reconnect if not connected and not closing
                        logging.warning(f"{self.session_id}Vosk client disconnected. Attempting reconnect...")
                        if await self._try_reconnect(reconnect_attempts, max_reconnect_attempts):
                            reconnect_attempts = 0 # Reset attempts on successful reconnect
                        else:
                            reconnect_attempts +=1
                            if reconnect_attempts >= max_reconnect_attempts:
                                logging.error(f"{self.session_id}Max Vosk reconnection attempts reached. Stopping transcript reception.")
                                break # Exit loop if max attempts failed
                            continue # Try to reconnect in the next iteration after backoff
                    
                    # Receive result from Vosk client (with timeout)
                    message = await self.vosk_client.receive_result()
                    
                    if self.debug and message is not None: # Log if a message (not timeout None) was received
                        logging.debug(f"{self.session_id}Raw Vosk response received: \"{message[:70]}...\"")
                    
                    if message is None:
                        # Timeout or no new message from Vosk (normal during silence or if connection dropped)
                        # If connection dropped, is_connected will be false, handled by next loop iteration's check
                        if self.vosk_client and not self.vosk_client.is_connected and not self._is_closing:
                            logging.warning(f"{self.session_id}Vosk connection found closed after receive_result timeout.")
                            # Reconnection will be attempted in the next iteration by the check at the loop start
                        continue # Continue to next receive attempt or reconnection
                    
                    reconnect_attempts = 0 # Reset on successful message receipt
                    
                    # Process the received message using TranscriptHandler
                    if not await self.transcript_handler.handle_message(message):
                        logging.warning(f"{self.session_id}Transcript handler failed to process message: {message[:100]}...")
                    
                except websockets.exceptions.ConnectionClosed as conn_err:
                    # This exception might be raised by receive_result if not handled internally by VoskClient
                    # or if it occurs between is_connected check and recv()
                    logging.error(f"{self.session_id}WebSocket connection closed unexpectedly in receive_transcripts: {conn_err}", exc_info=True)
                    if self.vosk_client: self.vosk_client.is_connected = False # Ensure state is updated
                    if self._is_closing or (hasattr(self.call, 'terminated') and self.call.terminated):
                        logging.info(f"{self.session_id}WebSocket connection closed during session shutdown (Code: {conn_err.code}).")
                        break # Exit loop if closing
                    # Reconnection will be attempted by the check at the start of the loop
                except asyncio.CancelledError:
                    logging.info(f"{self.session_id}Transcript receive task was cancelled.")
                    raise # Propagate cancellation
                except Exception as e: # Catch any other unexpected errors in the loop
                    logging.error(f"{self.session_id}Unexpected error in receive_transcripts loop: {e}", exc_info=True)
                    # Brief pause before retrying to prevent rapid error looping
                    await asyncio.sleep(1) 
            
            logging.info(f"{self.session_id}Exiting Vosk transcript receive_transcripts loop (closing: {self._is_closing}).")
        except asyncio.CancelledError: # Catch cancellation of the receive_transcripts task itself
             logging.info(f"{self.session_id}Vosk transcript receive_transcripts task definitively cancelled.")
        except Exception as e_outer: # Catch any unexpected error that might break the outer loop
            logging.critical(f"{self.session_id}Fatal error in receive_transcripts outer loop: {e_outer}", exc_info=True)


    async def _try_reconnect(self, current_attempts: int, max_attempts: int) -> bool:
        """
        Attempts to reconnect to the Vosk server with exponential backoff.

        Args:
            current_attempts: The number of reconnection attempts made so far.
            max_attempts: The maximum number of reconnection attempts before giving up.

        Returns:
            True if reconnection was successful, False otherwise.
        """
        if current_attempts >= max_attempts:
            logging.error(f"{self.session_id}Maximum Vosk reconnection attempts ({max_attempts}) reached. Giving up.")
            return False
            
        attempt_number = current_attempts + 1
        # Exponential backoff: 2s, 4s, 8s, capped at 10s
        backoff_time = min(2 ** attempt_number, 10)  
            
        logging.info(
            f"{self.session_id}Attempting to reconnect to Vosk server "
            f"(attempt {attempt_number}/{max_attempts}). Waiting {backoff_time}s."
        )
        await asyncio.sleep(backoff_time) 
        
        try:
            # Attempt to connect and re-send initial config
            if not await self.vosk_client.connect():
                logging.warning(f"{self.session_id}Failed to reconnect to Vosk server (attempt {attempt_number}).")
                return False

            logging.info(f"{self.session_id}Successfully reconnected to Vosk server (attempt {attempt_number}).")
            vosk_config = { "config": { "sample_rate": self.target_sample_rate, "num_channels": self.channels } }
            if not await self.vosk_client.send(vosk_config):
                logging.error(f"{self.session_id}Failed to send initial config to Vosk after reconnection. Disconnecting.")
                await self.vosk_client.disconnect()
                return False
            
            logging.info(f"{self.session_id}Resent configuration to Vosk server after reconnection.")
            return True # Reconnection successful
            
        except Exception as reconnect_error:
            logging.error(f"{self.session_id}Error during Vosk reconnection attempt {attempt_number}: {reconnect_error}", exc_info=True)
            return False # Reconnection failed

    async def close(self) -> None:
        """
        Closes the SmartSpeech session gracefully.

        This involves:
        1. Cancelling any active TTS task and clearing its queue.
        2. Processing any final audio in the VAD buffer.
        3. Finalizing the transcript (e.g., using partial if no final).
        4. Sending EOF to Vosk and disconnecting the client.
        5. Cancelling the Vosk transcript receiving task and timeout monitor.
        """
        if self._is_closing:
            logging.info(f"{self.session_id}Close operation already in progress. Skipping.")
            return
        logging.info(f"{self.session_id}Initiating closure of SmartSpeech session.")
        
        self._is_closing = True # Signal that closure is underway
        
        # 1. Cancel and clean up TTS task
        if hasattr(self, 'tts_task') and self.tts_task and not self.tts_task.done():
            logging.debug(f"{self.session_id}Attempting to cancel active TTS task during close.")
            if hasattr(self, 'tts_processor') and self.tts_processor:
                self.tts_processor.interrupt() # Signal TTSProcessor to stop and drain its queue
            self.tts_task.cancel()
            try:
                await self.tts_task
            except asyncio.CancelledError:
                logging.info(f"{self.session_id}Active TTS task successfully cancelled during close.")
            except Exception as e_tts_cancel:
                logging.error(f"{self.session_id}Error awaiting cancelled TTS task during close: {e_tts_cancel}", exc_info=True)
            self.tts_task = None # Ensure cleared
        
        # 2. Cancel timeout monitor task
        if hasattr(self, 'timeout_monitor_task') and self.timeout_monitor_task and not self.timeout_monitor_task.done():
            logging.debug(f"{self.session_id}Cancelling VAD timeout monitor task during close.")
            self.timeout_monitor_task.cancel()
            try:
                await self.timeout_monitor_task
            except asyncio.CancelledError:
                logging.info(f"{self.session_id}VAD timeout monitor task successfully cancelled during close.")
            except Exception as e_monitor_cancel:
                logging.error(f"{self.session_id}Error awaiting cancelled timeout monitor task during close: {e_monitor_cancel}", exc_info=True)
            self.timeout_monitor_task = None
        
        # 3. Process final VAD buffer (if VAD is not bypassed)
        if not self.bypass_vad:
            try:
                logging.debug(f"{self.session_id}Processing final VAD buffer before closing.")
                await self._process_final_vad_buffer()
            except Exception as e_vad_final:
                logging.error(f"{self.session_id}Error processing final VAD buffer during close: {e_vad_final}", exc_info=True)
        
        # 4. Finalize transcript (use partial if no final, etc.)
        try:
            self._finalize_transcript()
        except Exception as e_finalize:
            logging.error(f"{self.session_id}Error finalizing transcript during close: {e_finalize}", exc_info=True)

        # 5. Send EOF and disconnect Vosk client
        if self.vosk_client and self.vosk_client.is_connected:
            try:
                await self._send_eof_if_enabled() 
                logging.debug(f"{self.session_id}Attempting to disconnect Vosk client.")
                await self.vosk_client.disconnect() # disconnect is an alias for close
                logging.info(f"{self.session_id}Disconnected from Vosk server successfully during close.")
            except Exception as e_vosk_close:
                logging.error(f"{self.session_id}Error disconnecting from Vosk server during close: {e_vosk_close}", exc_info=True)
        
        # 6. Cancel Vosk transcript receiving task
        logging.debug(f"{self.session_id}Ensuring Vosk transcript receive task is cancelled during close.")
        await self._cancel_receive_task() # Handles if task is None or already done
        
        logging.info(f"{self.session_id}SmartSpeech session close procedure completed.")

    def _finalize_transcript(self) -> None:
        """
        Ensures a final transcript is available, using the last partial transcript if no
        explicit final transcript was received. Logs the definitive final transcript.
        """
        try:
            # If no final "text" was received, but there was a "partial", use the partial.
            if not self.transcript_handler.last_final_transcript and self.transcript_handler.last_partial_transcript:
                logging.info(
                    f"{self.session_id}No final transcript at session end, "
                    f"using last partial: \"{self.transcript_handler.last_partial_transcript[:80]}...\""
                )
                self.transcript_handler.last_final_transcript = self.transcript_handler.last_partial_transcript
            
            # Log the definitive final transcript for the session
            if self.transcript_handler.last_final_transcript:
                logging.info(f"{self.session_id}Definitive final transcript for session: \"{self.transcript_handler.last_final_transcript}\"")
            else:
                logging.info(f"{self.session_id}No transcript (final or partial) available at session end.")
        except Exception as e: # Should not happen with string operations, but as a safeguard.
            logging.error(f"{self.session_id}Error during _finalize_transcript: {e}", exc_info=True)


    def terminate_call(self) -> None:
        """ 
        Signals that the call associated with this SmartSpeech session should be terminated.
        This typically involves setting a flag on the call object that external logic checks.
        """
        logging.info(f"{self.session_id}Signaling to terminate call.")
        if hasattr(self.call, 'terminated'):
            self.call.terminated = True
        else:
            logging.warning(f"{self.session_id}Call object does not have a 'terminated' attribute to set.")

    def set_log_level(self, level: int) -> None:
        """
        Sets the logging level for this session and its components.
        
        Note: This currently sets the global logging level if `self.debug` is true.
        For per-session logging without affecting global state, dedicated loggers
        would be required.

        Args:
            level: The logging level (e.g., `logging.DEBUG`, `logging.INFO`).
        """
        # This will affect the root logger if not handled carefully.
        # Consider using a session-specific logger instance if finer control is needed.
        current_level_name = logging.getLevelName(logging.getLogger().getEffectiveLevel())
        new_level_name = logging.getLevelName(level)
        logging.info(f"{self.session_id}Attempting to set logging level to {new_level_name}. Current effective level: {current_level_name}.")
        
        self.debug = (level == logging.DEBUG) # Update internal debug flag
        
        # Propagate debug status to components
        if hasattr(self, 'audio_processor'): self.audio_processor.debug = self.debug
        if hasattr(self, 'vad_processor'): self.vad_processor.debug = self.debug
        if hasattr(self, 'tts_processor'): self.tts_processor.debug = self.debug
        
        # This might change global logging level if not careful.
        # A better approach for per-session verbosity might involve custom logger instances.
        if self.debug: 
            logging.getLogger().setLevel(logging.DEBUG) 
            logging.debug(f"{self.session_id}Switched to DEBUG logging level for current session components and potentially globally.")
        else:
            # Reverting global log level if this session is not debug.
            # This assumes a default INFO unless another session requires DEBUG.
            # This part is tricky with shared global loggers.
            # logging.getLogger().setLevel(logging.INFO) 
            pass # Avoid changing global level back and forth too much without a more robust system.

    async def _process_final_vad_buffer(self) -> None:
        """
        Processes the final VAD buffer before closing the session.

        If there's audio data in the VAD buffer deemed as speech, it's sent to the STT service.
        A short wait period is introduced to allow any resulting transcript from this final
        audio to be processed by the main transcript receiving loop.
        The `_finalize_transcript` method, called later in the `close()` sequence, will then
        use the latest available partial transcript if no final transcript was received.
        """
        try:
            is_speech, buffer_bytes = await self.vad_processor.process_final_buffer()
            
            if buffer_bytes and self.vosk_client and self.vosk_client.is_connected: 
                if is_speech:
                    if self.debug:
                        logging.debug(f"{self.session_id}Sending {len(buffer_bytes)} bytes from final VAD buffer to STT.")
                    await self.vosk_client.send_audio(buffer_bytes)
                    
                    # Calculate a reasonable wait time for network round trip and STT processing.
                    # This allows the receive_transcripts loop to potentially update last_partial_transcript.
                    buffer_duration_seconds = len(buffer_bytes) / (2 * self.target_sample_rate) # Assuming 16-bit mono
                    # Heuristic: half buffer duration + network overhead (e.g., 200ms), capped.
                    wait_time = min(buffer_duration_seconds * 0.5 + 0.2, 1.5) 
                                        
                    if self.debug:
                        logging.debug(f"{self.session_id}Waiting {wait_time:.2f}s for potential transcript from final VAD buffer send.")
                    await asyncio.sleep(wait_time) # Give time for the transcript to arrive
                elif self.debug:
                    logging.debug(f"{self.session_id}Final VAD buffer contained data, but not deemed as speech. Discarding.")
                
            elif buffer_bytes and (not self.vosk_client or not self.vosk_client.is_connected):
                logging.warning(f"{self.session_id}Final VAD buffer had data, but Vosk client is not connected. Cannot process.")
            elif self.debug: # No buffer_bytes
                logging.debug(f"{self.session_id}No data in final VAD buffer to process, or client not connected.")

        except Exception as e:
            logging.error(f"{self.session_id}Error processing final VAD buffer: {e}", exc_info=True)


    def get_final_transcript(self) -> str:
        """
        Returns the last recognized final transcript text for the session.
        
        Delegates to `TranscriptHandler.get_final_transcript()`.
        """
        return self.transcript_handler.get_final_transcript()

    async def _handle_final_transcript(self, final_text: str) -> None:
        """
        Callback triggered when a final transcript is received from `TranscriptHandler`.

        This method orchestrates the response to a final transcript:
        1. Ensures any previous TTS task is cancelled (e.g., if final transcripts arrive rapidly).
        2. (Simulates) Gets a response from an LLM based on `final_text`.
        3. Resets VAD state to prepare for new user speech.
        4. Initiates TTS generation for the LLM response via `TTSProcessor`.
        The TTS generation itself runs as a new asyncio task (`self.tts_task`).

        Args:
            final_text: The final recognized transcript string.
        """
        logging.info(f"{self.session_id}SmartSpeech: Handling final transcript: \"{final_text[:100]}...\"")
        
        # 0. Ensure any previous TTS task is fully handled/cancelled before starting a new one.
        # This can happen if final transcripts are generated very quickly or if a previous
        # barge-in cancellation is still being awaited when a new transcript arrives.
        if self.tts_task and not self.tts_task.done():
            logging.warning(
                f"{self.session_id}A previous TTS task was still active when a new final transcript "
                f"arrived ('{final_text[:50]}...'). Attempting to cancel the old task first."
            )
            self.is_tts_active = False # <<< ADDED: Ensure flag is cleared if old task is cancelled here
            self.tts_processor.interrupt()
            self.tts_task.cancel()
            try:
                await self.tts_task
            except asyncio.CancelledError:
                logging.info(f"{self.session_id}Successfully cancelled the lingering TTS task before starting new one.")
            except Exception as e: 
                logging.error(f"{self.session_id}Error awaiting lingering TTS task: {e}", exc_info=True)
        self.tts_task = None
        self.is_tts_active = False # <<< ADDED: Ensure flag is false before potentially starting new TTS

        # 1. Get LLM Response (Simulated - Placeholder for actual LLM interaction)
        # In a real system, this would be an awaitable call to an LLM service.
        turkish_sentences = [
            "Merhaba, size nasıl yardımcı olabilirim? Bu konuşma sistemimiz sayesinde isteklerinizi sesli olarak iletebilirsiniz. Ben sizin sorularınızı yanıtlamak, bilgi vermek ve çeşitli işlemlerinizi gerçekleştirmek için buradayım. Herhangi bir konuda yardıma ihtiyacınız olursa lütfen belirtin. Size en iyi şekilde yardımcı olmak için elimden geleni yapacağım. Sesli asistanınız olarak size hizmet vermekten mutluluk duyuyorum.", 
            "Lütfen isteğinizi belirtin. Sorularınızı mümkün olduğunca açık ve net bir şekilde ifade ederseniz size daha doğru ve hızlı bir şekilde yardımcı olabilirim. Detaylı bilgiye ihtiyacım olursa ek sorular sorabilirim. İhtiyacınızı tam olarak anlayabilmem için gerekli tüm detayları paylaşmanız önemlidir. Karmaşık konularda adım adım ilerlememiz gerekebilir. Hangi konuda yardıma ihtiyacınız olduğunu lütfen anlatın.",
            "Anlıyorum, isteğiniz işleniyor. Bu işlem birkaç saniye sürebilir, lütfen sabırla bekleyin. Sisteme erişim sağlanıyor ve gerekli bilgiler toplanıyor. Bilgileriniz güvenli bir şekilde işleniyor ve işlem süreci devam ediyor. İşlem tamamlandığında size hemen bilgi vereceğim. Eğer ek bilgiye ihtiyacımız olursa, sizinle tekrar iletişime geçeceğim. Bu süreçte başka bir sorunuz veya isteğiniz olursa lütfen belirtin.", 
            "Bir saniye lütfen, kontrol ediyorum. Talebiniz doğrultusunda sistem kayıtlarına erişiyor ve gerekli bilgileri topluyorum. Bu işlem biraz zaman alabilir, sistem yanıt verene kadar lütfen bekleyin. Veritabanımızda arama yapılıyor ve ilgili bilgiler toplanıyor. Arama algoritması en güncel ve doğru bilgileri bulmak için çalışıyor. Sorgulama işlemi tamamlanmak üzere, sonuçları hemen sizinle paylaşacağım.",
            "İşleminiz başarıyla tamamlandı. Talebiniz sistem tarafından onaylandı ve gerekli tüm adımlar yerine getirildi. Herhangi bir sorun veya hata tespit edilmedi. İşleminize dair tüm detaylar kayıt altına alındı ve sistem güncellemesi gerçekleştirildi. Değişiklikler şu andan itibaren aktif ve geçerlidir. İsterseniz işleminizle ilgili detaylı bir rapor sunabilirim. İşlem sonucu memnun kaldıysanız, size başka konularda da yardımcı olabilirim.", 
            "Başka bir isteğiniz var mı? Size farklı bir konuda da yardımcı olmaktan memnuniyet duyarım. Ek sorularınız veya bilgi almak istediğiniz başka konular varsa lütfen belirtin. Önceki işleminizle ilgili herhangi bir ek bilgiye ihtiyacınız varsa, detaylandırmaktan çekinmeyin. Sistemimizin sunduğu diğer hizmetler hakkında bilgi almak isterseniz bunu da sağlayabilirim. Her türlü talebiniz için buradayım ve size yardımcı olmak için hazırım. Lütfen nasıl yardımcı olabileceğimi belirtin.",
            "Üzgünüm, isteğinizi anlayamadım. Kullandığınız ifade veya soru formatı sistemimiz tarafından doğru şekilde işlenemedi. Farklı bir şekilde ifade etmeyi veya daha açık bir dille talep oluşturmayı deneyebilirsiniz. Bazı özel terimler veya teknik ifadeler bazen zorluk yaratabilir, bu durumda daha genel terimler kullanmanız daha iyi olabilir. Konuşma tanıma sistemi bazen arka plan gürültüsünden veya ses kalitesinden etkilenebilir. Talebinizi daha net ve yavaş bir şekilde tekrarlamanız yardımcı olabilir.", 
            "Tekrar deneyebilir misiniz? Son talebiniz ses tanıma sistemimiz tarafından tam olarak algılanamadı veya anlaşılamadı. Lütfen daha yüksek sesle ve net bir şekilde konuşmayı deneyiniz. Bulunduğunuz ortamda ses kalitesini etkileyebilecek gürültüler varsa, daha sessiz bir ortama geçmek faydalı olabilir. Bazen belirli cümle yapıları veya terimler sistemimiz için zorlayıcı olabilir, bu durumda talebinizi daha basit bir dille ifade etmeyi deneyebilirsiniz. Birkaç kelime ile kısa ve öz bir şekilde ne istediğinizi belirtmek de yardımcı olabilir.",
            "Yardımcı olabileceğim başka bir konu var mı? Bugün sizin için başka hangi işlemleri gerçekleştirebilirim? Sistemimiz birçok farklı konuda hizmet sunmaktadır ve sizin için daha fazla bilgi sağlamaktan veya farklı konularda yardımcı olmaktan memnuniyet duyarım. Hesap işlemleri, bilgi sorgulama, randevu oluşturma veya iptal etme gibi çeşitli hizmetlerimizden faydalanabilirsiniz. Ayrıca ürünlerimiz ve hizmetlerimiz hakkında detaylı bilgi almak isterseniz, bu konuda da size kapsamlı bilgi sunabilirim. İhtiyaçlarınız doğrultusunda size en iyi şekilde yardımcı olmak için buradayım.", 
            "Görüşmek üzere, iyi günler! Bugün bizi tercih ettiğiniz ve hizmetimizden yararlandığınız için teşekkür ederiz. Umarım tüm sorularınıza tatmin edici yanıtlar alabilmişsinizdir. Tekrar görüşmek dileğiyle, size güzel ve verimli bir gün diliyorum. Herhangi bir sorunuz veya ihtiyacınız olduğunda tekrar bizi aramanız yeterli olacaktır. Sizinle tekrar görüşmeyi umuyoruz. Her zaman hizmetinizdeyiz. Bizden tekrar yardım almak istediğinizde çağrı merkezimizi arayabilir veya web sitemiz üzerinden bizimle iletişime geçebilirsiniz. Kendinize iyi bakın!",
        ]
        llm_response_text = random.choice(turkish_sentences) # Placeholder
        logging.info(f"{self.session_id}SmartSpeech: Simulated LLM response: \"{llm_response_text[:70]}...\"")

        # 2. Reset VAD state before starting new TTS to prepare for potential user barge-in
        if not self.bypass_vad:
            self.vad_processor.reset_vad_state(preserve_buffer=False) # Clear VAD buffer and state
            logging.info(f"{self.session_id}SmartSpeech: VAD state reset after LLM response, before TTS playback.")
        
        # Reset barge-in state for new TTS session
        self.barge_in_pending = False
        self.barge_in_speech_start_time = 0.0
        
        # 3. Initiate TTS generation for the LLM response
        if self.tts_processor:
            try:
                self.is_tts_active = True # <<< ADDED: Set flag before creating TTS task
                self.tts_task = asyncio.create_task(
                    self.tts_processor.generate_and_queue_tts_audio(llm_response_text),
                    name=f"TTS-{self.session_id}-{time.time()}"
                )
                logging.info(f"{self.session_id}SmartSpeech: TTS generation started in background. Barge-in enabled.")
                
                async def log_tts_completion(task):
                    await asyncio.sleep(0) # Ensure done callback is fully processed before queue check
                    try:
                        task.result()
                        if not self.barge_in_pending: # Check barge_in_pending before logging success
                            logging.info(f"{self.session_id}SmartSpeech: TTS task completed successfully.")
                    except asyncio.CancelledError:
                        logging.info(f"{self.session_id}SmartSpeech: TTS task was cancelled (likely due to barge-in).")
                    except Exception as e:
                        logging.error(f"{self.session_id}SmartSpeech: TTS task failed with error: {e}", exc_info=True)
                    finally:
                        # Check queue status before setting TTS to inactive
                        # This is to ensure that all TTS audio packets have been sent from the queue
                        # especially if the TTS generation itself was very fast.
                        if not self.queue.empty():
                            logging.info(f"{self.session_id}SmartSpeech: TTS task finished, but output queue has {self.queue.qsize()} items. Waiting for queue to empty...")
                            queue_wait_start_time = time.time()
                            max_queue_wait_seconds = 3.0

                            while not self.queue.empty():
                                if self._is_closing:
                                    logging.warning(f"{self.session_id}SmartSpeech: Session closing, aborting TTS queue wait.")
                                    break
                                if self.barge_in_pending: # If barge-in started while waiting for queue
                                    logging.warning(f"{self.session_id}SmartSpeech: Barge-in detected, aborting TTS queue wait.")
                                    break
                                if (time.time() - queue_wait_start_time) > max_queue_wait_seconds:
                                    logging.error(
                                        f"{self.session_id}SmartSpeech: TTS output queue did not empty after {max_queue_wait_seconds}s. "
                                        f"Remaining items: {self.queue.qsize()}. Proceeding to set TTS inactive."
                                    )
                                    # Consider clearing the queue here if this timeout implies a problem
                                    # while not self.queue.empty():
                                    #     try: self.queue.get_nowait()
                                    #     except Empty: break
                                    break
                                await asyncio.sleep(0.1) # Short sleep while checking queue

                            elapsed_wait_time = time.time() - queue_wait_start_time
                            if self.queue.empty():
                                logging.info(f"{self.session_id}SmartSpeech: TTS output queue emptied after {elapsed_wait_time:.2f}s.")
                            elif not self._is_closing and not self.barge_in_pending : # Log if not emptied due to timeout
                                logging.warning(f"{self.session_id}SmartSpeech: TTS output queue wait finished after {elapsed_wait_time:.2f}s, but queue still has {self.queue.qsize()} items.")

                        self.is_tts_active = False
                        # If barge-in happened, it might have already set is_tts_active to False. This is safe.
                        logging.info(f"{self.session_id}SmartSpeech: is_tts_active set to False. Barge-in pending: {self.barge_in_pending}, Closing: {self._is_closing}")
                
                self.tts_task.add_done_callback(lambda task: asyncio.create_task(log_tts_completion(task)))
                
            except Exception as e_tts_gen:
                logging.error(f"{self.session_id}SmartSpeech: Error during TTS generation task creation: {e_tts_gen}", exc_info=True)
                self.tts_task = None
                self.is_tts_active = False # <<< ADDED: Clear flag on creation error
        else:
            logging.error(f"{self.session_id}SmartSpeech: TTSProcessor not initialized, cannot generate TTS.")
