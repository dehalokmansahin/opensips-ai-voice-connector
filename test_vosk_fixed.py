#!/usr/bin/env python3
"""
Düzeltilmiş Vosk WebSocket test scripti
"""

import asyncio
import logging
import sys
from pathlib import Path

# Path setup
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root / "src"))
sys.path.insert(0, str(project_root / "pipecat" / "src"))
sys.path.insert(0, str(project_root / "tests"))
import conftest

from services.vosk_websocket import VoskWebsocketSTTService
from transports.audio_utils import pcmu_to_pcm16k, validate_pcm_format
import structlog

logging.basicConfig(level=logging.DEBUG)
logger = structlog.get_logger()

async def test_audio_conversion():
    """Ses dönüşümünü test et"""
    
    print("🔄 Ses dönüşüm testi...")
    
    test_audio_file = Path("test_audio/barge_in_test.raw")
    
    if not test_audio_file.exists():
        print(f"❌ Test ses dosyası bulunamadı: {test_audio_file}")
        return None
    
    # Ses dosyasını oku
    with open(test_audio_file, "rb") as f:
        pcmu_data = f.read()
    
    print(f"📁 PCMU dosyası: {len(pcmu_data)} bytes")
    
    # PCMU → PCM16k dönüşüm
    pcm_data = pcmu_to_pcm16k(pcmu_data)
    print(f"🔄 PCM16k dönüşüm: {len(pcm_data)} bytes")
    
    # Format validation
    is_valid = validate_pcm_format(pcm_data)
    print(f"✅ PCM format geçerli: {is_valid}")
    
    if len(pcm_data) > 0:
        # İlk birkaç sample'ı göster
        import struct
        samples = struct.unpack('<10h', pcm_data[:20])  # İlk 10 sample
        print(f"📊 İlk 10 sample: {samples}")
    
    return pcm_data

async def test_vosk_with_fixed_audio():
    """Düzeltilmiş ses verisi ile Vosk testi"""
    
    print("🎤 Düzeltilmiş Vosk testi...")
    
    # Ses dönüşümünü test et
    pcm_data = await test_audio_conversion()
    
    if not pcm_data or len(pcm_data) < 100:
        print("❌ Geçerli ses verisi yok, sentetik veri kullanılacak")
        
        # Basit sentetik veri oluştur
        import numpy as np
        duration = 2.0  # 2 saniye
        sample_rate = 16000
        samples = int(sample_rate * duration)
        
        # Düşük frekanslı ton (200Hz)
        t = np.linspace(0, duration, samples, False)
        tone = np.sin(2 * np.pi * 200 * t) * 0.3
        
        pcm_data = (tone * 32767).astype(np.int16).tobytes()
        print(f"📊 Sentetik PCM verisi oluşturuldu: {len(pcm_data)} bytes")
    
    try:
        # Vosk servisini başlat
        stt_service = VoskWebsocketSTTService()
        await stt_service.start()
        print("✅ Vosk servisi başlatıldı")
        
        # Chunk'lara böl (100ms chunks)
        chunk_size = 3200  # 100ms at 16kHz 16-bit
        chunks = [pcm_data[i:i+chunk_size] for i in range(0, len(pcm_data), chunk_size)]
        
        print(f"📦 {len(chunks)} chunk işlenecek")
        
        for i, chunk in enumerate(chunks):
            if len(chunk) > 0:
                print(f"📤 Chunk {i+1}/{len(chunks)} - {len(chunk)} bytes")
                await stt_service.run_stt(chunk)
                await asyncio.sleep(0.1)
        
        print("🏁 Tüm chunk'lar gönderildi")
        await asyncio.sleep(2.0)  # Sonuçları bekle
        
    except Exception as e:
        print(f"❌ Test hatası: {e}")
        logger.exception("Vosk test failed")
        
    finally:
        try:
            await stt_service.stop()
            print("🔌 Bağlantı kapatıldı")
        except:
            pass

if __name__ == "__main__":
    print("🚀 Düzeltilmiş Vosk WebSocket Test")
    print("=" * 50)
    
    asyncio.run(test_vosk_with_fixed_audio())
    
    print("\n✨ Test tamamlandı!") 