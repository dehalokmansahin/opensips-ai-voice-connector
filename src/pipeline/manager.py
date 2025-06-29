"""
Pipeline Manager - Windows uyumlu basit versiyon
Interruption (Barge-in) desteği ile
"""

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
    """Basit pipeline yöneticisi - Windows uyumlu ve Interruption destekli"""
    
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
        """Pipeline'ı başlat"""
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
        """Interruption Manager'ı kur"""
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
        """Pipeline'ı durdur"""
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
        """Pipeline'a ses verisi gönder"""
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
        """Kullanıcı metni işle (STT'den gelen)"""
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
        """Kullanıcı konuşma durumunu güncelle"""
        self._user_speaking = speaking
        
        if self._interruption_manager:
            await self._interruption_manager.set_user_speaking(speaking)
        
        logger.debug("User speaking state updated", speaking=speaking)
    
    async def set_bot_speaking(self, speaking: bool) -> None:
        """Bot konuşma durumunu güncelle"""
        self._bot_speaking = speaking
        
        if self._interruption_manager:
            await self._interruption_manager.set_bot_speaking(speaking)
        
        logger.debug("Bot speaking state updated", speaking=speaking)
    
    async def _handle_interruption(self) -> None:
        """Interruption handling"""
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
        """Frame'i tüm processor'lardan geçir"""
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
        """Interruption durumunu döndür"""
        if not self._interruption_manager:
            return {"enabled": False}
        
        status = self._interruption_manager.get_status()
        status["enabled"] = True
        return status
    
    @property
    def is_running(self) -> bool:
        """Pipeline çalışıyor mu?"""
        return self._is_running
    
    @property
    def interruption_enabled(self) -> bool:
        """Interruption aktif mi?"""
        return self._enable_interruption and self._interruption_manager is not None

# Alias for backward compatibility
PipelineManager = SimplePipelineManager 