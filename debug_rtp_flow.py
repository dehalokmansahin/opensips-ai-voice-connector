#!/usr/bin/env python3
"""
RTP Flow Debug Tool
Wireshark ile birlikte kullanılmak üzere RTP akış sorunlarını debug etmek için
"""

import socket
import struct
import time
import threading
from typing import Dict, Any
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class RTPFlowDebugger:
    """RTP akış sorunlarını debug etmek için araç"""
    
    def __init__(self):
        self.rtp_ports = []
        self.active_flows = {}
        
    def test_port_binding(self, ip: str, port_range: tuple):
        """Port binding testleri"""
        logger.info(f"🔧 Testing port binding on {ip}:{port_range[0]}-{port_range[1]}")
        
        successful_ports = []
        failed_ports = []
        
        for port in range(port_range[0], port_range[1] + 1):
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                sock.bind((ip, port))
                
                actual_port = sock.getsockname()[1]
                successful_ports.append(actual_port)
                logger.info(f"✅ Port {port} -> {actual_port} bound successfully")
                sock.close()
                
            except Exception as e:
                failed_ports.append((port, str(e)))
                logger.error(f"❌ Port {port} binding failed: {e}")
        
        return successful_ports, failed_ports
    
    def test_rtp_connectivity(self, local_ip: str, local_port: int, remote_ip: str, remote_port: int):
        """RTP bağlantı testi"""
        logger.info(f"🎵 Testing RTP connectivity: {local_ip}:{local_port} -> {remote_ip}:{remote_port}")
        
        try:
            # UDP socket oluştur
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.bind((local_ip, local_port))
            sock.settimeout(5.0)
            
            # Test RTP paketi gönder
            test_rtp = self._create_test_rtp_packet()
            logger.info(f"📤 Sending test RTP packet to {remote_ip}:{remote_port}")
            sock.sendto(test_rtp, (remote_ip, remote_port))
            
            # Cevap bekleme
            try:
                data, addr = sock.recvfrom(1024)
                logger.info(f"📥 Received response from {addr}: {len(data)} bytes")
                return True
            except socket.timeout:
                logger.warning(f"⏰ No response received within timeout")
                return False
                
        except Exception as e:
            logger.error(f"❌ RTP connectivity test failed: {e}")
            return False
        finally:
            sock.close()
    
    def _create_test_rtp_packet(self) -> bytes:
        """Test RTP paketi oluştur"""
        # RTP Header: V=2, P=0, X=0, CC=0, M=0, PT=0, SEQ=1, TS=160, SSRC=12345
        rtp_header = struct.pack('!BBHII', 
                               0x80,  # V=2, P=0, X=0, CC=0
                               0x00,  # M=0, PT=0 (PCMU)
                               1,     # Sequence number
                               160,   # Timestamp
                               12345) # SSRC
        
        # Test payload (silence)
        payload = b'\xFF' * 160  # 160 bytes of PCMU silence
        
        return rtp_header + payload
    
    def capture_instructions(self):
        """Wireshark capture talimatları"""
        instructions = """
        🔍 WIRESHARK CAPTURE TALİMATLARI:
        
        1. Wireshark'ı Yönetici olarak çalıştırın
        
        2. Capture Interface'i seçin:
           - Windows: "Adapter for loopback traffic capture" (loopback)
           - Docker: "Docker NAT" veya "vEthernet (DockerNAT)"
           
        3. Capture Filter kullanın:
           - SIP traffic için: "port 5060 or port 8089"
           - RTP traffic için: "udp and portrange 35000-35020"
           - Tüm traffic için: "host 192.168.88.1 or host 192.168.88.120"
        
        4. Aradığınız paketler:
           ✅ SIP INVITE (192.168.88.1 -> OpenSIPS)
           ✅ SIP 200 OK (OAVC -> 192.168.88.1) 
           ✅ SIP ACK (192.168.88.1 -> OAVC)
           ❌ RTP packets (192.168.88.1 <-> 192.168.88.120:35008)
        
        5. RTP Flow analizi:
           - Statistics -> Flow Graph
           - Telephony -> RTP -> RTP Streams
           - Telephony -> VoIP Calls
        
        6. Kontrol edilecek noktalar:
           - RTP paketleri gönderiliyor mu?
           - Hedef IP doğru mu? (192.168.88.120)
           - Hedef port doğru mu? (35008)
           - Source IP client'dan geliyor mu? (192.168.88.1)
        """
        
        print(instructions)
        return instructions

def main():
    """Ana debug fonksiyonu"""
    debugger = RTPFlowDebugger()
    
    print("🚀 RTP Flow Debug Tool Started")
    print("=" * 50)
    
    # Wireshark talimatlarını göster
    debugger.capture_instructions()
    
    print("\n🔧 DOCKER PORT BINDING TEST")
    print("=" * 30)
    
    # Port binding testleri
    bind_ips = ["0.0.0.0", "127.0.0.1"]
    port_range = (35000, 35020)
    
    for ip in bind_ips:
        print(f"\n📍 Testing IP: {ip}")
        successful, failed = debugger.test_port_binding(ip, port_range)
        
        print(f"✅ Successful ports: {len(successful)}")
        print(f"❌ Failed ports: {len(failed)}")
        
        if failed:
            print("Failed ports details:")
            for port, error in failed[:5]:  # İlk 5 hatayı göster
                print(f"  - Port {port}: {error}")
    
    print("\n🎵 RTP CONNECTIVITY TEST")
    print("=" * 25)
    
    # RTP bağlantı testi
    test_configs = [
        ("0.0.0.0", 35008, "192.168.88.1", 4056),
        ("127.0.0.1", 35009, "127.0.0.1", 4057),
    ]
    
    for local_ip, local_port, remote_ip, remote_port in test_configs:
        print(f"\n📡 Testing: {local_ip}:{local_port} -> {remote_ip}:{remote_port}")
        result = debugger.test_rtp_connectivity(local_ip, local_port, remote_ip, remote_port)
        print(f"Result: {'✅ SUCCESS' if result else '❌ FAILED'}")
    
    print("\n📊 NETWORK CONFIGURATION SUMMARY")
    print("=" * 35)
    
    print("""
    🖥️  ANA MAKİNE:
        - Wi-Fi IP: 192.168.1.120
        - VMware IP: 192.168.116.1
    
    📞 SIP CLIENT:
        - IP: 192.168.88.1 (muhtemelen softphone)
        - Port: 64040 (dynamic)
    
    🐳 DOCKER CONTAINERS:
        - OpenSIPS: 172.18.0.4:5060
        - OAVC: 172.18.0.x:8089
        - RTP Advertised: 192.168.88.120:35008
    
    ⚠️  SORUN TEŞHİSİ:
        1. Client (192.168.88.1) -> RTP (192.168.88.120:35008) erişemiyor
        2. Docker container içindeki port host'a mapping yapılmamış olabilir
        3. IP adresi yanlış advertise ediliyor olabilir
        4. NAT/Firewall sorunu olabilir
    """)
    
    print("\n🔧 ÖNERİLEN ÇÖZÜMLER:")
    print("=" * 20)
    print("""
    1. Docker port mapping'ini kontrol edin
    2. SDP'deki IP adresini düzeltin
    3. Client ve container arasında ping testi yapın
    4. Windows Firewall'u kontrol edin
    5. Docker Desktop network ayarlarını kontrol edin
    """)

if __name__ == "__main__":
    main() 