#!/usr/bin/env python3
"""
RTP Test Client
SIP client'ın RTP davranışını simüle eder - Wireshark debug için
"""

import socket
import struct
import time
import threading
import argparse
from typing import Tuple
import random

# RTP Test Configuration
LOCAL_IP = "127.0.0.1"       # Localhost test
REMOTE_IP = "127.0.0.1"      # Localhost test

class RTPTestClient:
    """SIP client RTP davranışını simüle eden test client'ı"""
    
    def __init__(self, local_ip: str, local_port: int, remote_ip: str, remote_port: int):
        self.local_ip = local_ip
        self.local_port = local_port
        self.remote_ip = remote_ip
        self.remote_port = remote_port
        
        self.socket = None
        self.running = False
        self.sequence_number = 1
        self.timestamp = 0
        self.ssrc = 0x12345678
        
    def start(self):
        """RTP test client'ı başlat"""
        try:
            print(f"🚀 Starting RTP Test Client")
            print(f"📍 Local: {self.local_ip}:{self.local_port}")
            print(f"📍 Remote: {self.remote_ip}:{self.remote_port}")
            
            # UDP socket oluştur
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.socket.bind((self.local_ip, self.local_port))
            self.socket.settimeout(1.0)
            
            self.running = True
            
            # RTP sender ve receiver thread'lerini başlat
            sender_thread = threading.Thread(target=self._sender_loop)
            receiver_thread = threading.Thread(target=self._receiver_loop)
            
            sender_thread.start()
            receiver_thread.start()
            
            print("✅ RTP Test Client started successfully")
            print("📦 Sending RTP packets every 20ms...")
            print("📥 Listening for incoming RTP packets...")
            
            # Ana thread'de kullanıcı inputu bekle
            try:
                while self.running:
                    time.sleep(1)
            except KeyboardInterrupt:
                print("\n🛑 Stopping RTP Test Client...")
                self.stop()
            
            sender_thread.join()
            receiver_thread.join()
            
        except Exception as e:
            print(f"❌ Error starting RTP client: {e}")
            self.stop()
    
    def stop(self):
        """RTP test client'ı durdur"""
        self.running = False
        if self.socket:
            self.socket.close()
        print("✅ RTP Test Client stopped")
    
    def _sender_loop(self):
        """RTP paket gönderme döngüsü"""
        packet_count = 0
        
        while self.running:
            try:
                # RTP paketi oluştur
                rtp_packet = self._create_rtp_packet()
                
                # Paketi gönder
                self.socket.sendto(rtp_packet, (self.remote_ip, self.remote_port))
                
                packet_count += 1
                if packet_count % 50 == 0:  # Her saniye log
                    print(f"📤 Sent {packet_count} RTP packets to {self.remote_ip}:{self.remote_port}")
                
                # RTP state'i güncelle
                self.sequence_number = (self.sequence_number + 1) % 65536
                self.timestamp = (self.timestamp + 160) % 0x100000000  # 20ms at 8kHz
                
                # 20ms bekle (50 packets/second)
                time.sleep(0.02)
                
            except Exception as e:
                if self.running:
                    print(f"❌ Error sending RTP packet: {e}")
                break
    
    def _receiver_loop(self):
        """RTP paket alma döngüsü"""
        received_count = 0
        
        while self.running:
            try:
                # RTP paketi al
                data, addr = self.socket.recvfrom(4096)
                
                received_count += 1
                if received_count % 50 == 0:  # Her saniye log
                    print(f"📥 Received {received_count} RTP packets from {addr[0]}:{addr[1]}")
                
                # RTP paketi analiz et
                if received_count == 1:
                    self._analyze_rtp_packet(data, addr)
                
            except socket.timeout:
                continue
            except Exception as e:
                if self.running:
                    print(f"❌ Error receiving RTP packet: {e}")
                break
    
    def _create_rtp_packet(self) -> bytes:
        """RTP paketi oluştur"""
        # RTP Header (12 bytes)
        # V=2, P=0, X=0, CC=0, M=0, PT=0 (PCMU), SEQ, TS, SSRC
        rtp_header = struct.pack('!BBHII',
            0x80,  # V=2, P=0, X=0, CC=0  
            0x00,  # M=0, PT=0 (PCMU)
            self.sequence_number,
            self.timestamp,
            self.ssrc
        )
        
        # PCMU payload (160 bytes for 20ms at 8kHz)
        # Silence: 0xFF, Normal speech: alternating pattern
        payload = bytes([0x7F, 0xFF] * 80)  # Test pattern
        
        return rtp_header + payload
    
    def _analyze_rtp_packet(self, data: bytes, addr: Tuple[str, int]):
        """İlk RTP paketini analiz et"""
        try:
            if len(data) < 12:
                print(f"⚠️ Packet too short: {len(data)} bytes")
                return
            
            # RTP header'ı parse et
            rtp_header = struct.unpack('!BBHII', data[:12])
            
            version = (rtp_header[0] >> 6) & 0x3
            payload_type = rtp_header[1] & 0x7F
            sequence = rtp_header[2]
            timestamp = rtp_header[3]
            ssrc = rtp_header[4]
            
            payload_size = len(data) - 12
            
            print(f"📊 First RTP packet analysis from {addr[0]}:{addr[1]}:")
            print(f"   Version: {version}")
            print(f"   Payload Type: {payload_type} ({'PCMU' if payload_type == 0 else 'Unknown'})")
            print(f"   Sequence: {sequence}")
            print(f"   Timestamp: {timestamp}")
            print(f"   SSRC: 0x{ssrc:08X}")
            print(f"   Payload Size: {payload_size} bytes")
            
        except Exception as e:
            print(f"❌ Error analyzing RTP packet: {e}")

def main():
    """Ana fonksiyon"""
    parser = argparse.ArgumentParser(description='RTP Test Client')
    parser.add_argument('--local-ip', default='127.0.0.1', help='Local IP address')
    parser.add_argument('--local-port', type=int, default=4056, help='Local port')
    parser.add_argument('--remote-ip', default='127.0.0.1', help='Remote IP address')
    parser.add_argument('--remote-port', type=int, default=35008, help='Remote port')
    parser.add_argument('--duration', type=int, default=0, help='Test duration in seconds (0 = infinite)')
    
    args = parser.parse_args()
    
    print("🎵 RTP Test Client")
    print("=" * 50)
    print(f"Local Address: {args.local_ip}:{args.local_port}")
    print(f"Remote Address: {args.remote_ip}:{args.remote_port}")
    print(f"Duration: {'Infinite' if args.duration == 0 else f'{args.duration} seconds'}")
    print("=" * 50)
    
    # RTP test client'ı oluştur ve başlat
    client = RTPTestClient(
        local_ip=args.local_ip,
        local_port=args.local_port,
        remote_ip=args.remote_ip,
        remote_port=args.remote_port
    )
    
    try:
        if args.duration > 0:
            # Belirli süre çalıştır
            client_thread = threading.Thread(target=client.start)
            client_thread.start()
            
            time.sleep(args.duration)
            client.stop()
            client_thread.join()
        else:
            # Sonsuz çalıştır
            client.start()
            
    except KeyboardInterrupt:
        print("\n🛑 Test interrupted by user")
        client.stop()

if __name__ == "__main__":
    main()

# Kullanım örnekleri:
# python test_rtp_client.py --local-ip 192.168.88.1 --local-port 4056 --remote-ip 192.168.1.120 --remote-port 35008
# python test_rtp_client.py --duration 30  # 30 saniye test 