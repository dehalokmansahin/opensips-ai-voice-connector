import asyncio
import logging
import time
import torch
from typing import Optional, Tuple

# Import VADDetector from the same directory (speech_processing)
from .vad_detector import VADDetector

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
                 speech_detection_threshold: int = 1,
                 silence_detection_threshold: int = 1,
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

        self.consecutive_speech_packets = 0
        self.consecutive_silence_packets = 0
        self.speech_start_time = 0.0
        self.last_speech_activity_time = time.time()

        if not preserve_buffer:
            self._vad_buffer.clear()
            self._vad_buffer_size_samples = 0
            self._last_buffer_flush_time = time.time()

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

            buffer_duration_ms = (self._vad_buffer_size_samples / self.target_sample_rate) * 1000

            if buffer_duration_ms >= self.vad_buffer_chunk_ms:
                if self.debug:
                    logging.debug(
                        f"{self.session_id}VAD buffer reached {buffer_duration_ms:.2f}ms "
                        f"(threshold {self.vad_buffer_chunk_ms}ms), processing for VAD."
                    )
                is_speech_decision, processed_chunk_bytes = await self._process_buffer()
                return True, is_speech_decision, processed_chunk_bytes

            return False, False, None

    async def _process_buffer(self) -> Tuple[bool, bytes]:
        """
        Processes the current VAD buffer using the VAD detector.
        Returns:
            A tuple containing:
            - is_speech_in_current_chunk: Whether speech was detected in this chunk
            - buffer_bytes: The audio bytes that were processed (for forwarding to STT)
        """
        if self.debug:
            logging.debug(f"{self.session_id}VAD processing buffer of {len(self._vad_buffer)} bytes.")

        # Process buffer through helper methods
        buffer_bytes, audio_tensor = self._prepare_audio_tensor(self._vad_buffer)
        self._clear_vad_buffer()
        is_speech_in_current_chunk = self.vad.is_speech(audio_tensor)
        current_time = time.time()
        self._update_vad_state(is_speech_in_current_chunk, current_time)
        send_chunk_to_stt = self._should_send_to_stt(is_speech_in_current_chunk)

        # Debug final decision
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
        # This timeout should only apply if speech was previously active (speech_start_time is set)
        # and now we are in a period of silence (speech_active is False).
        # last_speech_activity_time marks the end of the last detected speech chunk.
        if self.speech_active or self.speech_start_time == 0.0 or self.last_speech_activity_time == 0.0:
            return False

        current_time = time.time()
        # Measure silence from the last moment speech activity was detected
        silence_duration = current_time - self.last_speech_activity_time
        return silence_duration > self.silence_timeout_seconds

    async def process_final_buffer(self) -> Tuple[bool, Optional[bytes]]:
        """
        Processes any remaining audio in the VAD buffer.
        Returns:
            A tuple (is_speech, processed_buffer_bytes).
        """
        async with self._vad_buffer_locks:
            if len(self._vad_buffer) > 0:
                if self.debug:
                    buffer_duration_ms = (self._vad_buffer_size_samples / self.target_sample_rate) * 1000
                    logging.debug(
                        f"{self.session_id}Processing remaining VAD buffer: "
                        f"{buffer_duration_ms:.2f} ms ({self._vad_buffer_size_samples} samples)."
                    )
                is_speech_decision, processed_chunk_bytes = await self._process_buffer()
                return is_speech_decision, processed_chunk_bytes

        if self.debug:
            logging.debug(f"{self.session_id}No remaining VAD buffer to process.")
        return False, None

    # New private helper methods for buffer processing and VAD state logic
    def _prepare_audio_tensor(self, buffer: bytearray) -> Tuple[bytes, torch.Tensor]:
        """Copy VAD buffer to bytes and convert to normalized float tensor."""
        buffer_bytes = bytes(buffer)
        buffer_copy = bytearray(buffer_bytes)
        audio_tensor = torch.frombuffer(buffer_copy, dtype=torch.int16).float() / 32768.0
        return buffer_bytes, audio_tensor

    def _clear_vad_buffer(self) -> None:
        """Clear the VAD buffer and reset its metadata."""
        self._vad_buffer.clear()
        self._vad_buffer_size_samples = 0
        self._last_buffer_flush_time = time.time()

    def _update_vad_state(self, is_speech: bool, current_time: float) -> None:
        """Update speech/silence counters and handle state transitions."""
        if is_speech:
            self.consecutive_speech_packets += 1
            self.consecutive_silence_packets = 0
            self.last_speech_activity_time = current_time
            if self.speech_start_time == 0.0:
                self.speech_start_time = current_time
            if self.debug:
                logging.debug(
                    f"{self.session_id}VAD detected speech in chunk (consecutive_speech={self.consecutive_speech_packets})"
                )
            if self.consecutive_speech_packets >= self.speech_detection_threshold and not self.speech_active:
                self.speech_active = True
                self.speech_start_time = current_time
                logging.info(
                    f"{self.session_id}Speech started (VAD active) after {self.consecutive_speech_packets} consecutive speech chunk(s)."
                )
        else:
            self.consecutive_silence_packets += 1
            self.consecutive_speech_packets = 0
            if self.debug and self.speech_active:
                logging.debug(
                    f"{self.session_id}VAD detected silence in chunk while speech was active (consecutive_silence={self.consecutive_silence_packets})"
                )
            if self.consecutive_silence_packets >= self.silence_detection_threshold and self.speech_active:
                self.speech_active = False
                self.speech_start_time = 0.0
                logging.info(
                    f"{self.session_id}Speech ended (VAD inactive) after {self.consecutive_silence_packets} consecutive silence chunk(s)."
                )

    def _should_send_to_stt(self, is_speech: bool) -> bool:
        """Determine whether to send this chunk to STT."""
        return is_speech or self.speech_active
