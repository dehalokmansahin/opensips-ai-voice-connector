import asyncio
import json
import logging
import time
from queue import Queue
from typing import Any, Callable, Awaitable, Optional, Tuple
from aiortc.sdp import SessionDescription # Added for sdp_object type hint

import torch
import websockets

from ..ai import AIEngine
from ..config import Config
from ..codec import get_codecs, PCMU, UnsupportedCodec, GenericCodec # Added GenericCodec for get_codec return hint
from .. import constants
from ..llm_client import LLMClient

from .audio_processor import AudioProcessor
from .vad_detector import VADDetector
from .adaptive_vad import AdaptiveVADDetector
from .vad_processor import VADProcessor
from .transcript_handler import TranscriptHandler
from .tts_processor import TTSProcessor
from .stt_engine_base import STTEngineBase
from .tts_engine_base import TTSEngineBase

class SessionConfigurator:
    """ Loads and holds all session-related configurations. """
    def __init__(self, global_config: Config, session_id: str, sdp_object: SessionDescription,
                 tts_voice_id: str, tts_input_rate: int):
        self.global_config: Config = global_config
        self.session_id: str = session_id
        self.sdp_object: SessionDescription = sdp_object
        
        self.session_cfg: Config = global_config.get("SpeechSessionManager", {})
        if not self.session_cfg or len(self.session_cfg) == 0: # Fallback
            self.session_cfg = global_config.get("SmartSpeech", {})

        # STT
        self.target_sample_rate: int = int(self.session_cfg.get("stt_target_sample_rate", "sample_rate", 16000))
        self.stt_channels: int = self.session_cfg.getint("stt_channels", "channels", 1)
        self.send_eof_to_stt: bool = self.session_cfg.getboolean("stt_send_eof", "send_eof", True)
        self.debug: bool = self.session_cfg.getboolean("debug", "debug", False)

        # VAD
        self.bypass_vad: bool = self.session_cfg.getboolean("bypass_vad", "bypass_vad", False)
        self.vad_threshold: float = self.session_cfg.getfloat("vad_threshold", "vad_threshold", 0.25)
        self.vad_min_speech_ms: int = self.session_cfg.getint("vad_min_speech_ms", "vad_min_speech_ms", 150)
        self.vad_min_silence_ms: int = self.session_cfg.getint("vad_min_silence_ms", "vad_min_silence_ms", 450)
        self.vad_buffer_chunk_ms: int = self.session_cfg.getint("vad_buffer_chunk_ms", "vad_buffer_chunk_ms", 600)
        self.speech_detection_threshold: int = self.session_cfg.getint("speech_detection_threshold", "speech_detection_threshold", 1)
        self.silence_detection_threshold: int = self.session_cfg.getint("silence_detection_threshold", "silence_detection_threshold", 1)

        # Adaptive VAD and Echo Cancellation
        self.use_adaptive_vad: bool = self.session_cfg.getboolean("use_adaptive_vad", "use_adaptive_vad", True)
        self.auto_calibration: bool = self.session_cfg.getboolean("auto_calibration", "auto_calibration", True)
        self.webrtc_aggressiveness: int = self.session_cfg.getint("webrtc_aggressiveness", "webrtc_aggressiveness", 2)
        self.calibration_window_ms: int = self.session_cfg.getint("calibration_window_ms", "calibration_window_ms", 5000)

        # Timeouts
        self.speech_timeout_seconds: float = self.session_cfg.getfloat("speech_timeout_seconds", "speech_timeout_seconds", 10.0)
        self.silence_timeout_seconds: float = self.session_cfg.getfloat("silence_timeout_seconds", "silence_timeout_seconds", 3.0)
        self.stale_partial_timeout_seconds: float = self.session_cfg.getfloat("stale_partial_timeout_seconds", "stale_partial_timeout_seconds", 2.5)
        self.barge_in_threshold_seconds: float = self.session_cfg.getfloat("barge_in_threshold_seconds", "barge_in_threshold_seconds", 1.5)

        # TTS
        self.tts_voice_id: str = tts_voice_id
        self.tts_input_rate: int = tts_input_rate
        self.tts_target_output_rate: int = int(self.session_cfg.get("tts_target_output_rate", "tts_target_output_rate", 8000))

        # LLM
        self.llm_server_uri: str = self.session_cfg.get("llm_server_uri", "ws://localhost:8765")
        # Updated default system prompt to the more detailed one previously hardcoded in SpeechSessionManager
        self.llm_system_prompt: str = self.session_cfg.get("llm_system_prompt", "llm_system_prompt", """
                    Sen Garanti BBVA IVR hattında, Türkçe TTS için konuşma metni üreten bir dil modelisin.

                    Kurallar:
                    1. Kısa-orta uzunlukta, net ve resmi cümleler yaz (en çok 20 kelime).
                    2. Türkçe imlâyı tam uygula (ç, ğ, ı, ö, ş, ü).
                    3. Tarihleri "2 Haziran 2025", saatleri "14.30" biçiminde yaz.
                    4. Kritik sayıları tam ver: "₺250", "1234".
                    5. Gereksiz sembol, yabancı kelime, ünlem ve jargon kullanma.
                    6. Yalnızca TTS'ye okunacak metni döndür; fazladan açıklama ekleme.

                    """)
        self.llm_max_tokens: int = self.session_cfg.getint("llm_max_tokens", "llm_max_tokens", 256) # Ensure default is passed if key missing
        self.llm_temperature: float = self.session_cfg.getfloat("llm_temperature", "llm_temperature", 0.7) # Ensure default is passed
        self.llm_connect_timeout: float = self.session_cfg.getfloat("llm_connect_timeout", "llm_connect_timeout", 10.0) # Default 10s
        self.llm_response_timeout: float = self.session_cfg.getfloat("llm_response_timeout", "llm_response_timeout", 10.0) # Default 10s

        # STT Reconnect
        self.stt_max_reconnect_attempts: int = self.session_cfg.getint("stt_max_reconnect_attempts", "STT_MAX_RECONNECT_ATTEMPTS", 5)
        self.stt_receive_error_sleep_s: float = self.session_cfg.getfloat("stt_receive_error_sleep_s", "STT_RECEIVE_ERROR_SLEEP_S", 1.0)
        self.stt_reconnect_backoff_base: int = self.session_cfg.getint("stt_reconnect_backoff_base", "STT_RECONNECT_BACKOFF_BASE", 2)
        self.stt_reconnect_max_backoff_s: float = self.session_cfg.getfloat("stt_reconnect_max_backoff_s", "STT_RECONNECT_MAX_BACKOFF_S", 10.0)
        self.stt_receive_timeout_seconds: float = self.session_cfg.getfloat("stt_receive_timeout_seconds", "stt_receive_timeout_seconds", 10.0) # Default 10s

        # TTS Timeouts
        self.tts_synthesis_total_timeout_seconds: float = self.session_cfg.getfloat("tts_synthesis_total_timeout_seconds", "tts_synthesis_total_timeout_seconds", 30.0) # Default 30s for overall synthesis

        # VAD Final Buffer
        self.vad_final_buffer_wait_factor: float = self.session_cfg.getfloat("vad_final_buffer_wait_factor", "VAD_FINAL_BUFFER_WAIT_FACTOR", 0.5)
        self.vad_final_buffer_wait_additive_s: float = self.session_cfg.getfloat("vad_final_buffer_wait_additive_s", "VAD_FINAL_BUFFER_WAIT_ADDITIVE_S", 0.2)
        self.vad_final_buffer_max_wait_s: float = self.session_cfg.getfloat("vad_final_buffer_max_wait_s", "VAD_FINAL_BUFFER_MAX_WAIT_S", 1.5)

        self.codec: PCMU = self._choose_codec()
        logging.info(f"{self.session_id}SessionConfigurator initialized. Codec: {self.codec.name if self.codec else 'None'}. Debug: {self.debug}")

    def _choose_codec(self) -> PCMU:
        codecs = get_codecs(self.sdp_object)
        for c in codecs:
            if c.payloadType == 0:
                logging.info(f"{self.session_id}PCMU codec selected by SessionConfigurator.")
                return PCMU(c)
        raise UnsupportedCodec(f"{self.session_id}No supported codec (PCMU/0) found by SessionConfigurator.")

