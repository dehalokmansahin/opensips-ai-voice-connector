"""
Basic RTP packet structures for audio streaming
Simplified version to avoid circular imports
"""

import struct
from dataclasses import dataclass
from typing import Optional

@dataclass
class RTPPacket:
    """Basic RTP packet structure"""
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

def parse_rtp_packet(data: bytes) -> Optional[RTPPacket]:
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
        
    except Exception:
        return None

def serialize_rtp_packet(packet: RTPPacket) -> bytes:
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
        
    except Exception:
        return b''