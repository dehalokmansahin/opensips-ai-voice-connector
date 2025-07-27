"""
RTP Transport for OpenSIPS AI Voice Connector
Handles real-time audio streaming via RTP protocol
"""

import asyncio
import logging
import socket
import struct
import time
from typing import Optional, Callable, AsyncGenerator
from dataclasses import dataclass

logger = logging.getLogger(__name__)

@dataclass
class RTPPacket:
    """RTP packet structure"""
    version: int = 2
    padding: bool = False
    extension: bool = False
    cc: int = 0
    marker: bool = False
    payload_type: int = 0  # 0 = PCMU
    sequence_number: int = 0
    timestamp: int = 0
    ssrc: int = 0
    payload: bytes = b''

class RTPTransport:
    """RTP transport for audio streaming"""
    
    def __init__(
        self,
        bind_ip: str = "0.0.0.0",
        bind_port: int = 0,
        remote_ip: str = "127.0.0.1",
        remote_port: int = 5060,
        sample_rate: int = 8000,
        frame_size_ms: int = 20
    ):
        """
        Initialize RTP transport
        
        Args:
            bind_ip: Local IP to bind to
            bind_port: Local port to bind to (0 = auto)
            remote_ip: Remote IP to send to
            remote_port: Remote port to send to
            sample_rate: Audio sample rate (8000 for PCMU)
            frame_size_ms: Frame size in milliseconds
        """
        self.bind_ip = bind_ip
        self.bind_port = bind_port
        self.remote_ip = remote_ip
        self.remote_port = remote_port
        self.sample_rate = sample_rate
        self.frame_size_ms = frame_size_ms
        
        # RTP state
        self.sequence_number = 0
        self.timestamp = 0
        self.ssrc = int(time.time()) & 0xFFFFFFFF
        
        # Transport
        self.socket: Optional[socket.socket] = None
        self.transport = None
        self.protocol = None
        self._running = False
        
        # Audio callbacks
        self.on_audio_received: Optional[Callable[[bytes], None]] = None
        
        # Frame size calculation
        self.samples_per_frame = (sample_rate * frame_size_ms) // 1000
        self.bytes_per_frame = self.samples_per_frame  # PCMU = 1 byte per sample
        
        logger.info(f"RTP transport initialized: {bind_ip}:{bind_port} <-> {remote_ip}:{remote_port}")
    
    async def start(self):
        """Start RTP transport"""
        try:
            # Create UDP socket
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            
            # Bind to local address
            self.socket.bind((self.bind_ip, self.bind_port))
            
            # Get actual bound port if auto-assigned
            if self.bind_port == 0:
                self.bind_port = self.socket.getsockname()[1]
            
            # Set non-blocking
            self.socket.setblocking(False)
            
            # Create asyncio transport
            loop = asyncio.get_running_loop()
            
            class RTPProtocol(asyncio.DatagramProtocol):
                def __init__(self, rtp_transport):
                    self.rtp_transport = rtp_transport
                
                def connection_made(self, transport):
                    self.transport = transport
                
                def datagram_received(self, data, addr):
                    """Handle incoming RTP packet"""
                    asyncio.create_task(self.rtp_transport._handle_incoming_rtp(data, addr))
            
            self.transport, self.protocol = await loop.create_datagram_endpoint(
                lambda: RTPProtocol(self),
                sock=self.socket
            )
            
            self._running = True
            logger.info(f"RTP transport started: {self.bind_ip}:{self.bind_port}")
            
        except Exception as e:
            logger.error(f"Failed to start RTP transport: {e}")
            raise
    
    async def stop(self):
        """Stop RTP transport"""
        try:
            self._running = False
            
            if self.transport:
                self.transport.close()
                self.transport = None
                self.protocol = None
            
            if self.socket:
                self.socket.close()
                self.socket = None
            
            logger.info("RTP transport stopped")
            
        except Exception as e:
            logger.error(f"Error stopping RTP transport: {e}")
    
    async def _handle_incoming_rtp(self, data: bytes, addr):
        """Handle incoming RTP packet"""
        try:
            if len(data) < 12:  # Minimum RTP header size
                logger.warning(f"RTP packet too short: {len(data)} bytes")
                return
            
            # Parse RTP header
            packet = self._parse_rtp_packet(data)
            if not packet:
                return
            
            logger.debug(f"RTP packet received: seq={packet.sequence_number}, "
                        f"ts={packet.timestamp}, payload={len(packet.payload)} bytes")
            
            # Extract audio payload
            if packet.payload and self.on_audio_received:
                if asyncio.iscoroutinefunction(self.on_audio_received):
                    await self.on_audio_received(packet.payload)
                else:
                    self.on_audio_received(packet.payload)
                    
        except Exception as e:
            logger.error(f"Error handling incoming RTP: {e}")
    
    def _parse_rtp_packet(self, data: bytes) -> Optional[RTPPacket]:
        """Parse RTP packet from binary data"""
        try:
            if len(data) < 12:
                return None
            
            # Parse fixed header (12 bytes)
            header = struct.unpack('!BBHII', data[:12])
            
            version_cc = header[0]
            version = (version_cc >> 6) & 0x3
            padding = bool((version_cc >> 5) & 0x1)
            extension = bool((version_cc >> 4) & 0x1)
            cc = version_cc & 0xF
            
            marker_pt = header[1]
            marker = bool((marker_pt >> 7) & 0x1)
            payload_type = marker_pt & 0x7F
            
            sequence_number = header[2]
            timestamp = header[3]
            ssrc = header[4]
            
            # Skip CSRC identifiers
            header_length = 12 + (cc * 4)
            
            # Skip extension if present
            if extension and len(data) >= header_length + 4:
                ext_header = struct.unpack('!HH', data[header_length:header_length + 4])
                ext_length = ext_header[1] * 4
                header_length += 4 + ext_length
            
            # Extract payload
            payload = data[header_length:]
            
            # Remove padding if present
            if padding and len(payload) > 0:
                padding_length = payload[-1]
                payload = payload[:-padding_length]
            
            return RTPPacket(
                version=version,
                padding=padding,
                extension=extension,
                cc=cc,
                marker=marker,
                payload_type=payload_type,
                sequence_number=sequence_number,
                timestamp=timestamp,
                ssrc=ssrc,
                payload=payload
            )
            
        except Exception as e:
            logger.error(f"Error parsing RTP packet: {e}")
            return None
    
    async def send_audio(self, audio_data: bytes):
        """Send audio data via RTP"""
        try:
            if not self._running or not self.transport:
                logger.warning("RTP transport not running, cannot send audio")
                return
            
            # Split audio into RTP frames
            for i in range(0, len(audio_data), self.bytes_per_frame):
                frame = audio_data[i:i + self.bytes_per_frame]
                if len(frame) == 0:
                    continue
                
                # Pad frame if necessary
                if len(frame) < self.bytes_per_frame:
                    frame += b'\\x00' * (self.bytes_per_frame - len(frame))
                
                # Create RTP packet
                packet = RTPPacket(
                    version=2,
                    payload_type=0,  # PCMU
                    sequence_number=self.sequence_number,
                    timestamp=self.timestamp,
                    ssrc=self.ssrc,
                    payload=frame
                )
                
                # Serialize and send
                rtp_data = self._serialize_rtp_packet(packet)
                self.transport.sendto(rtp_data, (self.remote_ip, self.remote_port))
                
                # Update counters
                self.sequence_number = (self.sequence_number + 1) & 0xFFFF
                self.timestamp = (self.timestamp + self.samples_per_frame) & 0xFFFFFFFF
                
                logger.debug(f"RTP packet sent: seq={packet.sequence_number}, "
                           f"ts={packet.timestamp}, size={len(frame)}")
                
        except Exception as e:
            logger.error(f"Error sending RTP audio: {e}")
    
    def _serialize_rtp_packet(self, packet: RTPPacket) -> bytes:
        """Serialize RTP packet to binary data"""
        try:
            # Create fixed header
            version_cc = (packet.version << 6) | (int(packet.padding) << 5) | \
                        (int(packet.extension) << 4) | packet.cc
            
            marker_pt = (int(packet.marker) << 7) | packet.payload_type
            
            header = struct.pack('!BBHII',
                               version_cc,
                               marker_pt,
                               packet.sequence_number,
                               packet.timestamp,
                               packet.ssrc)
            
            return header + packet.payload
            
        except Exception as e:
            logger.error(f"Error serializing RTP packet: {e}")
            return b''
    
    async def audio_stream(self) -> AsyncGenerator[bytes, None]:
        """Generator for incoming audio stream"""
        audio_queue = asyncio.Queue()
        
        # Set up audio callback
        original_callback = self.on_audio_received
        
        async def audio_callback(audio_data: bytes):
            await audio_queue.put(audio_data)
            # Call original callback if exists
            if original_callback:
                if asyncio.iscoroutinefunction(original_callback):
                    await original_callback(audio_data)
                else:
                    original_callback(audio_data)
        
        self.on_audio_received = audio_callback
        
        try:
            while self._running:
                try:
                    audio_data = await asyncio.wait_for(audio_queue.get(), timeout=1.0)
                    yield audio_data
                except asyncio.TimeoutError:
                    continue
                except Exception as e:
                    logger.error(f"Error in audio stream: {e}")
                    break
        finally:
            # Restore original callback
            self.on_audio_received = original_callback
    
    def get_sdp_info(self) -> dict:
        """Get SDP information for this transport"""
        return {
            'media_ip': self.bind_ip,
            'media_port': self.bind_port,
            'audio_format': 'PCMU',
            'sample_rate': self.sample_rate,
            'session_id': str(self.ssrc)
        }
    
    def get_stats(self) -> dict:
        """Get transport statistics"""
        return {
            'running': self._running,
            'local_endpoint': f"{self.bind_ip}:{self.bind_port}",
            'remote_endpoint': f"{self.remote_ip}:{self.remote_port}",
            'sequence_number': self.sequence_number,
            'timestamp': self.timestamp,
            'ssrc': self.ssrc,
            'sample_rate': self.sample_rate,
            'frame_size_ms': self.frame_size_ms,
            'bytes_per_frame': self.bytes_per_frame
        }