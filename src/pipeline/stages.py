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
    UserStartedSpeakingFrame, UserStoppedSpeakingFrame
)
from pipecat.processors.frame_processor import FrameProcessor, FrameDirection

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
    """Speech-to-Text processor using Vosk WebSocket - basitleştirilmiş"""
    
    def __init__(self, stt_service=None, **kwargs):
        super().__init__(**kwargs)
        self._stt_service = stt_service or VoskWebsocketSTTService(url="ws://vosk-server:2700")
        self._is_started = False
        logger.info("STTProcessor initialized", service_type=type(self._stt_service).__name__)
    
    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        """Process frames following Pipecat pattern"""
        
        # First call the parent class process_frame to handle StartFrame, etc.
        await super().process_frame(frame, direction)
        
        logger.debug("STT processing frame", frame_type=type(frame).__name__)
        
        if isinstance(frame, StartFrame):
            if not self._is_started:
                try:
                    # Service availability check
                    if not self._stt_service:
                        logger.error("STT service not available")
                        return
                        
                    await self._stt_service.start()
                    self._is_started = True
                    logger.info("🗣️ STT service started successfully")
                except Exception as e:
                    logger.error("Failed to start STT service", error=str(e))
                    # Continue without STT - graceful degradation
        
        elif isinstance(frame, EndFrame):
            if self._is_started:
                await self._stt_service.stop()
                self._is_started = False
                logger.info("STT service stopped")
        
        elif isinstance(frame, (AudioRawFrame, InputAudioRawFrame)):
            # Handle audio frames for STT
            logger.info("🗣️ STT received audio frame", 
                       frame_type=type(frame).__name__,
                       audio_size=len(frame.audio) if frame.audio else 0,
                       stt_started=self._is_started)
            
            # Ses frame'ini STT servisine gönder
            if self._is_started and frame.audio:
                logger.debug("🗣️ Sending audio to STT service", audio_size=len(frame.audio))
                await self._stt_service.run_stt(frame.audio)
                logger.debug("🗣️ Audio sent to STT service successfully")
            elif not self._is_started:
                logger.warning("🗣️ STT service not started, dropping audio frame")
            elif not frame.audio:
                logger.warning("🗣️ Empty audio frame received")
        
        elif isinstance(frame, UserStartedSpeakingFrame):
            logger.info("🗣️ STT received UserStartedSpeakingFrame")
        
        elif isinstance(frame, UserStoppedSpeakingFrame):
            logger.info("🗣️ STT received UserStoppedSpeakingFrame")
        
        # Frame'i devam ettir
        logger.debug("🗣️ STT pushing frame downstream", frame_type=type(frame).__name__)
        await self.push_frame(frame, direction)
        logger.debug("🗣️ STT frame pushed successfully")

class LLMProcessor(FrameProcessor):
    """Large Language Model processor using LLaMA WebSocket"""
    
    def __init__(self, llm_service=None, **kwargs):
        super().__init__(**kwargs)
        self._llm_service = llm_service or LlamaWebsocketLLMService(url="ws://llm-turkish-server:8765", model="llama3.2:3b-instruct-turkish")
        self._is_started = False
        logger.info("LLMProcessor initialized", service_type=type(self._llm_service).__name__)
    
    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        """Process frames following Pipecat pattern"""
        
        # First call the parent class process_frame to handle StartFrame, etc.
        await super().process_frame(frame, direction)
        
        if isinstance(frame, StartFrame):
            if not self._is_started:
                try:
                    # Service availability check
                    if not self._llm_service:
                        logger.error("LLM service not available")
                        return
                        
                    await self._llm_service.start()
                    self._is_started = True
                    logger.info("LLM service started successfully")
                except Exception as e:
                    logger.error("Failed to start LLM service", error=str(e))
                    # Continue without LLM - graceful degradation
        
        elif isinstance(frame, EndFrame):
            if self._is_started:
                await self._llm_service.stop()
                self._is_started = False
                logger.info("LLM service stopped")
        
        elif isinstance(frame, TranscriptionFrame):
            # Transcription frame'ini LLM'e gönder (streaming)
            if self._is_started and frame.text and frame.text.strip():
                logger.info("Processing transcription with streaming LLM", text=frame.text)
                
                try:
                    # Streaming LLM frame'lerini al ve pipeline'a gönder
                    async for llm_frame in self._llm_service.run_llm(frame.text.strip()):
                        await self.push_frame(llm_frame, direction)
                        
                except Exception as e:
                    logger.error("Error in streaming LLM processing", error=str(e))
                    # Hata durumunda varsayılan yanıt
                    await self.push_frame(LLMFullResponseStartFrame(), direction)
                    await self.push_frame(LLMTextFrame(text="Bir sorun yaşadım. Tekrar dener misiniz?"), direction)
                    await self.push_frame(LLMFullResponseEndFrame(), direction)
        
        # Frame'i devam ettir
        await self.push_frame(frame, direction)

class TTSProcessor(FrameProcessor):
    """Text-to-Speech processor using Piper WebSocket"""
    
    def __init__(self, tts_service=None, **kwargs):
        super().__init__(**kwargs)
        self._tts_service = tts_service or PiperWebsocketTTSService(url="ws://piper-tts-server:8000/tts")
        self._is_started = False
        logger.info("TTSProcessor initialized", service_type=type(self._tts_service).__name__)
    
    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        """Process frames following Pipecat pattern"""
        
        # First call the parent class process_frame to handle StartFrame, etc.
        await super().process_frame(frame, direction)
        
        if isinstance(frame, StartFrame):
            if not self._is_started:
                try:
                    # Service availability check
                    if not self._tts_service:
                        logger.error("TTS service not available")
                        return
                        
                    await self._tts_service.start()
                    self._is_started = True
                    logger.info("TTS service started successfully")
                except Exception as e:
                    logger.error("Failed to start TTS service", error=str(e))
                    # Continue without TTS - graceful degradation
        
        elif isinstance(frame, EndFrame):
            if self._is_started:
                await self._tts_service.stop()
                self._is_started = False
                logger.info("TTS service stopped")
        
        elif isinstance(frame, TranscriptionFrame):
            # Transcription frame'ini TTS'e gönder (backward compatibility)
            if self._is_started and frame.text:
                logger.info("Processing transcription for TTS", text=frame.text)
                
                try:
                    # TTS frame'lerini al ve pipeline'a gönder
                    async for tts_frame in self._tts_service.run_tts(frame.text):
                        await self.push_frame(tts_frame, direction)
                        
                except Exception as e:
                    logger.error("Error in TTS processing", error=str(e))
        
        elif isinstance(frame, (TextFrame, LLMTextFrame)):
            # LLM'den gelen TextFrame/LLMTextFrame'leri TTS'e gönder
            if self._is_started and frame.text:
                logger.info("Processing LLM text for TTS", text=frame.text)
                
                try:
                    # TTS frame'lerini al ve pipeline'a gönder
                    async for tts_frame in self._tts_service.run_tts(frame.text):
                        await self.push_frame(tts_frame, direction)
                        
                except Exception as e:
                    logger.error("Error in TTS processing", error=str(e))
        
        # Frame'i devam ettir
        await self.push_frame(frame, direction) 