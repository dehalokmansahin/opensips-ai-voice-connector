#!/usr/bin/env python3
"""
Internal Container Test
Container içinden SIP Listener'a direkt test message gönder
"""

import socket
import time

def test_internal_localhost():
    """Test UDP to localhost inside container"""
    print("🔧 Internal Container Test")
    print("=" * 40)
    
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(2.0)
        
        # Test localhost
        target_ip = "127.0.0.1"
        target_port = 8089
        
        test_messages = [
            b"INTERNAL_TEST_MESSAGE",
            b"INVITE sip:test@localhost SIP/2.0\r\n\r\n",
        ]
        
        for i, message in enumerate(test_messages, 1):
            print(f"\n📦 Test {i}: Sending to {target_ip}:{target_port}")
            print(f"   Message: {message.decode()[:50]}")
            
            try:
                bytes_sent = sock.sendto(message, (target_ip, target_port))
                print(f"✅ Sent {bytes_sent} bytes to localhost")
                
                # Brief pause
                time.sleep(0.1)
                
            except Exception as e:
                print(f"❌ Error: {e}")
                
        sock.close()
        print(f"\n✅ Internal test completed")
        
    except Exception as e:
        print(f"❌ Internal test failed: {e}")

if __name__ == "__main__":
    test_internal_localhost()
    print("💡 Check application logs for message processing") 