"""
RTP Packet Utilities
Eski rtp.py dosyasından alınan RTP encode/decode fonksiyonları
"""

from typing import Dict, Any


def decode_rtp_packet(packet_bytes: str) -> Dict[str, Any]:
    """
    Decodes a RTP packet from hex string
    
    Args:
        packet_bytes: Hex string representation of RTP packet
        
    Returns:
        Dictionary containing RTP packet fields
    """
    packet_vars = {}
    
    # First byte: V(2) + P(1) + X(1) + CC(4)
    byte1 = packet_bytes[0:2]
    byte1 = int(byte1, 16)
    byte1 = format(byte1, 'b').zfill(8)
    
    packet_vars['version'] = int(byte1[0:2], 2)
    packet_vars['padding'] = int(byte1[2:3])
    packet_vars['extension'] = int(byte1[3:4])
    packet_vars['csi_count'] = int(byte1[4:8], 2)

    # Second byte: M(1) + PT(7)
    byte2 = packet_bytes[2:4]
    byte2 = int(byte2, 16)
    byte2 = format(byte2, 'b').zfill(8)
    
    packet_vars['marker'] = int(byte2[0:1])
    packet_vars['payload_type'] = int(byte2[1:8], 2)

    # Sequence number (16 bits)
    packet_vars['sequence_number'] = int(str(packet_bytes[4:8]), 16)

    # Timestamp (32 bits)
    packet_vars['timestamp'] = int(str(packet_bytes[8:16]), 16)

    # SSRC (32 bits)
    packet_vars['ssrc'] = int(str(packet_bytes[16:24]), 16)

    # Payload (remaining bytes)
    packet_vars['payload'] = str(packet_bytes[24:])
    
    return packet_vars


def generate_rtp_packet(packet_vars: Dict[str, Any]) -> str:
    """
    Generates/Encodes a RTP packet to hex string
    
    Args:
        packet_vars: Dictionary containing RTP packet fields
        
    Returns:
        Hex string representation of RTP packet
    """
    # First byte: V(2) + P(1) + X(1) + CC(4)
    version = str(format(packet_vars['version'], 'b').zfill(2))
    padding = str(packet_vars['padding'])
    extension = str(packet_vars['extension'])
    csi_count = str(format(packet_vars['csi_count'], 'b').zfill(4))
    
    byte1_body = int((version + padding + extension + csi_count), 2)
    byte1 = format(byte1_body, 'x').zfill(2)

    # Second byte: M(1) + PT(7)
    marker = str(packet_vars['marker'])
    payload_type = str(format(packet_vars['payload_type'], 'b').zfill(7))
    byte2 = format(int((marker + payload_type), 2), 'x').zfill(2)

    # Sequence number (16 bits)
    sequence_number = format(packet_vars['sequence_number'], 'x').zfill(4)

    # Timestamp (32 bits)  
    timestamp = format(packet_vars['timestamp'], 'x').zfill(8)

    # SSRC (32 bits)
    ssrc = str(format(packet_vars['ssrc'], 'x').zfill(8))

    # Payload
    payload = packet_vars['payload']

    # Combine all parts
    packet = byte1 + byte2 + sequence_number + timestamp + ssrc + payload

    return packet 