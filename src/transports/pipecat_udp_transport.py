"""
Native Pipecat UDP/RTP Transport
Pipecat'in BaseTransport pattern'ini kullanarak OpenSIPS RTP entegrasyonu
"""

import asyncio
import socket
import struct
import random
import time
from typing import Optional, Dict, Any, Callable, Awaitable
import structlog

from pipecat.frames.frames import (
    Frame, InputAudioRawFrame, OutputAudioRawFrame, StartFrame, EndFrame, 
    CancelFrame, SystemFrame, StartInterruptionFrame
)
from pipecat.transports.base_input import BaseInputTransport
from pipecat.transports.base_output import BaseOutputTransport
from pipecat.transports.base_transport import BaseTransport, TransportParams
from pipecat.audio.utils import ulaw_to_pcm, pcm_to_ulaw, create_default_resampler
from pipecat.processors.frame_processor import FrameDirection

from transports.rtp_utils import decode_rtp_packet, generate_rtp_packet

logger = structlog.get_logger()


class UDPRTPTransportParams(TransportParams):
    """UDP/RTP Transport Parameters following Pipecat pattern"""
    
    bind_ip: str = "0.0.0.0"
    bind_port: int = 0  # 0 = auto-assign
    client_ip: Optional[str] = None
    client_port: Optional[int] = None
    
    def __init__(
        self,
        bind_ip: str = "0.0.0.0",
        bind_port: int = 0,
        client_ip: str = None,
        client_port: int = None,
        **kwargs
    ):
        # Enable audio in/out by default for RTP transport
        kwargs.setdefault('audio_in_enabled', True)
        kwargs.setdefault('audio_out_enabled', True)
        kwargs.setdefault('audio_in_sample_rate', 16000)  # Pipeline internal rate
        kwargs.setdefault('audio_out_sample_rate', 8000)  # RTP PCMU rate
        
        super().__init__(
            bind_ip=bind_ip,
            bind_port=bind_port,
            client_ip=client_ip,
            client_port=client_port,
            **kwargs
        )


