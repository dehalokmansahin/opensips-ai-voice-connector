#!/usr/bin/env python3
"""
RTP Flow Debug Script
RTP paketlerinin pipeline'a ulaşıp ulaşmadığını test eder
"""

import asyncio
import sys
import socket
import random
import time
import struct

def generate_dummy_rtp_packet():
    """Generate a dummy RTP packet with PCMU payload"""
    
    # RTP Header (12 bytes)
    version = 2
    padding = 0
    extension = 0
    cc = 0
    marker = 0
    payload_type = 0  # PCMU
    sequence_number = random.randint(1, 65535)
    timestamp = int(time.time() * 8000) & 0xFFFFFFFF
    ssrc = random.randint(1, 0xFFFFFFFF)
    
    # Pack RTP header
    rtp_header = struct.pack('!BBHII',
                            (version << 6) | (padding << 5) | (extension << 4) | cc,
                            (marker << 7) | payload_type,
                            sequence_number,
                            timestamp,
                            ssrc)
    
    # PCMU payload (160 bytes for 20ms at 8kHz)
    pcmu_payload = bytes([0x7F + random.randint(-20, 20) for _ in range(160)])
    
    return rtp_header + pcmu_payload

async def send_test_rtp_packets(target_ip: str, target_port: int, duration: int = 10):
    """Send test RTP packets to the specified address"""
    
    print(f"🎤 Sending test RTP packets to {target_ip}:{target_port} for {duration} seconds...")
    
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    
    try:
        start_time = time.time()
        packet_count = 0
        
        while time.time() - start_time < duration:
            # Generate and send RTP packet
            rtp_packet = generate_dummy_rtp_packet()
            sock.sendto(rtp_packet, (target_ip, target_port))
            
            packet_count += 1
            print(f"📦 Sent RTP packet #{packet_count}, size: {len(rtp_packet)} bytes")
            
            # Send every 20ms (50 packets per second)
            await asyncio.sleep(0.02)
            
    except Exception as e:
        print(f"❌ Error sending RTP packets: {e}")
    finally:
        sock.close()
        print(f"✅ Sent {packet_count} RTP packets total")

async def test_pipeline_audio_flow():
    """Test the complete audio flow"""
    
    print("🧪 Testing Pipeline Audio Flow...")
    
    # You need to get these from the actual call logs
    # Look for messages like "🎵 Generating SDP response ... local_port=42355"
    TARGET_IP = "192.168.88.1"  # Replace with your test client IP
    TARGET_PORT = 42355  # Replace with actual RTP port from logs
    
    print(f"Target: {TARGET_IP}:{TARGET_PORT}")
    print("Note: Replace these values with actual ones from your logs!")
    
    # Send test packets
    await send_test_rtp_packets(TARGET_IP, TARGET_PORT, duration=5)

def main():
    """Main function"""
    
    print("🚀 RTP Flow Debug Tool")
    print("=" * 50)
    
    if len(sys.argv) > 2:
        target_ip = sys.argv[1]
        target_port = int(sys.argv[2])
        
        print(f"Using provided target: {target_ip}:{target_port}")
        
        async def custom_test():
            await send_test_rtp_packets(target_ip, target_port, duration=10)
        
        asyncio.run(custom_test())
    else:
        print("Usage: python debug_rtp_flow.py <target_ip> <target_port>")
        print("Or run without args for default test...")
        
        # Run default test
        asyncio.run(test_pipeline_audio_flow())

if __name__ == "__main__":
    main() 