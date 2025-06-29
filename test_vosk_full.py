#!/usr/bin/env python3
"""
Tam Vosk WebSocket STT servisini test et
"""

import asyncio
import logging
import sys
from pathlib import Path

# Path setup ve soxr stub
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root / "src"))
sys.path.insert(0, str(project_root / "pipecat" / "src"))
sys.path.insert(0, str(project_root / "tests"))
import conftest  # soxr stub'ını yükler

from services.vosk_websocket import VoskWebsocketSTTService
from transports.audio_utils import pcmu_to_pcm16k
import structlog

logging.basicConfig(level=logging.INFO)
logger = structlog.get_logger()

async def test_vosk_service():
    """VoskWebsocketSTTService'i test et"""
    
    print("🎤 VoskWebsocketSTTService Test Başlıyor...")
    
    try:
        # Vosk servisini başlat
        stt_service = VoskWebsocketSTTService()
        
        print("🔗 Vosk WebSocket'e bağlanıyor...")
        await stt_service.start()
        print("✅ Vosk WebSocket bağlantısı başarılı")
        
        # Test ses verisi (basit sinüs dalgası veya sessizlik)
        import numpy as np
        
        # 1 saniye 16kHz PCM test verisi oluştur
        sample_rate = 16000
        duration = 1.0  # 1 saniye
        samples = int(sample_rate * duration)
        
        # Basit ton oluştur (440Hz A note)
        t = np.linspace(0, duration, samples, False)
        tone = np.sin(2 * np.pi * 440 * t) * 0.1  # Düşük volume
        
        # 16-bit PCM'e çevir
        pcm_data = (tone * 32767).astype(np.int16).tobytes()
        
        print(f"📊 Test ses verisi oluşturuldu: {len(pcm_data)} bytes PCM")
        
        # Ses verisini chunk'lara böl (160ms chunks)
        chunk_size = 2560  # 160ms at 16kHz 16-bit mono
        chunks = [pcm_data[i:i+chunk_size] for i in range(0, len(pcm_data), chunk_size)]
        
        print(f"📦 Ses verisi {len(chunks)} chunk'a bölündü")
        
        # Her chunk'ı işle
        for i, chunk in enumerate(chunks):
            if len(chunk) > 0:
                print(f"📤 Chunk {i+1}/{len(chunks)} işleniyor...")
                
                # run_stt metodunu kullan
                await stt_service.run_stt(chunk)
                
                await asyncio.sleep(0.1)
        
        print("🏁 Tüm chunk'lar işlendi")
        
        # Kısa bekleme
        await asyncio.sleep(1.0)
        
    except Exception as e:
        print(f"❌ Test hatası: {e}")
        logger.exception("Vosk service test failed")
        
    finally:
        try:
            await stt_service.stop()
            print("🔌 Vosk WebSocket bağlantısı kapatıldı")
        except:
            pass

async def test_vosk_with_real_audio():
    """Gerçek ses dosyası ile test"""
    
    print("🎵 Gerçek ses dosyası ile test...")
    
    test_audio_file = Path("test_audio/barge_in_test.raw")
    
    if not test_audio_file.exists():
        print(f"❌ Test ses dosyası bulunamadı: {test_audio_file}")
        return
    
    try:
        # Ses dosyasını oku ve dönüştür
        with open(test_audio_file, "rb") as f:
            pcmu_data = f.read()
        
        print(f"📁 PCMU dosyası okundu: {len(pcmu_data)} bytes")
        
        # PCMU'yu PCM16k'ya çevir
        pcm_data = pcmu_to_pcm16k(pcmu_data)
        print(f"🔄 PCM16k'ya çevrildi: {len(pcm_data)} bytes")
        
        # Vosk servisini başlat
        stt_service = VoskWebsocketSTTService()
        await stt_service.start()
        print("✅ Vosk servisi başlatıldı")
        
        # Chunk'lara böl ve işle
        chunk_size = 2560  # 160ms
        chunks = [pcm_data[i:i+chunk_size] for i in range(0, len(pcm_data), chunk_size)]
        
        print(f"📦 {len(chunks)} chunk işlenecek")
        
        for i, chunk in enumerate(chunks):
            if len(chunk) > 0:
                print(f"📤 Chunk {i+1}/{len(chunks)} işleniyor...")
                await stt_service.run_stt(chunk)
                await asyncio.sleep(0.05)  # Hızlı işleme
        
        print("🏁 Tüm chunk'lar işlendi")
        await asyncio.sleep(1.0)  # Final sonuçları bekle
        
    except Exception as e:
        print(f"❌ Gerçek ses testi hatası: {e}")
        logger.exception("Real audio test failed")
        
    finally:
        try:
            await stt_service.stop()
            print("🔌 Bağlantı kapatıldı")
        except:
            pass

if __name__ == "__main__":
    print("🚀 Tam Vosk WebSocket STT Service Test")
    print("=" * 50)
    
    print("\n1️⃣ Sentetik Ses Testi:")
    asyncio.run(test_vosk_service())
    
    print("\n" + "=" * 50)
    
    print("\n2️⃣ Gerçek Ses Dosyası Testi:")
    asyncio.run(test_vosk_with_real_audio())
    
    print("\n✨ Test tamamlandı!") 