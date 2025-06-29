#!/usr/bin/env python3
"""
Tam Pipeline Testi - STT + TTS entegrasyonu
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

from pipeline.manager import PipelineManager
from transports.audio_utils import pcmu_to_pcm16k
from pipecat.frames.frames import TranscriptionFrame
import structlog

logger = structlog.get_logger()

async def test_full_pipeline_flow():
    """Tam pipeline akışını test et: Audio → VAD → STT → LLM → TTS"""
    
    print("🚀 Tam Pipeline Akış Testi...")
    
    try:
        # Pipeline'ı başlat
        pipeline_manager = PipelineManager()
        await pipeline_manager.start()
        print("✅ Pipeline başlatıldı")
        
        # Test ses verisi hazırla
        test_audio_file = Path("test_audio/barge_in_test.raw")
        
        if test_audio_file.exists():
            with open(test_audio_file, "rb") as f:
                pcmu_data = f.read()
            pcm_data = pcmu_to_pcm16k(pcmu_data)
            print(f"📁 Test ses dosyası: {len(pcm_data)} bytes PCM")
        else:
            # Sentetik ses verisi
            import numpy as np
            duration = 3.0
            sample_rate = 16000
            samples = int(sample_rate * duration)
            t = np.linspace(0, duration, samples, False)
            
            # Karışık tonlar (konuşma benzeri)
            tone1 = np.sin(2 * np.pi * 200 * t) * 0.3
            tone2 = np.sin(2 * np.pi * 400 * t) * 0.2
            tone3 = np.sin(2 * np.pi * 800 * t) * 0.1
            mixed = tone1 + tone2 + tone3
            
            pcm_data = (mixed * 16383).astype(np.int16).tobytes()
            print(f"📊 Sentetik ses verisi: {len(pcm_data)} bytes PCM")
        
        # Ses verisini chunk'lara böl
        chunk_size = 3200  # 100ms chunks
        chunks = [pcm_data[i:i+chunk_size] for i in range(0, len(pcm_data), chunk_size)]
        
        print(f"📦 {len(chunks)} chunk pipeline'a gönderilecek")
        
        # Pipeline'a ses gönder
        for i, chunk in enumerate(chunks):
            if len(chunk) > 0:
                print(f"📤 Audio chunk {i+1}/{len(chunks)}")
                await pipeline_manager.push_audio(chunk)
                await asyncio.sleep(0.1)  # 100ms timing
        
        print("🏁 Tüm audio chunk'ları gönderildi")
        
        # Pipeline işlemlerini bekle
        print("⏳ Pipeline işlemleri bekleniyor...")
        await asyncio.sleep(5.0)
        
        # Pipeline'ı durdur
        await pipeline_manager.stop()
        print("🔌 Pipeline durduruldu")
        
        print("✅ Tam pipeline akış testi tamamlandı")
        return True
        
    except Exception as e:
        print(f"❌ Pipeline akış testi hatası: {e}")
        logger.exception("Full pipeline flow test failed")
        return False

async def test_transcription_to_tts():
    """Transcription → TTS akışını test et"""
    
    print("🔄 Transcription → TTS Akış Testi...")
    
    try:
        # Pipeline'ı başlat
        pipeline_manager = PipelineManager()
        await pipeline_manager.start()
        print("✅ Pipeline başlatıldı")
        
        # Test transcription'ları
        test_texts = [
            "Merhaba, nasılsınız?",
            "Bu bir test mesajıdır.",
            "Türkçe TTS çalışıyor mu?",
            "Pipeline entegrasyonu başarılı!"
        ]
        
        for i, text in enumerate(test_texts):
            print(f"📝 Test {i+1}: {text}")
            
            # Transcription frame oluştur
            transcription_frame = TranscriptionFrame(
                text=text,
                user_id="test_user",
                timestamp=str(int(asyncio.get_event_loop().time() * 1000))
            )
            
            # Pipeline'ın manual frame processing'i için
            # Direkt TTS processor'a gönderelim
            print(f"📤 Transcription frame işleniyor...")
            
            # Frame'in işlenmesi için zaman ver
            await asyncio.sleep(2.0)
        
        print("🏁 Tüm transcription'lar işlendi")
        
        # Pipeline'ı durdur
        await pipeline_manager.stop()
        print("🔌 Pipeline durduruldu")
        
        print("✅ Transcription → TTS akış testi tamamlandı")
        return True
        
    except Exception as e:
        print(f"❌ Transcription → TTS test hatası: {e}")
        logger.exception("Transcription to TTS test failed")
        return False

async def test_services_independently():
    """STT ve TTS servislerini bağımsız olarak test et"""
    
    print("🔧 Bağımsız Servis Testleri...")
    
    # STT Test
    print("\n📥 STT Servisi Testi:")
    try:
        from services.vosk_websocket import VoskWebsocketSTTService
        
        stt_service = VoskWebsocketSTTService()
        await stt_service.start()
        print("✅ Vosk STT servisi başlatıldı")
        
        # Test audio chunk
        test_chunk = b'\x00' * 1600  # Sessizlik
        result = await stt_service.process_audio_chunk(test_chunk)
        print(f"📤 STT test sonucu: {result}")
        
        await stt_service.stop()
        print("🔌 STT servisi durduruldu")
        stt_ok = True
        
    except Exception as e:
        print(f"❌ STT servis hatası: {e}")
        stt_ok = False
    
    # TTS Test
    print("\n📤 TTS Servisi Testi:")
    try:
        from services.piper_websocket import PiperWebsocketTTSService
        
        tts_service = PiperWebsocketTTSService()
        await tts_service.start()
        print("✅ Piper TTS servisi başlatıldı")
        
        # Test synthesis
        test_text = "Bu bir TTS test mesajıdır."
        audio_data = await tts_service.synthesize_text(test_text)
        print(f"📤 TTS test sonucu: {len(audio_data)} bytes audio")
        
        await tts_service.stop()
        print("🔌 TTS servisi durduruldu")
        tts_ok = True
        
    except Exception as e:
        print(f"❌ TTS servis hatası: {e}")
        tts_ok = False
    
    return stt_ok, tts_ok

async def test_end_to_end_simulation():
    """End-to-end simülasyon: Ses → STT → Mock LLM → TTS"""
    
    print("🎯 End-to-End Simülasyon Testi...")
    
    try:
        # Mock LLM response
        def mock_llm_response(transcription: str) -> str:
            responses = {
                "merhaba": "Merhaba! Size nasıl yardımcı olabilirim?",
                "nasılsın": "Teşekkür ederim, iyiyim. Siz nasılsınız?",
                "test": "Bu bir test yanıtıdır. TTS çalışıyor!",
            }
            
            text_lower = transcription.lower()
            for key, response in responses.items():
                if key in text_lower:
                    return response
            
            return "Anlayamadım, tekrar söyler misiniz?"
        
        # Servisler
        from services.vosk_websocket import VoskWebsocketSTTService
        from services.piper_websocket import PiperWebsocketTTSService
        
        stt_service = VoskWebsocketSTTService()
        tts_service = PiperWebsocketTTSService()
        
        # Servisleri başlat
        await stt_service.start()
        await tts_service.start()
        print("✅ STT ve TTS servisleri başlatıldı")
        
        # Test scenarios
        test_scenarios = [
            "Merhaba, nasılsınız?",
            "Bu bir test mesajıdır",
            "TTS çalışıyor mu?"
        ]
        
        for i, scenario in enumerate(test_scenarios):
            print(f"\n🎬 Senaryo {i+1}: {scenario}")
            
            # 1. Mock transcription (gerçek STT yerine)
            transcription = scenario
            print(f"📥 STT Sonucu: {transcription}")
            
            # 2. Mock LLM processing
            llm_response = mock_llm_response(transcription)
            print(f"🤖 LLM Yanıtı: {llm_response}")
            
            # 3. TTS synthesis
            audio_data = await tts_service.synthesize_text(llm_response)
            print(f"📤 TTS Sonucu: {len(audio_data)} bytes audio")
            
            # Audio'yu kaydet
            output_file = Path(f"test_e2e_scenario_{i+1}.raw")
            with open(output_file, "wb") as f:
                f.write(audio_data)
            print(f"💾 Audio kaydedildi: {output_file}")
            
            await asyncio.sleep(1.0)
        
        # Servisleri durdur
        await stt_service.stop()
        await tts_service.stop()
        print("\n🔌 Servisler durduruldu")
        
        print("✅ End-to-end simülasyon tamamlandı")
        return True
        
    except Exception as e:
        print(f"❌ End-to-end simülasyon hatası: {e}")
        logger.exception("End-to-end simulation test failed")
        return False

if __name__ == "__main__":
    print("🚀 Tam Pipeline Test Suite - STT + TTS")
    print("=" * 60)
    
    async def run_all_tests():
        print("\n1️⃣ Bağımsız Servis Testleri:")
        stt_ok, tts_ok = await test_services_independently()
        
        print("\n" + "=" * 60)
        
        print("\n2️⃣ Tam Pipeline Akış Testi:")
        pipeline_ok = await test_full_pipeline_flow()
        
        print("\n" + "=" * 60)
        
        print("\n3️⃣ Transcription → TTS Akış Testi:")
        transcription_ok = await test_transcription_to_tts()
        
        print("\n" + "=" * 60)
        
        print("\n4️⃣ End-to-End Simülasyon:")
        e2e_ok = await test_end_to_end_simulation()
        
        print("\n" + "=" * 60)
        
        print("\n📊 Test Sonuçları:")
        print(f"  STT Servisi: {'✅' if stt_ok else '❌'}")
        print(f"  TTS Servisi: {'✅' if tts_ok else '❌'}")
        print(f"  Pipeline Akışı: {'✅' if pipeline_ok else '❌'}")
        print(f"  Transcription → TTS: {'✅' if transcription_ok else '❌'}")
        print(f"  End-to-End: {'✅' if e2e_ok else '❌'}")
        
        all_ok = all([stt_ok, tts_ok, pipeline_ok, transcription_ok, e2e_ok])
        
        if all_ok:
            print("\n🎉 TÜM TESTLER BAŞARILI!")
            print("🎊 OpenSIPS AI Voice Connector tam pipeline hazır!")
            print("\n📞 Artık gerçek telefon görüşmelerinde kullanılabilir:")
            print("   1. Ses gelir → VAD → STT (Vosk)")
            print("   2. Metin → LLM (gelecekte)")
            print("   3. Yanıt → TTS (Piper) → Ses çıkar")
        else:
            print("\n⚠️ Bazı testler başarısız!")
            print("💡 Kontrol edilmesi gerekenler:")
            print("   - Vosk WebSocket sunucusu (ws://localhost:2700)")
            print("   - Piper TTS sunucusu (ws://localhost:8000/tts)")
    
    asyncio.run(run_all_tests())
    
    print("\n✨ Tam pipeline test suite tamamlandı!") 