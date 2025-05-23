"""
Provides the `SmartSpeech` class, an AIEngine implementation for speech-to-text (STT)
and text-to-speech (TTS) integration using Vosk for STT and a Piper client for TTS.

The module includes several helper classes:
- `AudioProcessor`: Handles raw audio processing, decoding, and resampling.
- `VADProcessor`: Manages Voice Activity Detection.
- `TranscriptHandler`: Processes and manages partial and final STT transcripts.
- `TTSProcessor`: Manages TTS audio generation and queuing.

The `SmartSpeech` class orchestrates these components to provide a full-duplex
voice conversation experience.
"""
from codec import get_codecs, PCMU, UnsupportedCodec
from vad_detector import VADDetector
from config import Config
import torch
# import numpy as np # Not directly used in this file, but numpy arrays are passed from pcmu_decoder
import asyncio
from ai import AIEngine
from queue import Empty, Queue
import json
import logging
from typing import Callable, Awaitable 
from vosk_client import VoskClient
import torchaudio
import time
from pcmu_decoder import PCMUDecoder
import websockets
import traceback # Used for logging exception details
import audioop  # For mu-law encoding
import random  # For simulated responses
from piper_client import PiperClient

class AudioProcessor:
    """
    Handles audio processing tasks such as decoding, resampling, normalization,
    and format conversion for speech recognition.

    The primary input is expected to be PCMU encoded audio bytes, which are
    processed into a format suitable for speech-to-text (STT) engines
    (typically 16kHz, 16-bit PCM).
    """
    
    def __init__(self, target_sample_rate: int = 16000, debug: bool = False, session_id: str = ""):
        """
        Initializes the AudioProcessor.

        Args:
            target_sample_rate: The desired sample rate for the output audio (e.g., 16000 Hz).
            debug: If True, enables detailed debug logging.
            session_id: An identifier for the current session, used for logging.
        """
        self.target_sample_rate = target_sample_rate
        self.debug = debug
        self.session_id = session_id
        
        # Decoder for PCMU (G.711 mu-law) audio
        self.pcmu_decoder = PCMUDecoder()
        
        # Resampler to convert from 8kHz (PCMU native rate) to the target sample rate
        self.resampler = torchaudio.transforms.Resample(orig_freq=8000, new_freq=self.target_sample_rate)
    
    def tensor_to_bytes(self, tensor: torch.Tensor) -> bytes:
        """
        Converts a float32 audio tensor to 16-bit PCM bytes.

        The input tensor is expected to be in the range [-1.0, 1.0].
        The tensor is clamped to this range, then scaled to int16 range
        [-32768, 32767] and converted to bytes.

        Args:
            tensor: A PyTorch float32 audio tensor.
            
        Returns:
            bytes: Audio data as 16-bit PCM bytes.
        """
        # Clamp tensor values to the valid range [-1.0, 1.0]
        processed_tensor = torch.clamp(tensor, -1.0, 1.0)
        # Scale to int16 range and convert to bytes
        return (processed_tensor * 32768.0).to(torch.int16).numpy().tobytes()
    
    def process_bytes_audio(self, audio: bytes) -> tuple[torch.Tensor | None, bytes | None]:
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
    Manages Voice Activity Detection (VAD) by buffering incoming audio,
    processing it in chunks, and determining speech segments.
    """
    
    def __init__(self, 
                 vad_detector: VADDetector, 
                 target_sample_rate: int, 
                 audio_processor: AudioProcessor, 
                 vad_buffer_chunk_ms: int = 750, 
                 speech_detection_threshold: int = 3, 
                 silence_detection_threshold: int = 10, 
                 debug: bool = False, 
                 session_id: str = ""):
        """
        Initializes the VADProcessor.

        Args:
            vad_detector: An instance of VADDetector for speech detection.
            target_sample_rate: The sample rate of the audio being processed (e.g., 16000 Hz).
            audio_processor: Reference to the AudioProcessor instance. (Currently unused directly but kept for API consistency)
            vad_buffer_chunk_ms: Duration of audio (in ms) to buffer before VAD processing.
            speech_detection_threshold: Number of consecutive speech chunks to trigger `speech_active`.
            silence_detection_threshold: Number of consecutive silence chunks to deactivate `speech_active`.
            debug: If True, enables detailed debug logging.
            session_id: An identifier for the current session, used for logging.
        """
        self.vad: VADDetector = vad_detector
        self.target_sample_rate: int = target_sample_rate
        self.audio_processor: AudioProcessor = audio_processor 
        self.vad_buffer_chunk_ms: int = vad_buffer_chunk_ms
        self.speech_detection_threshold: int = speech_detection_threshold
        self.silence_detection_threshold: int = silence_detection_threshold
        self.debug: bool = debug
        self.session_id: str = session_id
        
        self._vad_buffer: bytearray = bytearray()
        self._vad_buffer_size_samples: int = 0
        self._last_buffer_flush_time: float = time.time()
        self._vad_buffer_locks: asyncio.Lock = asyncio.Lock()
        
        self.consecutive_speech_packets: int = 0
        self.consecutive_silence_packets: int = 0
        self.speech_active: bool = False 
    
    def reset_vad_state(self, preserve_buffer: bool = False) -> None:
        """
        Resets the VAD state, clearing speech/silence counters and optionally the audio buffer.
        """
        if self.debug:
            logging.debug(f"{self.session_id}Resetting VAD state. Preserve buffer: {preserve_buffer}")
            
        self.consecutive_speech_packets = 0
        self.consecutive_silence_packets = 0
        
        was_active = self.speech_active
        self.speech_active = False 
        
        if not preserve_buffer:
            self._vad_buffer.clear()
            self._vad_buffer_size_samples = 0
            self._last_buffer_flush_time = time.time() 
            if self.debug:
                logging.debug(f"{self.session_id}VAD buffer cleared.")
            
        logging.info(f"{self.session_id}VAD state reset. Speech was {'active' if was_active else 'inactive'}. Buffer {'preserved' if preserve_buffer else 'cleared'}.")

    async def add_audio(self, audio_bytes: bytes, num_samples: int) -> tuple[bool, bool, bytes | None]:
        """
        Adds audio data to the VAD buffer and processes it if chunk size is reached.
        """
        async with self._vad_buffer_locks: 
            self._vad_buffer.extend(audio_bytes)
            self._vad_buffer_size_samples += num_samples
            
            buffer_ms = (self._vad_buffer_size_samples / self.target_sample_rate) * 1000
            
            if buffer_ms >= self.vad_buffer_chunk_ms:
                if self.debug:
                    logging.debug(f"{self.session_id}VAD buffer reached {buffer_ms:.2f}ms (threshold {self.vad_buffer_chunk_ms}ms), processing for VAD.")
                is_speech, processed_buffer_bytes = await self._process_buffer()
                return True, is_speech, processed_buffer_bytes 
                
            return False, False, None 
    
    async def _process_buffer(self) -> tuple[bool, bytes]:
        """
        Processes the current VAD buffer to detect speech and updates VAD state.
        Assumes `_vad_buffer_locks` is held by the caller.
        """
        buffer_bytes = bytes(self._vad_buffer)
        send_to_stt = False 
        
        try:
            audio_tensor = torch.frombuffer(bytearray(buffer_bytes), dtype=torch.int16).float() / 32768.0
            is_speech_in_chunk = self.vad.is_speech(audio_tensor)
            
            if self.debug:
                logging.debug(f"{self.session_id}VAD processing chunk: speech_detected_in_chunk={is_speech_in_chunk}, current_speech_active={self.speech_active}")

            if is_speech_in_chunk:
                self.consecutive_speech_packets += 1
                self.consecutive_silence_packets = 0 
            else:
                self.consecutive_silence_packets += 1
                self.consecutive_speech_packets = 0 
            
            if is_speech_in_chunk:
                if self.consecutive_speech_packets >= self.speech_detection_threshold and not self.speech_active:
                    self.speech_active = True
                    logging.info(f"{self.session_id}Speech started (VAD active) after {self.consecutive_speech_packets} consecutive speech chunk(s).")
            else:
                if self.debug and self.speech_active : 
                     logging.debug(f"{self.session_id}VAD CHECK (speech_active=true): consecutive_silence_packets={self.consecutive_silence_packets}, silence_detection_threshold={self.silence_detection_threshold}")
                if self.consecutive_silence_packets >= self.silence_detection_threshold and self.speech_active:
                    self.speech_active = False
                    logging.info(f"{self.session_id}Speech ended (VAD inactive) after {self.consecutive_silence_packets} consecutive silence chunk(s).")
            
            send_to_stt = is_speech_in_chunk or self.speech_active
            
            if self.debug:
                if send_to_stt:
                    logging.debug(f"{self.session_id}VAD decision: Send to STT (chunk_speech={is_speech_in_chunk}, overall_speech_active={self.speech_active})")
                else:
                    logging.debug(f"{self.session_id}VAD decision: Do not send to STT (chunk_speech={is_speech_in_chunk}, overall_speech_active={self.speech_active})")
            
            return send_to_stt, buffer_bytes
            
        except Exception as e:
            logging.error(f"{self.session_id}Error processing VAD buffer: {str(e)}", exc_info=True)
            return False, buffer_bytes 
        finally:
            self._vad_buffer.clear()
            self._vad_buffer_size_samples = 0
            self._last_buffer_flush_time = time.time()
            if self.debug:
                logging.debug(f"{self.session_id}VAD buffer cleared after processing.")
    
    async def process_final_buffer(self) -> tuple[bool, bytes | None]:
        """
        Processes any remaining audio in the VAD buffer, typically at stream end.
        """
        async with self._vad_buffer_locks: 
            if len(self._vad_buffer) > 0:
                buffer_seconds = self._vad_buffer_size_samples / self.target_sample_rate
                if self.debug:
                    logging.debug(f"{self.session_id}Processing remaining VAD buffer: {buffer_seconds:.2f} seconds ({self._vad_buffer_size_samples} samples).")
                is_speech, buffer_bytes = await self._process_buffer()
                return is_speech, buffer_bytes
            
        if self.debug:
            logging.debug(f"{self.session_id}No remaining VAD buffer to process.")
        return False, None 

class TranscriptHandler:
    """
    Manages the processing of transcript messages from an STT service.
    """
    
    def __init__(self, session_id: str = ""):
        """
        Initializes the TranscriptHandler.
        Args:
            session_id: Identifier for logging.
        """
        self.last_partial_transcript: str = ""
        self.last_final_transcript: str = ""
        self.on_partial_transcript: Callable[[str], Awaitable[None]] | None = None
        self.on_final_transcript: Callable[[str], Awaitable[None]] | None = None
        self.session_id: str = session_id
    
    async def handle_message(self, message: str) -> bool:
        """
        Processes an incoming STT message (JSON string).
        Updates transcript states and triggers callbacks.
        """
        try:
            response = json.loads(message)
            
            if "partial" in response:
                partial_text = response.get("partial", "") 
                self.last_partial_transcript = partial_text
                if partial_text:
                    logging.info(f"{self.session_id}Partial transcript: {partial_text}") 
                if partial_text and self.on_partial_transcript:
                    await self.on_partial_transcript(partial_text)
            
            if "text" in response:
                final_text = response.get("text", "") 
                self.last_final_transcript = final_text
                if final_text:
                    logging.info(f"{self.session_id}FINAL transcript: {final_text}")
                if final_text and self.on_final_transcript:
                    asyncio.create_task(self.on_final_transcript(final_text))
                    
            return True 
                
        except json.JSONDecodeError:
            logging.error(f"{self.session_id}Invalid JSON response: {message}")
            return False
        except Exception as e:
            logging.error(f"{self.session_id}Error processing transcript: {str(e)}", exc_info=True)
            return False
    
    def get_final_transcript(self) -> str:
        """
        Retrieves the most definitive transcript, with fallback logic.
        """
        if self.last_final_transcript:
            if self.session_id and logging.getLogger().isEnabledFor(logging.DEBUG): 
                 logging.debug(f"{self.session_id}Returning final transcript: {self.last_final_transcript[:50]}...")
            return self.last_final_transcript
        elif self.last_partial_transcript:
            if self.session_id and logging.getLogger().isEnabledFor(logging.DEBUG):
                logging.debug(f"{self.session_id}No final transcript available, returning partial: {self.last_partial_transcript[:50]}...")
            return self.last_partial_transcript
        else:
            if self.session_id and logging.getLogger().isEnabledFor(logging.DEBUG):
                logging.debug(f"{self.session_id}No transcript available, returning empty string")
            return ""

class TTSProcessor:
    """
    Handles Text-to-Speech (TTS) audio generation, processing, and queuing.
    """
    def __init__(self, 
                 rtp_queue: Queue,
                 tts_server_host: str, 
                 tts_server_port: int, 
                 tts_voice: str,
                 tts_target_output_rate: int = 8000, 
                 session_id: str = "", 
                 debug: bool = False):
        """
        Initializes the TTSProcessor.
        """
        self.rtp_queue = rtp_queue
        self.tts_server_host = tts_server_host
        self.tts_server_port = tts_server_port
        self.tts_voice = tts_voice
        self.tts_target_output_rate = tts_target_output_rate
        self.session_id = session_id
        self.debug = debug

        self.tts_resampler: torchaudio.transforms.Resample | None = None
        self.tts_input_rate: int = 22050 
        self.tts_processing_lock = asyncio.Lock()

    async def generate_and_queue_tts_audio(self, text_to_speak: str):
        """
        Generates TTS audio, processes it, and queues it for playback.
        """
        async with self.tts_processing_lock:
            if self.debug:
                logging.debug(f"{self.session_id}TTSProcessor: generating audio for text: '{text_to_speak[:50]}...'")

            q_size = self.rtp_queue.qsize()
            if q_size > 0:
                logging.info(f"{self.session_id}TTSProcessor: Draining {q_size} packets from RTP queue before TTS playback.")
                while not self.rtp_queue.empty():
                    try:
                        self.rtp_queue.get_nowait() 
                    except Empty:
                        break 
            
            tts_success = False
            try:
                piper_client = PiperClient(
                    server_host=self.tts_server_host,
                    server_port=self.tts_server_port,
                    session_id=self.session_id
                )
                
                cumulative_pcmu_bytes = bytearray()
                chunk_size = 160 
                first_audio_chunk = True
                
                async def on_audio(audio_bytes: bytes):
                    nonlocal cumulative_pcmu_bytes, first_audio_chunk
                    try:
                        if first_audio_chunk:
                            first_audio_chunk = False
                            if self.tts_input_rate != self.tts_target_output_rate:
                                if self.debug:
                                    logging.debug(f"{self.session_id}TTSProcessor: Initializing TTS resampler: {self.tts_input_rate}Hz -> {self.tts_target_output_rate}Hz")
                                self.tts_resampler = torchaudio.transforms.Resample(
                                    orig_freq=self.tts_input_rate,
                                    new_freq=self.tts_target_output_rate
                                )
                            elif self.debug:
                                logging.debug(f"{self.session_id}TTSProcessor: TTS output rate matches target rate ({self.tts_target_output_rate}Hz). No resampling needed.")
                        
                        input_tensor = torch.frombuffer(bytearray(audio_bytes), dtype=torch.int16).float() / 32768.0
                        
                        if self.tts_resampler:
                            resampled_tensor = self.tts_resampler(input_tensor.unsqueeze(0)).squeeze(0)
                        else:
                            resampled_tensor = input_tensor
                        
                        resampled_tensor_clamped = torch.clamp(resampled_tensor, -1.0, 1.0)
                        pcm_s16le_bytes = (resampled_tensor_clamped * 32768.0).to(torch.int16).numpy().tobytes()
                        
                        pcmu_chunk_bytes = audioop.lin2ulaw(pcm_s16le_bytes, 2) 
                        cumulative_pcmu_bytes.extend(pcmu_chunk_bytes)
                        
                        while len(cumulative_pcmu_bytes) >= chunk_size:
                            rtp_payload = cumulative_pcmu_bytes[:chunk_size]
                            self.rtp_queue.put_nowait(bytes(rtp_payload))
                            if self.debug:
                                logging.debug(f"{self.session_id}TTSProcessor: Queued {len(rtp_payload)} bytes of TTS audio for RTP.")
                            cumulative_pcmu_bytes = cumulative_pcmu_bytes[chunk_size:]
                            await asyncio.sleep(0) 
                            
                    except Exception as audio_e:
                        logging.error(f"{self.session_id}TTSProcessor: Error processing TTS audio chunk: {audio_e}", exc_info=True)
                
                async def on_start(data):
                    logging.info(f"{self.session_id}TTSProcessor: TTS stream starting: {data.get('message')}")
                    
                async def on_end(data):
                    nonlocal tts_success
                    tts_success = True
                    logging.info(f"{self.session_id}TTSProcessor: TTS stream complete: {data.get('message')}")
                    
                async def on_error(data):
                    logging.error(f"{self.session_id}TTSProcessor: TTS error from Piper: {data.get('message')}")
                
                if await piper_client.connect():
                    if await piper_client.synthesize(text_to_speak, voice=self.tts_voice):
                        await piper_client.process_stream(
                            on_start=on_start,
                            on_audio=on_audio,
                            on_end=on_end,
                            on_error=on_error
                        )
                    await piper_client.close()
                
                if cumulative_pcmu_bytes: 
                    if self.debug:
                        logging.debug(f"{self.session_id}TTSProcessor: Processing remaining {len(cumulative_pcmu_bytes)} TTS PCMU bytes.")
                    final_payload = bytes(cumulative_pcmu_bytes).ljust(chunk_size, b'\xff') 
                    self.rtp_queue.put_nowait(final_payload)
                    if self.debug:
                        logging.debug(f"{self.session_id}TTSProcessor: Queued final {len(final_payload)} bytes of TTS audio.")
                
                if tts_success:
                    logging.info(f"{self.session_id}TTSProcessor: Successfully generated and queued audio for: '{text_to_speak[:50]}...'")
                else:
                    logging.warning(f"{self.session_id}TTSProcessor: TTS generation did not complete successfully for: '{text_to_speak[:50]}...'")

            except Exception as e:
                logging.error(f"{self.session_id}TTSProcessor: Error during TTS processing: {e}", exc_info=True)

class SmartSpeech(AIEngine):
    """
    AIEngine implementation integrating Vosk for STT and Piper for TTS.
    Orchestrates audio processing, VAD, STT transcription, and TTS response.
    """
    
    def __init__(self, call, cfg):
        """
        Initializes the SmartSpeech engine.
        """
        self.cfg = Config.get("vosk", cfg)
        
        self.b2b_key = call.b2b_key if hasattr(call, 'b2b_key') else None
        self.session_id = f"[Session:{self.b2b_key}] " if self.b2b_key else ""
        self.queue: Queue = call.rtp 
        self._load_config()
        self._init_components(call)
        
        self.receive_task = None
        self.tts_task = None  
        self._is_closing = False
        self._setup_logging()
        
        logging.info(f"{self.session_id}SmartSpeech initialized. bypass_vad = {self.bypass_vad}")

    def _load_config(self):
        """Loads STT and TTS configurations."""
        self.vosk_server_url = self.cfg.get("url", "url", "ws://localhost:2700")
        self.websocket_timeout = self.cfg.get("websocket_timeout", "websocket_timeout", 5.0)
        self.target_sample_rate = int(self.cfg.get("sample_rate", "sample_rate", 16000))
        self.channels = self.cfg.get("channels", "channels", 1)
        self.send_eof = self.cfg.get("send_eof", "send_eof", True)
        self.debug = self.cfg.get("debug", "debug", False)
        
        self.bypass_vad = self.cfg.get("bypass_vad", "bypass_vad", False)
        self.vad_threshold = self.cfg.get("vad_threshold", "vad_threshold", 0.25)
        self.vad_min_speech_ms = self.cfg.get("vad_min_speech_ms", "vad_min_speech_ms", 350)
        self.vad_min_silence_ms = self.cfg.get("vad_min_silence_ms", "vad_min_silence_ms", 450)
        self.vad_buffer_chunk_ms = self.cfg.get("vad_buffer_chunk_ms", "vad_buffer_chunk_ms", 600)
        self.vad_buffer_max_seconds = self.cfg.get("vad_buffer_max_seconds", "vad_buffer_max_seconds", 2.0)
        self.speech_detection_threshold = self.cfg.get("speech_detection_threshold", "speech_detection_threshold", 1)
        self.silence_detection_threshold = self.cfg.get("silence_detection_threshold", "silence_detection_threshold", 2)
            
        self.tts_server_host_cfg = self.cfg.get("host", "TTS_HOST", "localhost")
        self.tts_server_port_cfg = int(self.cfg.get("port", "TTS_PORT", 8000))
        self.tts_voice_cfg = self.cfg.get("voice", "TTS_VOICE", "tr_TR-fahrettin-medium")
        self.tts_target_output_rate_cfg = 8000  
        
        logging.info(f"{self.session_id}Vosk URL: {self.vosk_server_url}, Target STT Rate: {self.target_sample_rate}")
        logging.info(f"{self.session_id}TTS Config: Host={self.tts_server_host_cfg}:{self.tts_server_port_cfg}, Voice={self.tts_voice_cfg}, TargetRate={self.tts_target_output_rate_cfg}")

    def _init_components(self, call):
        """Initializes various processing components."""
        self.call = call
        self.client_addr = call.client_addr
        self.client_port = call.client_port
        self.codec = self.choose_codec(call.sdp)
        
        self.audio_processor = AudioProcessor(
            target_sample_rate=self.target_sample_rate,
            debug=self.debug,
            session_id=self.session_id
        )
        
        vad_detector = VADDetector(
            sample_rate=self.target_sample_rate,
            threshold=self.vad_threshold,
            min_speech_duration_ms=self.vad_min_speech_ms,
            min_silence_duration_ms=self.vad_min_silence_ms
        )
        
        self.vad_processor = VADProcessor(
            vad_detector=vad_detector,
            target_sample_rate=self.target_sample_rate,
            audio_processor=self.audio_processor,
            vad_buffer_chunk_ms=self.vad_buffer_chunk_ms,
            speech_detection_threshold=self.speech_detection_threshold,
            silence_detection_threshold=self.silence_detection_threshold,
            debug=self.debug,
            session_id=self.session_id
        )
        
        if self.bypass_vad:
            self.vad_processor.speech_active = True
        
        self.transcript_handler = TranscriptHandler(session_id=self.session_id)
        self.vosk_client = VoskClient(self.vosk_server_url, timeout=self.websocket_timeout)
        
        self.tts_processor = TTSProcessor(
            rtp_queue=self.queue,
            tts_server_host=self.tts_server_host_cfg,
            tts_server_port=self.tts_server_port_cfg,
            tts_voice=self.tts_voice_cfg,
            tts_target_output_rate=self.tts_target_output_rate_cfg,
            session_id=self.session_id,
            debug=self.debug
        )
        
        self.transcript_handler.on_final_transcript = self._handle_final_transcript

    def _setup_logging(self):
        """Sets up basic logging configuration."""
        logging.basicConfig(level=logging.INFO)
        if self.debug:
            logging.getLogger().setLevel(logging.DEBUG)
            logging.debug(f"{self.session_id}Debug logging enabled")

    def choose_codec(self, sdp):
        """Chooses PCMU codec from SDP."""
        codecs = get_codecs(sdp)
        for c in codecs:
            if c.payloadType == 0: 
                return PCMU(c)
        raise UnsupportedCodec("No supported codec (PCMU) found in SDP.")

    async def start(self):
        """Starts the STT engine and connects to the Vosk server."""
        logging.info(f"{self.session_id}SmartSpeech engine starting...")
        
        try:
            self._is_closing = False
            await self.vosk_client.connect()
            config = {
                "config": {
                    "sample_rate": self.target_sample_rate,
                    "num_channels": self.channels
                }
            }
            await self.vosk_client.send(config)
            self.receive_task = asyncio.create_task(self.receive_transcripts())
            logging.info(f"{self.session_id}SmartSpeech engine started successfully.")
            return True
        except Exception as e:
            logging.error(f"{self.session_id}Error starting SmartSpeech engine: {e}", exc_info=True)
            return False
    
    async def stop(self):
        """Stops the STT engine and closes connections."""
        logging.info(f"{self.session_id}Stopping SmartSpeech engine.")
        
        try:
            await self._send_eof_if_enabled()
            if self.vosk_client.is_connected:
                try:
                    await self.vosk_client.disconnect()
                    logging.info(f"{self.session_id}Disconnected from Vosk server during stop.")
                except Exception as e_disconnect:
                    logging.error(f"{self.session_id}Error disconnecting Vosk client during stop: {e_disconnect}", exc_info=True)
            
            await self._cancel_receive_task() 
            logging.info(f"{self.session_id}SmartSpeech engine stopped successfully.")
            return True
        except Exception as e:
            logging.error(f"{self.session_id}Error stopping SmartSpeech engine: {e}", exc_info=True)
            return False

    async def _manage_task(self, task, timeout=2.0):
        """Manages an asyncio task with timeout and cancellation."""
        task_name = getattr(task, 'get_name', lambda: "Unknown Task")() 
        if task and not task.done():
            try:
                await asyncio.wait_for(task, timeout=timeout)
                return True
            except asyncio.TimeoutError:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
                logging.warning(f"{self.session_id}Task {task_name} was cancelled due to timeout.")
                return False
            except Exception as e_wait:
                logging.error(f"{self.session_id}Unexpected error managing task {task_name}: {e_wait}", exc_info=True)
                if not task.done():
                    task.cancel()
                    try:
                        await task 
                    except asyncio.CancelledError:
                        pass 
                    except Exception as e_final_cancel:
                        logging.error(f"{self.session_id}Error during final cancellation of task {task_name}: {e_final_cancel}", exc_info=True)
                return False
        return True

    async def _cancel_receive_task(self):
        """Cancels the transcript receive task."""
        if self.receive_task:
            if self.debug:
                logging.debug(f"{self.session_id}Cancelling receive_task.")
            if not await self._manage_task(self.receive_task, timeout=1.0): 
                logging.warning(f"{self.session_id}Receive task did not complete cleanly after cancellation request.")
            self.receive_task = None 
        elif self.debug:
            logging.debug(f"{self.session_id}Receive_task is None, no cancellation needed.")

    async def _send_eof_if_enabled(self):
        """Sends EOF to Vosk if enabled and connected."""
        if self.send_eof and self.vosk_client.is_connected:
            try:
                logging.debug(f"{self.session_id}Sending EOF to Vosk server.")
                await self.vosk_client.send(json.dumps({"eof": 1}))
                await asyncio.sleep(0.1) 
            except Exception as e:
                logging.error(f"{self.session_id}Error sending EOF to Vosk: {e}", exc_info=True)

    async def send(self, audio: bytes):
        """Processes and sends audio to Vosk, via VAD if enabled."""
        if self._is_closing: 
            logging.warning(f"{self.session_id}Attempted to send audio while session is closing. Skipping.")
            return

        if not self.vosk_client.is_connected:
            logging.warning(f"{self.session_id}WebSocket not connected. Cannot send audio.")
            return
            
        try:
            if not isinstance(audio, bytes):
                logging.warning(f"{self.session_id}Unexpected audio type received: {type(audio)}, expected bytes. Skipping.")
                return

            resampled_tensor, processed_audio_bytes = self.audio_processor.process_bytes_audio(audio)
            
            if processed_audio_bytes is None:
                return
                
            await self._handle_processed_audio(resampled_tensor, processed_audio_bytes)
                
        except Exception as e:
            logging.error(f"{self.session_id}Unhandled error in send method: {e}", exc_info=True)

    async def _handle_processed_audio(self, tensor: torch.Tensor | None, audio_bytes: bytes):
        """Handles processed audio, sending to VAD or directly to Vosk."""
        if self.debug: 
            logging.debug(f"{self.session_id}Handling processed audio: {len(audio_bytes)} bytes")
        
        if self.bypass_vad:
            if self.debug: 
                hex_preview = ' '.join([f'{b:02x}' for b in audio_bytes[:20]])
                logging.debug(f"{self.session_id}Sending audio bytes directly (VAD bypassed): len={len(audio_bytes)}, start_hex={hex_preview}")
            await self.vosk_client.send_audio(audio_bytes)
        else:
            num_samples = tensor.shape[0] if tensor is not None else len(audio_bytes) // 2 
            was_processed, is_speech, buffer_bytes = await self.vad_processor.add_audio(
                audio_bytes, num_samples)
                
            if was_processed and is_speech and buffer_bytes:
                if self.debug: 
                    hex_preview_vad = ' '.join([f'{b:02x}' for b in buffer_bytes[:20]])
                    logging.debug(f"{self.session_id}Sending VAD buffer bytes: len={len(buffer_bytes)}, start_hex={hex_preview_vad}")
                await self.vosk_client.send_audio(buffer_bytes)

    async def receive_transcripts(self):
        """Receives and processes transcripts from Vosk server."""
        try:
            reconnect_attempts = 0
            max_reconnect_attempts = 5  
            
            while True:
                try:
                    message = await self.vosk_client.receive_result()
                    
                    if self.debug:
                        logging.debug(f"{self.session_id}Vosk response received: {message}")
                    
                    if message is None:
                        logging.debug(f"{self.session_id}Timeout or no new message from Vosk (normal during silence).") 
                        if not self.vosk_client.is_connected:
                            logging.error(f"{self.session_id}WebSocket connection lost during transcript reception")
                            if self._is_closing or self.call.terminated:
                                logging.info(f"{self.session_id}Session is closing, not attempting to reconnect")
                                break
                                
                            success = await self._try_reconnect(reconnect_attempts, max_reconnect_attempts)
                            if success:
                                reconnect_attempts = 0
                            else:
                                reconnect_attempts += 1
                                if reconnect_attempts >= max_reconnect_attempts:
                                    logging.error(f"{self.session_id}Maximum reconnection attempts reached. Giving up.")
                                    break
                        continue
                    
                    reconnect_attempts = 0
                    if not await self.transcript_handler.handle_message(message):
                        logging.warning(f"{self.session_id}Transcript handler failed to process message.")
                    
                except websockets.exceptions.ConnectionClosed as conn_err:
                    if self._is_closing or self.call.terminated:
                        logging.info(f"{self.session_id}WebSocket connection closed as part of session shutdown (Code: {conn_err.code}).")
                        break 
                    
                    logging.error(f"{self.session_id}WebSocket connection closed unexpectedly: {conn_err}", exc_info=True)
                    self.vosk_client.is_connected = False 
                    
                    if await self._try_reconnect(reconnect_attempts, max_reconnect_attempts):
                        reconnect_attempts = 0 
                    else:
                        reconnect_attempts += 1
                        if reconnect_attempts >= max_reconnect_attempts:
                            logging.error(f"{self.session_id}Maximum reconnection attempts reached. Stopping transcript reception.")
                            break 
                except asyncio.CancelledError:
                    logging.info(f"{self.session_id}Transcript receive task was cancelled.")
                    raise 
                except Exception as e:
                    logging.error(f"{self.session_id}Unexpected error in receive_transcripts loop: {e}", exc_info=True)
                    await asyncio.sleep(1) 
            
            logging.info(f"{self.session_id}Exiting receive_transcripts loop.")

    async def _try_reconnect(self, attempts: int, max_attempts: int) -> bool:
        """Attempts to reconnect to the Vosk server with backoff."""
        if attempts >= max_attempts:
            logging.error(f"{self.session_id}Maximum reconnection attempts ({max_attempts}) reached. Giving up.")
            return False
            
        attempt_number = attempts + 1
        backoff_time = min(2 ** attempt_number, 10) 
            
        logging.info(f"{self.session_id}Attempting to reconnect to Vosk server (attempt {attempt_number}/{max_attempts}). Waiting {backoff_time}s.")
        await asyncio.sleep(backoff_time) 
        
        try:
            await self.vosk_client.connect() 
            if not self.vosk_client.is_connected: 
                 logging.error(f"{self.session_id}Failed to reconnect to Vosk server (connection status false).")
                 return False

            logging.info(f"{self.session_id}Successfully reconnected to Vosk server.")
            
            config_payload = {
                "config": {
                    "sample_rate": self.target_sample_rate,
                    "num_channels": self.channels
                }
            }
            await self.vosk_client.send(config_payload)
            logging.info(f"{self.session_id}Resent configuration to Vosk server after reconnection.")
            return True
            
        except Exception as reconnect_error:
            logging.error(f"{self.session_id}Error during reconnection attempt {attempt_number}: {reconnect_error}", exc_info=True)
            return False

    async def close(self):
        """Closes the SmartSpeech session gracefully."""
        if self._is_closing:
            logging.info(f"{self.session_id}Close operation already in progress.")
            return
        logging.info(f"{self.session_id}Initiating closure of SmartSpeech session.")
        
        self._is_closing = True 
        
        if hasattr(self, 'tts_task') and self.tts_task and not self.tts_task.done():
            logging.debug(f"{self.session_id}Attempting to cancel active TTS task.")
            self.tts_task.cancel()
            try:
                await self.tts_task
            except asyncio.CancelledError:
                logging.info(f"{self.session_id}Active TTS task cancelled successfully.")
            except Exception as e_tts_cancel:
                logging.error(f"{self.session_id}Error awaiting cancelled TTS task: {e_tts_cancel}", exc_info=True)
        
        if not self.bypass_vad:
            try:
                logging.debug(f"{self.session_id}Processing final VAD buffer before closing.")
                await self._process_final_vad_buffer()
            except Exception as e_vad_final:
                logging.error(f"{self.session_id}Error processing final VAD buffer during close: {e_vad_final}", exc_info=True)
        
        try:
            self._finalize_transcript()
        except Exception as e_finalize:
            logging.error(f"{self.session_id}Error finalizing transcript during close: {e_finalize}", exc_info=True)

        if self.vosk_client.is_connected:
            try:
                await self._send_eof_if_enabled() 
                logging.debug(f"{self.session_id}Attempting to disconnect Vosk client.")
                await self.vosk_client.disconnect()
                logging.info(f"{self.session_id}Disconnected from Vosk server successfully.")
            except Exception as e_vosk_close:
                logging.error(f"{self.session_id}Error disconnecting from Vosk server during close: {e_vosk_close}", exc_info=True)
        
        logging.debug(f"{self.session_id}Ensuring Vosk receive task is cancelled.")
        await self._cancel_receive_task() 
        
        logging.info(f"{self.session_id}SmartSpeech session close procedure completed.")

    def _finalize_transcript(self):
        """Ensure we have a final transcript (use partial if no final available)."""
        try:
            if not self.transcript_handler.last_final_transcript and self.transcript_handler.last_partial_transcript:
                logging.info(f"{self.session_id}No final transcript at session end, using last partial: {self.transcript_handler.last_partial_transcript[:80]}...")
                self.transcript_handler.last_final_transcript = self.transcript_handler.last_partial_transcript
            
            if self.transcript_handler.last_final_transcript:
                logging.info(f"{self.session_id}Definitive final transcript for session: {self.transcript_handler.last_final_transcript}")
            else:
                logging.info(f"{self.session_id}No transcript (final or partial) available at session end.")
        except Exception as e:
            logging.error(f"{self.session_id}Error during _finalize_transcript: {e}", exc_info=True)


    def terminate_call(self):
        """ Terminates the call """
        logging.info(f"{self.session_id}Terminating call")
        self.call.terminated = True

    def set_log_level(self, level):
        """Sets the logging level for this session and its components."""
        logging.getLogger().setLevel(level)
        logging.info(f"{self.session_id}Set logging level to {logging._levelToName.get(level, level)}")
        
        self.debug = (level == logging.DEBUG)
        self.audio_processor.debug = self.debug
        self.vad_processor.debug = self.debug # VADProcessor also has a debug flag
        if hasattr(self, 'tts_processor'): 
            self.tts_processor.debug = self.debug

    async def _process_final_vad_buffer(self):
        """Process final VAD buffer before closing, attempting to get a last transcript."""
        original_on_partial = None
        original_on_final = None
        try:
            is_speech, buffer_bytes = await self.vad_processor.process_final_buffer()
            
            if buffer_bytes and self.vosk_client.is_connected: 
                buffer_seconds = len(buffer_bytes) / (2 * self.target_sample_rate)  
                last_partial_from_final_buffer = None
                
                original_on_partial = self.transcript_handler.on_partial_transcript
                original_on_final = self.transcript_handler.on_final_transcript
                
                async def final_buffer_partial_callback(text: str):
                    nonlocal last_partial_from_final_buffer
                    last_partial_from_final_buffer = text
                    if self.debug:
                        logging.debug(f"{self.session_id}Partial from final VAD buffer: {text[:80]}...")

                self.transcript_handler.on_partial_transcript = final_buffer_partial_callback

                if is_speech:
                    if self.debug:
                        logging.debug(f"{self.session_id}Sending {len(buffer_bytes)} bytes from final VAD buffer to STT.")
                    await self.vosk_client.send_audio(buffer_bytes)
                
                wait_time = min(buffer_seconds * 0.4 + 0.2, 1.0) 
                if self.debug:
                    logging.debug(f"{self.session_id}Waiting {wait_time:.2f}s for potential transcript from final VAD buffer.")
                await asyncio.sleep(wait_time)
                
                if last_partial_from_final_buffer:
                    logging.info(f"{self.session_id}Using last partial from final VAD buffer as definitive final transcript: {last_partial_from_final_buffer[:80]}...")
                    self.transcript_handler.last_final_transcript = last_partial_from_final_buffer
                elif self.debug:
                    logging.debug(f"{self.session_id}No new partial transcript received from final VAD buffer send.")
                
            elif buffer_bytes and not self.vosk_client.is_connected:
                logging.warning(f"{self.session_id}Final VAD buffer had data, but Vosk client is not connected. Cannot process.")
            elif self.debug:
                logging.debug(f"{self.session_id}No data in final VAD buffer or client not connected.")

        except Exception as e:
            logging.error(f"{self.session_id}Error processing final VAD buffer: {e}", exc_info=True)
        finally:
            # Restore original transcript handlers
            if original_on_partial is not None and hasattr(self.transcript_handler, 'on_partial_transcript'):
                 self.transcript_handler.on_partial_transcript = original_on_partial 
            if original_on_final is not None and hasattr(self.transcript_handler, 'on_final_transcript'):
                 self.transcript_handler.on_final_transcript = original_on_final 


    def get_final_transcript(self) -> str:
        """Returns the last recognized final transcript text."""
        return self.transcript_handler.get_final_transcript()

    async def _handle_final_transcript(self, final_text: str):
        """
        Handles final transcript: Gets (simulated) LLM response, then calls TTSProcessor
        to generate and queue audio. Also manages VAD state reset.
        """
        logging.info(f"{self.session_id}SmartSpeech: Final transcript for LLM/TTS: '{final_text}'")
        
        # 1. Get LLM Response (Simulated)
        # PLACEHOLDER: Replace with actual LLM call
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
        llm_response_text = random.choice(turkish_sentences)
        logging.info(f"{self.session_id}SmartSpeech: Simulated LLM response: '{llm_response_text}'")

        if not self.bypass_vad:
            self.vad_processor.reset_vad_state(preserve_buffer=False)
            logging.info(f"{self.session_id}SmartSpeech: VAD state reset after LLM response, before TTS processing")
        
        if self.tts_processor:
            try:
                await self.tts_processor.generate_and_queue_tts_audio(llm_response_text)
            except Exception as e_tts_gen:
                logging.error(f"{self.session_id}SmartSpeech: Error during TTS generation call: {e_tts_gen}", exc_info=True)
        else:
            logging.error(f"{self.session_id}SmartSpeech: TTSProcessor not initialized, cannot generate TTS.")

[end of src/speech_session_vosk.py]
