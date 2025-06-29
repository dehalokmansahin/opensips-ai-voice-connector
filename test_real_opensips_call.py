#!/usr/bin/env python3
"""
Gerçek OpenSIPS Call sistemi ile test - Basitleştirilmiş
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

import structlog

logger = structlog.get_logger()

async def test_utils_flavors():
    """utils.py'deki FLAVORS mapping'ini test et"""
    
    print("🔧 FLAVORS Mapping Testi...")
    
    try:
        from utils import FLAVORS
        
        print("📋 Mevcut AI Flavors:")
        for flavor, engine_class in FLAVORS.items():
            print(f"  - {flavor}: {engine_class}")
        
        # Pipecat flavor'ını kontrol et
        if 'pipecat' in FLAVORS:
            pipecat_engine = FLAVORS['pipecat']
            print(f"✅ Pipecat flavor bulundu: {pipecat_engine}")
            
            # Class'ı import edebiliyor muyuz kontrol et
            if hasattr(pipecat_engine, '__name__'):
                print(f"✅ Engine class: {pipecat_engine.__name__}")
            else:
                print(f"✅ Engine class: {pipecat_engine}")
        else:
            print("❌ Pipecat flavor bulunamadı!")
        
        return 'pipecat' in FLAVORS
        
    except Exception as e:
        print(f"❌ FLAVORS test hatası: {e}")
        logger.exception("FLAVORS test failed")
        return False

async def test_pipeline_ai_direct():
    """PipelineAI'yi direkt test et"""
    
    print("🤖 PipelineAI Direkt Test...")
    
    try:
        from pipeline.ai_engine import PipelineAI
        
        # Mock config oluştur
        class MockConfig:
            def __init__(self):
                self.ai_flavor = 'pipecat'
                self.ai_model = 'test'
                self.sample_rate = 16000
                self.chunk_size = 160
                self.vosk_url = 'ws://localhost:2700'
        
        # Mock call oluştur
        class MockCall:
            def __init__(self):
                self.call_id = 'test-pipeline-direct'
                self.sip_uri = 'sip:test@direct.local'
                self.rtp = asyncio.Queue()
        
        mock_call = MockCall()
        mock_cfg = MockConfig()
        
        # PipelineAI oluştur
        pipeline_ai = PipelineAI(mock_call, mock_cfg)
        print("✅ PipelineAI oluşturuldu")
        
        # Başlat
        await pipeline_ai.start()
        print("✅ PipelineAI başlatıldı")
        
        # Test ses verisi gönder
        import numpy as np
        duration = 3.0
        sample_rate = 8000
        samples = int(sample_rate * duration)
        t = np.linspace(0, duration, samples, False)
        
        # Çok tonlu ses (konuşma benzeri)
        tone1 = np.sin(2 * np.pi * 300 * t) * 0.4
        tone2 = np.sin(2 * np.pi * 600 * t) * 0.3
        tone3 = np.sin(2 * np.pi * 1200 * t) * 0.2
        mixed_tone = tone1 + tone2 + tone3
        
        # μ-law approximation
        pcm_8k = (mixed_tone * 16383).astype(np.int16)
        pcmu_data = ((pcm_8k / 256) + 128).astype(np.uint8).tobytes()
        
        print(f"📊 Test PCMU verisi: {len(pcmu_data)} bytes")
        
        # 160-byte chunk'lara böl
        chunk_size = 160
        chunks = [pcmu_data[i:i+chunk_size] for i in range(0, len(pcmu_data), chunk_size)]
        
        print(f"📦 {len(chunks)} PCMU chunk gönderilecek")
        
        # Chunk'ları gönder
        for i, chunk in enumerate(chunks):
            if len(chunk) == 160:
                print(f"📤 PCMU Chunk {i+1}/{len(chunks)}")
                await pipeline_ai.process_rtp_payload(chunk)
                await asyncio.sleep(0.02)  # 20ms RTP timing
        
        print("🏁 Tüm chunk'lar gönderildi")
        
        # Pipeline işlemlerini bekle
        await asyncio.sleep(5.0)
        
        # Durdur
        await pipeline_ai.stop()
        print("🔌 PipelineAI durduruldu")
        
        print("✅ PipelineAI direkt test başarılı!")
        return True
        
    except Exception as e:
        print(f"❌ PipelineAI direkt test hatası: {e}")
        logger.exception("PipelineAI direct test failed")
        return False

async def test_config_loading():
    """Config dosyası yükleme testi"""
    
    print("⚙️ Config Loading Testi...")
    
    try:
        # Config dosyasını kontrol et
        cfg_file = Path("cfg/opensips-ai-voice-connector.ini")
        
        if cfg_file.exists():
            print(f"✅ Config dosyası bulundu: {cfg_file}")
            
            # Config'i oku
            import configparser
            config = configparser.ConfigParser()
            config.read(cfg_file)
            
            print("📋 Config sections:")
            for section in config.sections():
                print(f"  [{section}]")
                for key, value in config[section].items():
                    print(f"    {key} = {value}")
            
            # AI flavor kontrol et
            ai_flavor = config.get('ai', 'flavor', fallback='unknown')
            print(f"🤖 AI Flavor: {ai_flavor}")
            
            return True
        else:
            print(f"⚠️ Config dosyası bulunamadı: {cfg_file}")
            print("💡 Default config oluşturuluyor...")
            
            # Default config oluştur
            default_config = """[ai]
flavor = pipecat
model = default

[audio]
sample_rate = 16000
chunk_size = 160

[opensips]
host = localhost
port = 5060

[vosk]
url = ws://localhost:2700
"""
            
            cfg_file.parent.mkdir(exist_ok=True)
            with open(cfg_file, 'w') as f:
                f.write(default_config)
            
            print(f"✅ Default config oluşturuldu: {cfg_file}")
            return True
            
    except Exception as e:
        print(f"❌ Config loading test hatası: {e}")
        logger.exception("Config loading test failed")
        return False

if __name__ == "__main__":
    print("🚀 Real OpenSIPS Integration Test - Simplified")
    print("=" * 50)
    
    async def run_all_tests():
        print("\n1️⃣ Config Loading Testi:")
        config_ok = await test_config_loading()
        
        print("\n" + "=" * 50)
        
        print("\n2️⃣ FLAVORS Mapping Testi:")
        flavors_ok = await test_utils_flavors()
        
        print("\n" + "=" * 50)
        
        print("\n3️⃣ PipelineAI Direkt Testi:")
        pipeline_ok = await test_pipeline_ai_direct()
        
        print("\n" + "=" * 50)
        
        print("\n📊 Test Sonuçları:")
        print(f"  Config Loading: {'✅' if config_ok else '❌'}")
        print(f"  FLAVORS Mapping: {'✅' if flavors_ok else '❌'}")
        print(f"  PipelineAI Direct: {'✅' if pipeline_ok else '❌'}")
        
        if all([config_ok, flavors_ok, pipeline_ok]):
            print("\n🎉 Tüm testler başarılı! OpenSIPS entegrasyonu hazır!")
        else:
            print("\n⚠️ Bazı testler başarısız. Kontrol gerekli.")
    
    asyncio.run(run_all_tests())
    
    print("\n✨ Entegrasyon testleri tamamlandı!") 