class AudioOrchestrator:
    def __init__(self, configurator: SessionConfigurator, session_id: str,
                 on_vad_audio_chunk: Callable[[bytes], Awaitable[None]],
                 on_barge_in_detected: Callable[[], Awaitable[None]],
                 on_vad_timeout: Callable[[str], Awaitable[None]],
                 is_tts_active_func: Callable[[], bool]):
        self.config = configurator
        self.session_id = session_id
        self.on_vad_audio_chunk = on_vad_audio_chunk
        self.on_barge_in_detected = on_barge_in_detected
        self.on_vad_timeout = on_vad_timeout
        self.is_tts_active_func = is_tts_active_func

        self.audio_processor: AudioProcessor = AudioProcessor(
            target_sample_rate=self.config.target_sample_rate,
            debug=self.config.debug, session_id=self.session_id)
            
        # Use AdaptiveVADDetector if enabled in config, otherwise fall back to standard VADDetector
        if self.config.use_adaptive_vad:
            logging.info(f"{self.session_id}Using AdaptiveVADDetector with auto_calibration={self.config.auto_calibration}")
            vad_detector = AdaptiveVADDetector(
                sample_rate=self.config.target_sample_rate, 
                initial_threshold=self.config.vad_threshold,
                min_speech_duration_ms=self.config.vad_min_speech_ms, 
                min_silence_duration_ms=self.config.vad_min_silence_ms,
                calibration_window_ms=self.config.calibration_window_ms,
                webrtc_aggressiveness=self.config.webrtc_aggressiveness,
                auto_calibration=self.config.auto_calibration)
        else:
            logging.info(f"{self.session_id}Using standard VADDetector")
            vad_detector = VADDetector(
                sample_rate=self.config.target_sample_rate, 
                threshold=self.config.vad_threshold,
                min_speech_duration_ms=self.config.vad_min_speech_ms, 
                min_silence_duration_ms=self.config.vad_min_silence_ms)
                
        self.vad_detector = vad_detector
        self.vad_processor: VADProcessor = VADProcessor(
            vad_detector=vad_detector, target_sample_rate=self.config.target_sample_rate,
            vad_buffer_chunk_ms=self.config.vad_buffer_chunk_ms,
            speech_detection_threshold=self.config.speech_detection_threshold,
            silence_detection_threshold=self.config.silence_detection_threshold,
            debug=self.config.debug, session_id=self.session_id)
        self.vad_processor.speech_timeout_seconds = self.config.speech_timeout_seconds
        self.vad_processor.silence_timeout_seconds = self.config.silence_timeout_seconds
        if self.config.bypass_vad:
            self.vad_processor.speech_active = True
            logging.info(f"{self.session_id}VAD is bypassed in AudioOrchestrator.")
        self.timeout_monitor_task: Optional[asyncio.Task] = None
        self._is_monitoring: bool = False
        self.barge_in_speech_start_time: float = 0.0
        self.barge_in_pending: bool = False
        self._is_paused: bool = False # Added for explicit pause state

    async def process_incoming_audio(self, raw_audio_bytes: bytes) -> None:
        if self._is_paused:
            logging.debug(f"{self.session_id}AO: Processing paused, dropping incoming audio.")
            return

        # High-level audio processing pipeline
        prep = await self._prepare_audio_for_stt(raw_audio_bytes)
        if prep is None:
            return
        resampled_tensor, bytes_for_stt = prep

        if await self._handle_bypass_vad(bytes_for_stt):
            return

        num_samples = resampled_tensor.shape[0] if resampled_tensor is not None else len(bytes_for_stt) // 2
        was_processed, is_speech, vad_buffer = await self._run_vad(bytes_for_stt, num_samples)

        allow_dispatch = await self._update_barge_in_state(is_speech)

        await self._dispatch_vad_buffer(vad_buffer, was_processed, allow_dispatch)

        if self._is_monitoring:
            await asyncio.sleep(0)

    async def _dispatch_vad_buffer(self, vad_buffer: Optional[bytes], was_processed: bool, allow_dispatch: bool) -> None:
        """Send a VAD-produced audio chunk to STT if appropriate."""
        if was_processed and vad_buffer and allow_dispatch:
            if not self.is_tts_active_func() or self.config.bypass_vad:
                await self.on_vad_audio_chunk(vad_buffer)
            else:
                logging.debug(f"{self.session_id}AO: VAD audio chunk produced but TTS active and barge-in not triggered.")

    async def _update_barge_in_state(self, is_speech_present: bool) -> bool:
        """Manage barge-in timer and return False if buffer should be dropped."""
        current_time = time.time()
        if self.is_tts_active_func() and is_speech_present and not self.barge_in_pending:
            self.barge_in_pending = True
            self.barge_in_speech_start_time = current_time
            logging.info(f"{self.session_id}AO: Barge-in timer started.")
        if self.barge_in_pending and is_speech_present:
            if (current_time - self.barge_in_speech_start_time) >= self.config.barge_in_threshold_seconds:
                logging.info(f"{self.session_id}AO: Barge-in triggered.")
                await self.on_barge_in_detected()
                return False
        elif self.barge_in_pending and not is_speech_present:
            logging.info(f"{self.session_id}AO: Barge-in timer reset (speech stopped).")
            self.barge_in_pending = False
        return True

    async def _run_vad(self, bytes_for_stt: bytes, num_samples: int) -> Tuple[bool, bool, Optional[bytes]]:
        """Run VAD processing on audio bytes and return processed flag, speech flag, buffer."""
        return await self.vad_processor.add_audio(bytes_for_stt, num_samples)

    async def _handle_bypass_vad(self, bytes_for_stt: bytes) -> bool:
        """If bypass VAD is enabled, send or drop immediately, return True if handled."""
        if self.config.bypass_vad:
            if not self.is_tts_active_func():
                await self.on_vad_audio_chunk(bytes_for_stt)
            else:
                logging.debug(f"{self.session_id}AO: VAD bypassed, TTS active, audio not sent for STT.")
            return True
        return False

    async def _prepare_audio_for_stt(self, raw_audio_bytes: bytes) -> Optional[Tuple[torch.Tensor, bytes]]:
        """Decode and prepare audio for STT, returning tensor and bytes or None."""
        resampled_tensor, bytes_for_stt = self.audio_processor.process_bytes_audio(raw_audio_bytes)
        if bytes_for_stt is None:
            return None
        if self.config.debug:
            logging.debug(f"{self.session_id}AO: Handling processed audio: {len(bytes_for_stt)} bytes.")
        return resampled_tensor, bytes_for_stt

    async def _monitor_vad_timeouts(self) -> None:
        try:
            while self._is_monitoring:
                await asyncio.sleep(constants.VAD_MONITOR_INTERVAL_S)
                if not self.vad_processor: continue
                if self.vad_processor.has_speech_timeout():
                    logging.warning(f"{self.session_id}AO: Speech timeout."); await self.on_vad_timeout("Speech timeout"); continue
                if self.vad_processor.has_silence_timeout():
                    logging.info(f"{self.session_id}AO: Silence timeout."); await self.on_vad_timeout("Silence timeout"); continue
        except asyncio.CancelledError: logging.info(f"{self.session_id}AO: VAD timeout monitor cancelled.")
        except Exception as e: logging.error(f"{self.session_id}AO: Error in VAD timeout monitor: {e}", exc_info=True)

    def start_monitoring(self) -> None:
        self._is_monitoring = True
        if not self.config.bypass_vad:
            if self.timeout_monitor_task and not self.timeout_monitor_task.done():
                logging.warning(f"{self.session_id}AO: start_monitoring called but task already exists.")
            else:
                self.timeout_monitor_task = asyncio.create_task(self._monitor_vad_timeouts(), name=f"VADTimeout-{self.session_id}")
        logging.info(f"{self.session_id}AudioOrchestrator monitoring started.")

    async def stop_monitoring(self) -> None:
        self._is_monitoring = False # Ensure loop condition in _monitor_vad_timeouts becomes false
        if self.timeout_monitor_task and not self.timeout_monitor_task.done():
            self.timeout_monitor_task.cancel()
            try:
                await self.timeout_monitor_task
            except asyncio.CancelledError:
                logging.info(f"{self.session_id}AO: VAD timeout monitor task successfully cancelled.")
            except Exception as e:
                logging.error(f"{self.session_id}AO: Error awaiting cancelled VAD timeout monitor: {e}", exc_info=True)
        self.timeout_monitor_task = None # Clear the task
        logging.info(f"{self.session_id}AudioOrchestrator monitoring stopped.")

    async def pause_processing(self) -> None:
        """Pauses audio processing and VAD monitoring."""
        if self._is_paused:
            logging.debug(f"{self.session_id}AO: Already paused.")
            return
        self._is_paused = True
        await self.stop_monitoring() # Stop VAD timeout checks
        logging.info(f"{self.session_id}AudioOrchestrator processing paused.")

    async def resume_processing(self) -> None:
        """Resumes audio processing and VAD monitoring."""
        if not self._is_paused:
            logging.debug(f"{self.session_id}AO: Already resumed or not paused.")
            return
        self._is_paused = False
        self.start_monitoring() # Restart VAD timeout checks
        logging.info(f"{self.session_id}AudioOrchestrator processing resumed.")

    async def process_final_buffer(self) -> Tuple[bool, Optional[bytes]]:
        if not self.config.bypass_vad and self.vad_processor: return await self.vad_processor.process_final_buffer()
        return False, None

    def reset_vad_state(self, preserve_buffer: bool = False) -> None:
        if self.vad_processor: self.vad_processor.reset_vad_state(preserve_buffer)
        self.barge_in_pending = False

