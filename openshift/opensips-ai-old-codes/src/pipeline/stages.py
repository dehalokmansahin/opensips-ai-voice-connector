"""
Native Pipecat Pipeline Stages
Pipecat'in frame processor pattern'ini kullanarak VAD, STT, LLM, TTS işlemleri
"""

import asyncio
import logging
from typing import Optional, Dict, Any, AsyncGenerator
import structlog

from pipecat.frames.frames import (
    Frame, AudioRawFrame, InputAudioRawFrame, OutputAudioRawFrame,
    StartFrame, EndFrame, TranscriptionFrame, LLMTextFrame, TextFrame,
    LLMFullResponseStartFrame, LLMFullResponseEndFrame,
    UserStartedSpeakingFrame, UserStoppedSpeakingFrame, LLMMessagesFrame
)
from pipecat.processors.frame_processor import FrameProcessor, FrameDirection
from pipecat.services.stt_service import STTService
from pipecat.services.llm_service import LLMService
from pipecat.services.tts_service import TTSService

# Absolute imports
from services.vosk_websocket import VoskWebsocketSTTService
from services.piper_websocket import PiperWebsocketTTSService
from services.llama_websocket import LlamaWebsocketLLMService

# VAD configuration
try:
    from pipeline.vad_config import DEFAULT_VAD_CONFIG, VADConfig
except ImportError:
    import structlog
    logger = structlog.get_logger()
    logger.warning("VAD config not available, using defaults")
    DEFAULT_VAD_CONFIG = None

logger = structlog.get_logger()

class VADProcessor(FrameProcessor):
    """Voice Activity Detection processor - Pipecat compatible"""
    
    def __init__(self, vad_config=None, **kwargs):
        super().__init__(**kwargs)
        self._vad_config = vad_config or DEFAULT_VAD_CONFIG
        self._is_speaking = False
        self._speech_start_time = None
        self._silence_start_time = None
        self._last_activity_time = 0
        
        # Use config values or fallback defaults
        if self._vad_config:
            self._speech_threshold = self._vad_config.volume_threshold * 32768  # Convert to int16 range
            self._min_speech_duration_ms = self._vad_config.min_speech_duration_ms
            self._min_silence_duration_ms = self._vad_config.min_silence_duration_ms
        else:
            self._speech_threshold = 1000
            self._min_speech_duration_ms = 250
            self._min_silence_duration_ms = 500
            
        logger.info("VADProcessor initialized", 
                   speech_threshold=self._speech_threshold,
                   min_speech_ms=self._min_speech_duration_ms,
                   min_silence_ms=self._min_silence_duration_ms,
                   config_available=self._vad_config is not None)
    
    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        """Process frames following Pipecat pattern"""
        
        # First call the parent class process_frame to handle StartFrame, etc.
        await super().process_frame(frame, direction)
        
        logger.debug("VAD processing frame", frame_type=type(frame).__name__)
        
        if isinstance(frame, StartFrame):
            logger.info("🎤 VAD processor started!")
        elif isinstance(frame, (AudioRawFrame, InputAudioRawFrame)):
            # Handle both AudioRawFrame and InputAudioRawFrame
            logger.info("🎤 VAD received audio frame", 
                       frame_type=type(frame).__name__,
                       audio_size=len(frame.audio) if frame.audio else 0,
                       sample_rate=getattr(frame, 'sample_rate', 'unknown'))
            
            # Improved VAD with timing controls
            if frame.audio and len(frame.audio) > 0:
                logger.debug("🎤 VAD processing audio frame", frame_size=len(frame.audio))
                import struct
                import math
                import time
                
                try:
                    current_time = time.time() * 1000  # ms
                    
                    # 16-bit PCM samples'ı al
                    samples = struct.unpack(f'<{len(frame.audio)//2}h', frame.audio)
                    rms = math.sqrt(sum(s*s for s in samples) / len(samples))
                    
                    is_active = rms > self._speech_threshold
                    
                    logger.debug("🎤 VAD analysis", 
                                 rms=rms, 
                                 threshold=self._speech_threshold,
                                 is_active=is_active,
                                 is_speaking=self._is_speaking)
                    
                    # Speech detection logic with timing
                    if is_active:
                        if not self._is_speaking:
                            if self._speech_start_time is None:
                                self._speech_start_time = current_time
                                logger.debug("🎤 Speech detection started", rms=rms)
                            elif (current_time - self._speech_start_time) >= self._min_speech_duration_ms:
                                self._is_speaking = True
                                self._silence_start_time = None
                                speech_frame = UserStartedSpeakingFrame()  
                                await self.push_frame(speech_frame, direction)
                                logger.info("🎤 Speech started", rms=rms, duration_ms=current_time - self._speech_start_time)
                        else:
                            self._silence_start_time = None  # Reset silence timer
                    else:
                        # No activity - check for speech end
                        if self._is_speaking:
                            if self._silence_start_time is None:
                                self._silence_start_time = current_time
                                logger.debug("🎤 Silence detection started")
                            elif (current_time - self._silence_start_time) >= self._min_silence_duration_ms:
                                self._is_speaking = False
                                self._speech_start_time = None
                                speech_frame = UserStoppedSpeakingFrame()
                                await self.push_frame(speech_frame, direction)
                                logger.info("🎤 Speech stopped", silence_duration_ms=current_time - self._silence_start_time)
                        else:
                            self._speech_start_time = None  # Reset speech timer
                            
                except Exception as e:
                    logger.warning("VAD processing error", error=str(e), frame_size=len(frame.audio))
            else:
                logger.warning("🎤 VAD received empty audio frame")
        
        # Frame'i devam ettir
        logger.debug("🎤 VAD pushing frame downstream", frame_type=type(frame).__name__)
        await self.push_frame(frame, direction)
        logger.debug("🎤 VAD frame pushed successfully")

