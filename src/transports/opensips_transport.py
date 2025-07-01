#!/usr/bin/env python3
"""
OpenSIPS Transport - Following Twilio/Telnyx Pattern
Simplified implementation using serializer and event handlers
"""

import asyncio
import socket
from typing import Optional, Dict, Any, Callable
import structlog

from pipecat.frames.frames import (
    Frame, InputAudioRawFrame, OutputAudioRawFrame, StartFrame, EndFrame,
    CancelFrame
)
from pipecat.transports.base_input import BaseInputTransport
from pipecat.transports.base_output import BaseOutputTransport  
from pipecat.transports.base_transport import BaseTransport, TransportParams
from pipecat.audio.vad.silero import SileroVADAnalyzer

# Import our new serializer
from serializers.opensips import OpenSIPSFrameSerializer

logger = structlog.get_logger()


class OpenSIPSTransportParams(TransportParams):
    """OpenSIPS Transport Parameters - Following Pydantic BaseModel pattern"""
    
    # OpenSIPS specific fields
    bind_ip: str = "0.0.0.0"
    bind_port: int = 0
    call_id: Optional[str] = None
    serializer: Optional[OpenSIPSFrameSerializer] = None
    
    # Default audio configuration for RTP
    audio_in_enabled: bool = True
    audio_out_enabled: bool = True
    audio_in_sample_rate: int = 8000   # RTP is 8kHz
    audio_out_sample_rate: int = 8000  # RTP output 8kHz


class OpenSIPSInputTransport(BaseInputTransport):
    """OpenSIPS Input Transport with UDP/RTP handling"""
    
    def __init__(self, transport: "OpenSIPSTransport", params: OpenSIPSTransportParams):
        super().__init__(params)
        self._transport = transport
        self._params = params
        self._receiver_task: Optional[asyncio.Task] = None
        self._socket: Optional[socket.socket] = None
        
    async def start(self, frame: StartFrame):
        """Start RTP receiver following Twilio/Telnyx pattern"""
        await super().start(frame)
        
        if not self._receiver_task:
            self._receiver_task = asyncio.create_task(self._receive_rtp_packets())
            logger.debug("RTP receiver task started")
        
        # Trigger on_client_connected event
        await self._transport._trigger_event("on_client_connected", self._transport, None)
        
        await self.push_frame(frame)
    
    async def stop(self, frame: EndFrame):
        """Stop RTP receiver"""
        await super().stop(frame)
        
        if self._receiver_task:
            self._receiver_task.cancel()
            try:
                await self._receiver_task
            except asyncio.CancelledError:
                pass
            self._receiver_task = None
        
        if self._socket:
            self._socket.close()
            self._socket = None
        
        # Trigger on_client_disconnected event
        await self._transport._trigger_event("on_client_disconnected", self._transport, None)
    
    async def cancel(self, frame: CancelFrame):
        """Cancel RTP receiver"""
        await super().cancel(frame)
        
        if self._receiver_task:
            self._receiver_task.cancel()
            self._receiver_task = None
        
        if self._socket:
            self._socket.close()
            self._socket = None
    
    async def _receive_rtp_packets(self):
        """RTP packet receiver - simplified following Twilio pattern"""
        try:
            # Create and bind socket
            self._socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self._socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self._socket.bind((self._params.bind_ip, self._params.bind_port))
            self._socket.setblocking(False)
            
            # Get actual bound address
            actual_addr = self._socket.getsockname()
            self._params.bind_port = actual_addr[1]  # Update with actual port
            
            logger.info("RTP receiver bound", 
                       bind_address=f"{self._params.bind_ip}:{self._params.bind_port}")
            
            loop = asyncio.get_running_loop()
            packet_count = 0
            
            while True:
                try:
                    data, addr = await loop.sock_recvfrom(self._socket, 2048)
                    packet_count += 1
                    
                    logger.debug("RTP packet received", 
                                packet_num=packet_count,
                                size=len(data), 
                                from_addr=f"{addr[0]}:{addr[1]}")
                    
                    # Use serializer to deserialize RTP packet - following Twilio/Telnyx pattern
                    if self._params.serializer:
                        frame = await self._params.serializer.deserialize(data)
                        if frame:
                            if isinstance(frame, InputAudioRawFrame):
                                await self.push_audio_frame(frame)  # Audio frames go to audio channel
                            else:
                                await self.push_frame(frame)        # Other frames go to normal channel
                    
                except ConnectionResetError:
                    continue
                except OSError as e:
                    if e.errno == 10054:  # Windows connection reset
                        continue
                    else:
                        logger.error("Socket error in RTP receiver", error=str(e))
                        await asyncio.sleep(0.01)
                except Exception as e:
                    logger.error("RTP receive error", error=str(e))
                    await asyncio.sleep(0.01)
                    
        except Exception as e:
            logger.error("Fatal error in RTP receiver", error=str(e))
            raise


