"""
Pipeline Manager - Windows uyumlu basit versiyon
"""

import asyncio
import logging
from typing import Optional, List
import structlog

from pipecat.frames.frames import Frame, AudioRawFrame, StartFrame, EndFrame
from pipecat.clocks.system_clock import SystemClock

# Local imports
from pipeline.stages import VADProcessor, STTProcessor, LLMProcessor, TTSProcessor

logger = structlog.get_logger()

class SimplePipelineManager:
    """Basit pipeline yöneticisi - Windows uyumlu"""
    
    def __init__(self):
        self._processors: List = []
        self._clock: Optional[SystemClock] = None
        self._is_running = False
        self._lock = asyncio.Lock()
        
        logger.info("SimplePipelineManager initialized")
    
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
                logger.info("Simple pipeline started successfully")
                
            except Exception as e:
                logger.error("Failed to start simple pipeline", error=str(e))
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
            
            # Frame'i pipeline'dan geçir
            await self._process_frame_through_pipeline(audio_frame)
            
            logger.debug("Audio frame processed through pipeline", size=len(pcm_bytes))
            
        except Exception as e:
            logger.error("Error processing audio through pipeline", error=str(e))
    
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
    
    @property
    def is_running(self) -> bool:
        """Pipeline çalışıyor mu?"""
        return self._is_running

# Alias for backward compatibility
PipelineManager = SimplePipelineManager 