class TranscriptCoordinator:
    def __init__(self, stt_engine: STTEngineBase, configurator: SessionConfigurator,
                 session_id: str, on_final_transcript: Callable[[str], Awaitable[None]]):
        self.stt_engine = stt_engine; self.config = configurator; self.session_id = session_id
        self.on_final_transcript_callback = on_final_transcript
        self.transcript_handler: TranscriptHandler = TranscriptHandler(session_id=self.session_id)
        self.transcript_handler.on_final_transcript = self._internal_on_final_transcript
        self.receive_task: Optional[asyncio.Task] = None; self._is_running: bool = False

    async def _internal_on_final_transcript(self, final_text: str): await self.on_final_transcript_callback(final_text)

    async def start(self) -> bool:
        self._is_running = True
        logging.info(f"{self.session_id}TC: Starting STT connection.")
        success = await self._setup_stt_connection()
        if not success:
            self._is_running = False
            return False
        self.receive_task = asyncio.create_task(self.receive_transcripts_loop(), name=f"STTReceive-{self.session_id}")
        logging.info(f"{self.session_id}TC: Started successfully.")
        return True

    async def _setup_stt_connection(self) -> bool:
        """Connect and configure the STT engine."""
        try:
            if not await self.stt_engine.connect():
                logging.error(f"{self.session_id}TC: Failed to connect STT.")
                return False
            stt_cfg = {"config": {"sample_rate": self.config.target_sample_rate, "num_channels": self.config.stt_channels}}
            if not await self.stt_engine.send_config(stt_cfg):
                logging.error(f"{self.session_id}TC: Failed to send config to STT.")
                await self.stt_engine.disconnect()
                return False
            return True
        except Exception as e:
            logging.error(f"{self.session_id}TC: Error during STT setup: {e}", exc_info=True)
            if self.stt_engine and self.stt_engine.is_connected():
                await self.stt_engine.disconnect()
            return False

    async def stop(self) -> bool:
        logging.info(f"{self.session_id}TC: Stopping STT components.")
        self._is_running = False
        await self._teardown_stt_connection()
        logging.info(f"{self.session_id}TC: STT components stopped.")
        return True

    async def _teardown_stt_connection(self) -> None:
        """Send EOF, disconnect the STT engine, and cancel receive task."""
        if self.config.send_eof_to_stt and self.stt_engine and self.stt_engine.is_connected():
            try:
                logging.debug(f"{self.session_id}TC: Sending EOF.")
                await self.stt_engine.send_eof()
            except Exception as e:
                logging.error(f"{self.session_id}TC: Error sending EOF: {e}", exc_info=True)
        if self.stt_engine and self.stt_engine.is_connected():
            try:
                await self.stt_engine.disconnect()
            except Exception as e:
                logging.error(f"{self.session_id}TC: Error disconnecting STT: {e}", exc_info=True)
        if self.receive_task and not self.receive_task.done():
            self.receive_task.cancel()
            try:
                await self.receive_task
            except asyncio.CancelledError:
                logging.info(f"{self.session_id}TC: STT receive task cancelled.")

    async def send_audio_to_stt(self, audio_bytes: bytes) -> None:
        if not self._is_running or not self.stt_engine or not self.stt_engine.is_connected(): return
        try: await self.stt_engine.send_audio(audio_bytes)
        except Exception as e: logging.error(f"{self.session_id}TC: Error sending audio to STT: {e}", exc_info=True)

    async def receive_transcripts_loop(self) -> None:
        reconnect_attempts = 0
        try:
            while self._is_running:
                try:
                    if not self.stt_engine or not self.stt_engine.is_connected():
                        if not self._is_running: break
                        logging.warning(f"{self.session_id}TC: STT disconnected. Reconnecting...")
                        if await self._try_reconnect_stt_engine(reconnect_attempts): reconnect_attempts = 0
                        else:
                            reconnect_attempts += 1
                            if reconnect_attempts >= self.config.stt_max_reconnect_attempts:
                                logging.error(f"{self.session_id}TC: Max STT reconnect attempts. Stopping."); self._is_running = False; break
                            continue

                    # Wait for STT result with timeout
                    message = await asyncio.wait_for(
                        self.stt_engine.receive_result(),
                        timeout=self.config.stt_receive_timeout_seconds
                    )

                    if not self._is_running and message is None: # If stopping and STT engine properly returns None on close
                        break

                    # If message is None, it might mean the STT engine closed the stream from its end (e.g. end of utterance)
                    # or the connection is somehow closed without an exception.
                    if message is None:
                        # If the engine itself says it's not connected, let the reconnect logic handle it.
                        if self.stt_engine and not self.stt_engine.is_connected() and self._is_running:
                            logging.warning(f"{self.session_id}TC: STT connection likely closed (receive_result returned None and engine reports not connected). Will attempt reconnect.")
                        # If message is None but engine still thinks it's connected, it might be an end-of-speech signal from STT.
                        # Depending on STTEngineBase contract, this might be normal.
                        # For now, we assume 'None' without ConnectionClosed means the stream ended gracefully or needs a check.
                        # If it needs a check and is_connected is still true, the next loop iteration will re-evaluate.
                        # If it's an issue, timeout or other errors should ideally occur.
                        # If this 'None' is unexpected, it might warrant a forced disconnect to ensure robust reconnection.
                        # However, for now, we continue to allow the main loop's connection check to handle it.
                        logging.debug(f"{self.session_id}TC: receive_result returned None. Current engine connected state: {self.stt_engine.is_connected() if self.stt_engine else 'N/A'}")
                        if self.stt_engine and self.stt_engine.is_connected() and self._is_running:
                             # If STT returns None but claims to be connected, this might be an issue or specific engine behavior.
                             # We'll let it loop and potentially timeout or fail on next receive if it's a true stall.
                             # If it's a graceful end of stream from STT (e.g. after final transcript), this is fine.
                             pass # Continue, let transcript_handler decide if it's an issue.
                        else: # Not connected, so loop will try to reconnect
                            continue

                    reconnect_attempts = 0 # Reset on successful message
                    if self.config.debug: logging.debug(f"{self.session_id}TC: Raw STT: \"{message[:70]}...\"")
                    await self.transcript_handler.handle_message(message)

                except asyncio.TimeoutError:
                    logging.warning(f"{self.session_id}TC: STT receive timeout after {self.config.stt_receive_timeout_seconds}s.")
                    if not self._is_running: break
                    # Assume connection is stalled or problematic.
                    # Force a disconnect to make the reconnection logic take over.
                    if self.stt_engine and self.stt_engine.is_connected():
                        logging.warning(f"{self.session_id}TC: STT receive timeout while engine connected. Forcing disconnect to trigger reconnect.")
                        await self.stt_engine.disconnect()
                    # No need to increment reconnect_attempts here, the main loop's check will handle it.
                    continue # Let the loop re-evaluate connection status.

                except websockets.exceptions.ConnectionClosed as conn_err:
                    logging.error(f"{self.session_id}TC: STT connection closed: {conn_err}", exc_info=False)
                    if self.stt_engine: await self.stt_engine.disconnect() # Ensure state is updated
                    if not self._is_running: break
                    # Reconnection will be attempted by the loop's main check

                except asyncio.CancelledError:
                    logging.info(f"{self.session_id}TC: receive_transcripts_loop cancelled."); raise

                except Exception as e:
                    logging.error(f"{self.session_id}TC: Error in receive_transcripts_loop: {e}", exc_info=True)
                    if not self._is_running: break
                    # For generic errors, also ensure STT engine is disconnected if it seems problematic
                    if self.stt_engine and self.stt_engine.is_connected():
                        await self.stt_engine.disconnect()
                    await asyncio.sleep(self.config.stt_receive_error_sleep_s)

            logging.info(f"{self.session_id}TC: Exiting receive_transcripts_loop.")
        except asyncio.CancelledError: logging.info(f"{self.session_id}TC: receive_transcripts_loop explicitly cancelled.")
        except Exception as e: logging.critical(f"{self.session_id}TC: Fatal error in receive_transcripts_loop: {e}", exc_info=True)
        finally: logging.info(f"{self.session_id}TC: receive_transcripts_loop finally block.")

    async def force_final_transcript(self, reason: str) -> None:
        try:
            if not self.transcript_handler.last_partial_transcript:
                logging.info(f"{self.session_id}TC: No partial for forced final ({reason})."); return
            partial_text = self.transcript_handler.last_partial_transcript.strip()
            if not partial_text or len(partial_text) < constants.MIN_PARTIAL_LENGTH_FOR_FORCED_FINAL:
                logging.info(f"{self.session_id}TC: Partial too short for forced final ({reason}): '{partial_text}'")
                self.transcript_handler.clear_transcripts(); return
            logging.info(f"{self.session_id}TC: Forcing final transcript ({reason}): \"{partial_text}\"")
            self.transcript_handler.last_final_transcript = partial_text
            self.transcript_handler.clear_transcripts()
            if self.transcript_handler.on_final_transcript:
                asyncio.create_task(self.transcript_handler.on_final_transcript(partial_text))
        except Exception as e: logging.error(f"{self.session_id}TC: Error forcing final transcript: {e}", exc_info=True)

    async def _try_reconnect_stt_engine(self, current_attempts: int) -> bool:
        if current_attempts >= self.config.stt_max_reconnect_attempts: return False
        attempt_num = current_attempts + 1
        backoff_time = min(self.config.stt_reconnect_backoff_base ** attempt_num, self.config.stt_reconnect_max_backoff_s)
        logging.info(f"{self.session_id}TC: Reconnecting STT (attempt {attempt_num}/{self.config.stt_max_reconnect_attempts}), wait {backoff_time}s.")
        await asyncio.sleep(backoff_time)
        try:
            if not await self.stt_engine.connect(): return False
            stt_cfg = {"config": {"sample_rate": self.config.target_sample_rate, "num_channels": self.config.stt_channels}}
            if not await self.stt_engine.send_config(stt_cfg):
                await self.stt_engine.disconnect(); return False
            logging.info(f"{self.session_id}TC: STT engine reconnected and configured.")
            return True
        except Exception as e: logging.error(f"{self.session_id}TC: Error reconnecting STT: {e}", exc_info=True); return False