class OpenSIPSOutputTransport(BaseOutputTransport):
    """OpenSIPS Output Transport with RTP sending"""
    
    def __init__(self, transport: "OpenSIPSTransport", params: OpenSIPSTransportParams):
        super().__init__(params)
        self._transport = transport
        self._params = params
        self._socket: Optional[socket.socket] = None
        
    async def start(self, frame: StartFrame):
        """Start output transport"""
        await super().start(frame)
        
        # Create UDP socket for sending
        self._socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        logger.debug("RTP sender socket created")
        
        await self.push_frame(frame)
    
    async def send_frame(self, frame: Frame):
        """Send frame using serializer - following Twilio/Telnyx pattern"""
        try:
            if isinstance(frame, OutputAudioRawFrame) and self._params.serializer:
                # Serialize frame to RTP packet
                rtp_packet = await self._params.serializer.serialize(frame)
                
                if rtp_packet and self._socket:
                    # Send to client if we have client info
                    client_ip = self._params.serializer.media_ip
                    client_port = self._params.serializer.media_port
                    
                    if client_ip and client_port:
                        await asyncio.get_running_loop().sock_sendto(
                            self._socket, rtp_packet, (client_ip, client_port)
                        )
                        
                        logger.debug("RTP packet sent", 
                                   size=len(rtp_packet),
                                   to_addr=f"{client_ip}:{client_port}")
                    else:
                        logger.debug("No client info for RTP sending")
            
            # Continue processing in pipeline
            await super().send_frame(frame)
            
        except Exception as e:
            logger.error("Error sending RTP packet", error=str(e))
            # Continue processing even if send fails
            await super().send_frame(frame)


class OpenSIPSTransport(BaseTransport):
    """
    OpenSIPS Transport - Following Twilio/Telnyx Pattern
    Using serializer and event handlers
    """
    
    def __init__(self, params: OpenSIPSTransportParams):
        super().__init__()
        self._params = params
        self._input_transport = OpenSIPSInputTransport(self, params)
        self._output_transport = OpenSIPSOutputTransport(self, params)
        
        # Event handlers - following Twilio/Telnyx pattern
        self._event_handlers: Dict[str, Callable] = {}
        
        logger.info("OpenSIPS Transport initialized", 
                   call_id=params.call_id,
                   bind_ip=params.bind_ip,
                   bind_port=params.bind_port)
    
    def input(self) -> OpenSIPSInputTransport:
        """Return input transport"""
        return self._input_transport
    
    def output(self) -> OpenSIPSOutputTransport:
        """Return output transport"""
        return self._output_transport
    
    def event_handler(self, event_name: str):
        """Event handler decorator - following Twilio/Telnyx pattern"""
        def decorator(func):
            self._event_handlers[event_name] = func
            logger.debug("Event handler registered", event_name=event_name)
            return func
        return decorator
    
    async def _trigger_event(self, event_name: str, *args, **kwargs):
        """Trigger event handler"""
        if event_name in self._event_handlers:
            try:
                await self._event_handlers[event_name](*args, **kwargs)
                logger.debug("Event handler executed", event_name=event_name)
            except Exception as e:
                logger.error("Error in event handler", event_name=event_name, error=str(e))
    
    def update_client_info(self, client_ip: str, client_port: int):
        """Update client RTP information"""
        if self._params.serializer:
            self._params.serializer.update_sdp_info(media_ip=client_ip, media_port=client_port)
        
        logger.info("Client RTP info updated", 
                   call_id=self._params.call_id,
                   client_ip=client_ip, 
                   client_port=client_port)
    
    def get_bind_info(self) -> Dict[str, Any]:
        """Get transport bind information"""
        return {
            'bind_ip': self._params.bind_ip,
            'bind_port': self._params.bind_port,
            'call_id': self._params.call_id
        }
    
    def get_sdp_info(self) -> Dict[str, Any]:
        """Get SDP information for 200 OK response"""
        if self._params.serializer:
            return self._params.serializer.get_sdp_info()
        
        # Fallback SDP info
        media_ip = self._params.bind_ip
        if media_ip == "0.0.0.0":
            try:
                # Try to detect local IP
                import socket
                with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                    s.connect(("8.8.8.8", 80))
                    media_ip = s.getsockname()[0]
            except Exception:
                media_ip = "127.0.0.1"
        
        return {
            'media_ip': media_ip,
            'media_port': self._params.bind_port,
            'audio_format': 'PCMU',
            'call_id': self._params.call_id
        }


def create_opensips_transport(
    bind_ip: str = "0.0.0.0",
    bind_port: int = 0,
    call_id: str = None,
    vad_analyzer: Optional[SileroVADAnalyzer] = None,
    **kwargs
) -> OpenSIPSTransport:
    """
    Create OpenSIPS transport following Twilio/Telnyx pattern
    """
    # Create serializer
    serializer = OpenSIPSFrameSerializer(
        call_id=call_id or "default_call",
        media_ip=bind_ip,
        media_port=bind_port
    )
    
    # Create transport params
    params = OpenSIPSTransportParams(
        bind_ip=bind_ip,
        bind_port=bind_port,
        call_id=call_id,
        vad_analyzer=vad_analyzer,
        serializer=serializer,
        **kwargs
    )
    
    transport = OpenSIPSTransport(params)
    
    logger.info("OpenSIPS transport created with serializer", 
               call_id=call_id,
               bind_ip=bind_ip,
               bind_port=bind_port)
    
    return transport 