class STTProcessor(FrameProcessor):
    """Speech-to-Text processor using a Pipecat STTService."""
    
    def __init__(self, stt_service: STTService, **kwargs):
        super().__init__(**kwargs)
        self.stt_service = stt_service
        logger.info("STTProcessor initialized", service_type=type(self.stt_service).__name__)

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        """Processes a frame and passes it to the STT service."""
        await self.stt_service.process_frame(frame, direction)

    async def _on_downstream_frame(self, frame: Frame):
        # The STT service will push transcription frames, which need to be
        # pushed downstream from this processor.
        await self.push_frame(frame, FrameDirection.DOWNSTREAM)

class LLMProcessor(FrameProcessor):
    """Large Language Model processor using a Pipecat LLMService."""
    
    def __init__(self, llm_service: LLMService, **kwargs):
        super().__init__(**kwargs)
        self.llm_service = llm_service
        logger.info("LLMProcessor initialized", service_type=type(self.llm_service).__name__)
        self._history = []

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        """Processes a frame, collects transcriptions, and passes them to the LLM service."""
        
        if isinstance(frame, TranscriptionFrame):
            # For now, let's assume we send the full transcription to the LLM.
            # A more advanced implementation could buffer or handle interim results.
            if frame.text and frame.text.strip():
                logger.info("LLMProcessor received transcription", text=frame.text)
                self._history.append({"role": "user", "content": frame.text})
                await self.llm_service.process_frame(LLMMessagesFrame(messages=self._history), direction)
        elif isinstance(frame, (StartFrame, EndFrame)):
             await self.llm_service.process_frame(frame, direction)
        else:
            # Forward other frames if necessary
            await self.push_frame(frame, direction)

    async def _on_downstream_frame(self, frame: Frame):
         # The LLM service will push TextFrames, which need to be pushed downstream.
        if isinstance(frame, TextFrame):
            self._history.append({"role": "assistant", "content": frame.text})
        await self.push_frame(frame, FrameDirection.DOWNSTREAM)

class TTSProcessor(FrameProcessor):
    """Text-to-Speech processor using a Pipecat TTSService."""
    
    def __init__(self, tts_service: TTSService, **kwargs):
        super().__init__(**kwargs)
        self.tts_service = tts_service
        logger.info("TTSProcessor initialized", service_type=type(self.tts_service).__name__)

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        """Processes a frame and passes it to the TTS service."""
        await self.tts_service.process_frame(frame, direction)

    async def _on_downstream_frame(self, frame: Frame):
        # The TTS service will push AudioRawFrames, which need to be
        # pushed downstream from this processor.
        await self.push_frame(frame, FrameDirection.DOWNSTREAM) 