class TTSCoordinator:
    def __init__(self, tts_engine: TTSEngineBase, configurator: SessionConfigurator,
                 rtp_queue: Queue, session_id: str, vad_detector: Optional[Any] = None):
        """
        Initializes the TTSCoordinator.

        Args:
            tts_engine: An instance of a TTSEngineBase implementation for speech synthesis.
            configurator: The SessionConfigurator with speech configuration parameters.
            rtp_queue: Queue where TTS audio packets will be placed.
            session_id: The session identifier for this call.
            vad_detector: Optional VAD detector for echo cancellation.
        """
        self.tts_engine: TTSEngineBase = tts_engine
        self.config: SessionConfigurator = configurator
        self.session_id: str = session_id
        self.tts_processor: TTSProcessor = TTSProcessor(
            rtp_queue=rtp_queue,
            tts_engine=self.tts_engine,
            tts_voice_id=self.config.tts_voice_id,
            tts_input_rate=self.config.tts_input_rate,
            tts_target_output_rate=self.config.tts_target_output_rate,
            session_id=self.session_id,
            debug=self.config.debug,
            vad_detector=vad_detector,
            synthesis_timeout_seconds=self.config.tts_synthesis_total_timeout_seconds # Pass timeout
        )
        self._current_tts_task: Optional[asyncio.Task] = None
        logging.info(f"{self.session_id}TTSCoordinator initialized with voice '{self.config.tts_voice_id}'")

    async def synthesize_and_send(self, text: str) -> asyncio.Task:
        if self._cancel_current_tts():
            await asyncio.sleep(0)  # Allow cancellation to register
        self._current_tts_task = asyncio.create_task(
            self.tts_processor.generate_and_queue_tts_audio(text), name=f"TTSGen-{self.session_id}-{time.time()}")
        return self._current_tts_task

    def _cancel_current_tts(self) -> bool:
        """Cancel current TTS task if active."""
        if self._current_tts_task and not self._current_tts_task.done():
            logging.info(f"{self.session_id}TTSC: Cancelling previous TTS task via helper.")
            self.interrupt()
            return True
        return False

    def interrupt(self) -> None:
        logging.info(f"{self.session_id}TTSC: Interrupt called.")
        if self.tts_processor: self.tts_processor.interrupt()
        if self._current_tts_task and not self._current_tts_task.done(): self._current_tts_task.cancel()

    def is_active(self) -> bool: return bool(self._current_tts_task and not self._current_tts_task.done())

    async def close(self) -> None:
        logging.info(f"{self.session_id}TTSC: Closing.")
        self._cancel_current_tts()
        await self._disconnect_engine()
        logging.info(f"{self.session_id}TTSC: Closed.")

    async def _disconnect_engine(self) -> None:
        """Disconnect TTS engine if connected."""
        if self.tts_engine and self.tts_engine.is_connected():
            try:
                await self.tts_engine.disconnect()
            except Exception as e:
                logging.error(f"{self.session_id}TTSC: Error disconnecting TTS engine: {e}")

