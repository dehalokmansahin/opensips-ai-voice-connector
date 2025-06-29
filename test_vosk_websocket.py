#!/usr/bin/env python3
"""
Vosk WebSocket STT servisini test etmek için güncellenmiş test scripti
"""

import asyncio
import logging
import sys
from pathlib import Path

# Path setup
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root / "src"))
sys.path.insert(0, str(project_root / "pipecat" / "src"))

try:
    from pipecat.frames.frames import Frame
    print("✅ Pipecat modülü başarıyla import edildi")
except ImportError as e:
    print(f"❌ Pipecat import hatası: {e}")
    sys.exit(1)

from services.vosk_websocket import VoskWebsocketSTTService
from transports.audio_utils import pcmu_to_pcm16k
import structlog

logging.basicConfig(level=logging.INFO)
logger = structlog.get_logger()

async def test_vosk_websocket():
    """Vosk WebSocket servisini test et"""
    
    print("🎤 Vosk WebSocket STT Test Başlıyor...")
    
    # Test için ses dosyası yükle
    test_audio_file = Path("test_audio/barge_in_test.raw")
    
    if not test_audio_file.exists():
        print(f"❌ Test ses dosyası bulunamadı: {test_audio_file}")
        print("💡 Basit ses verisi ile test yapılacak")
        # Basit test verisi oluştur (sessizlik)
        test_audio_data = b'\x00' * 3200  # 200ms sessizlik
    else:
        with open(test_audio_file, "rb") as f:
            pcmu_data = f.read()
        test_audio_data = pcmu_to_pcm16k(pcmu_data)
        print(f"📁 Test dosyası okundu: {len(test_audio_data)} bytes PCM data")
    
    try:
        # Vosk servisini başlat
        stt_service = VoskWebsocketSTTService()
        
        print("🔗 Vosk WebSocket'e bağlanıyor...")
        await stt_service.start()
        print("✅ Vosk WebSocket bağlantısı başarılı")
        
        # Ses verisini chunk'lara böl (160ms chunks = 2560 bytes at 16kHz)
        chunk_size = 2560  # 160ms at 16kHz 16-bit mono
        chunks = [test_audio_data[i:i+chunk_size] for i in range(0, len(test_audio_data), chunk_size)]
        
        print(f"📦 Ses verisi {len(chunks)} chunk'a bölündü")
        
        # Her chunk'ı Vosk'a gönder
        for i, chunk in enumerate(chunks):
            if len(chunk) > 0:
                print(f"📤 Chunk {i+1}/{len(chunks)} gönderiliyor... ({len(chunk)} bytes)")
                
                result = await stt_service.process_audio_chunk(chunk)
                
                if result:
                    print(f"🎯 STT Sonuç: {result}")
                else:
                    print("⏳ Ara sonuç (henüz metin yok)")
                
                await asyncio.sleep(0.1)
        
        # Final sonucu al
        print("🏁 Final sonuç bekleniyor...")
        final_result = await stt_service.finalize()
        if final_result:
            print(f"✅ Final STT Sonuç: {final_result}")
        else:
            print("ℹ️ Final sonuç boş (test verisi sessizlik olabilir)")
        
    except Exception as e:
        print(f"❌ Test hatası: {e}")
        logger.exception("Vosk test failed")
        
    finally:
        try:
            await stt_service.stop()
            print("🔌 Vosk WebSocket bağlantısı kapatıldı")
        except:
            pass

if __name__ == "__main__":
    print("🚀 Vosk WebSocket Test Scripti - Güncellenmiş")
    print("=" * 50)
    
    asyncio.run(test_vosk_websocket())
    
    print("\n✨ Test tamamlandı!") 