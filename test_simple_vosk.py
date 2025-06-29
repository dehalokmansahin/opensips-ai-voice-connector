#!/usr/bin/env python3
"""
Basit Vosk WebSocket bağlantı testi - Düzeltilmiş versiyon
"""

import asyncio
import websockets
import json
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def test_vosk_simple():
    """Basit Vosk WebSocket bağlantı testi"""
    
    print("🔗 Vosk WebSocket'e bağlanıyor...")
    
    try:
        uri = "ws://localhost:2700"
        
        async with websockets.connect(uri) as websocket:
            print("✅ Bağlantı başarılı!")
            
            # Vosk WebSocket protokolü farklı - sadece config gönder
            config_message = {
                "config": {
                    "sample_rate": 16000,
                    "format": "json",
                    "words": True
                }
            }
            
            await websocket.send(json.dumps(config_message))
            print("📤 Config mesajı gönderildi")
            
            # Kısa bekleme
            await asyncio.sleep(0.5)
            
            # Boş ses verisi gönder (test için)
            empty_audio = b'\x00' * 1600  # 100ms of silence at 16kHz
            await websocket.send(empty_audio)
            print("📤 Test ses verisi gönderildi")
            
            # Yanıt bekle (timeout ile)
            try:
                response = await asyncio.wait_for(websocket.recv(), timeout=2.0)
                print(f"📥 Yanıt alındı: {response}")
            except asyncio.TimeoutError:
                print("⏰ Yanıt timeout - bu normal olabilir")
            
            # Final mesaj - EOS (End of Stream)
            await websocket.send(b'{"eof": 1}')
            print("📤 EOS mesajı gönderildi")
            
            # Final yanıt bekle
            try:
                final_response = await asyncio.wait_for(websocket.recv(), timeout=2.0)
                print(f"📥 Final yanıt: {final_response}")
            except asyncio.TimeoutError:
                print("⏰ Final yanıt timeout")
            
    except websockets.exceptions.ConnectionClosedError as e:
        print(f"❌ Bağlantı kapandı: {e}")
    except Exception as e:
        print(f"❌ Bağlantı hatası: {e}")
        print("💡 Vosk WebSocket sunucusunu kontrol edin:")
        print("   docker ps | grep vosk")
        print("   docker logs [container_id]")

async def test_vosk_protocol_discovery():
    """Vosk WebSocket protokolünü keşfet"""
    
    print("🔍 Vosk WebSocket protokolünü keşfediyor...")
    
    try:
        uri = "ws://localhost:2700"
        
        async with websockets.connect(uri) as websocket:
            print("✅ Bağlantı kuruldu")
            
            # Farklı mesaj formatlarını dene
            test_messages = [
                # Format 1: JSON config
                {"config": {"sample_rate": 16000}},
                
                # Format 2: Simple start
                {"action": "start"},
                
                # Format 3: GStreamer style
                {
                    "config": {
                        "sample_rate": 16000,
                        "format": "json",
                        "words": True
                    }
                }
            ]
            
            for i, msg in enumerate(test_messages):
                try:
                    print(f"📤 Test mesajı {i+1}: {json.dumps(msg)}")
                    await websocket.send(json.dumps(msg))
                    
                    # Yanıt bekle
                    response = await asyncio.wait_for(websocket.recv(), timeout=1.0)
                    print(f"📥 Yanıt {i+1}: {response}")
                    
                except asyncio.TimeoutError:
                    print(f"⏰ Mesaj {i+1} için yanıt yok")
                except Exception as e:
                    print(f"❌ Mesaj {i+1} hatası: {e}")
                    break
                    
    except Exception as e:
        print(f"❌ Keşif hatası: {e}")

if __name__ == "__main__":
    print("🚀 Vosk WebSocket Test - Gelişmiş")
    print("=" * 40)
    
    print("\n1️⃣ Protokol Keşfi:")
    asyncio.run(test_vosk_protocol_discovery())
    
    print("\n" + "=" * 40)
    
    print("\n2️⃣ Basit Test:")
    asyncio.run(test_vosk_simple())
    
    print("\n✨ Test tamamlandı!") 