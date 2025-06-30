#!/usr/bin/env python3
"""
Test UDP Connectivity
Port 8089'a basit UDP paketleri göndererek connectivity test eder
"""

import socket
import time

def test_udp_connectivity():
    """Test UDP connectivity to OAVC container"""
    print("🌐 UDP Connectivity Test")
    print("=" * 40)
    
    target_ip = "192.168.88.120"
    target_port = 8089
    
    try:
        # Create UDP socket
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(2.0)
        
        # Test messages
        test_messages = [
            b"TEST UDP MESSAGE 1",
            b"TEST UDP MESSAGE 2", 
            b"SIMPLE\r\n\r\n",  # Very simple
            b"INVITE test SIP/2.0\r\n\r\n"  # Minimal SIP-like
        ]
        
        for i, message in enumerate(test_messages, 1):
            print(f"\n📦 Test {i}: Sending '{message.decode()[:30]}...'")
            
            try:
                # Send message
                bytes_sent = sock.sendto(message, (target_ip, target_port))
                print(f"✅ Sent {bytes_sent} bytes to {target_ip}:{target_port}")
                
                # Try to receive response (not expected, just testing)
                try:
                    response, addr = sock.recvfrom(1024)
                    print(f"📨 Response received from {addr}: {response.decode()[:100]}")
                except socket.timeout:
                    print("⏰ No response (expected)")
                    
            except Exception as e:
                print(f"❌ Error sending message {i}: {e}")
                
            time.sleep(0.5)
            
        sock.close()
        print(f"\n✅ UDP connectivity test completed")
        print(f"📍 Target: {target_ip}:{target_port}")
        print("💡 Check container logs for received messages")
        
    except Exception as e:
        print(f"❌ UDP test failed: {e}")

def test_raw_socket_info():
    """Display socket information"""
    print("\n🔍 Socket Information")
    print("=" * 40)
    
    try:
        # Test socket creation
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        print(f"✅ UDP socket created successfully")
        
        # Get local address after binding to any port
        sock.bind(('', 0))
        local_addr = sock.getsockname()
        print(f"📍 Local socket: {local_addr[0]}:{local_addr[1]}")
        
        sock.close()
        
    except Exception as e:
        print(f"❌ Socket info test failed: {e}")

def test_container_reachability():
    """Test if the container port is reachable"""
    print("\n🎯 Container Reachability Test")
    print("=" * 40)
    
    target_ip = "192.168.88.120"
    
    # Test different ports
    test_ports = [8089, 8090, 22, 80]
    
    for port in test_ports:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.settimeout(1.0)
            
            # Send a simple message
            sock.sendto(b"PING", (target_ip, port))
            print(f"📍 Port {port}: ✅ Reachable (UDP)")
            
            sock.close()
            
        except Exception as e:
            print(f"📍 Port {port}: ❌ Error ({str(e)[:50]})")

if __name__ == "__main__":
    test_udp_connectivity()
    test_raw_socket_info()
    test_container_reachability()
    
    print("\n🏁 All tests completed!")
    print("💡 If no messages appear in container logs, there's a network routing issue") 