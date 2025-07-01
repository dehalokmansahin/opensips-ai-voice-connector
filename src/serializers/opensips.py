#!/usr/bin/env python3
"""
OpenSIPS Frame Serializer for Pipecat
Handles RTP/UDP audio frame serialization/deserialization following Twilio/Telnyx pattern
"""

import struct
from typing import Optional, Dict, Any
import asyncio
import structlog

# Pipecat imports
from pipecat.frames.frames import (
    Frame,
    StartFrame, 
    InputAudioRawFrame,
    AudioRawFrame
)
from pipecat.serializers.base_serializer import FrameSerializer, FrameSerializerType
from pipecat.audio.utils import create_default_resampler, pcm_to_ulaw, ulaw_to_pcm

logger = structlog.get_logger()

class OpenSIPSFrameSerializer(FrameSerializer):
    """
    OpenSIPS Frame Serializer for RTP/UDP audio
    Following Twilio/Telnyx pattern for consistency
    """
    
    def __init__(self, 
                 call_id: str,
                 media_ip: str = None, 
                 media_port: int = None):
        """Initialize OpenSIPS frame serializer"""
        self.call_id = call_id
        self.media_ip = media_ip
        self.media_port = media_port
        
        # Audio configuration
        self.rtp_sample_rate = 8000  # RTP typically uses 8kHz for ulaw
        self.pipeline_sample_rate = 16000  # Pipeline input rate (will be set in setup)
        
        # Audio resampler for format conversion
        self.resampler = create_default_resampler()
        
        # SDP info for OpenSIPS
        self.sdp_info = {
            'media_ip': media_ip,
            'media_port': media_port,
            'codec': 'PCMU',
            'sample_rate': self.rtp_sample_rate
        }
        
        logger.info("OpenSIPS frame serializer initialized",
                   call_id=call_id,
                   media_ip=media_ip,
                   media_port=media_port)
    
    @property
    def type(self) -> FrameSerializerType:
        """Serializer type - using BINARY for RTP audio data"""
        return FrameSerializerType.BINARY
    
    async def setup(self, frame: StartFrame):
        """Setup serializer with pipeline configuration"""
        self.pipeline_sample_rate = frame.audio_in_sample_rate
        
        logger.info("OpenSIPS serializer setup completed",
                   call_id=self.call_id,
                   pipeline_sample_rate=self.pipeline_sample_rate,
                   rtp_sample_rate=self.rtp_sample_rate)
    
    async def serialize(self, frame: Frame) -> str | bytes | None:
        """
        Serialize Pipecat frame to RTP/UDP audio data
        Convert PCM audio to ulaw format for RTP transmission
        """
        if isinstance(frame, AudioRawFrame):
            try:
                # Convert PCM at frame's rate to 8kHz μ-law for RTP
                ulaw_data = await pcm_to_ulaw(
                    frame.audio, 
                    frame.sample_rate, 
                    self.rtp_sample_rate, 
                    self.resampler
                )
                
                logger.debug("Audio frame serialized", 
                           call_id=self.call_id,
                           input_rate=frame.sample_rate,
                           output_rate=self.rtp_sample_rate,
                           input_size=len(frame.audio),
                           output_size=len(ulaw_data))
                
                return ulaw_data
                
            except Exception as e:
                logger.error("Audio serialization failed", 
                           call_id=self.call_id,
                           error=str(e))
                return None
        
        # Return None for unhandled frame types
        return None
    
    async def deserialize(self, data: str | bytes) -> Frame | None:
        """
        Deserialize RTP/UDP audio data to Pipecat InputAudioRawFrame
        Convert ulaw audio to PCM format for pipeline processing
        """
        if not isinstance(data, bytes):
            logger.warning("Non-bytes data received for deserialization",
                         call_id=self.call_id,
                         data_type=type(data))
            return None
        
        try:
            # Convert RTP's 8kHz μ-law to PCM at pipeline input rate
            pcm_audio = await ulaw_to_pcm(
                data, 
                self.rtp_sample_rate, 
                self.pipeline_sample_rate, 
                self.resampler
            )
            
            # Create input audio frame for pipeline
            audio_frame = InputAudioRawFrame(
                audio=pcm_audio,
                num_channels=1,
                sample_rate=self.pipeline_sample_rate
            )
            
            logger.debug("Audio frame deserialized",
                        call_id=self.call_id,
                        input_rate=self.rtp_sample_rate,
                        output_rate=self.pipeline_sample_rate,
                        input_size=len(data),
                        output_size=len(pcm_audio))
            
            return audio_frame
            
        except Exception as e:
            logger.error("Audio deserialization failed",
                        call_id=self.call_id,
                        error=str(e))
            return None
    
    def get_sdp_info(self) -> Dict[str, Any]:
        """Get SDP information for OpenSIPS response"""
        return self.sdp_info.copy()
    
    def update_sdp_info(self, media_ip: str = None, media_port: int = None):
        """Update SDP information"""
        if media_ip:
            self.media_ip = media_ip
            self.sdp_info['media_ip'] = media_ip
        
        if media_port:
            self.media_port = media_port
            self.sdp_info['media_port'] = media_port
        
        logger.info("SDP info updated",
                   call_id=self.call_id,
                   media_ip=self.media_ip,
                   media_port=self.media_port) 