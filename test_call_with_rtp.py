#!/usr/bin/env python3
"""
Test Call with RTP Flow
Yeni bir SIP çağrısı başlatır ve RTP paketleri gönderir
"""

import asyncio
import socket
import struct
import time
import random
import sys
from typing import Dict, Any

# SIP Message Templates
INVITE_TEMPLATE = """INVITE sip:pipecat@192.168.88.120:8089 SIP/2.0
Via: SIP/2.0/UDP 192.168.88.1:5060;branch=z9hG4bKtest-{branch}
From: "Test Client" <sip:test@192.168.88.1>;tag=test-{tag}
To: <sip:pipecat@192.168.88.120>
Call-ID: test-call-{call_id}
CSeq: 1 INVITE
Contact: <sip:test@192.168.88.1:5060>
Content-Type: application/sdp
Content-Length: {content_length}

{sdp_body}"""

SDP_TEMPLATE = """v=0
o=- {session_id} {session_version} IN IP4 192.168.88.1
s=Test Call
c=IN IP4 192.168.88.1
t=0 0
m=audio {rtp_port} RTP/AVP 0
a=rtpmap:0 PCMU/8000
a=sendrecv"""

async def create_test_sip_invite(client_rtp_port: int = 4000) -> str:
    """Create a test SIP INVITE message"""
    call_id = random.randint(100000, 999999)
    tag = random.randint(100000, 999999)
    branch = random.randint(100000, 999999)
    session_id = random.randint(1000000000, 9999999999)
    session_version = random.randint(1000000000, 9999999999)
    
    # Generate SDP
    sdp_body = SDP_TEMPLATE.format(
        session_id=session_id,
        session_version=session_version,
        rtp_port=client_rtp_port
    )
    
    # Create INVITE
    invite = INVITE_TEMPLATE.format(
        branch=branch,
        tag=tag,
        call_id=call_id,
        content_length=len(sdp_body),
        sdp_body=sdp_body
    )
    
    return invite, call_id

async def send_sip_invite() -> Dict[str, Any]:
    """Send SIP INVITE to OpenSIPS"""
    try:
        print("📞 Creating test SIP INVITE...")
        
        # Create INVITE message
        invite_msg, call_id = await create_test_sip_invite()
        
        # Send to OpenSIPS (container network)
        opensips_ip = "172.18.0.2"  # OpenSIPS container IP
        opensips_port = 5060
        
        print(f"📡 Sending INVITE to {opensips_ip}:{opensips_port}")
        print(f"📞 Call ID: test-call-{call_id}")
        
        # Create UDP socket for SIP
        sip_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sip_sock.sendto(invite_msg.encode(), (opensips_ip, opensips_port))
        
        print("✅ SIP INVITE sent successfully")
        
        # Wait for 200 OK response (basic)
        sip_sock.settimeout(10.0)
        try:
            response_data, addr = sip_sock.recvfrom(4096)
            response = response_data.decode()
            print(f"📨 SIP Response received from {addr}")
            
            # Extract RTP port from SDP response
            lines = response.split('\n')
            rtp_port = None
            for line in lines:
                if line.startswith('m=audio'):
                    parts = line.split()
                    if len(parts) >= 2:
                        rtp_port = int(parts[1])
                        break
            
            if rtp_port:
                print(f"🎵 OAVC RTP Port: {rtp_port}")
                return {
                    'success': True,
                    'call_id': f"test-call-{call_id}",
                    'rtp_port': rtp_port,
                    'response': response[:200] + "..."
                }
            else:
                print("❌ Could not extract RTP port from response")
                return {'success': False, 'error': 'No RTP port in response'}
                
        except socket.timeout:
            print("⏰ Timeout waiting for SIP response")
            return {'success': False, 'error': 'SIP timeout'}
        finally:
            sip_sock.close()
            
    except Exception as e:
        print(f"❌ Error sending SIP INVITE: {e}")
        return {'success': False, 'error': str(e)}

def generate_test_rtp_packet() -> bytes:
    """Generate a test RTP packet with PCMU payload"""
    # RTP Header
    version = 2
    padding = 0
    extension = 0
    cc = 0
    marker = 0
    pt = 0  # PCMU
    sequence = random.randint(1, 65535)
    timestamp = int(time.time() * 8000) & 0xFFFFFFFF
    ssrc = 0x12345678
    
    # Pack RTP header
    rtp_header = struct.pack('!BBHII',
        (version << 6) | (padding << 5) | (extension << 4) | cc,
        (marker << 7) | pt,
        sequence,
        timestamp,
        ssrc
    )
    
    # Generate PCMU payload (160 bytes for 20ms)
    pcmu_payload = bytes([0xFF, 0x7F] * 80)
    
    return rtp_header + pcmu_payload

async def send_test_rtp_packets(target_ip: str, target_port: int, duration: int = 10):
    """Send test RTP packets"""
    try:
        print(f"🎤 Sending RTP packets to {target_ip}:{target_port} for {duration} seconds...")
        
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        packet_count = 0
        start_time = time.time()
        
        while time.time() - start_time < duration:
            rtp_packet = generate_test_rtp_packet()
            sock.sendto(rtp_packet, (target_ip, target_port))
            
            packet_count += 1
            if packet_count % 50 == 0:  # Log every 50 packets (1 second)
                print(f"📦 Sent {packet_count} RTP packets...")
            
            await asyncio.sleep(0.02)  # 20ms intervals
            
        sock.close()
        print(f"✅ Completed! Sent {packet_count} RTP packets total")
        
    except Exception as e:
        print(f"❌ Error sending RTP packets: {e}")

async def monitor_container_logs():
    """Monitor container logs for RTP activity"""
    import subprocess
    
    print("🔍 Monitoring container logs for RTP activity...")
    try:
        # Run docker logs in background
        process = subprocess.Popen(
            ["docker", "logs", "opensips-ai-voice-connector", "--follow"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        
        # Read logs for a few seconds
        await asyncio.sleep(5)
        process.terminate()
        
    except Exception as e:
        print(f"❌ Error monitoring logs: {e}")

async def main():
    """Main test function"""
    print("🚀 Test Call with RTP Flow")
    print("=" * 50)
    
    # Step 1: Send SIP INVITE
    print("\n📞 Step 1: Sending SIP INVITE...")
    call_result = await send_sip_invite()
    
    if not call_result['success']:
        print(f"❌ SIP INVITE failed: {call_result['error']}")
        return
    
    print(f"✅ Call established - RTP Port: {call_result['rtp_port']}")
    
    # Step 2: Wait a moment for pipeline setup
    print("\n⏳ Step 2: Waiting for pipeline setup...")
    await asyncio.sleep(2)
    
    # Step 3: Send RTP packets
    print("\n🎵 Step 3: Sending RTP packets...")
    
    # Create background log monitoring
    log_task = asyncio.create_task(monitor_container_logs())
    
    # Send RTP packets
    await send_test_rtp_packets("192.168.88.120", call_result['rtp_port'], duration=15)
    
    # Stop log monitoring
    log_task.cancel()
    
    print("\n🎉 Test completed!")
    print(f"📞 Call ID: {call_result['call_id']}")
    print(f"🎵 RTP Port: {call_result['rtp_port']}")
    print("💡 Check container logs for RTP processing details")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n⏹️ Test interrupted by user")
    except Exception as e:
        print(f"\n❌ Test failed: {e}") 