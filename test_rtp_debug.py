#!/usr/bin/env python3
"""
Comprehensive RTP Debug Test Script
Tüm debug araçlarını bir araya getiren kapsamlı test scripti
"""

import os
import sys
import subprocess
import time
import threading
import argparse
from concurrent.futures import ThreadPoolExecutor

def run_command(cmd, description):
    """Komutu çalıştır ve sonucu göster"""
    print(f"\n🔧 {description}")
    print("=" * 50)
    
    try:
        if isinstance(cmd, list):
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        else:
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30)
        
        if result.returncode == 0:
            print(f"✅ Success:")
            print(result.stdout)
        else:
            print(f"❌ Error (code {result.returncode}):")
            print(result.stderr)
            
    except subprocess.TimeoutExpired:
        print("⏰ Command timed out")
    except Exception as e:
        print(f"❌ Exception: {e}")

def test_network_connectivity():
    """Network bağlantı testleri"""
    print("\n🌐 NETWORK CONNECTIVITY TESTS")
    print("=" * 50)
    
    # Test endpoints
    endpoints = [
        ("127.0.0.1", "Loopback"),
        ("192.168.1.120", "Ana Makine Wi-Fi IP"),
        ("192.168.88.1", "SIP Client IP"),
        ("192.168.88.120", "Eski RTP IP"),
    ]
    
    for ip, description in endpoints:
        print(f"\n📍 Testing {description} ({ip}):")
        
        # Ping test
        ping_cmd = f"ping -n 1 -w 1000 {ip}" if os.name == 'nt' else f"ping -c 1 -W 1 {ip}"
        run_command(ping_cmd, f"Ping {ip}")

def test_docker_ports():
    """Docker port testleri"""
    print("\n🐳 DOCKER PORT TESTS")
    print("=" * 50)
    
    # Docker container status
    run_command("docker ps", "Docker Container Status")
    
    # Port mapping check
    run_command("docker port opensips-ai-voice-connector", "OAVC Port Mappings")
    
    # Network check
    run_command("docker network ls", "Docker Networks")
    run_command("docker network inspect opensips_network", "Network Details")

def test_windows_firewall():
    """Windows Firewall testleri"""
    print("\n🔥 WINDOWS FIREWALL TESTS")
    print("=" * 50)
    
    # Firewall status
    run_command("netsh advfirewall show allprofiles", "Firewall Status")
    
    # Port listening check
    run_command("netstat -an | findstr :35008", "Port 35008 Status")
    run_command("netstat -an | findstr :8089", "Port 8089 Status")

def run_rtp_test_client(duration=30):
    """RTP test client'ı çalıştır"""
    print(f"\n🎵 RTP TEST CLIENT ({duration} seconds)")
    print("=" * 50)
    
    cmd = [
        "python", "test_rtp_client.py",
        "--local-ip", "192.168.88.1",
        "--local-port", "4056", 
        "--remote-ip", "192.168.1.120",
        "--remote-port", "35008",
        "--duration", str(duration)
    ]
    
    try:
        print("🚀 Starting RTP Test Client...")
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=duration + 10)
        
        print("📊 RTP Test Results:")
        print(result.stdout)
        
        if result.stderr:
            print("⚠️ Errors:")
            print(result.stderr)
            
    except subprocess.TimeoutExpired:
        print("⏰ RTP test timed out")
    except FileNotFoundError:
        print("❌ test_rtp_client.py not found")
    except Exception as e:
        print(f"❌ Error running RTP test: {e}")

