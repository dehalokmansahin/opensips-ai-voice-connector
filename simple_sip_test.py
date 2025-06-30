#!/usr/bin/env python3
"""
Simple SIP Test
Basit bir SIP INVITE testi - container network üzerinden
"""

import socket
import random
import time

def create_simple_invite():
    """Create a simple SIP INVITE"""
    call_id = random.randint(100000, 999999)
    tag = random.randint(100000, 999999)
    branch = random.randint(100000, 999999)
    
    # SIP INVITE message - very basic
    invite = f"""INVITE sip:test@192.168.88.120:8089 SIP/2.0
Via: SIP/2.0/UDP 192.168.88.1:5060;branch=z9hG4bK{branch}
From: <sip:test@192.168.88.1>;tag={tag}
To: <sip:test@192.168.88.120:8089>
Call-ID: test{call_id}
CSeq: 1 INVITE
Contact: <sip:test@192.168.88.1:5060>
Content-Type: application/sdp
Content-Length: 135

v=0
o=- {random.randint(1000000, 9999999)} 1 IN IP4 192.168.88.1
s=Test
c=IN IP4 192.168.88.1
t=0 0
m=audio 4000 RTP/AVP 0
a=rtpmap:0 PCMU/8000"""
    
    return invite, call_id

def main():
    """Test function"""
    print("📞 Simple SIP Test")
    print("=" * 30)
    
    try:
        # Create INVITE
        invite, call_id = create_simple_invite()
        print(f"📞 Call ID: test{call_id}")
        
        # Send to OAVC (host IP)
        target_ip = "192.168.88.120"  # Host IP where OAVC is exposed
        target_port = 8089  # OAVC SIP port
        
        print(f"📡 Sending INVITE to {target_ip}:{target_port}")
        print(f"📄 Message preview:\n{invite[:200]}...")
        
        # Send UDP message
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.sendto(invite.encode(), (target_ip, target_port))
        
        # Try to receive response
        sock.settimeout(5.0)
        try:
            response, addr = sock.recvfrom(4096)
            print(f"✅ Response received from {addr}")
            print(f"📨 Response: {response.decode()[:300]}...")
            
            # Look for RTP port
            response_str = response.decode()
            if "m=audio" in response_str:
                lines = response_str.split('\n')
                for line in lines:
                    if line.startswith('m=audio'):
                        parts = line.split()
                        if len(parts) >= 2:
                            rtp_port = parts[1]
                            print(f"🎵 RTP Port found: {rtp_port}")
                            return rtp_port
            
        except socket.timeout:
            print("⏰ No response received (timeout)")
        
        sock.close()
        
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    main() 