class SpeechSessionManager(AIEngine):
    def __init__(self, call: Any, cfg: Config, stt_engine: STTEngineBase, tts_engine: TTSEngineBase,
                 tts_voice_id: str, tts_input_rate: int):
        self.call_ref = call
        self.session_id: str = f"[Session:{call.b2b_key}] " if hasattr(call, 'b2b_key') else "[Session:Unknown] "
        self._is_closing: bool = False
        
        # TTS Queue System - Cümlelerin sırayla işlenmesi için
        self._tts_queue: asyncio.Queue = asyncio.Queue()
        self._tts_processor_task: Optional[asyncio.Task] = None
        self._current_tts_task: Optional[asyncio.Task] = None
        self._tts_generation_counter: int = 0
        
        self.configurator = SessionConfigurator(cfg, self.session_id, call.sdp, tts_voice_id, tts_input_rate)
        self._setup_logging()
        self.audio_orchestrator = AudioOrchestrator(
            configurator=self.configurator, session_id=self.session_id,
            on_vad_audio_chunk=self._handle_vad_audio_chunk, on_barge_in_detected=self._handle_barge_in,
            on_vad_timeout=self._handle_vad_timeout,
            is_tts_active_func=lambda: (
                (self.tts_coordinator.is_active() if hasattr(self, 'tts_coordinator') else False) or
                (not self._tts_queue.empty() if hasattr(self, '_tts_queue') else False) or
                (self._current_tts_task and not self._current_tts_task.done() if hasattr(self, '_current_tts_task') and self._current_tts_task else False)
            ))
        self.transcript_coordinator = TranscriptCoordinator(
            stt_engine=stt_engine, configurator=self.configurator, session_id=self.session_id,
            on_final_transcript=self._handle_final_transcript)
        self.tts_coordinator = TTSCoordinator(
            tts_engine=tts_engine, configurator=self.configurator, rtp_queue=call.rtp_queue, session_id=self.session_id,
            vad_detector=self.audio_orchestrator.vad_detector
        )
        
        # Initialize LLM client
        self.llm_client = LLMClient(
            server_uri=self.configurator.llm_server_uri,
            sentence_callback=self._handle_llm_sentence,
            session_id=self.session_id,
            debug=self.configurator.debug,
            connect_timeout=self.configurator.llm_connect_timeout,
            response_timeout=self.configurator.llm_response_timeout
        )
        
        logging.info(f"{self.session_id}SSM initialized. VAD Bypass: {self.configurator.bypass_vad}, Barge-in: {self.configurator.barge_in_threshold_seconds}s, LLM Connect Timeout: {self.configurator.llm_connect_timeout}s, LLM Response Timeout: {self.configurator.llm_response_timeout}s")

    def _setup_logging(self) -> None:
        if self.configurator.debug: logging.getLogger().setLevel(logging.DEBUG)
        logging.debug(f"{self.session_id}Debug logging for session: {self.configurator.debug}")

    async def start(self) -> bool:
        logging.info(f"{self.session_id}SSM starting session..."); self._is_closing = False
        if not await self.transcript_coordinator.start():
            logging.error(f"{self.session_id}SSM: Failed to start TranscriptCoordinator."); return False
        self.audio_orchestrator.start_monitoring()
        
        # TTS Queue Processor'ı başlat
        self._tts_processor_task = asyncio.create_task(self._process_tts_queue(), name=f"TTSQueue-{self.session_id}")
        
        logging.info(f"{self.session_id}SSM session started successfully."); return True

    async def _process_tts_queue(self) -> None:
        """TTS cümlelerini sırayla işler - bir cümle tamamen bitmeden diğerine geçmez."""
        logging.info(f"{self.session_id}SSM: TTS queue processor started.")
        
        try:
            while not self._is_closing:
                try:
                    # Queue'dan sonraki cümleyi al (timeout ile)
                    sentence, generation_id = await asyncio.wait_for(
                        self._tts_queue.get(), timeout=1.0
                    )
                    
                    if self._is_closing:
                        break
                        
                    logging.info(f"{self.session_id}SSM: Processing TTS sentence (ID:{generation_id}): \"{sentence[:50]}...\"")
                    
                    try:
                        # TTS task'ı başlat ve TAMAMEN bitirmesini bekle
                        self._current_tts_task = await self.tts_coordinator.synthesize_and_send(sentence)
                        if self._current_tts_task:
                            await self._current_tts_task  # TTS'in tamamen bitmesini bekle
                            logging.debug(f"{self.session_id}SSM: TTS sentence completed (ID:{generation_id})")
                        
                        # Task tamamlandığında temizle
                        self._current_tts_task = None
                        
                        # Queue'dan item'ı çıkar
                        self._tts_queue.task_done()
                        
                    except asyncio.CancelledError:
                        logging.info(f"{self.session_id}SSM: TTS sentence cancelled (ID:{generation_id})")
                        self._tts_queue.task_done()
                        # Barge-in durumunda queue'yu temizle
                        await self._clear_tts_queue()
                        break
                    except Exception as e:
                        logging.error(f"{self.session_id}SSM: Error processing TTS sentence (ID:{generation_id}): {e}", exc_info=True)
                        self._tts_queue.task_done()
                        
                except asyncio.TimeoutError:
                    # Timeout - normal, döngüyü devam ettir
                    continue
                    
        except asyncio.CancelledError:
            logging.info(f"{self.session_id}SSM: TTS queue processor cancelled.")
        except Exception as e:
            logging.error(f"{self.session_id}SSM: Fatal error in TTS queue processor: {e}", exc_info=True)
        finally:
            logging.info(f"{self.session_id}SSM: TTS queue processor stopped.")

    async def _clear_tts_queue(self) -> None:
        """TTS queue'sunu temizle (barge-in durumunda)."""
        cleared_count = 0
        try:
            while not self._tts_queue.empty():
                try:
                    self._tts_queue.get_nowait()
                    self._tts_queue.task_done()
                    cleared_count += 1
                except asyncio.QueueEmpty:
                    break
        except Exception as e:
            logging.error(f"{self.session_id}SSM: Error clearing TTS queue: {e}")
        
        if cleared_count > 0:
            logging.info(f"{self.session_id}SSM: Cleared {cleared_count} pending TTS sentences from queue.")

    async def send(self, audio: bytes) -> None:
        if self._is_closing: return
        await self.audio_orchestrator.process_incoming_audio(audio)

    async def _handle_vad_audio_chunk(self, audio_bytes: bytes) -> None:
        if self._is_closing: return
        await self._process_vad_audio_chunk(audio_bytes)

    async def _process_vad_audio_chunk(self, audio_bytes: bytes) -> None:
        """Delegate VAD audio chunk to the transcript coordinator."""
        await self.transcript_coordinator.send_audio_to_stt(audio_bytes)

    async def _handle_barge_in(self) -> None:
        if self._is_closing: return
        logging.info(f"{self.session_id}SSM: Handling barge-in.")
        await self._perform_barge_in()

    async def _perform_barge_in(self) -> None:
        """Interrupt TTS, reset VAD, and clear transcripts."""
        # TTS interrupt et
        self.tts_coordinator.interrupt()
        
        # Aktif TTS task'ı iptal et
        if self._current_tts_task and not self._current_tts_task.done():
            self._current_tts_task.cancel()
            
        # TTS queue'sunu temizle
        await self._clear_tts_queue()
        
        # VAD state'i sıfırla
        self.audio_orchestrator.reset_vad_state(preserve_buffer=False)
        
        # Transcript'leri temizle
        if hasattr(self.transcript_coordinator, 'transcript_handler'):
            self.transcript_coordinator.transcript_handler.clear_transcripts()
            
        logging.debug(f"{self.session_id}SSM: Barge-in performed - TTS queue cleared.")

    async def _handle_vad_timeout(self, reason: str) -> None:
        if self._is_closing: return
        logging.info(f"{self.session_id}SSM: Handling VAD timeout: {reason}.")
        await self._perform_vad_timeout(reason)

    async def _perform_vad_timeout(self, reason: str) -> None:
        """Force final transcript and reset VAD state."""
        await self.transcript_coordinator.force_final_transcript(reason)
        self.audio_orchestrator.reset_vad_state(preserve_buffer=False)

    async def _handle_final_transcript(self, final_text: str) -> None:
        if self._is_closing: return
        logging.info(f"{self.session_id}SSM: Handling final transcript: \"{final_text[:100]}...\"")
        await self._process_final_transcript(final_text)

    async def _process_final_transcript(self, final_text: str) -> None:
        """Handle final transcript: interrupt active TTS, generate response, reset state, and start new TTS."""
        # Aktif TTS'i interrupt et ve queue'yu temizle
        if self.tts_coordinator.is_active():
            logging.info(f"{self.session_id}SSM: Interrupting active TTS for new final transcript.")
            self.tts_coordinator.interrupt()
            if self._current_tts_task and not self._current_tts_task.done():
                self._current_tts_task.cancel()
                try:
                    await self._current_tts_task
                except asyncio.CancelledError:
                    logging.info(f"{self.session_id}SSM: Previous TTS task cancelled.")
                    
        # TTS queue'sunu temizle
        await self._clear_tts_queue()
        self._current_tts_task = None
        
        # Yeni generation ID
        self._tts_generation_counter += 1
        current_generation = self._tts_generation_counter
        
        # Generate LLM response using streaming client
        logging.info(f"{self.session_id}SSM: Generating LLM response (Gen:{current_generation}) for: \"{final_text}\"")
        
        # Reset VAD and barge-in flags
        self.audio_orchestrator.reset_vad_state(preserve_buffer=False)
        self.audio_orchestrator.barge_in_pending = False
        
        # Generate streaming LLM response (sentences will be processed via _handle_llm_sentence)
        try:
            success = await self.llm_client.generate_response(
                system_prompt=self.configurator.llm_system_prompt, # Use prompt from configurator
                user_prompt=final_text,
                max_tokens=self.configurator.llm_max_tokens,
                temperature=self.configurator.llm_temperature
            )
            if not success:
                logging.error(f"{self.session_id}SSM: LLM generation failed")
                # Fallback to a default response
                await self._handle_llm_sentence("Üzgünüm, şu anda yardımcı olamıyorum. Lütfen daha sonra tekrar deneyin.")
        except Exception as e:
            logging.error(f"{self.session_id}SSM: Error generating LLM response: {e}", exc_info=True)
            await self._handle_llm_sentence("Üzgünüm, bir hata oluştu. Lütfen tekrar deneyin.")

    async def _handle_llm_sentence(self, sentence: str) -> None:
        """Handle individual sentences from LLM streaming response - queue'ya ekle."""
        if self._is_closing:
            return
            
        try:
            # Cümleyi temizle - özel karakterleri kaldır
            cleaned_sentence = sentence.strip()
            cleaned_sentence = cleaned_sentence.replace("*", "").replace("**", "")
            cleaned_sentence = " ".join(cleaned_sentence.split())  # Çoklu boşlukları temizle
            
            if not cleaned_sentence:
                logging.debug(f"{self.session_id}SSM: Empty sentence after cleaning, skipping.")
                return
                
            current_generation = self._tts_generation_counter
            logging.info(f"{self.session_id}SSM: Queuing TTS sentence (Gen:{current_generation}): \"{cleaned_sentence[:50]}...\"")
            
            # Cümleyi TTS queue'suna ekle (sırayla işlenecek)
            await self._tts_queue.put((cleaned_sentence, current_generation))
            
        except Exception as e:
            logging.error(f"{self.session_id}SSM: Error queuing TTS sentence: {e}", exc_info=True)

    async def stop(self) -> bool:
        logging.info(f"{self.session_id}SSM: stop called (delegating to TranscriptCoordinator).")
        if hasattr(self, 'transcript_coordinator'): return await self.transcript_coordinator.stop()
        return True

    async def close(self) -> None:
        if self._is_closing: logging.info(f"{self.session_id}SSM: close already in progress."); return
        logging.info(f"{self.session_id}SSM: closing session..."); self._is_closing = True
        
        # TTS Queue Processor'ı durdur
        if self._tts_processor_task and not self._tts_processor_task.done():
            self._tts_processor_task.cancel()
            try: 
                await self._tts_processor_task
            except asyncio.CancelledError: 
                logging.debug(f"{self.session_id}SSM: TTS queue processor cancelled.")
        
        # TTS queue'sunu temizle
        await self._clear_tts_queue()
        
        if hasattr(self, 'audio_orchestrator'): await self.audio_orchestrator.stop_monitoring()
        if hasattr(self, 'tts_coordinator'): await self.tts_coordinator.close()
        if self._current_tts_task and not self._current_tts_task.done():
             self._current_tts_task.cancel()
             try: await self._current_tts_task
             except asyncio.CancelledError: pass
        if hasattr(self, 'transcript_coordinator'):
            if hasattr(self, 'audio_orchestrator') and not self.configurator.bypass_vad:
                try:
                    is_speech, fb = await self.audio_orchestrator.process_final_buffer()
                    if fb and is_speech:
                        logging.debug(f"{self.session_id}SSM: Sending final VAD buffer to STT on close.")
                        await self.transcript_coordinator.send_audio_to_stt(fb)
                        await asyncio.sleep(self.configurator.vad_final_buffer_wait_factor)
                except Exception as e: logging.error(f"{self.session_id}SSM: Error final VAD processing: {e}", exc_info=True)
            await self.transcript_coordinator.close()
        if hasattr(self, 'transcript_coordinator') and hasattr(self.transcript_coordinator, 'transcript_handler'):
             final_text = self.transcript_coordinator.transcript_handler.get_final_transcript()
             logging.info(f"{self.session_id}SSM: Definitive final transcript on close: \"{final_text if final_text else '(empty)'}\"")
        logging.info(f"{self.session_id}SSM: session closed.")

    def choose_codec(self, sdp: SessionDescription) -> GenericCodec:
        """Select codec based on SDP for this session using the SessionConfigurator."""
        return self.configurator._choose_codec()

    def get_codec(self) -> PCMU:
        """Return the codec selected by the SessionConfigurator (PCMU)."""
        if not hasattr(self, 'configurator'):
            raise RuntimeError("SessionConfigurator not initialized.")
        return self.configurator.codec

    def get_final_transcript(self) -> str:
        if hasattr(self, 'transcript_coordinator') and hasattr(self.transcript_coordinator, 'transcript_handler'):
            return self.transcript_coordinator.transcript_handler.get_final_transcript()
        return ""

    def terminate_call(self) -> None:
        logging.info(f"{self.session_id}SSM: terminate_call invoked by external interface.")
        if hasattr(self.call_ref, 'terminate'): self.call_ref.terminate()
        else:
            logging.warning(f"{self.session_id}SSM: call_ref has no terminate method. Initiating direct close.")
            if not self._is_closing: asyncio.create_task(self.close())

    def set_log_level(self, level: int) -> None:
        if hasattr(self, 'configurator'):
            self.configurator.debug = (level == logging.DEBUG)
            self._setup_logging()
            logging.info(f"{self.session_id}Log level set to {logging.getLevelName(level)} via SSM.")
        else: logging.warning(f"{self.session_id}SSM: Cannot set log level, configurator not initialized.")

    async def pause(self):
        """Pauses the SpeechSessionManager's audio processing."""
        logging.info(f"{self.session_id}SSM: Pausing session...")
        if hasattr(self, 'audio_orchestrator') and self.audio_orchestrator:
            await self.audio_orchestrator.pause_processing()
        # Note: TranscriptCoordinator currently doesn't have explicit pause.
        # It will stop receiving new audio chunks from AudioOrchestrator.
        # TTS is interrupt-driven by new transcripts or barge-in, so less critical to "pause" actively.
        logging.info(f"{self.session_id}SSM: Session paused.")

    async def resume(self):
        """Resumes the SpeechSessionManager's audio processing."""
        logging.info(f"{self.session_id}SSM: Resuming session...")
        if hasattr(self, 'audio_orchestrator') and self.audio_orchestrator:
            await self.audio_orchestrator.resume_processing()
        # Note: TranscriptCoordinator will start receiving audio chunks again if AudioOrchestrator resumes.
        logging.info(f"{self.session_id}SSM: Session resumed.")
