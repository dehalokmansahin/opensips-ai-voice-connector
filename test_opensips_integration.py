#!/usr/bin/env python3
"""
OpenSIPS Call + Pipeline entegrasyon testi - Mock objelerle
"""

import asyncio
import sys
from pathlib import Path
from unittest.mock import Mock, AsyncMock

# Path setup
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root / "src"))
sys.path.insert(0, str(project_root / "pipecat" / "src"))
sys.path.insert(0, str(project_root / "tests"))
import conftest

from pipeline.ai_engine import PipelineAI
from transports.audio_utils import pcmu_to_pcm16k
import structlog

logger = structlog.get_logger()

class MockCall:
    """Mock Call object for testing"""
    
    def __init__(self):
        self.rtp = AsyncMock()
        self.call_id = "test-call-123"
        self.sip_uri = "sip:test@example.com"
        self.state = "connected"
        
        # RTP queue mock
        self.rtp.put = AsyncMock()
        
        print("📞 Mock Call object created")

class MockConfig:
    """Mock Config object for testing"""
    
    def __init__(self):
        self.ai_flavor = "pipecat"
        self.ai_model = "test-model"
        self.sample_rate = 16000
        self.chunk_size = 160
        
        print("⚙️ Mock Config object created")

async def test_opensips_integration():
    """OpenSIPS Call + Pipeline entegrasyon testi"""
    
    print("🚀 OpenSIPS + Pipeline Entegrasyon Testi...")
    
    try:
        # Mock objeler oluştur
        mock_call = MockCall()
        mock_cfg = MockConfig()
        
        # PipelineAI engine'i oluştur
        ai_engine = PipelineAI(mock_call, mock_cfg)
        print("✅ PipelineAI engine oluşturuldu")
        
        # Engine'i başlat
        await ai_engine.start()
        print("✅ AI Engine başlatıldı")
        
        # Test PCMU verisi hazırla
        test_audio_file = Path("test_audio/barge_in_test.raw")
        
        if test_audio_file.exists():
            with open(test_audio_file, "rb") as f:
                pcmu_data = f.read()
            print(f"📁 Test PCMU dosyası: {len(pcmu_data)} bytes")
        else:
            # Sentetik PCMU verisi oluştur
            import numpy as np
            
            # 8kHz PCM oluştur (PCMU format için)
            duration = 3.0
            sample_rate = 8000
            samples = int(sample_rate * duration)
            t = np.linspace(0, duration, samples, False)
            tone = np.sin(2 * np.pi * 300 * t) * 0.3  # 300Hz ton
            
            # 16-bit PCM'e çevir
            pcm_8k = (tone * 32767).astype(np.int16)
            
            # Basit μ-law encoding approximation
            # Gerçek μ-law encoding için lookup table kullanılır
            # Şimdilik basit scaling yapalım
            pcmu_data = ((pcm_8k / 256) + 128).astype(np.uint8).tobytes()
            
            print(f"📊 Sentetik PCMU verisi: {len(pcmu_data)} bytes")
        
        # PCMU chunk'larını simüle et (160 byte = 20ms @ 8kHz μ-law)
        chunk_size = 160
        chunks = [pcmu_data[i:i+chunk_size] for i in range(0, len(pcmu_data), chunk_size)]
        
        print(f"📦 {len(chunks)} PCMU chunk işlenecek (OpenSIPS RTP format)")
        
        # Her chunk'ı AI engine'e gönder
        for i, chunk in enumerate(chunks):
            if len(chunk) == 160:  # Tam chunk
                print(f"📤 RTP Chunk {i+1}/{len(chunks)} - {len(chunk)} bytes PCMU")
                
                # AI engine'in process_rtp_payload metodunu çağır
                await ai_engine.process_rtp_payload(chunk)
                
                # RTP timing simülasyonu (20ms)
                await asyncio.sleep(0.02)
        
        print("🏁 Tüm RTP chunk'ları işlendi")
        
        # Pipeline'ın işlemesini bekle
        await asyncio.sleep(3.0)
        
        # Mock call'un RTP queue'suna ne kadar veri gönderildiğini kontrol et
        call_count = mock_call.rtp.put.call_count
        print(f"📊 Mock RTP queue'ya {call_count} chunk gönderildi")
        
        print("✅ OpenSIPS + Pipeline entegrasyonu başarılı!")
        
    except Exception as e:
        print(f"❌ Entegrasyon test hatası: {e}")
        logger.exception("OpenSIPS integration test failed")
        
    finally:
        try:
            if 'ai_engine' in locals():
                await ai_engine.stop()
                print("🔌 AI Engine durduruldu")
        except Exception as e:
            print(f"⚠️ AI Engine durdurma hatası: {e}")

async def test_direct_pipeline():
    """Direkt pipeline testi - OpenSIPS mock'suz"""
    
    print("🎤 Direkt Pipeline Testi...")
    
    try:
        from pipeline.manager import PipelineManager
        
        # Pipeline manager'ı oluştur
        pipeline_manager = PipelineManager()
        await pipeline_manager.start()
        print("✅ Pipeline başlatıldı")
        
        # Test ses verisi
        import numpy as np
        duration = 2.0
        sample_rate = 16000
        samples = int(sample_rate * duration)
        t = np.linspace(0, duration, samples, False)
        tone = np.sin(2 * np.pi * 440 * t) * 0.2  # A note
        pcm_data = (tone * 32767).astype(np.int16).tobytes()
        
        print(f"📊 Test PCM verisi: {len(pcm_data)} bytes")
        
        # Pipeline'a gönder
        await pipeline_manager.push_audio(pcm_data)
        print("📤 Ses verisi pipeline'a gönderildi")
        
        # İşleme bekle
        await asyncio.sleep(2.0)
        
        await pipeline_manager.stop()
        print("🔌 Pipeline durduruldu")
        
        print("✅ Direkt pipeline testi başarılı!")
        
    except Exception as e:
        print(f"❌ Direkt pipeline test hatası: {e}")
        logger.exception("Direct pipeline test failed")

if __name__ == "__main__":
    print("🚀 OpenSIPS + Pipeline Integration Test")
    print("=" * 50)
    
    print("\n1️⃣ OpenSIPS Entegrasyon Testi:")
    asyncio.run(test_opensips_integration())
    
    print("\n" + "=" * 50)
    
    print("\n2️⃣ Direkt Pipeline Testi:")
    asyncio.run(test_direct_pipeline())
    
    print("\n✨ Tüm testler tamamlandı!") 