def show_wireshark_instructions():
    """Wireshark kullanım talimatları"""
    instructions = """
    
    🔍 WIRESHARK DEBUG TALİMATLARI:
    ═══════════════════════════════════════════════════════════════════════════
    
    1. 🚀 BAŞLATMA:
       - Wireshark'ı YÖNETİCİ olarak çalıştırın
       - "Capture" -> "Options" menüsünden interface seçin
    
    2. 📡 INTERFACE SEÇİMİ:
       Windows'ta şu interface'leri deneyin:
       ✅ "Adapter for loopback traffic capture" (Loopback)
       ✅ "Wi-Fi" (Ana network kartı)
       ✅ "Ethernet" (Kablolu bağlantı)
       ✅ "vEthernet (DockerNAT)" (Docker network)
    
    3. 🔍 CAPTURE FILTER'LAR:
       Aşağıdaki filtreleri "Capture Filter" alanına yazın:
       
       SIP + RTP Traffic:
       host 192.168.88.1 or host 192.168.1.120 or port 5060 or port 8089
       
       Sadece RTP Traffic:
       udp and portrange 35000-35020
       
       Geniş Kapsamlı:
       (host 192.168.88.1 or host 192.168.1.120) and (port 5060 or port 8089 or portrange 35000-35020)
    
    4. 📊 ANALİZ ADIMLARI:
       
       a) 📞 SIP AKIŞI:
          - INVITE: 192.168.88.1 -> OpenSIPS (5060)
          - INVITE: OpenSIPS -> OAVC (8089)
          - 200 OK: OAVC -> OpenSIPS
          - 200 OK: OpenSIPS -> 192.168.88.1
          - ACK: 192.168.88.1 -> OAVC
       
       b) 🎵 RTP AKIŞI (BU EKSIK OLAN KISIM):
          - RTP: 192.168.88.1:4056 -> 192.168.1.120:35008
          - RTP: 192.168.1.120:35008 -> 192.168.88.1:4056
    
    5. 🔎 DISPLAY FILTER'LAR:
       Capture tamamlandıktan sonra şu filtreleri kullanın:
       
       sip                           # Sadece SIP paketleri
       rtp                           # Sadece RTP paketleri  
       ip.addr == 192.168.88.1      # Client traffic
       ip.addr == 192.168.1.120     # Host traffic
       udp.port == 35008             # Belirli RTP port
    
    6. 📈 MENÜ ANALİZİ:
       - Statistics -> Flow Graph (Tüm akış)
       - Telephony -> VoIP Calls (SIP call'ları)
       - Telephony -> RTP -> RTP Streams (RTP akışları)
       - Statistics -> Conversations (IP istatistikleri)
    
    7. ✅ BAŞARILI AKIŞ:
       Şunları görmelisiniz:
       ✅ SIP INVITE/200 OK/ACK sequence
       ✅ RTP paketleri her iki yönde (192.168.88.1 <-> 192.168.1.120)
       ✅ RTP Payload Type 0 (PCMU)
       ✅ RTP paketleri 20ms arayla (50 paket/saniye)
    
    8. ❌ SORUN TEŞHİSİ:
       Eğer RTP paketleri görünmüyorsa:
       - Port mapping'leri kontrol edin (docker ps -a)
       - Windows Firewall'u kontrol edin
       - IP adresi routing'ini kontrol edin
       - Docker network bridge'ini kontrol edin
    
    ═══════════════════════════════════════════════════════════════════════════
    """
    
    print(instructions)

def main():
    """Ana test fonksiyonu"""
    parser = argparse.ArgumentParser(description='Comprehensive RTP Debug Tool')
    parser.add_argument('--quick', action='store_true', help='Quick test (skip long operations)')
    parser.add_argument('--rtp-duration', type=int, default=30, help='RTP test duration in seconds')
    parser.add_argument('--skip-network', action='store_true', help='Skip network tests')
    parser.add_argument('--skip-docker', action='store_true', help='Skip Docker tests')
    parser.add_argument('--skip-firewall', action='store_true', help='Skip firewall tests')
    parser.add_argument('--rtp-only', action='store_true', help='Only run RTP test')
    
    args = parser.parse_args()
    
    print("🚀 COMPREHENSIVE RTP DEBUG TOOL")
    print("=" * 80)
    print(f"Mode: {'Quick' if args.quick else 'Full'}")
    print(f"RTP Test Duration: {args.rtp_duration} seconds")
    print("=" * 80)
    
    if args.rtp_only:
        run_rtp_test_client(args.rtp_duration)
        return
    
    # Test sırası
    test_functions = []
    
    if not args.skip_network:
        test_functions.append(test_network_connectivity)
    
    if not args.skip_docker:
        test_functions.append(test_docker_ports)
    
    if not args.skip_firewall and not args.quick:
        test_functions.append(test_windows_firewall)
    
    # Testleri çalıştır
    for test_func in test_functions:
        try:
            test_func()
        except Exception as e:
            print(f"❌ Test failed: {e}")
        
        time.sleep(1)  # Test'ler arası kısa bekleme
    
    # RTP test client
    if not args.quick:
        run_rtp_test_client(args.rtp_duration)
    
    # Wireshark talimatları
    show_wireshark_instructions()
    
    print("\n🎯 SONUÇ VE ÖNERİLER:")
    print("=" * 50)
    print("""
    1. 🔍 Wireshark'ı başlatın ve yukarıdaki talimatları takip edin
    2. 📞 SIP call başlatın (softphone ile)
    3. 🎵 RTP paketlerini arayın
    4. ❌ RTP yok ise: Docker port mapping, IP routing, firewall kontrol edin
    5. 🐛 Debug için log'ları kontrol edin: ./logs/
    
    📧 Sonuçları paylaşmak için:
    - Wireshark capture file (.pcap)
    - Docker container log'ları
    - Bu test script'inin çıktısı
    """)

if __name__ == "__main__":
    main()

# Kullanım örnekleri:
# python test_rtp_debug.py                    # Full test
# python test_rtp_debug.py --quick            # Quick test
# python test_rtp_debug.py --rtp-only         # Sadece RTP test
# python test_rtp_debug.py --rtp-duration 60  # 60 saniye RTP test 