class UDPRTPInputTransport(BaseInputTransport):
    """
    Native Pipecat UDP/RTP Input Transport
    Handles incoming RTP packets and converts to pipeline frames
    """
    
    def __init__(self, transport: "UDPRTPTransport", params: UDPRTPTransportParams, **kwargs):
        super().__init__(params, **kwargs)
        
        self._transport = transport
        self._params: UDPRTPTransportParams = params
        self._socket: Optional[socket.socket] = None
        self._udp_task: Optional[asyncio.Task] = None
        self._resampler = create_default_resampler()
        
        # RTP state
        self._client_learned = False
        self._packet_count = 0
        self._initialized = False
        
        # Bind socket immediately to get port for SDP
        self._bind_socket()
        
        logger.info("🎵 UDPRTPInputTransport initialized")
    
    def _bind_socket(self):
        """Bind UDP socket and get port (called during init)"""
        try:
            # Create and bind UDP socket
            self._socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self._socket.bind((self._params.bind_ip, self._params.bind_port))
            self._socket.setblocking(False)
            
            # Get actual bound port and update transport
            actual_port = self._socket.getsockname()[1]
            self._transport._local_port = actual_port
            
            logger.info("🌐 UDP socket bound", 
                       bind_ip=self._params.bind_ip, 
                       actual_port=actual_port)
            
        except Exception as e:
            logger.error("Failed to bind UDP socket", error=str(e))
            raise

    async def start(self, frame: StartFrame):
        """Start the UDP/RTP input transport"""
        await super().start(frame)
        
        if self._initialized:
            return
            
        self._initialized = True
        
        try:
            # Socket is already bound from init, just start async tasks
            if not self._socket:
                raise ValueError("Socket not bound")
            
            # Start UDP packet reading task
            self._udp_task = self.create_task(self._udp_reader_task())
            
            # Signal transport ready
            await self.set_transport_ready(frame)
            
        except Exception as e:
            logger.error("Failed to start UDP/RTP input transport", error=str(e))
            raise
    
    async def stop(self, frame: EndFrame):
        """Stop the UDP/RTP input transport"""
        await super().stop(frame)
        
        # Cancel UDP reader task
        if self._udp_task:
            await self.cancel_task(self._udp_task)
            self._udp_task = None
        
        # Close socket
        if self._socket:
            self._socket.close()
            self._socket = None
            
        logger.info("🛑 UDP/RTP input transport stopped")
    
    async def cancel(self, frame: CancelFrame):
        """Cancel the UDP/RTP input transport"""
        await super().cancel(frame)
        
        if self._udp_task:
            await self.cancel_task(self._udp_task)
            self._udp_task = None
            
        if self._socket:
            self._socket.close()
            self._socket = None
    
    async def _udp_reader_task(self):
        """Main UDP packet reading loop"""
        logger.info("🔄 UDP reader task started")
        
        try:
            packet_count = 0
            while True:
                try:
                    # Read UDP packet (non-blocking)
                    data, addr = await asyncio.get_event_loop().sock_recvfrom(
                        self._socket, 4096
                    )
                    
                    packet_count += 1
                    logger.info("📦 UDP packet received", 
                               packet_num=packet_count,
                               size=len(data), 
                               from_addr=f"{addr[0]}:{addr[1]}")
                    
                    await self._handle_rtp_packet(data, addr)
                    
                except Exception as e:
                    logger.error("Error reading UDP packet", error=str(e))
                    await asyncio.sleep(0.01)  # Brief pause on error
                    
        except asyncio.CancelledError:
            logger.info("UDP reader task cancelled")
            raise
        except Exception as e:
            logger.error("Fatal error in UDP reader task", error=str(e))
    
    async def _handle_rtp_packet(self, data: bytes, addr: tuple):
        """Process incoming RTP packet"""
        try:
            logger.info("🎵 Processing RTP packet", 
                       size=len(data), 
                       from_addr=f"{addr[0]}:{addr[1]}",
                       data_preview=data[:20].hex())
            
            # Learn client address from first packet
            if not self._client_learned:
                self._params.client_ip = addr[0]
                self._params.client_port = addr[1]
                self._client_learned = True
                logger.info("🎯 Learned client address from first RTP packet", 
                           client_ip=addr[0], client_port=addr[1])
                
                # Notify transport about client connection
                await self._transport._notify_client_connected()
            
            # Validate source (with some flexibility for NAT)
            if addr[0] != self._params.client_ip and self._packet_count > 10:
                logger.debug("RTP packet from unexpected source", 
                           source=f"{addr[0]}:{addr[1]}", 
                           expected=f"{self._params.client_ip}:{self._params.client_port}")
                return
            
            self._packet_count += 1
            
            # Decode RTP packet
            logger.debug("🔍 Decoding RTP packet", packet_hex=data.hex()[:40])
            rtp_packet = decode_rtp_packet(data.hex())
            pcmu_payload = bytes.fromhex(rtp_packet['payload'])
            
            logger.info("✅ RTP packet decoded successfully", 
                       payload_type=rtp_packet.get('payload_type'),
                       sequence=rtp_packet.get('sequence_number'),
                       pcmu_size=len(pcmu_payload))
            
            # Convert PCMU to PCM using Pipecat native utilities
            pcm_data = await ulaw_to_pcm(
                ulaw_bytes=pcmu_payload,
                in_rate=8000,    # PCMU input rate
                out_rate=self.sample_rate,  # Pipeline processing rate (16kHz)
                resampler=self._resampler
            )
            
            if pcm_data and len(pcm_data) > 0:
                # Create Pipecat audio frame
                audio_frame = InputAudioRawFrame(
                    audio=pcm_data,
                    sample_rate=self.sample_rate,
                    num_channels=1
                )
                
                # Push to Pipecat pipeline using native method
                await self.push_audio_frame(audio_frame)
                
                logger.info("🎵 RTP→PCM→Pipeline successful", 
                           pcmu_size=len(pcmu_payload),
                           pcm_size=len(pcm_data),
                           packet_num=self._packet_count)
            else:
                logger.warning("❌ PCM conversion failed or empty", 
                              pcmu_size=len(pcmu_payload))
            
        except Exception as e:
            logger.error("Error handling RTP packet", error=str(e), exc_info=True)


