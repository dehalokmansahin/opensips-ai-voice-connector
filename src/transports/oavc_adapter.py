"""Adapter layer between OpenSIPS Audio/Video Connector (OAVC) and our
Pipecat pipeline.

OpenSIPS RTP relays audio frames as PCMU/8000 (μ-law) 20 ms packets
(160 bytes). This adapter converts each packet to 16-kHz, 16-bit PCM and
forwards it into the pipeline via :class:`pipeline.manager.PipelineManager`.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional
import structlog

from pipecat.frames.frames import Frame, SystemFrame
from pipecat.processors.frame_processor import FrameDirection

# Use a forward reference for the type hint to avoid circular import
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from pipeline.manager import EnhancedPipelineManager as PipelineManager

logger = structlog.get_logger()


class OAVCAdapter:
    """Bridges raw RTP payloads from OAVC to the Pipecat pipeline."""

    def __init__(self, pipeline_manager: "PipelineManager"):
        """
        OAVC Adapter constructor
        
        Args:
            pipeline_manager: PipelineManager instance
        """
        self._pipeline_manager = pipeline_manager
        self._executor = None
        self._is_running = True
        
        logger.info("OAVCAdapter initialized")

    async def feed_pcmu(self, pcmu_bytes: bytes) -> None:
        """
        PCMU ses verisini pipeline'a gönder
        
        Args:
            pcmu_bytes: PCMU encoded audio data
        """
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
                # Check if audio input is enabled
                if hasattr(self._pipeline_manager, '_audio_in_enabled') and not self._pipeline_manager._audio_in_enabled:
                    logger.debug("Audio input disabled in pipeline manager")
                    return
                    
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
        """OAVC adapter'ı başlat"""
        try:
            # Thread pool executor oluştur (gerekirse)
            import concurrent.futures
            self._executor = concurrent.futures.ThreadPoolExecutor(max_workers=2)
            
            logger.info("OAVC adapter started")
            
        except Exception as e:
            logger.error("Error starting OAVC adapter", error=str(e))
    
    async def stop(self) -> None:
        """OAVC adapter'ı durdur"""
        try:
            if self._executor:
                self._executor.shutdown(wait=True)
                self._executor = None
            
            logger.info("OAVC adapter stopped")
            
        except Exception as e:
            logger.error("Error stopping OAVC adapter", error=str(e))
    
    def __repr__(self) -> str:
        """String representation"""
        return f"OAVCAdapter(pipeline_running={self._pipeline_manager.is_running if self._pipeline_manager else False})" 

    async def write_frame_to_pipeline(self, call_id: str, frame: Frame):
        # Implementation of write_frame_to_pipeline method
        pass 