"""
Pipeline AI Engine - Temizlenmiş versiyon
"""

import asyncio
import logging
from typing import Optional, TYPE_CHECKING
import structlog

from pipeline.manager import EnhancedPipelineManager as PipelineManager
from transports.oavc_adapter import OAVCAdapter

if TYPE_CHECKING:
    from transports.call_manager import Call

logger = structlog.get_logger()

class PipelineAI:
    """Pipeline tabanlı AI Engine - OpenSIPS Call sistemi ile entegrasyon"""
    
    def __init__(self, call: "Call", cfg: dict):
        """
        PipelineAI constructor
        
        Args:
            call: OpenSIPS Call objesi
            cfg: Configuration objesi
        """
        self._call = call
        self._cfg = cfg
        self._pipeline_manager: Optional[PipelineManager] = self._call.pipeline_manager
        self._oavc_adapter: Optional[OAVCAdapter] = None
        self._is_running = False
        
        logger.info("PipelineAI initialized", 
                   call_id=getattr(self._call, 'b2b_key', 'unknown'),
                   ai_flavor=self._cfg.get('ai_flavor', 'pipecat'))
    
    async def start(self) -> None:
        """AI Engine'i başlat"""
        logger.info("⭕ PipelineAI.start called", is_running=self._is_running)
        if self._is_running:
            logger.warning("PipelineAI already running")
            return
        
        try:
            logger.info("🔧 Validating pre-started pipeline manager...")
            # The pipeline manager should already be started from main.py
            if not self._pipeline_manager or not self._pipeline_manager.is_running:
                logger.error("❌ Pipeline manager is not available or not running in PipelineAI.start. Aborting.")
                return

            logger.info("✅ Pipeline manager is running. Proceeding with PipelineAI start.")
            
            # OAVC adapter just needs to be instantiated with the running manager.
            self._oavc_adapter = OAVCAdapter(self._pipeline_manager)
            logger.info("🔧 OAVC adapter created successfully")
            
            self._is_running = True
            logger.info("✅ PipelineAI started successfully")
            
        except Exception as e:
            logger.error("❌ Failed to start PipelineAI", error=str(e), exc_info=True)
            # Do not re-raise, to avoid silent crash of the asyncio task.
    
    async def stop(self) -> None:
        """AI Engine'i durdur"""
        if not self._is_running:
            return
        
        try:
            # The OAVC adapter does not have a stop method.
            # We also don't want to stop the shared pipeline_manager here.
            # Its lifecycle is managed by the main application.
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
        logger.debug("🔄 PipelineAI.process_rtp_payload called", running=self._is_running, adapter_present=self._oavc_adapter is not None)
        if not self._is_running or not self._oavc_adapter:
            logger.warning("PipelineAI not running or adapter missing, cannot process RTP", 
                         running=self._is_running, 
                         adapter_present=bool(self._oavc_adapter))
            return
        
        try:
            logger.debug("🔗 PipelineAI feeding pcmu payload to OAVCAdapter", size=len(pcmu_payload))
            # OAVC adapter ile PCMU'yu pipeline'a gönder
            await self._oavc_adapter.feed_pcmu(pcmu_payload)
            
            logger.debug("RTP payload processed successfully by PipelineAI", size=len(pcmu_payload))
            
        except Exception as e:
            logger.error("Error processing RTP payload in PipelineAI", error=str(e), exc_info=True)
    
    @property
    def is_running(self) -> bool:
        """AI Engine çalışıyor mu?"""
        return self._is_running
    
    def __repr__(self) -> str:
        """String representation"""
        return f"PipelineAI(call_id={getattr(self._call, 'b2b_key', 'unknown')}, running={self._is_running})" 