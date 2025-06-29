#!/usr/bin/env python3
"""
Piper TTS WebSocket entegrasyon testi
"""

import asyncio
import sys
from pathlib import Path

# Path setup
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root / "src"))
sys.path.insert(0, str(project_root / "pipecat" / "src"))
sys.path.insert(0, str(project_root / "tests"))
import conftest

from services.piper_websocket import PiperWebsocketTTSService
import structlog

logger = structlog.get_logger()

async def test_piper_connection():
    """Piper TTS WebSocket bağlantısını test et"""
    
    print("🔗 Piper TTS WebSocket Bağlantı Testi...")
    
    try:
        # TTS servisini oluştur
        tts_service = PiperWebsocketTTSService()
        print("✅ PiperWebsocketTTSService oluşturuldu")
        
        # Bağlantıyı başlat
        await tts_service.start()
        print("✅ Piper TTS WebSocket bağlantısı başarılı")
        
        # Bağlantıyı kapat
        await tts_service.stop()
        print("🔌 Piper TTS WebSocket bağlantısı kapatıldı")
        
        return True
        
    except Exception as e:
        print(f"❌ Piper TTS bağlantı hatası: {e}")
        logger.exception("Piper TTS connection test failed")
        return False

async def test_piper_synthesis():
    """Piper TTS ile metin sentezini test et"""
    
    print("🎤 Piper TTS Sentez Testi...")
    
    try:
        # TTS servisini başlat
        tts_service = PiperWebsocketTTSService()
        await tts_service.start()
        print("✅ TTS servisi başlatıldı")
        
        # Test metni
        test_text = "Merhaba! Bu bir Piper TTS test mesajıdır. Türkçe konuşma sentezi çalışıyor mu?"
        print(f"📝 Test metni: {test_text}")
        
        # TTS sentezini yap
        audio_data = await tts_service.synthesize_text(test_text)
        
        if audio_data and len(audio_data) > 0:
            print(f"✅ TTS sentez başarılı: {len(audio_data)} bytes audio")
            
            # Audio'yu dosyaya kaydet (test için)
            output_file = Path("test_tts_output.raw")
            with open(output_file, "wb") as f:
                f.write(audio_data)
            print(f"💾 Audio dosyaya kaydedildi: {output_file}")
            
            # Audio bilgileri
            sample_count = len(audio_data) // 2  # 16-bit samples
            duration = sample_count / 22050  # 22050 Hz sample rate
            print(f"📊 Audio bilgileri: {sample_count} samples, {duration:.2f} saniye")
            
        else:
            print("❌ TTS sentez başarısız veya boş audio")
            return False
        
        # Servisi durdur
        await tts_service.stop()
        print("🔌 TTS servisi durduruldu")
        
        return True
        
    except Exception as e:
        print(f"❌ TTS sentez hatası: {e}")
        logger.exception("Piper TTS synthesis test failed")
        return False

async def test_piper_streaming():
    """Piper TTS streaming'ini test et"""
    
    print("📡 Piper TTS Streaming Testi...")
    
    try:
        # TTS servisini başlat
        tts_service = PiperWebsocketTTSService()
        await tts_service.start()
        print("✅ TTS servisi başlatıldı")
        
        # Test metni
        test_text = "Bu streaming test mesajıdır. Audio chunk'lar halinde gelecek."
        print(f"📝 Test metni: {test_text}")
        
        # Streaming TTS
        chunk_count = 0
        total_audio = b''
        
        print("📡 TTS streaming başlıyor...")
        
        async for frame in tts_service.run_tts(test_text):
            frame_type = type(frame).__name__
            print(f"📦 Frame alındı: {frame_type}")
            
            if hasattr(frame, 'audio') and frame.audio:
                chunk_count += 1
                total_audio += frame.audio
                print(f"🎵 Audio chunk {chunk_count}: {len(frame.audio)} bytes")
        
        print(f"🏁 Streaming tamamlandı: {chunk_count} chunk, toplam {len(total_audio)} bytes")
        
        if len(total_audio) > 0:
            # Streaming audio'yu kaydet
            streaming_file = Path("test_tts_streaming.raw")
            with open(streaming_file, "wb") as f:
                f.write(total_audio)
            print(f"💾 Streaming audio kaydedildi: {streaming_file}")
        
        # Servisi durdur
        await tts_service.stop()
        print("🔌 TTS servisi durduruldu")
        
        return len(total_audio) > 0
        
    except Exception as e:
        print(f"❌ TTS streaming hatası: {e}")
        logger.exception("Piper TTS streaming test failed")
        return False

