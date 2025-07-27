"""
Networking utilities for OpenSIPS AI Voice Connector
Network-related helper functions
"""

import socket
import logging
import asyncio
from typing import Tuple, Optional, List
import struct
import time

logger = logging.getLogger(__name__)

def find_free_port(start_port: int = 8000, end_port: int = 9000, host: str = "0.0.0.0") -> Optional[int]:
    """Find a free port in the given range"""
    for port in range(start_port, end_port + 1):
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.bind((host, port))
            sock.close()
            return port
        except OSError:
            continue
    return None

def get_local_ip() -> str:
    """Get local IP address"""
    try:
        # Create a dummy connection to get local IP
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.connect(("8.8.8.8", 80))
        local_ip = sock.getsockname()[0]
        sock.close()
        return local_ip
    except Exception:
        return "127.0.0.1"

def is_port_open(host: str, port: int, timeout: float = 3.0) -> bool:
    """Check if a port is open"""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        result = sock.connect_ex((host, port))
        sock.close()
        return result == 0
    except Exception:
        return False

def parse_sip_uri(uri: str) -> Optional[Tuple[str, int]]:
    """Parse SIP URI to extract host and port"""
    try:
        # Remove sip: prefix if present
        if uri.startswith('sip:'):
            uri = uri[4:]
        
        # Remove user part if present (user@host:port)
        if '@' in uri:
            uri = uri.split('@', 1)[1]
        
        # Split host and port
        if ':' in uri:
            host, port_str = uri.rsplit(':', 1)
            port = int(port_str)
        else:
            host = uri
            port = 5060  # Default SIP port
        
        return host, port
        
    except Exception as e:
        logger.error(f"Error parsing SIP URI '{uri}': {e}")
        return None

def format_sip_uri(host: str, port: int = 5060, user: str = None) -> str:
    """Format SIP URI"""
    if user:
        return f"sip:{user}@{host}:{port}"
    else:
        return f"sip:{host}:{port}"

class UDPServer:
    """Simple UDP server for testing"""
    
    def __init__(self, host: str = "0.0.0.0", port: int = 0):
        self.host = host
        self.port = port
        self.socket: Optional[socket.socket] = None
        self.running = False
        
    async def start(self, message_handler=None):
        """Start UDP server"""
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.socket.bind((self.host, self.port))
            
            # Get actual port if auto-assigned
            if self.port == 0:
                self.port = self.socket.getsockname()[1]
            
            self.running = True
            logger.info(f"UDP server started on {self.host}:{self.port}")
            
            if message_handler:
                # Start message handling loop
                await self._message_loop(message_handler)
                
        except Exception as e:
            logger.error(f"Failed to start UDP server: {e}")
            raise
    
    async def _message_loop(self, handler):
        """Message handling loop"""
        loop = asyncio.get_running_loop()
        
        while self.running:
            try:
                # Receive data (non-blocking)
                data, addr = await loop.sock_recvfrom(self.socket, 4096)
                
                # Handle message
                if asyncio.iscoroutinefunction(handler):
                    await handler(data, addr)
                else:
                    handler(data, addr)
                    
            except Exception as e:
                if self.running:
                    logger.error(f"Error in UDP message loop: {e}")
                break
    
    async def send(self, data: bytes, addr: Tuple[str, int]):
        """Send data to address"""
        try:
            if self.socket and self.running:
                self.socket.sendto(data, addr)
        except Exception as e:
            logger.error(f"Error sending UDP data: {e}")
    
    async def stop(self):
        """Stop UDP server"""
        self.running = False
        if self.socket:
            self.socket.close()
            self.socket = None
        logger.info("UDP server stopped")

class NetworkMonitor:
    """Network connectivity monitor"""
    
    def __init__(self):
        self.connected = True
        self.last_check = 0
        self.check_interval = 30  # seconds
    
    async def is_connected(self, force_check: bool = False) -> bool:
        """Check network connectivity"""
        now = time.time()
        
        if not force_check and (now - self.last_check) < self.check_interval:
            return self.connected
        
        try:
            # Try to connect to Google DNS
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(5)
            result = sock.connect_ex(("8.8.8.8", 53))
            sock.close()
            
            self.connected = (result == 0)
            self.last_check = now
            
            return self.connected
            
        except Exception:
            self.connected = False
            self.last_check = now
            return False
    
    async def wait_for_connection(self, timeout: float = 60.0) -> bool:
        """Wait for network connection"""
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            if await self.is_connected(force_check=True):
                return True
            await asyncio.sleep(1)
        
        return False

