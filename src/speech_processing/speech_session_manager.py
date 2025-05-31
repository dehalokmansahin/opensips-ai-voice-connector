import asyncio
import json
import logging
import time
import random # For simulated LLM responses (placeholder)
import audioop # For mu-law encoding/decoding if needed (TTS output to PCMU)
from queue import Empty, Queue
from typing import Any, Callable, Awaitable, Optional, Tuple

# Framework /
import torch
import torchaudio
import websockets # Still needed by engines, but not directly by SpeechSessionManager

# Project-specific imports (relative paths)
from ..ai import AIEngine
from ..config import Config
from ..codec import get_codecs, PCMU, UnsupportedCodec

from .audio_processor import AudioProcessor
from .vad_detector import VADDetector
from .vad_processor import VADProcessor
from .transcript_handler import TranscriptHandler
from .tts_processor import TTSProcessor
from .stt_engine_base import STTEngineBase
from .tts_engine_base import TTSEngineBase
# Specific engine implementations are not directly imported here, they are passed in.
# from .vosk_stt_engine import VoskSTTEngine
# from .piper_tts_engine import PiperTTSEngine


class SpeechSessionManager(AIEngine):
    """
    Orchestrates full-duplex speech interaction using injected STT and TTS engines.

    This class, derived from `AIEngine`, manages the entire lifecycle of a speech
    session. It initializes and coordinates helper classes for audio input processing
    (`AudioProcessor`), voice activity detection (`VADProcessor`), STT transcript
    handling (`TranscriptHandler`), and TTS audio generation/playback (`TTSProcessor`).
    The actual STT and TTS operations are delegated to engine instances provided
    during initialization, which must adhere to STTEngineBase and TTSEngineBase interfaces.
    """

    def __init__(self,
                 call: Any,
                 cfg: Config,
                 stt_engine: STTEngineBase,
                 tts_engine: TTSEngineBase,
                 tts_voice_id: str, # Added: Voice ID for TTS
                 tts_input_rate: int # Added: Expected input sample rate for TTSProcessor from tts_engine
                 ):
        """
        Initializes the SpeechSessionManager.

        Args:
            call: The call object, with `rtp` queue, `sdp`, `client_addr`/`port`.
            cfg: The application configuration object.
            stt_engine: An initialized STT engine instance (implementing STTEngineBase).
            tts_engine: An initialized TTS engine instance (implementing TTSEngineBase).
            tts_voice_id: The voice ID to be used for TTS synthesis.
            tts_input_rate: The sample rate of audio produced by the tts_engine (e.g., 22050 for Piper).
        """
        self.cfg_root: Config = cfg # Store root config
        self.session_cfg: Config = Config.get("SpeechSessionManager", cfg, Config.get("SmartSpeech", cfg)) # Use "SpeechSessionManager" or fallback to "SmartSpeech"

        self.stt_engine: STTEngineBase = stt_engine
        self.tts_engine: TTSEngineBase = tts_engine
        # Store tts_voice_id and tts_input_rate for TTSProcessor initialization
        self.tts_voice_id_cfg: str = tts_voice_id
        self.tts_input_rate_cfg: int = tts_input_rate

        self.b2b_key: Optional[str] = call.b2b_key if hasattr(call, 'b2b_key') else None
        self.session_id: str = f"[Session:{self.b2b_key}] " if self.b2b_key else "[Session:Unknown] "

        self.rtp_queue: Queue = call.rtp

        self._load_config()
        self._init_components(call)

        self.receive_task: Optional[asyncio.Task] = None
        self.tts_task: Optional[asyncio.Task] = None
        self.timeout_monitor_task: Optional[asyncio.Task] = None
        self._is_closing: bool = False
        self.is_tts_active: bool = False

        self.barge_in_speech_start_time: float = 0.0
        self.barge_in_pending: bool = False

        self._setup_logging()

        logging.info(f"{self.session_id}SpeechSessionManager initialized. VAD Bypass: {self.bypass_vad}, Barge-in threshold: {self.barge_in_threshold_seconds}s")

    def _load_config(self) -> None:
        """Loads session configurations from the application config."""
        # STT general settings (engine specific settings are handled by the engine itself)
        self.target_sample_rate: int = int(self.session_cfg.get("stt_target_sample_rate", "sample_rate", 16000))
        self.stt_channels: int = self.session_cfg.get("stt_channels", "channels", 1)
        self.send_eof_to_stt: bool = self.session_cfg.get("stt_send_eof", "send_eof", True)
        self.debug: bool = self.session_cfg.get("debug", "debug", False)

        # VAD settings
        self.bypass_vad: bool = self.session_cfg.get("bypass_vad", "bypass_vad", False)
        self.vad_threshold: float = self.session_cfg.get("vad_threshold", "vad_threshold", 0.25)
        self.vad_min_speech_ms: int = self.session_cfg.get("vad_min_speech_ms", "vad_min_speech_ms", 150)
        self.vad_min_silence_ms: int = self.session_cfg.get("vad_min_silence_ms", "vad_min_silence_ms", 450)
        self.vad_buffer_chunk_ms: int = self.session_cfg.get("vad_buffer_chunk_ms", "vad_buffer_chunk_ms", 600)
        self.speech_detection_threshold: int = self.session_cfg.get("speech_detection_threshold", "speech_detection_threshold", 1)
        self.silence_detection_threshold: int = self.session_cfg.get("silence_detection_threshold", "silence_detection_threshold", 1)

        self.speech_timeout_seconds: float = self.session_cfg.get("speech_timeout_seconds", "speech_timeout_seconds", 10.0)
        self.silence_timeout_seconds: float = self.session_cfg.get("silence_timeout_seconds", "silence_timeout_seconds", 3.0)
        self.stale_partial_timeout_seconds: float = self.session_cfg.get("stale_partial_timeout_seconds", "stale_partial_timeout_seconds", 2.5)
        self.barge_in_threshold_seconds: float = self.session_cfg.get("barge_in_threshold_seconds", "barge_in_threshold_seconds", 1.5)

        # TTS general settings (engine specific settings are handled by the engine itself)
        # self.tts_voice_cfg is passed in __init__
        self.tts_target_output_rate_cfg: int = int(self.session_cfg.get("tts_target_output_rate", "tts_target_output_rate", 8000))

        logging.info(f"{self.session_id}STT Target Rate: {self.target_sample_rate}Hz, Channels: {self.stt_channels}")
        logging.info(
            f"{self.session_id}TTS Config: Voice={self.tts_voice_id_cfg}, InputRate (from engine)={self.tts_input_rate_cfg}Hz, Target Output Rate={self.tts_target_output_rate_cfg}Hz"
        )
        # VAD, Timeout, Barge-in logs remain similar to before.

    def _init_components(self, call: Any) -> None:
        """Initializes all processing components."""
        self.call: Any = call
        self.client_addr: Tuple[str, int] = call.client_addr
        self.client_port: int = call.client_port
        self.codec: PCMU = self.choose_codec(call.sdp)

        self.audio_processor: AudioProcessor = AudioProcessor(
            target_sample_rate=self.target_sample_rate, # For STT
            debug=self.debug,
            session_id=self.session_id
        )

        vad_detector_instance = VADDetector( # VAD still uses its own model
            sample_rate=self.target_sample_rate, # Operates on STT-ready audio
            threshold=self.vad_threshold,
            min_speech_duration_ms=self.vad_min_speech_ms,
            min_silence_duration_ms=self.vad_min_silence_ms
        )

        self.vad_processor: VADProcessor = VADProcessor(
            vad_detector=vad_detector_instance,
            target_sample_rate=self.target_sample_rate,
            vad_buffer_chunk_ms=self.vad_buffer_chunk_ms,
            speech_detection_threshold=self.speech_detection_threshold,
            silence_detection_threshold=self.silence_detection_threshold,
            debug=self.debug,
            session_id=self.session_id
        )

        self.vad_processor.speech_timeout_seconds = self.speech_timeout_seconds
        self.vad_processor.silence_timeout_seconds = self.silence_timeout_seconds

        if self.bypass_vad:
            self.vad_processor.speech_active = True
            logging.info(f"{self.session_id}VAD is bypassed.")

        self.transcript_handler: TranscriptHandler = TranscriptHandler(session_id=self.session_id)

        # STT Engine is already initialized and passed in (self.stt_engine)
        # TTS Engine is already initialized and passed in (self.tts_engine)

        self.tts_processor: TTSProcessor = TTSProcessor(
            rtp_queue=self.rtp_queue,
            tts_engine=self.tts_engine, # Pass the initialized TTS engine
            tts_voice_id=self.tts_voice_id_cfg,
            tts_input_rate=self.tts_input_rate_cfg, # Pass the engine's specific input rate
            tts_target_output_rate=self.tts_target_output_rate_cfg,
            session_id=self.session_id,
            debug=self.debug
        )

        self.transcript_handler.on_final_transcript = self._handle_final_transcript
        logging.info(f"{self.session_id}All SpeechSessionManager components initialized.")

    def _setup_logging(self) -> None:
        if self.debug:
            logging.getLogger().setLevel(logging.DEBUG)
            logging.debug(f"{self.session_id}Debug logging enabled for SpeechSessionManager.")

    def choose_codec(self, sdp: str) -> PCMU:
        codecs = get_codecs(sdp)
        for c in codecs:
            if c.payloadType == 0:
                logging.info(f"{self.session_id}PCMU codec selected.")
                return PCMU(c)
        raise UnsupportedCodec(f"{self.session_id}No supported codec (PCMU/0) found.")

    async def start(self) -> bool:
        logging.info(f"{self.session_id}SpeechSessionManager starting...")
        self._is_closing = False

        try:
            if not await self.stt_engine.connect():
                logging.error(f"{self.session_id}Failed to connect STT engine. Cannot start session.")
                return False

            stt_engine_config = { "config": { "sample_rate": self.target_sample_rate, "num_channels": self.stt_channels } }
            # Note: This config structure is Vosk-like. Other engines might need different config structures.
            # This might need to be made more generic or handled by the engine implementation itself if possible.
            if not await self.stt_engine.send_config(stt_engine_config):
                logging.error(f"{self.session_id}Failed to send initial config to STT engine. Disconnecting.")
                await self.stt_engine.disconnect()
                return False

            self.receive_task = asyncio.create_task(self.receive_transcripts(), name=f"STTReceive-{self.session_id}")

            if not self.bypass_vad:
                self.timeout_monitor_task = asyncio.create_task(self._monitor_vad_timeouts(), name=f"VADTimeout-{self.session_id}")

            logging.info(f"{self.session_id}SpeechSessionManager started successfully.")
            return True

        except Exception as e:
            logging.error(f"{self.session_id}Error during SpeechSessionManager start: {e}", exc_info=True)
            if self.stt_engine and self.stt_engine.is_connected():
                await self.stt_engine.disconnect()
            return False

    async def _monitor_vad_timeouts(self) -> None:
        # This method remains largely the same as it interacts with VADProcessor and TranscriptHandler
        try:
            while not self._is_closing:
                await asyncio.sleep(0.5)
                if not self.vad_processor or not self.transcript_handler: continue
                if self.vad_processor.has_speech_timeout():
                    logging.warning(f"{self.session_id}Speech timeout. Forcing final transcript.")
                    await self._force_final_transcript("Speech timeout")
                    continue
                if self.vad_processor.has_silence_timeout():
                    logging.info(f"{self.session_id}Silence timeout. Forcing final transcript.")
                    await self._force_final_transcript("Silence timeout")
                    continue
                if self.transcript_handler.has_stale_partial(max_unchanged_seconds=self.stale_partial_timeout_seconds):
                    logging.info(f"{self.session_id}Stale partial. Promoting to final.")
                    await self._force_final_transcript("Stale partial")
        except asyncio.CancelledError:
            logging.info(f"{self.session_id}VAD timeout monitor cancelled.")
        except Exception as e:
            logging.error(f"{self.session_id}Error in VAD timeout monitor: {e}", exc_info=True)

    async def _force_final_transcript(self, reason: str) -> None:
        # This method remains largely the same
        try:
            if not self.transcript_handler.last_partial_transcript:
                logging.info(f"{self.session_id}No partial for forced final ({reason}).")
                if not self.bypass_vad: self.vad_processor.reset_vad_state(preserve_buffer=False)
                return
            partial_text = self.transcript_handler.last_partial_transcript.strip()
            if not partial_text or len(partial_text) < 2 : # Added min length check
                logging.info(f"{self.session_id}Partial too short or empty for forced final ({reason}): '{partial_text}'")
                if not self.bypass_vad: self.vad_processor.reset_vad_state(preserve_buffer=False)
                self.transcript_handler.clear_transcripts()
                return
            logging.info(f"{self.session_id}Forcing final transcript ({reason}): \"{partial_text}\"")
            self.transcript_handler.last_final_transcript = partial_text
            if not self.bypass_vad: self.vad_processor.reset_vad_state(preserve_buffer=False)
            self.transcript_handler.clear_transcripts()
            if self.transcript_handler.on_final_transcript:
                asyncio.create_task(self.transcript_handler.on_final_transcript(partial_text))
        except Exception as e:
            logging.error(f"{self.session_id}Error forcing final transcript: {e}", exc_info=True)

    async def stop(self) -> bool:
        # This method should primarily deal with the STT engine for graceful shutdown of STT.
        # Full cleanup is in `close`.
        logging.info(f"{self.session_id}Stopping SpeechSessionManager STT components.")
        try:
            await self._send_eof_to_stt_if_enabled()
            if self.stt_engine.is_connected():
                await self.stt_engine.disconnect() # Disconnect STT engine
            await self._cancel_task(self.receive_task, "STTReceiveTask")
            logging.info(f"{self.session_id}SpeechSessionManager STT components stopped.")
            return True
        except Exception as e:
            logging.error(f"{self.session_id}Error stopping STT components: {e}", exc_info=True)
            return False

    async def _cancel_task(self, task: Optional[asyncio.Task], task_name: str, timeout: float = 1.0) -> bool:
        if not task or task.done(): return True
        try:
            logging.debug(f"{self.session_id}Cancelling {task_name}.")
            task.cancel()
            await asyncio.wait_for(task, timeout=timeout)
            return True
        except asyncio.TimeoutError:
            logging.warning(f"{self.session_id}{task_name} timed out during cancellation.")
        except asyncio.CancelledError:
            logging.info(f"{self.session_id}{task_name} was cancelled successfully.")
        except Exception as e:
            logging.error(f"{self.session_id}Error managing {task_name}: {e}", exc_info=True)
        return False

    async def _send_eof_to_stt_if_enabled(self) -> None:
        if self.send_eof_to_stt and self.stt_engine and self.stt_engine.is_connected():
            try:
                logging.debug(f"{self.session_id}Sending EOF to STT engine.")
                await self.stt_engine.send_eof()
            except Exception as e:
                logging.error(f"{self.session_id}Error sending EOF to STT engine: {e}", exc_info=True)

    async def send(self, audio: bytes) -> None:
        if self._is_closing:
            logging.warning(f"{self.session_id}Send called while closing. Skipping.")
            return
        if not self.stt_engine or not self.stt_engine.is_connected():
            logging.warning(f"{self.session_id}STT engine not connected. Cannot send audio.")
            return
        try:
            if not isinstance(audio, bytes):
                logging.warning(f"{self.session_id}Audio type {type(audio)}, expected bytes. Skipping.")
                return
            resampled_tensor, processed_audio_bytes_for_stt = self.audio_processor.process_bytes_audio(audio)
            if processed_audio_bytes_for_stt is None: return
            await self._handle_processed_audio(resampled_tensor, processed_audio_bytes_for_stt)
        except Exception as e:
            logging.error(f"{self.session_id}Error in SpeechSessionManager.send: {e}", exc_info=True)

    async def _handle_processed_audio(self, tensor: Optional[torch.Tensor], audio_bytes_for_stt: bytes) -> None:
        # This method's logic for VAD and barge-in remains, but STT send uses self.stt_engine
        if self.debug: logging.debug(f"{self.session_id}Handling processed audio: {len(audio_bytes_for_stt)} bytes.")

        if self.bypass_vad:
            if not self.is_tts_active:
                if self.stt_engine and self.stt_engine.is_connected():
                    await self.stt_engine.send_audio(audio_bytes_for_stt)
            # ... (logging for VAD bypass)
        else: # VAD is active
            num_samples = tensor.shape[0] if tensor is not None else len(audio_bytes_for_stt) // 2
            was_vad_proc, is_speech, vad_buffer = await self.vad_processor.add_audio(audio_bytes_for_stt, num_samples)

            current_time = time.time()
            # Barge-in logic (simplified for brevity, assume it's similar to original)
            if self.is_tts_active and is_speech and not self.barge_in_pending:
                self.barge_in_pending = True; self.barge_in_speech_start_time = current_time
                logging.info(f"{self.session_id}Barge-in timer started.")

            if self.barge_in_pending and is_speech:
                if (current_time - self.barge_in_speech_start_time) >= self.barge_in_threshold_seconds:
                    logging.info(f"{self.session_id}Barge-in triggered.")
                    if self.tts_task and not self.tts_task.done():
                        self.tts_processor.interrupt(); self.tts_task.cancel()
                        try: await self.tts_task
                        except asyncio.CancelledError: logging.info(f"{self.session_id}TTS task cancelled by barge-in.")
                    self.is_tts_active = False
                    self.transcript_handler.clear_transcripts()
                    self.vad_processor.reset_vad_state(preserve_buffer=False)
                    self.barge_in_pending = False
                    vad_buffer = None # Audio consumed by barge-in start
            elif self.barge_in_pending and not is_speech:
                 logging.info(f"{self.session_id}Barge-in timer reset (speech stopped).")
                 self.barge_in_pending = False

            if was_vad_proc and vad_buffer:
                if not self.is_tts_active:
                    if self.stt_engine and self.stt_engine.is_connected():
                        await self.stt_engine.send_audio(vad_buffer)
                # ... (logging for sending VAD buffer)
            if not self._is_closing: await asyncio.sleep(0)

    async def receive_transcripts(self) -> None:
        # Uses self.stt_engine.receive_result()
        try:
            reconnect_attempts = 0; max_reconnect_attempts = 5
            while not self._is_closing:
                try:
                    if not self.stt_engine or not self.stt_engine.is_connected():
                        logging.warning(f"{self.session_id}STT engine disconnected. Attempting reconnect...")
                        if await self._try_reconnect_stt_engine(reconnect_attempts, max_reconnect_attempts):
                            reconnect_attempts = 0
                        else:
                            reconnect_attempts +=1
                            if reconnect_attempts >= max_reconnect_attempts: break
                            continue

                    message = await self.stt_engine.receive_result()
                    if self.debug and message: logging.debug(f"{self.session_id}Raw STT response: \"{message[:70]}...\"")

                    if message is None:
                        if self.stt_engine and not self.stt_engine.is_connected() and not self._is_closing:
                            logging.warning(f"{self.session_id}STT connection closed after receive_result timeout.")
                        continue

                    reconnect_attempts = 0
                    if not await self.transcript_handler.handle_message(message):
                        logging.warning(f"{self.session_id}Transcript handler failed for: {message[:100]}...")
                except websockets.exceptions.ConnectionClosed as conn_err: # This might be too specific if not all STT engines use websockets
                    logging.error(f"{self.session_id}STT connection closed: {conn_err}", exc_info=True)
                    if self.stt_engine: await self.stt_engine.disconnect() # Ensure engine knows
                    if self._is_closing: break
                except asyncio.CancelledError: raise
                except Exception as e:
                    logging.error(f"{self.session_id}Error in receive_transcripts: {e}", exc_info=True)
                    await asyncio.sleep(1)
            logging.info(f"{self.session_id}Exiting receive_transcripts loop.")
        except asyncio.CancelledError: logging.info(f"{self.session_id}Receive_transcripts task cancelled.")
        except Exception as e: logging.critical(f"{self.session_id}Fatal error in receive_transcripts: {e}", exc_info=True)

    async def _try_reconnect_stt_engine(self, current_attempts: int, max_attempts: int) -> bool:
        # Uses self.stt_engine
        if current_attempts >= max_attempts: return False
        attempt_num = current_attempts + 1
        backoff_time = min(2 ** attempt_num, 10)
        logging.info(f"{self.session_id}Reconnecting STT engine (attempt {attempt_num}/{max_attempts}), wait {backoff_time}s.")
        await asyncio.sleep(backoff_time)
        try:
            if not await self.stt_engine.connect(): return False
            stt_cfg = {"config": {"sample_rate": self.target_sample_rate, "num_channels": self.stt_channels}}
            if not await self.stt_engine.send_config(stt_cfg):
                await self.stt_engine.disconnect()
                return False
            logging.info(f"{self.session_id}STT engine reconnected and configured.")
            return True
        except Exception as e:
            logging.error(f"{self.session_id}Error reconnecting STT engine: {e}", exc_info=True)
            return False

    async def close(self) -> None:
        if self._is_closing: logging.info(f"{self.session_id}Close already in progress."); return
        logging.info(f"{self.session_id}Closing SpeechSessionManager.")
        self._is_closing = True

        await self._cancel_task(self.tts_task, "TTSGenerationTask")
        if self.tts_processor: self.tts_processor.interrupt() # Clear RTP queue

        await self._cancel_task(self.timeout_monitor_task, "VADTimeoutMonitor")

        if not self.bypass_vad and hasattr(self, 'vad_processor'): # Check attribute exists
            try: await self._process_final_vad_buffer()
            except Exception as e: logging.error(f"{self.session_id}Error final VAD processing: {e}", exc_info=True)

        if hasattr(self, 'transcript_handler'): self._finalize_transcript()

        if self.stt_engine and self.stt_engine.is_connected():
            try:
                await self._send_eof_to_stt_if_enabled()
                await self.stt_engine.disconnect()
            except Exception as e: logging.error(f"{self.session_id}Error disconnecting STT: {e}", exc_info=True)

        if self.tts_engine and self.tts_engine.is_connected(): # Also disconnect TTS engine
            try: await self.tts_engine.disconnect()
            except Exception as e: logging.error(f"{self.session_id}Error disconnecting TTS: {e}", exc_info=True)

        await self._cancel_task(self.receive_task, "STTReceiveTask")
        logging.info(f"{self.session_id}SpeechSessionManager closed.")

    def _finalize_transcript(self) -> None:
        # This method remains largely the same
        if not self.transcript_handler.last_final_transcript and self.transcript_handler.last_partial_transcript:
            self.transcript_handler.last_final_transcript = self.transcript_handler.last_partial_transcript
        final_text = self.transcript_handler.last_final_transcript
        logging.info(f"{self.session_id}Definitive final transcript: \"{final_text if final_text else '(empty)'}\"")

    def terminate_call(self) -> None: # Remains the same
        logging.info(f"{self.session_id}Signaling call termination.")
        if hasattr(self.call, 'terminated'): self.call.terminated = True

    def set_log_level(self, level: int) -> None: # Remains the same
        self.debug = (level == logging.DEBUG)
        if hasattr(self, 'audio_processor'): self.audio_processor.debug = self.debug
        if hasattr(self, 'vad_processor'): self.vad_processor.debug = self.debug
        if hasattr(self, 'tts_processor'): self.tts_processor.debug = self.debug
        # STT/TTS engine debug levels are managed by their own instances/configs
        logging.getLogger().setLevel(level if self.debug else logging.INFO) # Adjust global or dedicated logger
        logging.info(f"{self.session_id}Log level set to {logging.getLevelName(level)}.")

    async def _process_final_vad_buffer(self) -> None:
        # This method remains largely the same, uses self.stt_engine
        is_speech, buffer_bytes = await self.vad_processor.process_final_buffer()
        if buffer_bytes and self.stt_engine and self.stt_engine.is_connected():
            if is_speech:
                await self.stt_engine.send_audio(buffer_bytes)
                wait_time = min(len(buffer_bytes) / (2 * self.target_sample_rate) * 0.5 + 0.2, 1.5)
                await asyncio.sleep(wait_time)

    def get_final_transcript(self) -> str: # Remains the same
        return self.transcript_handler.get_final_transcript()

    async def _handle_final_transcript(self, final_text: str) -> None:
        # This method remains largely the same, TTSProcessor already uses the tts_engine
        logging.info(f"{self.session_id}Handling final transcript: \"{final_text[:100]}...\"")
        if self.tts_task and not self.tts_task.done():
            self.is_tts_active = False
            self.tts_processor.interrupt(); self.tts_task.cancel()
            try: await self.tts_task
            except asyncio.CancelledError: logging.info(f"{self.session_id}Lingering TTS task cancelled.")
        self.tts_task = None; self.is_tts_active = False

        # Simulated LLM response
        llm_response_text = random.choice(["Merhaba.", "Anlıyorum.", "Lütfen devam edin."])
        logging.info(f"{self.session_id}Simulated LLM response: \"{llm_response_text}\"")

        if not self.bypass_vad: self.vad_processor.reset_vad_state(preserve_buffer=False)
        self.barge_in_pending = False

        if self.tts_processor:
            try:
                self.is_tts_active = True
                self.tts_task = asyncio.create_task(
                    self.tts_processor.generate_and_queue_tts_audio(llm_response_text),
                    name=f"TTS-{self.session_id}-{time.time()}"
                )
                # Simplified done callback for brevity
                self.tts_task.add_done_callback(lambda t: setattr(self, 'is_tts_active', False) or logging.info(f"{self.session_id}TTS task done (status: {t.exception() is None})."))
            except Exception as e:
                logging.error(f"{self.session_id}Error creating TTS task: {e}", exc_info=True)
                self.is_tts_active = False
        else:
            logging.error(f"{self.session_id}TTSProcessor not available.")
