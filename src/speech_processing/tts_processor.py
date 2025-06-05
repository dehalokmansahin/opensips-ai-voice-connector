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
    """
    def __init__(self,
                 rtp_queue: Queue,
                 tts_engine: TTSEngineBase,
                 tts_voice_id: str, # Voice ID for the TTS engine
                 tts_input_rate: int, # Expected sample rate from TTSEngineBase
                 tts_target_output_rate: int = 8000,
                 session_id: str = "",
                 debug: bool = False,
                 audio_queue: asyncio.Queue = None,
                 on_tts_start: Callable[[], None] = None,
                 on_tts_end: Callable[[], None] = None,
                 vad_detector: Optional[Any] = None):
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
            audio_queue: An asyncio.Queue where generated audio chunks will be placed.
            on_tts_start: Optional callback function to be called when TTS generation starts.
            on_tts_end: Optional callback function to be called when TTS generation ends.
            vad_detector: Optional VAD detector to register TTS audio for echo cancellation.
        """
        self.rtp_queue: Queue = rtp_queue
        self.tts_engine: TTSEngineBase = tts_engine
        self.tts_voice_id: str = tts_voice_id
        self.tts_input_rate: int = tts_input_rate # e.g., 22050 for Piper
        self.tts_target_output_rate: int = tts_target_output_rate
        self.session_id: str = session_id
        self.debug: bool = debug
        self.audio_queue: asyncio.Queue = audio_queue
        self.on_tts_start: Optional[Callable[[], None]] = on_tts_start
        self.on_tts_end: Optional[Callable[[], None]] = on_tts_end
        self.vad_detector: Optional[Any] = vad_detector

        self.tts_resampler: Optional[torchaudio.transforms.Resample] = None
        if self.tts_input_rate != self.tts_target_output_rate:
            self.tts_resampler = torchaudio.transforms.Resample(
                orig_freq=self.tts_input_rate,
                new_freq=self.tts_target_output_rate
            )
            logging.info(f"{self.session_id}TTSProcessor: Resampler initialized: {self.tts_input_rate}Hz -> {self.tts_target_output_rate}Hz")

        self.tts_processing_lock: asyncio.Lock = asyncio.Lock()
        self._interrupt_event: asyncio.Event = asyncio.Event()

        logging.info(
            f"{self.session_id}TTSProcessor initialized: Voice='{self.tts_voice_id}', "
            f"InputRate={self.tts_input_rate}Hz, TargetRate={self.tts_target_output_rate}Hz"
        )

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

    def _resample_and_clamp(self, tensor: torch.Tensor) -> torch.Tensor:
        """Resample to target rate if needed and clamp values to [-1,1]."""
        if self.tts_resampler:
            tensor = self.tts_resampler(tensor.unsqueeze(0)).squeeze(0)
        return torch.clamp(tensor, -1.0, 1.0)

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
            engine_was_connected_by_us = False
            try:
                if not self.tts_engine.is_connected():
                    logging.info(f"{self.session_id}TTSProcessor: TTS engine not connected. Attempting to connect.")
                    if not await self.tts_engine.connect():
                        logging.error(f"{self.session_id}TTSProcessor: Failed to connect TTS engine.")
                        return False
                    engine_was_connected_by_us = True

                cumulative_pcmu_bytes = bytearray()
                rtp_chunk_size_bytes = 160

                # Requesting raw PCM s16le from the engine. Resampling is handled here.
                async for audio_chunk_from_engine in self.tts_engine.synthesize_speech(
                    text=text,
                    voice=self.tts_voice_id,
                    output_format="pcm_s16le" # Standard format for further processing
                ):
                    if self._interrupt_event.is_set():
                        logging.info(f"{self.session_id}TTSProcessor: Interruption detected during audio stream.")
                        raise asyncio.CancelledError("TTS interrupted by user (audio stream)")

                    # Process raw audio chunk through helper methods
                    input_tensor = self._tensor_from_audio_chunk(audio_chunk_from_engine)
                    processed_tensor = self._resample_and_clamp(input_tensor)
                    pcm_s16le_bytes = self._tensor_to_pcm_s16le_bytes(processed_tensor)
                    pcmu_chunk_bytes = self._pcm_s16le_to_ulaw(pcm_s16le_bytes)
                    cumulative_pcmu_bytes.extend(pcmu_chunk_bytes)

                    # Split and enqueue RTP-sized chunks
                    await self._queue_pcmu_chunks(cumulative_pcmu_bytes, rtp_chunk_size_bytes)

                if not self._interrupt_event.is_set() and cumulative_pcmu_bytes:
                    final_payload = bytes(cumulative_pcmu_bytes).ljust(rtp_chunk_size_bytes, b'\xff')
                    self.rtp_queue.put_nowait(final_payload)
                    if self.debug:
                        logging.debug(f"{self.session_id}TTSProcessor: Queued final {len(final_payload)} bytes (padded).")

                tts_success = True

            except asyncio.CancelledError:
                logging.info(f"{self.session_id}TTSProcessor: TTS generation task was cancelled.")
                tts_success = False
                self._interrupt_event.set()
            except Exception as e:
                logging.error(f"{self.session_id}TTSProcessor: Error during TTS processing: {e}", exc_info=True)
                tts_success = False
            finally:
                if engine_was_connected_by_us and self.tts_engine.is_connected():
                    logging.info(f"{self.session_id}TTSProcessor: Disconnecting TTS engine as it was connected by this process.")
                    await self.tts_engine.disconnect()

                if self._interrupt_event.is_set():
                     logging.info(f"{self.session_id}TTSProcessor: Finished. Interruption signal was active.")

            if tts_success and not self._interrupt_event.is_set():
                logging.info(f"{self.session_id}TTSProcessor: Successfully generated and queued: \"{text[:70]}...\"")
            elif self._interrupt_event.is_set() and not tts_success : # Already logged CancelledError
                logging.info(f"{self.session_id}TTSProcessor: Generation interrupted for: \"{text[:70]}...\"")
            elif not tts_success:
                 logging.warning(f"{self.session_id}TTSProcessor: Generation failed for: \"{text[:70]}...\"")

            if tts_success and self.vad_detector is not None and hasattr(self.vad_detector, 'register_tts_audio'):
                try:
                    self.vad_detector.register_tts_audio(processed_tensor)
                    logging.debug(f"{self.session_id}TTSProcessor: Registered TTS audio with VAD detector for echo cancellation")
                except Exception as e:
                    logging.warning(f"{self.session_id}TTSProcessor: Failed to register TTS audio with VAD: {e}")

        finally:
            if self.on_tts_end:
                try:
                    self.on_tts_end()
                except Exception as e:
                    logging.error(f"{self.session_id}TTSProcessor: Error in TTS end callback: {e}", exc_info=True)
                    
            if self.vad_detector is not None and hasattr(self.vad_detector, 'tts_finished'):
                try:
                    self.vad_detector.tts_finished()
                    logging.debug(f"{self.session_id}TTSProcessor: Notified VAD detector that TTS has finished")
                except Exception as e:
                    logging.warning(f"{self.session_id}TTSProcessor: Failed to notify VAD about TTS completion: {e}")

        return tts_success