def create_rtp_header(
    sequence: int,
    timestamp: int,
    ssrc: int,
    payload_type: int = 0,
    marker: bool = False
) -> bytes:
    """Create RTP header"""
    try:
        # RTP version 2
        version = 2
        
        # First byte: V(2) + P(1) + X(1) + CC(4)
        byte1 = (version << 6) | 0  # No padding, extension, or CSRC
        
        # Second byte: M(1) + PT(7)
        byte2 = (int(marker) << 7) | (payload_type & 0x7F)
        
        # Pack header (12 bytes)
        header = struct.pack('!BBHII',
                           byte1,
                           byte2,
                           sequence & 0xFFFF,
                           timestamp & 0xFFFFFFFF,
                           ssrc & 0xFFFFFFFF)
        
        return header
        
    except Exception as e:
        logger.error(f"Error creating RTP header: {e}")
        return b''

def parse_rtp_header(data: bytes) -> Optional[dict]:
    """Parse RTP header"""
    try:
        if len(data) < 12:
            return None
        
        # Unpack fixed header
        header = struct.unpack('!BBHII', data[:12])
        
        byte1 = header[0]
        byte2 = header[1]
        
        return {
            'version': (byte1 >> 6) & 0x3,
            'padding': bool((byte1 >> 5) & 0x1),
            'extension': bool((byte1 >> 4) & 0x1),
            'cc': byte1 & 0xF,
            'marker': bool((byte2 >> 7) & 0x1),
            'payload_type': byte2 & 0x7F,
            'sequence': header[2],
            'timestamp': header[3],
            'ssrc': header[4]
        }
        
    except Exception as e:
        logger.error(f"Error parsing RTP header: {e}")
        return None

async def test_network_latency(host: str, port: int, count: int = 5) -> dict:
    """Test network latency to a host"""
    try:
        latencies = []
        
        for i in range(count):
            start_time = time.time()
            
            try:
                # TCP connection test
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(5)
                result = sock.connect_ex((host, port))
                sock.close()
                
                if result == 0:
                    latency_ms = (time.time() - start_time) * 1000
                    latencies.append(latency_ms)
                
            except Exception:
                pass
            
            await asyncio.sleep(0.1)
        
        if latencies:
            return {
                'success': True,
                'count': len(latencies),
                'min_ms': min(latencies),
                'max_ms': max(latencies),
                'avg_ms': sum(latencies) / len(latencies),
                'host': host,
                'port': port
            }
        else:
            return {
                'success': False,
                'error': 'No successful connections',
                'host': host,
                'port': port
            }
            
    except Exception as e:
        return {
            'success': False,
            'error': str(e),
            'host': host,
            'port': port
        }

def format_bytes(size_bytes: int) -> str:
    """Format bytes in human readable format"""
    if size_bytes == 0:
        return "0 B"
    
    size_names = ["B", "KB", "MB", "GB"]
    i = 0
    while size_bytes >= 1024 and i < len(size_names) - 1:
        size_bytes /= 1024.0
        i += 1
    
    return f"{size_bytes:.1f} {size_names[i]}"

def calculate_bandwidth(bytes_transferred: int, duration_seconds: float) -> dict:
    """Calculate bandwidth statistics"""
    try:
        if duration_seconds <= 0:
            return {'error': 'Invalid duration'}
        
        bits_per_second = (bytes_transferred * 8) / duration_seconds
        bytes_per_second = bytes_transferred / duration_seconds
        
        return {
            'bytes_transferred': bytes_transferred,
            'duration_seconds': duration_seconds,
            'bytes_per_second': bytes_per_second,
            'bits_per_second': bits_per_second,
            'kbps': bits_per_second / 1000,
            'mbps': bits_per_second / 1000000,
            'formatted': f"{bits_per_second/1000:.1f} kbps"
        }
        
    except Exception as e:
        return {'error': str(e)}