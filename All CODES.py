"""
# OpenSIPS AI Voice Connector - Pipeline & Transports Code

## src/pipeline/__init__.py
from .manager import PipelineManager  # noqa: F401 

## src/pipeline/manager.py
import asyncio
import logging
from typing import Optional, List
import structlog

from pipecat.frames.frames import Frame, AudioRawFrame, StartFrame, EndFrame, TextFrame
from pipecat.clocks.system_clock import SystemClock

# Local imports
from pipeline.stages import VADProcessor, STTProcessor, LLMProcessor, TTSProcessor
from pipeline.interruption import InterruptionManager, MinWordsInterruptionStrategy, VolumeBasedInterruptionStrategy

logger = structlog.get_logger()

class SimplePipelineManager:
    def __init__(self, llm_service=None, stt_service=None, tts_service=None, enable_interruption: bool = True):
        self._processors: List = []
        self._clock: Optional[SystemClock] = None
        self._is_running = False
        self._lock = asyncio.Lock()
        
        # Services
        self._llm_service = llm_service
        self._stt_service = stt_service
        self._tts_service = tts_service
        
        # Interruption Manager
        self._interruption_manager = None
        self._enable_interruption = enable_interruption
        
        # State tracking
        self._bot_speaking = False
        self._user_speaking = False
        
        logger.info("SimplePipelineManager initialized", 
                   enable_interruption=enable_interruption)
    
    async def start(self) -> None:
        async with self._lock:
            if self._is_running:
                logger.warning("Pipeline already running")
                return
            
            try:
                # System clock oluştur
                self._clock = SystemClock()
                
                # Processor'ları oluştur
                self._processors = [
                    VADProcessor(),
                    STTProcessor(),
                    LLMProcessor(),
                    TTSProcessor()
                ]
                
                # Interruption Manager'ı başlat
                if self._enable_interruption:
                    await self._setup_interruption_manager()
                
                # Processor'ları manuel olarak link et
                for i in range(len(self._processors) - 1):
                    current = self._processors[i]
                    next_proc = self._processors[i + 1]
                    
                    # Manual linking - basit callback sistemi
                    current._next_processor = next_proc
                
                # Start frame'ini gönder
                start_frame = StartFrame()
                await self._process_frame_through_pipeline(start_frame)
                
                self._is_running = True
                logger.info("Simple pipeline started successfully", 
                           interruption_enabled=self._enable_interruption)
                
            except Exception as e:
                logger.error("Failed to start simple pipeline", error=str(e))
                raise
    
    async def _setup_interruption_manager(self):
        try:
            # Interruption strategies
            strategies = [
                MinWordsInterruptionStrategy(min_words=2),  # 2 kelime sonra kesebilir
                VolumeBasedInterruptionStrategy(volume_threshold=0.6, min_duration_ms=300)  # Yüksek ses 300ms
            ]
            
            self._interruption_manager = InterruptionManager(strategies=strategies)
            logger.info("Interruption manager setup completed",
                       strategies=[type(s).__name__ for s in strategies])
                       
        except Exception as e:
            logger.error("Failed to setup interruption manager", error=str(e))
            raise
    
    async def stop(self) -> None:
        async with self._lock:
            if not self._is_running:
                return
            
            try:
                # End frame'ini gönder
                end_frame = EndFrame()
                await self._process_frame_through_pipeline(end_frame)
                
                # Interruption manager'ı temizle
                if self._interruption_manager:
                    await self._interruption_manager.reset_interruption()
                
                self._processors = []
                self._clock = None
                self._is_running = False
                
                logger.info("Simple pipeline stopped successfully")
                
            except Exception as e:
                logger.error("Error stopping simple pipeline", error=str(e))
    
    async def push_audio(self, pcm_bytes: bytes) -> None:
        if not self._is_running:
            logger.warning("Pipeline not running, cannot push audio")
            return
        
        try:
            # Audio frame oluştur
            audio_frame = AudioRawFrame(
                audio=pcm_bytes,
                sample_rate=16000,
                num_channels=1
            )
            
            # Interruption manager'a ses verisi gönder
            if self._interruption_manager and self._user_speaking:
                await self._interruption_manager.append_user_audio(pcm_bytes, 16000)
            
            # Frame'i pipeline'dan geçir
            await self._process_frame_through_pipeline(audio_frame)
            
            logger.debug("Audio frame processed through pipeline", size=len(pcm_bytes))
            
        except Exception as e:
            logger.error("Error processing audio through pipeline", error=str(e))
    
    async def handle_user_text(self, text: str) -> None:
        if not self._is_running:
            return
            
        try:
            # Interruption manager'a metin gönder
            if self._interruption_manager:
                await self._interruption_manager.append_user_text(text)
                
                # Interruption kontrolü yap
                interrupted = await self._interruption_manager.check_interruption()
                if interrupted:
                    logger.info("🛑 User interrupted bot!", text=text[:30])
                    await self._handle_interruption()
            
            # Text frame'i pipeline'a gönder
            text_frame = TextFrame(text=text)
            await self._process_frame_through_pipeline(text_frame)
            
        except Exception as e:
            logger.error("Error handling user text", error=str(e), text=text[:50])
    
    async def set_user_speaking(self, speaking: bool) -> None:
        self._user_speaking = speaking
        
        if self._interruption_manager:
            await self._interruption_manager.set_user_speaking(speaking)
        
        logger.debug("User speaking state updated", speaking=speaking)
    
    async def set_bot_speaking(self, speaking: bool) -> None:
        self._bot_speaking = speaking
        
        if self._interruption_manager:
            await self._interruption_manager.set_bot_speaking(speaking)
        
        logger.debug("Bot speaking state updated", speaking=speaking)
    
    async def _handle_interruption(self) -> None:
        try:
            # Bot'u durdur
            await self.set_bot_speaking(False)
            
            # TTS'i durdur (eğer varsa)
            if self._tts_service and hasattr(self._tts_service, 'stop_playback'):
                await self._tts_service.stop_playback()
            
            # LLM generation'ı durdur (eğer varsa)
            if self._llm_service and hasattr(self._llm_service, 'stop_generation'):
                await self._llm_service.stop_generation()
            
            logger.info("🛑 Interruption handled - bot stopped")
            
        except Exception as e:
            logger.error("Error handling interruption", error=str(e))
    
    async def _process_frame_through_pipeline(self, frame: Frame) -> None:
        current_frame = frame
        
        for i, processor in enumerate(self._processors):
            try:
                logger.debug(f"Processing frame through {processor.__class__.__name__}")
                
                # Frame'i processor'a gönder
                if hasattr(processor, 'process_frame'):
                    from pipecat.processors.frame_processor import FrameDirection
                    await processor.process_frame(current_frame, FrameDirection.DOWNSTREAM)
                else:
                    logger.warning(f"Processor {processor.__class__.__name__} has no process_frame method")
                
            except Exception as e:
                logger.error(f"Error in processor {processor.__class__.__name__}", error=str(e))
                # Continue with next processor
    
    def get_interruption_status(self) -> dict:
        if not self._interruption_manager:
            return {"enabled": False}
        
        status = self._interruption_manager.get_status()
        status["enabled"] = True
        return status
    
    @property
    def is_running(self) -> bool:
        return self._is_running
    
    @property
    def interruption_enabled(self) -> bool:
        return self._enable_interruption and self._interruption_manager is not None

# Alias for backward compatibility
PipelineManager = SimplePipelineManager

## src/pipeline/stages.py
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
    def __init__(self, **kwargs):
        self._next_processor = None
    
    async def process_frame(self, frame: Frame, direction=None) -> None:
        pass
    
    async def push_frame(self, frame: Frame, direction=None) -> None:
        if self._next_processor:
            await self._next_processor.process_frame(frame, direction)

class VADProcessor(BaseProcessor):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._is_speaking = False
        logger.info("VADProcessor initialized (simplified)")
    
    async def process_frame(self, frame: Frame, direction=None) -> None:
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
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._stt_service = VoskWebsocketSTTService(url="ws://vosk-server:2700")
        self._is_started = False
        logger.info("STTProcessor initialized (simplified)")
    
    async def process_frame(self, frame: Frame, direction=None) -> None:
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
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._llm_service = LlamaWebsocketLLMService(url="ws://llm-turkish-server:8765")
        self._is_started = False
        logger.info("LLMProcessor initialized with LLaMA WebSocket")
    
    async def process_frame(self, frame: Frame, direction=None) -> None:
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
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._tts_service = PiperWebsocketTTSService(url="ws://piper-tts-server:8000/tts")
        self._is_started = False
        logger.info("TTSProcessor initialized with Piper WebSocket")
    
    async def process_frame(self, frame: Frame, direction=None) -> None:
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

## src/pipeline/interruption.py
import asyncio
import time
from abc import ABC, abstractmethod
from typing import Optional, List
import structlog

logger = structlog.get_logger()

class BaseInterruptionStrategy(ABC):
    async def append_audio(self, audio: bytes, sample_rate: int):
        pass

    async def append_text(self, text: str):
        pass

    @abstractmethod
    async def should_interrupt(self) -> bool:
        pass

    @abstractmethod
    async def reset(self):
        pass

class MinWordsInterruptionStrategy(BaseInterruptionStrategy):
    def __init__(self, *, min_words: int = 2):
        super().__init__()
        self._min_words = min_words
        self._text = ""

    async def append_text(self, text: str):
        self._text += " " + text.strip()
        self._text = self._text.strip()

    async def should_interrupt(self) -> bool:
        word_count = len(self._text.split())
        interrupt = word_count >= self._min_words
        logger.debug(
            "Interruption strategy check",
            should_interrupt=interrupt,
            num_spoken_words=word_count,
            min_words=self._min_words,
            text=self._text[:50]
        )
        return interrupt

    async def reset(self):
        self._text = ""

class VolumeBasedInterruptionStrategy(BaseInterruptionStrategy):
    def __init__(self, *, volume_threshold: float = 0.5, min_duration_ms: int = 500):
        super().__init__()
        self._volume_threshold = volume_threshold
        self._min_duration_ms = min_duration_ms
        self._high_volume_start = None
        self._current_volume = 0.0
        self._last_audio_time = None
        
    async def append_audio(self, audio: bytes, sample_rate: int):
        try:
            import numpy as np
            # PCM bytes to numpy array
            audio_array = np.frombuffer(audio, dtype=np.int16)
            
            # Boş array kontrolü
            if len(audio_array) == 0:
                return
            
            # RMS hesapla - NaN kontrolü ile
            mean_square = np.mean(audio_array.astype(np.float64)**2)
            if mean_square < 0 or np.isnan(mean_square):
                rms = 0.0
            else:
                rms = np.sqrt(mean_square)
            
            # Normalize (0-1 arası) - güvenli normalizasyon
            if rms > 0:
                self._current_volume = min(rms / 32768.0, 1.0)
            else:
                self._current_volume = 0.0
            
            current_time = time.time() * 1000  # ms
            self._last_audio_time = current_time
            
            if self._current_volume > self._volume_threshold:
                if self._high_volume_start is None:
                    self._high_volume_start = current_time
            else:
                self._high_volume_start = None
                
        except Exception as e:
            logger.warning("Volume analysis error", error=str(e))
            self._current_volume = 0.0
    
    async def should_interrupt(self) -> bool:
        if self._high_volume_start is None:
            return False
            
        current_time = time.time() * 1000
        
        # Eğer son audio'dan beri çok zaman geçmişse, reset et
        if self._last_audio_time and (current_time - self._last_audio_time) > 1000:
            self._high_volume_start = None
            return False
            
        duration = current_time - self._high_volume_start
        interrupt = duration >= self._min_duration_ms
        
        logger.debug(
            "Volume-based interruption check",
            should_interrupt=interrupt,
            current_volume=self._current_volume,
            threshold=self._volume_threshold,
            duration_ms=duration,
            min_duration_ms=self._min_duration_ms
        )
        
        return interrupt
    
    async def reset(self):
        self._high_volume_start = None
        self._current_volume = 0.0
        self._last_audio_time = None

class InterruptionManager:
    def __init__(self, strategies: List[BaseInterruptionStrategy] = None):
        self.strategies = strategies or [MinWordsInterruptionStrategy(min_words=2)]
        self.bot_speaking = False
        self.user_speaking = False
        self.interruption_active = False
        self._reset_lock = asyncio.Lock()
        
        logger.info("InterruptionManager initialized", 
                   num_strategies=len(self.strategies),
                   strategy_types=[type(s).__name__ for s in self.strategies])
    
    async def set_bot_speaking(self, speaking: bool):
        self.bot_speaking = speaking
        logger.debug("Bot speaking state changed", speaking=speaking)
        
        if not speaking and self.interruption_active:
            # Bot durduysa interruption'ı sıfırla
            await self.reset_interruption()
    
    async def set_user_speaking(self, speaking: bool):
        self.user_speaking = speaking
        logger.debug("User speaking state changed", speaking=speaking)
        
        if not speaking:
            # Kullanıcı durduğunda interruption kontrolü yap
            await self.check_interruption()
    
    async def append_user_audio(self, audio: bytes, sample_rate: int):
        if self.user_speaking:
            for strategy in self.strategies:
                await strategy.append_audio(audio, sample_rate)
    
    async def append_user_text(self, text: str):
        if self.user_speaking and text.strip():
            for strategy in self.strategies:
                await strategy.append_text(text)
            
            logger.debug("User text appended to strategies", text=text[:30])
    
    async def check_interruption(self) -> bool:
        if not self.bot_speaking:
            return False
        
        # Tüm strategies'i kontrol et
        should_interrupt = False
        for strategy in self.strategies:
            if await strategy.should_interrupt():
                should_interrupt = True
                logger.info("Interruption triggered", 
                           strategy=type(strategy).__name__)
                break
        
        if should_interrupt:
            await self.trigger_interruption()
            return True
        
        return False
    
    async def trigger_interruption(self):
        if self.interruption_active:
            return
        
        self.interruption_active = True
        logger.info("🛑 Barge-in interruption triggered!")
        
        # Bot'u durdur (bu pipeline'a gönderilecek)
        await self.set_bot_speaking(False)
        
        # Strategies'i sıfırla
        await self.reset_strategies()
    
    async def reset_interruption(self):
        async with self._reset_lock:
            if self.interruption_active:
                self.interruption_active = False
                await self.reset_strategies()
                logger.debug("Interruption reset completed")
    
    async def reset_strategies(self):
        for strategy in self.strategies:
            await strategy.reset()
        logger.debug("All interruption strategies reset")
    
    def is_interruption_allowed(self) -> bool:
        return self.bot_speaking and self.user_speaking
    
    def get_status(self) -> dict:
        return {
            "bot_speaking": self.bot_speaking,
            "user_speaking": self.user_speaking,
            "interruption_active": self.interruption_active,
            "interruption_allowed": self.is_interruption_allowed(),
            "num_strategies": len(self.strategies),
            "strategy_types": [type(s).__name__ for s in self.strategies]
        }

## src/pipeline/ai_engine.py
import asyncio
import logging
from typing import Optional
import structlog

from pipeline.manager import PipelineManager
from transports.oavc_adapter import OAVCAdapter

logger = structlog.get_logger()

class PipelineAI:
    def __init__(self, call, cfg):
        self._call = call
        self._cfg = cfg
        self._pipeline_manager: Optional[PipelineManager] = None
        self._oavc_adapter: Optional[OAVCAdapter] = None
        self._is_running = False
        
        logger.info("PipelineAI initialized", 
                   call_id=getattr(call, 'call_id', 'unknown'),
                   ai_flavor=getattr(cfg, 'ai_flavor', 'pipecat'))
    
    async def start(self) -> None:
        if self._is_running:
            logger.warning("PipelineAI already running")
            return
        
        try:
            # Pipeline manager'ı oluştur ve başlat
            self._pipeline_manager = PipelineManager()
            await self._pipeline_manager.start()
            logger.info("Pipeline manager started")
            
            # OAVC adapter'ı oluştur ve başlat
            self._oavc_adapter = OAVCAdapter(self._pipeline_manager)
            await self._oavc_adapter.start()
            logger.info("OAVC adapter started")
            
            self._is_running = True
            logger.info("PipelineAI started successfully")
            
        except Exception as e:
            logger.error("Failed to start PipelineAI", error=str(e))
            raise
    
    async def stop(self) -> None:
        if not self._is_running:
            return
        
        try:
            if self._oavc_adapter:
                await self._oavc_adapter.stop()
                logger.info("OAVC adapter stopped")
            
            if self._pipeline_manager:
                await self._pipeline_manager.stop()
                logger.info("Pipeline manager stopped")
            
            self._pipeline_manager = None
            self._oavc_adapter = None
            self._is_running = False
            
            logger.info("PipelineAI stopped successfully")
            
        except Exception as e:
            logger.error("Error stopping PipelineAI", error=str(e))
    
    async def process_rtp_payload(self, pcmu_payload: bytes) -> None:
        if not self._is_running or not self._oavc_adapter:
            logger.warning("PipelineAI not running, cannot process RTP")
            return
        
        try:
            # OAVC adapter ile PCMU'yu pipeline'a gönder
            await self._oavc_adapter.feed_pcmu(pcmu_payload)
            
            logger.debug("RTP payload processed", size=len(pcmu_payload))
            
        except Exception as e:
            logger.error("Error processing RTP payload", error=str(e))
    
    @property
    def is_running(self) -> bool:
        return self._is_running
    
    def __repr__(self) -> str:
        return f"PipelineAI(call_id={getattr(self._call, 'call_id', 'unknown')}, running={self._is_running})"

## src/transports/__init__.py
#

## src/transports/oavc_adapter.py
from __future__ import annotations

import asyncio
import logging
from typing import Optional
import structlog

from pipeline.manager import PipelineManager
from transports.audio_utils import pcmu_to_pcm16k

logger = structlog.get_logger()

class OAVCAdapter:
    def __init__(self, pipeline_manager):
        self._pipeline_manager = pipeline_manager
        self._executor = None
        
        logger.info("OAVCAdapter initialized")

    async def feed_pcmu(self, pcmu_bytes: bytes) -> None:
        if not pcmu_bytes or len(pcmu_bytes) == 0:
            logger.debug("Empty PCMU data, skipping")
            return
        
        try:
            # PCMU'yu PCM16k'ya çevir
            pcm_data = pcmu_to_pcm16k(pcmu_bytes)
            
            if not pcm_data or len(pcm_data) == 0:
                logger.warning("PCMU to PCM conversion failed or empty result")
                return
            
            logger.debug("PCMU conversion successful", 
                        pcmu_size=len(pcmu_bytes), 
                        pcm_size=len(pcm_data))
            
            # PCM verisini pipeline'a gönder
            if self._pipeline_manager and self._pipeline_manager.is_running:
                await self._pipeline_manager.push_audio(pcm_data)
                logger.debug("Audio pushed to pipeline")
            else:
                logger.warning("Pipeline manager not running, cannot push audio")
                
        except Exception as e:
            logger.error("Error in OAVC adapter feed_pcmu", error=str(e))
            # Hata detayları için
            import traceback
            logger.debug("OAVC adapter error traceback", traceback=traceback.format_exc())

    async def start(self) -> None:
        try:
            # Thread pool executor oluştur (gerekirse)
            import concurrent.futures
            self._executor = concurrent.futures.ThreadPoolExecutor(max_workers=2)
            
            logger.info("OAVC adapter started")
            
        except Exception as e:
            logger.error("Error starting OAVC adapter", error=str(e))
    
    async def stop(self) -> None:
        try:
            if self._executor:
                self._executor.shutdown(wait=True)
                self._executor = None
            
            logger.info("OAVC adapter stopped")
            
        except Exception as e:
            logger.error("Error stopping OAVC adapter", error=str(e))
    
    def __repr__(self) -> str:
        return f"OAVCAdapter(pipeline_running={self._pipeline_manager.is_running if self._pipeline_manager else False})"

## src/transports/audio_utils.py
from __future__ import annotations

import logging
from typing import Tuple, Union

import numpy as np
import struct

# Simple μ-law codec implementation 
# Constants for μ-law conversion
BIAS = 0x84
CLIP = 32635
SIGN_BIT = 0x80
QUANT_MASK = 0xf
NSEGS = 8
SEG_SHIFT = 4
SEG_MASK = 0x70

logger = logging.getLogger(__name__)

# Constants
ULAW_SAMPLE_RATE = 8000  # Hz
PCM_TARGET_SAMPLE_RATE = 16000  # Hz expected by pipeline

# G.711 μ-law decode tablosu
ULAW_DECODE_TABLE = np.array([
    -32124, -31100, -30076, -29052, -28028, -27004, -25980, -24956,
    -23932, -22908, -21884, -20860, -19836, -18812, -17788, -16764,
    -15996, -15484, -14972, -14460, -13948, -13436, -12924, -12412,
    -11900, -11388, -10876, -10364, -9852, -9340, -8828, -8316,
    -7932, -7676, -7420, -7164, -6908, -6652, -6396, -6140,
    -5884, -5628, -5372, -5116, -4860, -4604, -4348, -4092,
    -3900, -3772, -3644, -3516, -3388, -3260, -3132, -3004,
    -2876, -2748, -2620, -2492, -2364, -2236, -2108, -1980,
    -1884, -1820, -1756, -1692, -1628, -1564, -1500, -1436,
    -1372, -1308, -1244, -1180, -1116, -1052, -988, -924,
    -876, -844, -812, -780, -748, -716, -684, -652,
    -620, -588, -556, -524, -492, -460, -428, -396,
    -372, -356, -340, -324, -308, -292, -276, -260,
    -244, -228, -212, -196, -180, -164, -148, -132,
    -120, -112, -104, -96, -88, -80, -72, -64,
    -56, -48, -40, -32, -24, -16, -8, 0,
    32124, 31100, 30076, 29052, 28028, 27004, 25980, 24956,
    23932, 22908, 21884, 20860, 19836, 18812, 17788, 16764,
    15996, 15484, 14972, 14460, 13948, 13436, 12924, 12412,
    11900, 11388, 10876, 10364, 9852, 9340, 8828, 8316,
    7932, 7676, 7420, 7164, 6908, 6652, 6396, 6140,
    5884, 5628, 5372, 5116, 4860, 4604, 4348, 4092,
    3900, 3772, 3644, 3516, 3388, 3260, 3132, 3004,
    2876, 2748, 2620, 2492, 2364, 2236, 2108, 1980,
    1884, 1820, 1756, 1692, 1628, 1564, 1500, 1436,
    1372, 1308, 1244, 1180, 1116, 1052, 988, 924,
    876, 844, 812, 780, 748, 716, 684, 652,
    620, 588, 556, 524, 492, 460, 428, 396,
    372, 356, 340, 324, 308, 292, 276, 260,
    244, 228, 212, 196, 180, 164, 148, 132,
    120, 112, 104, 96, 88, 80, 72, 64,
    56, 48, 40, 32, 24, 16, 8, 0
], dtype=np.int16)

def pcmu_to_pcm16(pcmu_bytes: bytes) -> bytes:
    if not pcmu_bytes:
        return b''
    
    try:
        # PCMU bytes'ı numpy array'e çevir
        pcmu_array = np.frombuffer(pcmu_bytes, dtype=np.uint8)
        
        # μ-law decode tablosunu kullanarak decode et
        pcm_array = ULAW_DECODE_TABLE[pcmu_array]
        
        # 16-bit signed PCM bytes'a çevir
        return pcm_array.astype(np.int16).tobytes()
        
    except Exception as e:
        logger.error(f"PCMU to PCM16 conversion error: {e}")
        return b''

def resample_pcm(pcm_bytes: bytes, input_rate: int, output_rate: int) -> bytes:
    if not pcm_bytes or input_rate == output_rate:
        return pcm_bytes
    
    try:
        # Bytes'ı 16-bit signed array'e çevir
        pcm_array = np.frombuffer(pcm_bytes, dtype=np.int16)
        
        if len(pcm_array) == 0:
            return b''
        
        # Resampling ratio hesapla
        ratio = output_rate / input_rate
        output_length = int(len(pcm_array) * ratio)
        
        if output_length == 0:
            return b''
        
        # Linear interpolation ile resample
        input_indices = np.arange(len(pcm_array))
        output_indices = np.linspace(0, len(pcm_array) - 1, output_length)
        
        resampled = np.interp(output_indices, input_indices, pcm_array.astype(np.float32))
        
        # 16-bit signed'a geri çevir
        return resampled.astype(np.int16).tobytes()
        
    except Exception as e:
        logger.error(f"PCM resampling error: {e}")
        return pcm_bytes

def pcmu_to_pcm16k(pcmu_bytes: bytes) -> bytes:
    if not pcmu_bytes:
        return b''
    
    try:
        # PCMU → PCM 16-bit (8kHz)
        pcm_8k = pcmu_to_pcm16(pcmu_bytes)
        
        if not pcm_8k:
            return b''
        
        # 8kHz → 16kHz resample
        pcm_16k = resample_pcm(pcm_8k, 8000, 16000)
        
        return pcm_16k
        
    except Exception as e:
        logger.error("PCMU to PCM16k conversion error", error=str(e))
        return b''

# μ-law encoding function - direct implementation for better performance
def linear_to_ulaw(sample: int) -> int:
    # Get the sign and absolute value
    sign = 0
    if sample < 0:
        sign = 0x80
        sample = -sample
    
    # Clip to avoid overflow
    if sample > CLIP:
        sample = CLIP
    
    # Add bias
    sample = sample + BIAS
    
    # Find segment
    seg = 8
    for i in range(8):
        if sample <= (0xFF << i):
            seg = i
            break
    
    if seg >= 8:
        return sign | 0x7F
    
    # Quantization
    result = sign | ((seg << 4) | ((sample >> (seg + 3)) & 0x0F))
    
    # Invert bits for μ-law
    return ~result & 0xFF

def pcm16_to_pcmu(pcm_bytes: bytes) -> bytes:
    if not pcm_bytes:
        return b''
    
    try:
        # Bytes'ı 16-bit signed array'e çevir
        pcm_array = np.frombuffer(pcm_bytes, dtype=np.int16)
        
        if len(pcm_array) == 0:
            return b''
        
        # Convert each sample to μ-law
        ulaw_array = np.zeros(len(pcm_array), dtype=np.uint8)
        for i in range(len(pcm_array)):
            ulaw_array[i] = linear_to_ulaw(int(pcm_array[i]))
        
        return ulaw_array.tobytes()
        
    except Exception as e:
        logger.error(f"PCM16 to PCMU conversion error: {e}")
        return b''

def pcm16k_to_pcmu(pcm_bytes: bytes) -> bytes:
    if not pcm_bytes:
        return b''
    
    try:
        # 16kHz → 8kHz resample
        pcm_8k = resample_pcm(pcm_bytes, 16000, 8000)
        
        if not pcm_8k:
            return b''
        
        # PCM 16-bit → PCMU
        pcmu = pcm16_to_pcmu(pcm_8k)
        
        return pcmu
        
    except Exception as e:
        logger.error("PCM16k to PCMU conversion error", error=str(e))
        return b''

def validate_pcm_format(pcm_bytes: bytes, expected_sample_rate: int = 16000) -> bool:
    if not pcm_bytes:
        return False
    
    # Check length is multiple of 2 (16-bit samples)
    if len(pcm_bytes) % 2 != 0:
        return False
    
    # Check minimum size (at least 10ms of audio)
    min_samples = expected_sample_rate // 100
    if len(pcm_bytes) < min_samples * 2:
        return False
    
    # Check for extreme values that might indicate format issues
    pcm_array = np.frombuffer(pcm_bytes, dtype=np.int16)
    if np.max(np.abs(pcm_array)) == 0:
        return False  # Silent audio
    
    return True

## src/transports/call_manager.py
import random
import socket
import asyncio
import logging
import secrets
import datetime
from queue import Queue, Empty
from typing import Optional, Dict, Any
import structlog

from transports.rtp_utils import decode_rtp_packet, generate_rtp_packet
from transports.audio_utils import pcmu_to_pcm16k, pcm16k_to_pcmu
from config import Config

logger = structlog.get_logger()

# RTP port management - will be initialized when first Call is created
_available_ports = None
_min_rtp_port = 35000
_max_rtp_port = 65000

def _init_rtp_ports():
    global _available_ports, _min_rtp_port, _max_rtp_port
    
    if _available_ports is not None:
        return  # Already initialized
    
    try:
        rtp_cfg = Config.get("rtp")
        _min_rtp_port = int(rtp_cfg.get("min_port", "35000"))
        _max_rtp_port = int(rtp_cfg.get("max_port", "65000"))
        logger.info("RTP config loaded", min_port=_min_rtp_port, max_port=_max_rtp_port)
    except (TypeError, ValueError, AttributeError):
        # Fallback values if config is not available
        logger.warning("RTP config not available, using defaults", 
                      min_port=_min_rtp_port, max_port=_max_rtp_port)
    
    _available_ports = set(range(_min_rtp_port, _max_rtp_port))
    logger.info("RTP port pool initialized", total_ports=len(_available_ports))

class NoAvailablePorts(Exception):
    pass

class Call:
    def __init__(self, b2b_key: str, mi_conn, sdp_info: dict, pipeline_manager, config: dict = None):
        # RTP configuration
        _init_rtp_ports()  # Ensure RTP config is loaded
        
        try:
            rtp_cfg = Config.get("rtp")
            host_ip = rtp_cfg.get('bind_ip', '0.0.0.0')
            rtp_ip = rtp_cfg.get('ip', None)
        except:
            host_ip = '0.0.0.0'
            rtp_ip = None
        
        # Get hostname if rtp_ip not configured
        if not rtp_ip:
            try:
                hostname = socket.gethostbyname(socket.gethostname())
            except socket.gaierror:
                hostname = "127.0.0.1"
            rtp_ip = hostname

        # Call properties
        self.b2b_key = b2b_key
        self.mi_conn = mi_conn
        self.pipeline_manager = pipeline_manager
        self.config = config or {}

        # Client RTP endpoint (from SDP)
        self.client_addr = sdp_info.get('media_ip') or sdp_info.get('connection_ip')
        self.client_port = sdp_info.get('media_port')
        
        # Call state
        self.paused = False
        self.terminated = False
        self.first_packet = True
        self.last_received_packet_time = datetime.datetime.now()

        # RTP queues and events
        self.rtp_out_queue = Queue()
        self.stop_event = asyncio.Event()
        self.stop_event.clear()

        # Create and bind RTP socket
        self.serversock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.bind_rtp_socket(host_ip)
        self.serversock.setblocking(False)

        # Generate SDP response
        self.response_sdp = self.generate_response_sdp(sdp_info, rtp_ip)

        logger.info("RTP listener initialized", 
                   call_key=b2b_key, 
                   client_addr=self.client_addr,
                   client_port=self.client_port)
        
        logger.info("RTP socket bound", 
                   call_key=b2b_key,
                   host_ip=host_ip, 
                   port=self.serversock.getsockname()[1])

    def bind_rtp_socket(self, host_ip: str):
        global _available_ports
        
        #"""