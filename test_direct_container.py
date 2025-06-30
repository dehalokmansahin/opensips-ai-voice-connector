#!/usr/bin/env python3
"""
Direct Container Test
Container IP'sine direkt UDP mesajı gönder
"""

import socket
import time

def test_direct_container():
    """Test direct UDP to container IP"""
    print("🐳 Direct Container UDP Test")
    print("=" * 40)
    
    # Container IP from logs: 172.18.0.6
    container_ip = "172.18.0.6" 
    target_port = 8089
    
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(2.0)
        
        test_messages = [
            b"DIRECT_TEST_MESSAGE_1",
            b"INVITE sip:test@container SIP/2.0\r\n\r\n",
            b"TEST UDP PACKET"
        ]
        
        for i, message in enumerate(test_messages, 1):
            print(f"\n📦 Test {i}: Sending to {container_ip}:{target_port}")
            print(f"   Message: {message.decode()[:50]}")
            
            try:
                bytes_sent = sock.sendto(message, (container_ip, target_port))
                print(f"✅ Sent {bytes_sent} bytes")
                
                # Try to receive (not expected)
                try:
                    response, addr = sock.recvfrom(1024)
                    print(f"📨 Response: {response.decode()[:100]}")
                except socket.timeout:
                    print("⏰ No response (expected)")
                    
            except Exception as e:
                print(f"❌ Error: {e}")
                
            time.sleep(0.5)
            
        sock.close()
        print(f"\n✅ Direct container test completed")
        
    except Exception as e:
        print(f"❌ Direct container test failed: {e}")

def test_host_bridge():
    """Test via host bridge"""
    print("\n🌉 Host Bridge Test")
    print("=" * 40)
    
    # Host IP (what we've been using)
    host_ip = "192.168.88.120" 
    target_port = 8089
    
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(2.0)
        
        message = b"HOST_BRIDGE_TEST_MESSAGE"
        print(f"📦 Sending to {host_ip}:{target_port}")
        print(f"   Message: {message.decode()}")
        
        bytes_sent = sock.sendto(message, (host_ip, target_port))
        print(f"✅ Sent {bytes_sent} bytes")
        
        sock.close()
        
    except Exception as e:
        print(f"❌ Host bridge test failed: {e}")

if __name__ == "__main__":
    test_direct_container()
    test_host_bridge()
    
    print("\n💡 Check container logs after tests")
    print("💡 If direct container test works but host bridge doesn't, it's a Docker networking issue")
    print("💡 If neither works, it's a SIP Listener task issue") 