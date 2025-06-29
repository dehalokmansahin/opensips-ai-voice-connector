"""
Pipeline AI Engine - Temizlenmiş versiyon
"""

import asyncio
import logging
from typing import Optional
import structlog

from pipeline.manager import PipelineManager
from transports.oavc_adapter import OAVCAdapter

logger = structlog.get_logger()

class PipelineAI:
    """Pipeline tabanlı AI Engine - OpenSIPS Call sistemi ile entegrasyon"""
    
    def __init__(self, call, cfg):
        """
        PipelineAI constructor
        
        Args:
            call: OpenSIPS Call objesi
            cfg: Configuration objesi
        """
        self._call = call
        self._cfg = cfg
        self._pipeline_manager: Optional[PipelineManager] = None
        self._oavc_adapter: Optional[OAVCAdapter] = None
        self._is_running = False
        
        logger.info("PipelineAI initialized", 
                   call_id=getattr(call, 'call_id', 'unknown'),
                   ai_flavor=getattr(cfg, 'ai_flavor', 'pipecat'))
    
    async def start(self) -> None:
        """AI Engine'i başlat"""
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
        """AI Engine'i durdur"""
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
        """
        RTP payload'ını işle
        
        Args:
            pcmu_payload: PCMU encoded audio data (160 bytes = 20ms)
        """
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
        """AI Engine çalışıyor mu?"""
        return self._is_running
    
    def __repr__(self) -> str:
        """String representation"""
        return f"PipelineAI(call_id={getattr(self._call, 'call_id', 'unknown')}, running={self._is_running})" 