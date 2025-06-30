#!/usr/bin/env python3
"""
Pipeline Flow Debug Script
RTP → Pipeline → AI Services akışını kontrol eder
"""

import asyncio
import sys
import time
import subprocess
import json
from typing import Dict, Any

def check_container_logs(container_name: str, keyword: str, lines: int = 20) -> bool:
    """Check container logs for specific keywords"""
    try:
        cmd = f"docker logs {container_name} --tail={lines}"
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        
        if result.returncode == 0:
            logs = result.stdout
            return keyword.lower() in logs.lower()
        else:
            print(f"❌ Failed to get logs from {container_name}: {result.stderr}")
            return False
    except Exception as e:
        print(f"❌ Error checking logs: {e}")
        return False

def check_container_status(container_name: str) -> Dict[str, Any]:
    """Check container status and health"""
    try:
        cmd = f"docker inspect {container_name}"
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        
        if result.returncode == 0:
            data = json.loads(result.stdout)[0]
            state = data.get('State', {})
            return {
                'running': state.get('Running', False),
                'status': state.get('Status', 'unknown'),
                'started_at': state.get('StartedAt', 'unknown'),
                'health': state.get('Health', {}).get('Status', 'no health check')
            }
        else:
            return {'running': False, 'status': 'not found'}
    except Exception as e:
        print(f"❌ Error checking container status: {e}")
        return {'running': False, 'status': 'error'}

async def test_rtp_flow():
    """Test RTP packet flow"""
    print("🎵 Testing RTP Packet Flow...")
    print("=" * 50)
    
    # Check OAVC container status
    oavc_status = check_container_status("opensips-ai-voice-connector")
    print(f"📦 OAVC Container: {oavc_status['status']}")
    
    if not oavc_status['running']:
        print("❌ OAVC container is not running!")
        return False
    
    # Check recent logs for RTP activity
    print("🔍 Checking recent RTP activity...")
    
    keywords_to_check = [
        ("📦 UDP packet received", "RTP packets being received"),
        ("🎵 Processing RTP packet", "RTP packet processing"),
        ("✅ RTP packet decoded", "RTP decoding success"),
        ("✅ PCMU→PCM conversion", "Audio conversion success"),
        ("📦 Created InputAudioRawFrame", "Audio frame creation"),
        ("✅ Audio frame pushed to pipeline", "Pipeline push success"),
        ("🎤 VAD received audio frame", "VAD processing"),
        ("🗣️ STT received audio frame", "STT processing")
    ]
    
    for keyword, description in keywords_to_check:
        found = check_container_logs("opensips-ai-voice-connector", keyword)
        status = "✅" if found else "❌"
        print(f"{status} {description}: {'Found' if found else 'Not found'}")
    
    print()
    return True

async def test_service_connectivity():
    """Test AI service connectivity"""
    print("🧠 Testing AI Service Connectivity...")
    print("=" * 50)
    
    services = {
        "vosk-server": {"port": 2700, "type": "STT"},
        "llm-turkish-server": {"port": 8765, "type": "LLM"},
        "piper-tts-server": {"port": 8000, "type": "TTS"}
    }
    
    for service_name, info in services.items():
        status = check_container_status(service_name)
        status_icon = "✅" if status['running'] else "❌"
        print(f"{status_icon} {info['type']} ({service_name}): {status['status']}")
        
        # Check service-specific logs
        if status['running']:
            service_active = check_container_logs(service_name, "connected", 10)
            activity_icon = "🟢" if service_active else "🟡"
            print(f"   {activity_icon} Recent activity: {'Yes' if service_active else 'Minimal'}")
    
    print()

async def test_pipeline_flow():
    """Test complete pipeline flow"""
    print("🔄 Testing Complete Pipeline Flow...")
    print("=" * 50)
    
    # Check pipeline stages
    pipeline_stages = [
        ("StartFrame", "Pipeline initialization"),
        ("InputAudioRawFrame", "Audio input"),
        ("VAD processing", "Voice activity detection"),
        ("STT processing", "Speech to text"),
        ("LLM processing", "Language model"),
        ("TTS processing", "Text to speech"),
        ("OutputAudioRawFrame", "Audio output")
    ]
    
    for stage, description in pipeline_stages:
        found = check_container_logs("opensips-ai-voice-connector", stage)
        status = "✅" if found else "❌"
        print(f"{status} {description}: {'Active' if found else 'No recent activity'}")
    
    print()

async def check_network_connectivity():
    """Check network connectivity between components"""
    print("🌐 Testing Network Connectivity...")
    print("=" * 50)
    
    # Test UDP connectivity to OAVC
    try:
        import socket
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(2.0)
        
        # Test RTP port
        test_msg = b"PING"
        sock.sendto(test_msg, ("192.168.88.120", 35009))
        print("✅ UDP connectivity to RTP port: Success")
        sock.close()
        
    except Exception as e:
        print(f"❌ UDP connectivity to RTP port: Failed ({e})")
    
    # Check Docker network
    try:
        cmd = "docker network ls | grep opensips"
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        if result.returncode == 0 and result.stdout.strip():
            print("✅ Docker network: Found")
        else:
            print("❌ Docker network: Not found")
    except Exception as e:
        print(f"❌ Docker network check failed: {e}")
    
    print()

async def send_test_rtp_packets(duration: int = 5):
    """Send test RTP packets"""
    print(f"📡 Sending test RTP packets for {duration} seconds...")
    print("=" * 50)
    
    try:
        # Import RTP debug functions
        from debug_rtp_flow import send_test_rtp_packets
        
        # Send packets to current call's RTP port
        await send_test_rtp_packets("192.168.88.120", 35009, duration)
        print("✅ Test RTP packets sent successfully")
        
    except Exception as e:
        print(f"❌ Failed to send test RTP packets: {e}")
    
    print()

async def main():
    """Main debug function"""
    print("🚀 OpenSIPS AI Voice Connector - Pipeline Debug Tool")
    print("=" * 60)
    print()
    
    # Test sequence
    await test_service_connectivity()
    await check_network_connectivity()
    await test_rtp_flow()
    await test_pipeline_flow()
    
    # Interactive test options
    print("🎛️ Interactive Test Options:")
    print("1. Send test RTP packets (5 seconds)")
    print("2. Send test RTP packets (30 seconds)")
    print("3. Monitor live logs")
    print("4. Exit")
    
    while True:
        try:
            choice = input("\nSelect option (1-4): ").strip()
            
            if choice == "1":
                await send_test_rtp_packets(5)
                break
            elif choice == "2":
                await send_test_rtp_packets(30)
                break
            elif choice == "3":
                print("🔍 Starting live log monitor...")
                subprocess.run("docker logs opensips-ai-voice-connector --follow", shell=True)
                break
            elif choice == "4":
                print("👋 Exiting debug tool")
                break
            else:
                print("❌ Invalid choice. Please select 1-4.")
                
        except KeyboardInterrupt:
            print("\n👋 Debug tool interrupted")
            break
        except Exception as e:
            print(f"❌ Error: {e}")
            break

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Debug tool interrupted")
    except Exception as e:
        print(f"❌ Fatal error: {e}") 