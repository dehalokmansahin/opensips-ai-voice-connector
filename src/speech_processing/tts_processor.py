import asyncio
import audioop
import torch
import torchaudio
import logging
import time
from queue import Queue, Empty
from typing import Optional, Any, Callable, Dict, List, Tuple

from .tts_engine_base import TTSEngineBase

class TTSProcessor:
    """
    Handles Text-to-Speech (TTS) audio generation, processing, and queuing.
    This class is now engine-agnostic, using TTSEngineBase for synthesis.

    Audio Sample Rate Management:
    - `tts_input_rate`: This is the native sample rate at which the underlying TTS
      engine (an implementation of TTSEngineBase) generates audio. For example,
      Piper default is 22050 Hz.
    - `tts_target_output_rate`: This is the sample rate required for the RTP stream,
      typically 8000 Hz for PCMU (G.711 ulaw) codec. Audio from the TTS engine
      is resampled to this rate by `self.rtp_resampler` before being encoded
      to PCMU and queued for RTP.
    - VAD Detector's Sample Rate (`self.vad_detector.sample_rate`): For effective
      echo cancellation, the AdaptiveVADDetector needs to process the TTS audio
      at its own configured sample rate (e.g., 16000 Hz). Audio from the TTS
      engine is resampled to this rate by `self.vad_resampler` before being
      registered with the VAD via `vad_detector.register_tts_audio()`.
    """
    def __init__(self,
                 rtp_queue: Queue,
                 tts_engine: TTSEngineBase,
                 tts_voice_id: str, # Voice ID for the TTS engine
                 tts_input_rate: int, # Expected sample rate from TTSEngineBase
                 tts_target_output_rate: int = 8000, # Target sample rate for RTP (e.g., PCMU)
                 session_id: str = "",
                 debug: bool = False,
                 audio_queue: asyncio.Queue = None, # Note: audio_queue is not used in current implementation
                 on_tts_start: Callable[[], None] = None,
                 on_tts_end: Callable[[], None] = None,
                 vad_detector: Optional[Any] = None,
                 synthesis_timeout_seconds: float = 30.0): # Added synthesis_timeout_seconds
        """
        Initializes the TTSProcessor.

        Args:
            rtp_queue: The queue where processed TTS audio packets (PCMU) will be placed.
            tts_engine: An instance of a TTSEngineBase implementation.
            tts_voice_id: The voice identifier to be used by the TTS engine.
            tts_input_rate: The sample rate of audio provided by the tts_engine.
            tts_target_output_rate: The target sample rate for the output audio (e.g., 8000 Hz for PCMU).
            session_id: An identifier for the current session, used for contextual logging.
            debug: If True, enables detailed debug logging for TTS processing.
            audio_queue: An asyncio.Queue where generated audio chunks will be placed. (Currently unused)
            on_tts_start: Optional callback function to be called when TTS generation starts.
            on_tts_end: Optional callback function to be called when TTS generation ends.
            vad_detector: Optional VAD detector to register TTS audio for echo cancellation.
            synthesis_timeout_seconds: Overall timeout for the entire TTS synthesis stream.
        """
        self.rtp_queue: Queue = rtp_queue
        self.tts_engine: TTSEngineBase = tts_engine
        self.tts_voice_id: str = tts_voice_id
        self.tts_input_rate: int = tts_input_rate # e.g., 22050 for Piper (native rate from TTS engine)
        self.tts_target_output_rate: int = tts_target_output_rate # Rate for RTP (e.g., 8000 Hz for PCMU)
        self.session_id: str = session_id
        self.debug: bool = debug
        self.audio_queue: asyncio.Queue = audio_queue # Currently unused
        self.on_tts_start: Optional[Callable[[], None]] = on_tts_start
        self.on_tts_end: Optional[Callable[[], None]] = on_tts_end
        self.vad_detector: Optional[Any] = vad_detector
        self.synthesis_timeout_seconds: float = synthesis_timeout_seconds

        # Resampler for RTP output (e.g., to 8kHz for PCMU)
        self.rtp_resampler: Optional[torchaudio.transforms.Resample] = None
        if self.tts_input_rate != self.tts_target_output_rate:
            self.rtp_resampler = torchaudio.transforms.Resample(
                orig_freq=self.tts_input_rate,
                new_freq=self.tts_target_output_rate
            )
            logging.info(f"{self.session_id}TTSProcessor: RTP Resampler initialized: {self.tts_input_rate}Hz -> {self.tts_target_output_rate}Hz")

        # Resampler for VAD echo cancellation (to VAD's operating sample rate)
        self.vad_resampler: Optional[torchaudio.transforms.Resample] = None
        if self.vad_detector and hasattr(self.vad_detector, 'sample_rate'):
            if self.tts_input_rate != self.vad_detector.sample_rate:
                self.vad_resampler = torchaudio.transforms.Resample(
                    orig_freq=self.tts_input_rate,
                    new_freq=self.vad_detector.sample_rate
                )
                logging.info(f"{self.session_id}TTSProcessor: VAD Resampler initialized: {self.tts_input_rate}Hz -> {self.vad_detector.sample_rate}Hz")
        elif self.vad_detector:
            logging.warning(f"{self.session_id}TTSProcessor: VAD detector provided but missing 'sample_rate' attribute. Cannot initialize VAD resampler.")


        self.tts_processing_lock: asyncio.Lock = asyncio.Lock()
        self._interrupt_event: asyncio.Event = asyncio.Event()

        log_message = (
            f"{self.session_id}TTSProcessor initialized: Voice='{self.tts_voice_id}', "
            f"InputRate={self.tts_input_rate}Hz, TargetRateRTP={self.tts_target_output_rate}Hz"
        )
        if self.vad_detector and hasattr(self.vad_detector, 'sample_rate'):
            log_message += f", TargetRateVAD={self.vad_detector.sample_rate}Hz"
        logging.info(log_message)

    def interrupt(self) -> None:
        if self.debug:
            logging.debug(f"{self.session_id}TTSProcessor: Interrupt signal received.")
        self._interrupt_event.set()

        drained_count = 0
        while not self.rtp_queue.empty():
            try:
                self.rtp_queue.get_nowait()
                drained_count += 1
            except Empty:
                break
        if drained_count > 0 and self.debug:
            logging.debug(f"{self.session_id}TTSProcessor: Drained {drained_count} packets from RTP queue during interruption.")

    def _tensor_from_audio_chunk(self, audio_chunk: bytes) -> torch.Tensor:
        """Convert PCM s16le bytes to normalized float tensor in [-1.0,1.0]."""
        buffer = bytearray(audio_chunk)
        return torch.frombuffer(buffer, dtype=torch.int16).float() / 32768.0

    def _resample_for_rtp_and_clamp(self, tensor: torch.Tensor) -> torch.Tensor:
        """Resample to RTP target rate if needed and clamp values to [-1,1]."""
        if self.rtp_resampler:
            tensor = self.rtp_resampler(tensor.unsqueeze(0)).squeeze(0)
        return torch.clamp(tensor, -1.0, 1.0)

    def _resample_for_vad(self, tensor: torch.Tensor) -> Optional[torch.Tensor]:
        """Resample to VAD sample rate if needed."""
        if not self.vad_detector or not hasattr(self.vad_detector, 'sample_rate'):
            return None # Or return original tensor if VAD should process at input rate

        if self.vad_resampler:
            return self.vad_resampler(tensor.unsqueeze(0)).squeeze(0)
        elif self.tts_input_rate == self.vad_detector.sample_rate: # No resampling needed
            return tensor
        return None # Should not happen if vad_resampler logic is correct

    def _tensor_to_pcm_s16le_bytes(self, tensor: torch.Tensor) -> bytes:
        """Convert normalized float tensor to raw PCM s16le bytes."""
        return (tensor * 32767.0).to(torch.int16).numpy().tobytes()

    def _pcm_s16le_to_ulaw(self, pcm_bytes: bytes) -> bytes:
        """Convert raw PCM s16le bytes to μ-law (G.711 u-law) bytes."""
        return audioop.lin2ulaw(pcm_bytes, 2)

    async def _queue_pcmu_chunks(self, cumulative_pcmu_bytes: bytearray, chunk_size: int) -> None:
        """Slice cumulative μ-law bytes into fixed-size RTP payloads and enqueue them."""
        while len(cumulative_pcmu_bytes) >= chunk_size:
            if self._interrupt_event.is_set():
                raise asyncio.CancelledError("TTS interrupted by user (before RTP queueing)")
            payload = cumulative_pcmu_bytes[:chunk_size]
            self.rtp_queue.put_nowait(bytes(payload))
            if self.debug:
                logging.debug(f"{self.session_id}TTSProcessor: Queued {len(payload)} bytes for RTP.")
            del cumulative_pcmu_bytes[:chunk_size]
            await asyncio.sleep(0.001)

    async def generate_and_queue_tts_audio(self, text: str, metadata: Optional[Dict[str, Any]] = None) -> bool:
        """
        Generates TTS audio from the given text and queues it to the RTP queue.

        Args:
            text: The text to be converted to speech.
            metadata: Optional metadata for the TTS generation.

        Returns:
            bool: True if the TTS generation was successful, False otherwise.
        """
        self._interrupt_event.clear()
        
        if self._interrupt_event.is_set():
            logging.info(f"{self.session_id}TTSProcessor: TTS generation cancelled at entry due to prior interrupt signal.")
            return False

        if metadata is None:
            metadata = {}
        
        generation_id = metadata.get('generation_id', 'unknown')
        logging.info(f"{self.session_id}TTSProcessor: Starting TTS generation (ID:{generation_id}) for text: '{text}'")
        
        if self.on_tts_start:
            try:
                self.on_tts_start()
            except Exception as e:
                logging.error(f"{self.session_id}TTSProcessor: Error in TTS start callback: {e}", exc_info=True)

        try:
            tts_success = False
            engine_was_connected_by_us = False # Track if we initiated the connection

            async def synthesis_stream_processing():
                nonlocal tts_success, engine_was_connected_by_us # Allow modification
                if not self.tts_engine.is_connected():
                    logging.info(f"{self.session_id}TTSProcessor: TTS engine not connected. Attempting to connect.")
                    if not await self.tts_engine.connect():
                        logging.error(f"{self.session_id}TTSProcessor: Failed to connect TTS engine.")
                        # tts_success remains False, will be returned
                        return
                    engine_was_connected_by_us = True

                cumulative_pcmu_bytes = bytearray()
                rtp_chunk_size_bytes = 160

                async for audio_chunk_from_engine in self.tts_engine.synthesize_speech(
                    text=text,
                    voice=self.tts_voice_id,
                    output_format="pcm_s16le"
                ):
                    if self._interrupt_event.is_set():
                        logging.info(f"{self.session_id}TTSProcessor: Interruption detected during audio stream.")
                        raise asyncio.CancelledError("TTS interrupted by user (audio stream)")

                    input_tensor = self._tensor_from_audio_chunk(audio_chunk_from_engine)

                    if self.vad_detector and hasattr(self.vad_detector, 'register_tts_audio'):
                        vad_chunk_tensor = self._resample_for_vad(input_tensor.clone())
                        if vad_chunk_tensor is not None:
                            try:
                                self.vad_detector.register_tts_audio(vad_chunk_tensor)
                                if self.debug:
                                    logging.debug(f"{self.session_id}TTSProcessor: Registered TTS chunk with VAD (len: {vad_chunk_tensor.shape[0]} samples).")
                            except Exception as e:
                                logging.warning(f"{self.session_id}TTSProcessor: Failed to register TTS audio chunk with VAD: {e}")
                        elif self.debug:
                                logging.debug(f"{self.session_id}TTSProcessor: VAD chunk tensor is None, skipping VAD registration for this chunk.")

                    rtp_processed_tensor = self._resample_for_rtp_and_clamp(input_tensor)
                    pcm_s16le_bytes_for_rtp = self._tensor_to_pcm_s16le_bytes(rtp_processed_tensor)
                    pcmu_chunk_bytes = self._pcm_s16le_to_ulaw(pcm_s16le_bytes_for_rtp)
                    cumulative_pcmu_bytes.extend(pcmu_chunk_bytes)
                    await self._queue_pcmu_chunks(cumulative_pcmu_bytes, rtp_chunk_size_bytes)

                if not self._interrupt_event.is_set() and cumulative_pcmu_bytes:
                    final_payload = bytes(cumulative_pcmu_bytes).ljust(rtp_chunk_size_bytes, b'\xff')
                    self.rtp_queue.put_nowait(final_payload)
                    if self.debug:
                        logging.debug(f"{self.session_id}TTSProcessor: Queued final {len(final_payload)} bytes (padded).")

                tts_success = True # Mark success if loop completes without cancellation

            # Wrap the actual synthesis streaming part with an overall timeout
            try:
                await asyncio.wait_for(synthesis_stream_processing(), timeout=self.synthesis_timeout_seconds)
            except asyncio.TimeoutError:
                logging.warning(f"{self.session_id}TTSProcessor: Overall TTS synthesis timed out after {self.synthesis_timeout_seconds}s for text: '{text[:70]}...'")
                tts_success = False # Ensure success is false on timeout
                # Interrupt event might also be set here if we want to signal other parts
                self._interrupt_event.set() # Signal interruption due to timeout
            except asyncio.CancelledError: # Propagated from synthesis_stream_processing
                logging.info(f"{self.session_id}TTSProcessor: TTS generation task was cancelled (outer).")
                tts_success = False
                self._interrupt_event.set() # Ensure interrupt is set
            except Exception as e: # Other errors from synthesis_stream_processing
                logging.error(f"{self.session_id}TTSProcessor: Error during TTS processing (outer): {e}", exc_info=True)
                tts_success = False
            finally: # This finally is for the synthesis_stream_processing block
                if engine_was_connected_by_us and self.tts_engine.is_connected():
                    logging.info(f"{self.session_id}TTSProcessor: Disconnecting TTS engine as it was connected by this process.")
                    await self.tts_engine.disconnect()
                if self._interrupt_event.is_set():
                     logging.info(f"{self.session_id}TTSProcessor: Finished stream processing. Interruption signal was active.")

            # Logging based on outcome
            if tts_success and not self._interrupt_event.is_set():
                logging.info(f"{self.session_id}TTSProcessor: Successfully generated and queued: \"{text[:70]}...\"")
            elif self._interrupt_event.is_set() and not tts_success: # Typically timeout or cancellation
                 logging.info(f"{self.session_id}TTSProcessor: Generation failed or was interrupted for: \"{text[:70]}...\"")
            elif not tts_success: # General failure not covered by interrupt
                 logging.warning(f"{self.session_id}TTSProcessor: Generation failed without explicit interrupt for: \"{text[:70]}...\"")

        finally: # This is the outermost finally for generate_and_queue_tts_audio
            if self.vad_detector is not None and hasattr(self.vad_detector, 'tts_finished'):
                try:
                    self.vad_detector.tts_finished()
                    if self.debug:
                        logging.debug(f"{self.session_id}TTSProcessor: Notified VAD detector that TTS (all chunks) has finished.")
                except Exception as e:
                    logging.warning(f"{self.session_id}TTSProcessor: Failed to notify VAD about TTS completion: {e}")

            if self.on_tts_end:
                try:
                    self.on_tts_end()
                except Exception as e:
                    logging.error(f"{self.session_id}TTSProcessor: Error in TTS end callback: {e}", exc_info=True)
                    
            if self.vad_detector is not None and hasattr(self.vad_detector, 'tts_finished'):
                try:
                    # Logging for tts_finished is now inside the try-except block above.
                    pass # Kept for structure, but action moved up.

        return tts_success