class UDPRTPOutputTransport(BaseOutputTransport):
    """
    Native Pipecat UDP/RTP Output Transport  
    Handles outgoing audio frames and converts to RTP packets
    """
    
    def __init__(self, transport: "UDPRTPTransport", params: UDPRTPTransportParams, **kwargs):
        super().__init__(params, **kwargs)
        
        self._transport = transport
        self._params: UDPRTPTransportParams = params
        self._resampler = create_default_resampler()
        self._initialized = False
        
        # RTP state
        self._sequence_number = random.randint(0, 65535)
        self._timestamp = random.randint(0, 0xFFFFFFFF)
        self._ssrc = random.randint(0, 0xFFFFFFFF)
        
        logger.info("🎵 UDPRTPOutputTransport initialized")
    
    async def start(self, frame: StartFrame):
        """Start the UDP/RTP output transport"""
        await super().start(frame)
        
        if self._initialized:
            return
            
        self._initialized = True
        
        # Signal transport ready
        await self.set_transport_ready(frame)
        
        logger.info("🚀 UDP/RTP output transport started")
    
    async def write_audio_frame(self, frame: OutputAudioRawFrame):
        """Write audio frame as RTP packets"""
        if not self._params.client_ip or not self._params.client_port:
            logger.debug("No client address available, dropping audio frame")
            return
            
        try:
            # Convert PCM to PCMU using Pipecat native utilities
            pcmu_data = await pcm_to_ulaw(
                pcm_bytes=frame.audio,
                in_rate=frame.sample_rate,  # Pipeline output rate
                out_rate=8000,  # PCMU rate
                resampler=self._resampler
            )
            
            if pcmu_data and len(pcmu_data) > 0:
                # Split into 20ms chunks (160 bytes at 8kHz)
                chunk_size = 160
                for i in range(0, len(pcmu_data), chunk_size):
                    chunk = pcmu_data[i:i+chunk_size]
                    
                    # Pad if needed
                    if len(chunk) < chunk_size:
                        chunk = chunk + bytes([0xFF] * (chunk_size - len(chunk)))
                    
                    await self._send_rtp_packet(chunk)
                    
                logger.debug("🎵 Audio frame converted to RTP packets", 
                           pcm_size=len(frame.audio),
                           pcmu_size=len(pcmu_data))
            
        except Exception as e:
            logger.error("Error writing audio frame", error=str(e))
    
    async def _send_rtp_packet(self, pcmu_payload: bytes):
        """Send a single RTP packet"""
        try:
            # Generate RTP packet
            rtp_packet_data = {
                'version': 2,
                'padding': 0,
                'extension': 0,
                'csi_count': 0,
                'marker': 0,
                'payload_type': 0,  # PCMU
                'sequence_number': self._sequence_number,
                'timestamp': self._timestamp,
                'ssrc': self._ssrc,
                'payload': pcmu_payload.hex()
            }
            
            rtp_packet_hex = generate_rtp_packet(rtp_packet_data)
            rtp_packet_bytes = bytes.fromhex(rtp_packet_hex)
            
            # Send via transport socket
            if self._transport._input and self._transport._input._socket:
                self._transport._input._socket.sendto(
                    rtp_packet_bytes,
                    (self._params.client_ip, self._params.client_port)
                )
                
                logger.debug("📤 RTP packet sent", 
                           seq=self._sequence_number,
                           dest=f"{self._params.client_ip}:{self._params.client_port}")
            
            # Update RTP state
            self._sequence_number = (self._sequence_number + 1) % 65536
            self._timestamp = (self._timestamp + 160) % 0x100000000  # 20ms at 8kHz
            
        except Exception as e:
            logger.error("Error sending RTP packet", error=str(e))


class UDPRTPTransport(BaseTransport):
    """
    Native Pipecat UDP/RTP Transport
    Combines input and output transports for full duplex RTP communication
    """
    
    def __init__(
        self,
        params: UDPRTPTransportParams,
        input_name: Optional[str] = None,
        output_name: Optional[str] = None,
    ):
        super().__init__(input_name=input_name, output_name=output_name)
        
        self._params = params
        self._input: Optional[UDPRTPInputTransport] = None
        self._output: Optional[UDPRTPOutputTransport] = None
        self._local_port: int = 0
        
        # Register event handlers
        self._register_event_handler("on_client_connected")
        self._register_event_handler("on_client_disconnected")
        self._register_event_handler("on_rtp_ready")
        
        logger.info("🎵 UDPRTPTransport initialized")
    
    def input(self) -> UDPRTPInputTransport:
        """Get input transport"""
        if not self._input:
            self._input = UDPRTPInputTransport(
                self, self._params, name=self._input_name
            )
        return self._input
    
    def output(self) -> UDPRTPOutputTransport:
        """Get output transport"""
        if not self._output:
            self._output = UDPRTPOutputTransport(
                self, self._params, name=self._output_name
            )
        return self._output
    
    @property
    def local_port(self) -> int:
        """Get local UDP port"""
        return self._local_port
    
    @property
    def client_address(self) -> tuple:
        """Get client address"""
        return (self._params.client_ip, self._params.client_port)
    
    def get_sdp_info(self) -> Dict[str, Any]:
        """Get SDP information for this transport"""
        return {
            "media_port": self.local_port,
            "media_ip": self._params.bind_ip,
            "audio_format": "PCMU",
            "sample_rate": 8000,
            "connection_ip": self._params.bind_ip
        }
    
    async def _notify_client_connected(self):
        """Notify about client connection"""
        await self._call_event_handler("on_client_connected", self._params.client_ip, self._params.client_port)
        await self._call_event_handler("on_rtp_ready")


# Helper function to create transport with common settings
def create_opensips_rtp_transport(
    bind_ip: str = "0.0.0.0",
    bind_port: int = 0,
    **kwargs
) -> UDPRTPTransport:
    """
    Create UDP/RTP transport optimized for OpenSIPS integration
    """
    params = UDPRTPTransportParams(
        bind_ip=bind_ip,
        bind_port=bind_port,
        audio_in_enabled=True,
        audio_out_enabled=True,
        audio_in_sample_rate=16000,  # Pipeline processing rate
        audio_out_sample_rate=8000,  # RTP PCMU rate
        **kwargs
    )
    
    return UDPRTPTransport(params) 