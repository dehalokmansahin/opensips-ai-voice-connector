"""
RTP Packet Utilities
Eski rtp.py dosyasından alınan RTP encode/decode fonksiyonları
"""

from typing import Dict, Any


def decode_rtp_packet(packet: bytes) -> Dict[str, Any]:
    """
    Decodes a raw RTP packet from bytes.

    Handles variable-length RTP headers (CSRC list, header extension)
    and optional padding as per RFC 3550.

    Args:
        packet: Raw RTP packet as bytes.

    Returns:
        A dictionary containing the parsed RTP packet fields,
        with the payload as bytes.

    Raises:
        ValueError: If the packet is malformed or too short.
    """
    if len(packet) < 12:
        raise ValueError("RTP packet is too short (less than 12 bytes)")

    packet_vars = {}

    # First byte: Version, Padding, Extension, CSRC Count
    v_p_x_cc = packet[0]
    packet_vars['version'] = v_p_x_cc >> 6
    packet_vars['padding'] = (v_p_x_cc >> 5) & 1
    packet_vars['extension'] = (v_p_x_cc >> 4) & 1
    packet_vars['csi_count'] = v_p_x_cc & 0x0F

    # Second byte: Marker, Payload Type
    m_pt = packet[1]
    packet_vars['marker'] = m_pt >> 7
    packet_vars['payload_type'] = m_pt & 0x7F

    # Sequence Number (16 bits)
    packet_vars['sequence_number'] = int.from_bytes(packet[2:4], 'big')

    # Timestamp (32 bits)
    packet_vars['timestamp'] = int.from_bytes(packet[4:8], 'big')

    # SSRC (32 bits)
    packet_vars['ssrc'] = int.from_bytes(packet[8:12], 'big')

    # Calculate header length
    header_len = 12 + (packet_vars['csi_count'] * 4)

    # Handle header extension
    if packet_vars['extension']:
        if len(packet) < header_len + 4:
            raise ValueError("RTP packet too short for extension header")
        ext_header_field = packet[header_len:header_len+4]
        ext_len_words = int.from_bytes(ext_header_field[2:4], 'big')
        ext_len_bytes = (ext_len_words * 4)
        header_len += (4 + ext_len_bytes)

    if len(packet) < header_len:
        raise ValueError("RTP packet header length is larger than packet size")

    payload = packet[header_len:]

    # Handle padding
    if packet_vars['padding'] and payload:
        pad_len = payload[-1]
        if pad_len <= len(payload):
            payload = payload[:-pad_len]
        else:
            raise ValueError("RTP packet padding length is invalid")

    packet_vars['payload'] = payload

    return packet_vars


def generate_rtp_packet(packet_vars: Dict[str, Any]) -> bytes:
    """
    Generates/Encodes an RTP packet to bytes.
    
    Args:
        packet_vars: Dictionary containing RTP packet fields.
        The payload should be provided as bytes.
        
    Returns:
        The raw RTP packet as bytes.
    """
    # First byte: V(2) + P(1) + X(1) + CC(4)
    byte1 = (
        (packet_vars['version'] << 6) |
        (packet_vars['padding'] << 5) |
        (packet_vars['extension'] << 4) |
        packet_vars['csi_count']
    )

    # Second byte: M(1) + PT(7)
    byte2 = (packet_vars['marker'] << 7) | packet_vars['payload_type']

    header = bytearray()
    header.append(byte1)
    header.append(byte2)
    header.extend(packet_vars['sequence_number'].to_bytes(2, 'big'))
    header.extend(packet_vars['timestamp'].to_bytes(4, 'big'))
    header.extend(packet_vars['ssrc'].to_bytes(4, 'big'))

    # Payload
    payload = packet_vars.get('payload', b'')

    return bytes(header) + payload 