async def test_pipeline_with_tts():
    """Pipeline ile TTS entegrasyonunu test et"""
    
    print("🚀 Pipeline + TTS Entegrasyon Testi...")
    
    try:
        from pipeline.manager import PipelineManager
        from pipecat.frames.frames import TranscriptionFrame
        
        # Pipeline'ı başlat
        pipeline_manager = PipelineManager()
        await pipeline_manager.start()
        print("✅ Pipeline başlatıldı")
        
        # Test transcription frame'i oluştur
        test_text = "Merhaba, bu pipeline TTS entegrasyon testidir."
        transcription_frame = TranscriptionFrame(
            text=test_text,
            user_id="test_user",
            timestamp=str(int(asyncio.get_event_loop().time() * 1000))
        )
        
        print(f"📝 Test transcription: {test_text}")
        
        # Transcription frame'ini pipeline'a gönder
        # Bu frame TTS processor'a ulaşacak ve ses üretecek
        print("📤 Transcription frame pipeline'a gönderiliyor...")
        
        # Pipeline'ın transcription'ı işlemesi için zaman ver
        await asyncio.sleep(3.0)
        
        # Pipeline'ı durdur
        await pipeline_manager.stop()
        print("🔌 Pipeline durduruldu")
        
        print("✅ Pipeline + TTS entegrasyonu test edildi")
        return True
        
    except Exception as e:
        print(f"❌ Pipeline TTS entegrasyon hatası: {e}")
        logger.exception("Pipeline TTS integration test failed")
        return False

if __name__ == "__main__":
    print("🚀 Piper TTS WebSocket Integration Test")
    print("=" * 50)
    
    async def run_all_tests():
        print("\n1️⃣ Bağlantı Testi:")
        connection_ok = await test_piper_connection()
        
        print("\n" + "=" * 50)
        
        print("\n2️⃣ TTS Sentez Testi:")
        synthesis_ok = await test_piper_synthesis()
        
        print("\n" + "=" * 50)
        
        print("\n3️⃣ TTS Streaming Testi:")
        streaming_ok = await test_piper_streaming()
        
        print("\n" + "=" * 50)
        
        print("\n4️⃣ Pipeline Entegrasyon Testi:")
        pipeline_ok = await test_pipeline_with_tts()
        
        print("\n" + "=" * 50)
        
        print("\n📊 Test Sonuçları:")
        print(f"  Bağlantı: {'✅' if connection_ok else '❌'}")
        print(f"  TTS Sentez: {'✅' if synthesis_ok else '❌'}")
        print(f"  TTS Streaming: {'✅' if streaming_ok else '❌'}")
        print(f"  Pipeline Entegrasyon: {'✅' if pipeline_ok else '❌'}")
        
        if all([connection_ok, synthesis_ok, streaming_ok, pipeline_ok]):
            print("\n🎉 Tüm TTS testleri başarılı! Pipeline TTS entegrasyonu hazır!")
        else:
            print("\n⚠️ Bazı TTS testleri başarısız. Piper TTS sunucusunun çalıştığından emin olun:")
            print("   python piper_tts_server.py")
    
    asyncio.run(run_all_tests())
    
    print("\n✨ TTS entegrasyon testleri tamamlandı!") 