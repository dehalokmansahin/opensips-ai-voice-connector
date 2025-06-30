#!/usr/bin/env python3
"""
RTP Flow Debug Script
RTP paketlerinin pipeline'a ulaşıp ulaşmadığını test eder
"""

import asyncio
import socket
import struct
import time
import sys

def generate_dummy_rtp_packet():
    """Generate a dummy RTP packet with PCMU payload"""
    
    # RTP Header (12 bytes)
    version = 2        # Version (2 bits)
    padding = 0        # Padding (1 bit)
    extension = 0      # Extension (1 bit)
    cc = 0            # CSRC count (4 bits)
    marker = 0        # Marker (1 bit)
    pt = 0            # Payload type (7 bits) - PCMU
    sequence = 12345  # Sequence number (16 bits)
    timestamp = int(time.time() * 8000) & 0xFFFFFFFF  # Timestamp (32 bits)
    ssrc = 0x12345678  # SSRC (32 bits)
    
    # Pack RTP header
    rtp_header = struct.pack('!BBHII',
        (version << 6) | (padding << 5) | (extension << 4) | cc,
        (marker << 7) | pt,
        sequence,
        timestamp,
        ssrc
    )
    
    # Generate PCMU payload (160 bytes for 20ms at 8kHz)
    pcmu_payload = bytes([0xFF, 0x7F] * 80)  # Alternating pattern
    
    return rtp_header + pcmu_payload

async def send_test_rtp_packets(target_ip: str, target_port: int, duration: int = 10):
    """Send test RTP packets to the specified address"""
    try:
        print(f"🎤 Sending test RTP packets to {target_ip}:{target_port} for {duration} seconds...")
        
        # Create UDP socket
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        
        packet_count = 0
        start_time = time.time()
        
        while time.time() - start_time < duration:
            try:
                # Generate and send RTP packet
                rtp_packet = generate_dummy_rtp_packet()
                sock.sendto(rtp_packet, (target_ip, target_port))
                
                packet_count += 1
                
                print(f"📦 Sent RTP packet #{packet_count}, size: {len(rtp_packet)} bytes")
                
                # 20ms intervals (50 packets per second)
                await asyncio.sleep(0.02)
                
            except Exception as e:
                print(f"❌ Error sending RTP packets: {e}")
                break
        
        sock.close()
        print(f"✅ Sent {packet_count} RTP packets total")
        
    except Exception as e:
        print(f"❌ Failed to create socket or send packets: {e}")

async def test_socket_connectivity(target_ip: str, target_port: int):
    """Test basic UDP connectivity to target"""
    try:
        print(f"🔌 Testing UDP connectivity to {target_ip}:{target_port}")
        
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(2.0)
        
        # Send a test message
        test_msg = b"PING"
        sock.sendto(test_msg, (target_ip, target_port))
        print(f"✅ Test UDP packet sent successfully")
        
        sock.close()
        
    except Exception as e:
        print(f"❌ UDP connectivity test failed: {e}")

async def main():
    """Main RTP debug function"""
    # FROM LOG: RTP port 35009 was selected
    TARGET_IP = "192.168.88.120"    # RTP IP from SDP
    TARGET_PORT = 35009             # Actual RTP port from logs
    
    print("🚀 RTP Flow Debug Tool")
    print("=" * 50)
    print(f"Target: {TARGET_IP}:{TARGET_PORT}")
    print("=" * 50)
    
    # Test basic connectivity first
    await test_socket_connectivity(TARGET_IP, TARGET_PORT)
    
    # Send test RTP packets
    await send_test_rtp_packets(TARGET_IP, TARGET_PORT, duration=10)

if __name__ == "__main__":
    if len(sys.argv) >= 3:
        target_ip = sys.argv[1]
        target_port = int(sys.argv[2])
        duration = int(sys.argv[3]) if len(sys.argv) > 3 else 10
        
        asyncio.run(send_test_rtp_packets(target_ip, target_port, duration))
    else:
        asyncio.run(main())

# Test commands:
# python debug_rtp_flow.py                           # Use defaults from logs
# python debug_rtp_flow.py 192.168.88.120 35009     # Manual IP/port
# python debug_rtp_flow.py 172.18.0.6 35009         # Container IP 