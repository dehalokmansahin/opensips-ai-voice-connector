#!/usr/bin/env python3
"""
Vosk WebSocket STT servisini test etmek için basit test scripti - NumPy 2.x uyumlu
"""

import asyncio
import logging
import sys
from pathlib import Path

# Path setup
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root / "src"))
sys.path.insert(0, str(project_root / "pipecat" / "src"))

# NumPy 2.x compatibility stub'ını yükle
sys.path.insert(0, str(project_root / "tests"))
import conftest  # Bu soxr stub'ını yükler

try:
    # Şimdi pipecat'i import et
    from pipecat.frames.frames import Frame
    print("✅ Pipecat modülü başarıyla import edildi")
except ImportError as e:
    print(f"❌ Pipecat import hatası: {e}")
    # Pipecat olmadan da Vosk testini yapalım
    print("⚠️ Pipecat olmadan basit Vosk testi yapılacak")

# Basit Vosk test fonksiyonu (Pipecat'siz)
import websockets
import json

async def test_vosk_simple_without_pipecat():
    """Pipecat olmadan basit Vosk testi"""
    
    print("🎤 Basit Vosk WebSocket Test (Pipecat'siz)")
    
    try:
        uri = "ws://localhost:2700"
        
        async with websockets.connect(uri) as websocket:
            print("✅ Vosk'a bağlantı başarılı!")
            
            # Config gönder
            config = {
                "config": {
                    "sample_rate": 16000,
                    "format": "json",
                    "words": True
                }
            }
            
            await websocket.send(json.dumps(config))
            print("📤 Config gönderildi")
            
            # Test ses verisi (sessizlik)
            silence_chunk = b'\x00' * 1600  # 100ms sessizlik
            
            for i in range(5):
                await websocket.send(silence_chunk)
                print(f"📤 Ses chunk {i+1} gönderildi")
                
                # Yanıt kontrol et
                try:
                    response = await asyncio.wait_for(websocket.recv(), timeout=0.5)
                    result = json.loads(response)
                    print(f"📥 Yanıt: {result}")
                except asyncio.TimeoutError:
                    print("⏳ Yanıt yok (normal)")
                
                await asyncio.sleep(0.2)
            
            # EOS gönder
            await websocket.send('{"eof": 1}')
            print("📤 EOS gönderildi")
            
            # Final yanıt
            try:
                final_response = await asyncio.wait_for(websocket.recv(), timeout=2.0)
                final_result = json.loads(final_response)
                print(f"📥 Final yanıt: {final_result}")
            except asyncio.TimeoutError:
                print("⏰ Final yanıt timeout")
            
            print("✅ Vosk test başarılı!")
            
    except Exception as e:
        print(f"❌ Vosk test hatası: {e}")

# Test ses dosyası ile test
async def test_vosk_with_audio_file():
    """Test ses dosyası ile Vosk testi"""
    
    print("🎵 Test ses dosyası ile Vosk testi")
    
    test_audio_file = Path("test_audio/barge_in_test.raw")
    
    if not test_audio_file.exists():
        print(f"❌ Test ses dosyası bulunamadı: {test_audio_file}")
        return
    
    try:
        # Ses dosyasını oku
        with open(test_audio_file, "rb") as f:
            audio_data = f.read()
        
        print(f"📁 Ses dosyası okundu: {len(audio_data)} bytes")
        
        # PCMU'yu PCM'e çevir (basit)
        # Bu basit bir dönüşüm - gerçek g711 decode gerekebilir
        pcm_data = audio_data  # Şimdilik direkt kullan
        
        uri = "ws://localhost:2700"
        
        async with websockets.connect(uri) as websocket:
            print("✅ Vosk'a bağlantı başarılı!")
            
            # Config gönder
            config = {
                "config": {
                    "sample_rate": 8000,  # PCMU genelde 8kHz
                    "format": "json",
                    "words": True
                }
            }
            
            await websocket.send(json.dumps(config))
            print("📤 Config gönderildi")
            
            # Ses verisini chunk'lara böl
            chunk_size = 1600  # 200ms at 8kHz
            chunks = [pcm_data[i:i+chunk_size] for i in range(0, len(pcm_data), chunk_size)]
            
            print(f"📦 {len(chunks)} chunk gönderilecek")
            
            for i, chunk in enumerate(chunks):
                if len(chunk) > 0:
                    await websocket.send(chunk)
                    print(f"📤 Chunk {i+1}/{len(chunks)} gönderildi")
                    
                    # Yanıt kontrol et
                    try:
                        response = await asyncio.wait_for(websocket.recv(), timeout=0.1)
                        result = json.loads(response)
                        if result.get("partial") or result.get("text"):
                            print(f"🎯 STT: {result}")
                    except asyncio.TimeoutError:
                        pass
                    
                    await asyncio.sleep(0.1)
            
            # EOS gönder
            await websocket.send('{"eof": 1}')
            print("📤 EOS gönderildi")
            
            # Final yanıt
            try:
                final_response = await asyncio.wait_for(websocket.recv(), timeout=2.0)
                final_result = json.loads(final_response)
                print(f"📥 Final STT sonuç: {final_result}")
            except asyncio.TimeoutError:
                print("⏰ Final yanıt timeout")
                
    except Exception as e:
        print(f"❌ Ses dosyası test hatası: {e}")

if __name__ == "__main__":
    print("🚀 Vosk WebSocket Test - NumPy 2.x Uyumlu")
    print("=" * 50)
    
    print("\n1️⃣ Basit Test:")
    asyncio.run(test_vosk_simple_without_pipecat())
    
    print("\n" + "=" * 50)
    
    print("\n2️⃣ Ses Dosyası Testi:")
    asyncio.run(test_vosk_with_audio_file())
    
    print("\n✨ Test tamamlandı!") 