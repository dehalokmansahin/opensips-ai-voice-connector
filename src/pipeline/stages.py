"""
Pipeline Stages - Basitleştirilmiş Windows uyumlu versiyon
"""

import asyncio
import logging
from typing import Optional
import structlog

from pipecat.frames.frames import (
    Frame,
    AudioRawFrame,
    StartFrame,
    EndFrame,
    UserStartedSpeakingFrame,
    UserStoppedSpeakingFrame,
    InterimTranscriptionFrame,
    TranscriptionFrame,
    LLMTextFrame,
    TextFrame,
)

# Absolute imports
from services.vosk_websocket import VoskWebsocketSTTService
from services.piper_websocket import PiperWebsocketTTSService
from services.llama_websocket import LlamaWebsocketLLMService

logger = structlog.get_logger()

class BaseProcessor:
    """Basit processor base class"""
    
    def __init__(self, **kwargs):
        self._next_processor = None
    
    async def process_frame(self, frame: Frame, direction=None) -> None:
        """Frame'i işle - alt sınıflar override edecek"""
        pass
    
    async def push_frame(self, frame: Frame, direction=None) -> None:
        """Frame'i bir sonraki processor'a gönder"""
        if self._next_processor:
            await self._next_processor.process_frame(frame, direction)

class VADProcessor(BaseProcessor):
    """Voice Activity Detection processor - basitleştirilmiş"""
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._is_speaking = False
        logger.info("VADProcessor initialized (simplified)")
    
    async def process_frame(self, frame: Frame, direction=None) -> None:
        """Frame'leri işle"""
        
        if isinstance(frame, StartFrame):
            logger.info("VAD processor started")
        elif isinstance(frame, AudioRawFrame):
            # Basit VAD - ses seviyesi kontrolü
            if frame.audio and len(frame.audio) > 0:
                # Basit RMS hesapla
                import struct
                import math
                
                try:
                    # 16-bit PCM samples'ı al
                    samples = struct.unpack(f'<{len(frame.audio)//2}h', frame.audio)
                    rms = math.sqrt(sum(s*s for s in samples) / len(samples))
                    
                    # Threshold
                    speech_threshold = 1000  # Adjust as needed
                    
                    if rms > speech_threshold and not self._is_speaking:
                        self._is_speaking = True
                        speech_frame = UserStartedSpeakingFrame()
                        await self.push_frame(speech_frame, direction)
                        logger.debug("Speech started detected", rms=rms)
                    elif rms <= speech_threshold and self._is_speaking:
                        self._is_speaking = False
                        speech_frame = UserStoppedSpeakingFrame()
                        await self.push_frame(speech_frame, direction)
                        logger.debug("Speech stopped detected", rms=rms)
                        
                except Exception as e:
                    logger.warning("VAD processing error", error=str(e))
        
        # Frame'i devam ettir
        await self.push_frame(frame, direction)

class STTProcessor(BaseProcessor):
    """Speech-to-Text processor using Vosk WebSocket - basitleştirilmiş"""
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._stt_service = VoskWebsocketSTTService(url="ws://vosk-server:2700")
        self._is_started = False
        logger.info("STTProcessor initialized (simplified)")
    
    async def process_frame(self, frame: Frame, direction=None) -> None:
        """Frame'leri işle"""
        
        if isinstance(frame, StartFrame):
            if not self._is_started:
                await self._stt_service.start()
                self._is_started = True
                logger.info("STT service started")
        
        elif isinstance(frame, EndFrame):
            if self._is_started:
                await self._stt_service.stop()
                self._is_started = False
                logger.info("STT service stopped")
        
        elif isinstance(frame, AudioRawFrame):
            # Ses frame'ini STT servisine gönder
            if self._is_started and frame.audio:
                await self._stt_service.run_stt(frame.audio)
        
        # Frame'i devam ettir
        await self.push_frame(frame, direction)

class LLMProcessor(BaseProcessor):
    """Large Language Model processor using LLaMA WebSocket"""
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._llm_service = LlamaWebsocketLLMService(url="ws://llm-turkish-server:8765")
        self._is_started = False
        logger.info("LLMProcessor initialized with LLaMA WebSocket")
    
    async def process_frame(self, frame: Frame, direction=None) -> None:
        """Frame'leri işle"""
        
        if isinstance(frame, StartFrame):
            if not self._is_started:
                await self._llm_service.start()
                self._is_started = True
                logger.info("LLM service started")
        
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

class TTSProcessor(BaseProcessor):
    """Text-to-Speech processor using Piper WebSocket"""
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._tts_service = PiperWebsocketTTSService(url="ws://piper-tts-server:8000/tts")
        self._is_started = False
        logger.info("TTSProcessor initialized with Piper WebSocket")
    
    async def process_frame(self, frame: Frame, direction=None) -> None:
        """Frame'leri işle"""
        
        if isinstance(frame, StartFrame):
            if not self._is_started:
                await self._tts_service.start()
                self._is_started = True
                logger.info("TTS service started")
        
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