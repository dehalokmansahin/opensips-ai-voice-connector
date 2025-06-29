#!/usr/bin/env python3
"""
Vosk STT entegreli pipeline testi
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
import structlog

logger = structlog.get_logger()

async def test_pipeline_with_vosk():
    """Vosk STT ile tam pipeline testi"""
    
    print("🚀 Pipeline + Vosk STT Test Başlıyor...")
    
    try:
        # Pipeline manager'ı başlat
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
            # Sentetik veri
            import numpy as np
            duration = 3.0
            sample_rate = 16000
            samples = int(sample_rate * duration)
            t = np.linspace(0, duration, samples, False)
            tone = np.sin(2 * np.pi * 300 * t) * 0.2  # 300Hz ton
            pcm_data = (tone * 32767).astype(np.int16).tobytes()
            print(f"📊 Sentetik ses verisi: {len(pcm_data)} bytes PCM")
        
        # Ses verisini pipeline'a gönder
        chunk_size = 3200  # 100ms chunks
        chunks = [pcm_data[i:i+chunk_size] for i in range(0, len(pcm_data), chunk_size)]
        
        print(f"📦 {len(chunks)} chunk pipeline'a gönderilecek")
        
        for i, chunk in enumerate(chunks):
            if len(chunk) > 0:
                print(f"📤 Pipeline chunk {i+1}/{len(chunks)}")
                await pipeline_manager.push_audio(chunk)
                await asyncio.sleep(0.1)
        
        print("🏁 Tüm chunk'lar gönderildi")
        await asyncio.sleep(3.0)  # Pipeline işlemlerini bekle
        
    except Exception as e:
        print(f"❌ Pipeline test hatası: {e}")
        logger.exception("Pipeline test failed")
        
    finally:
        try:
            await pipeline_manager.stop()
            print("🔌 Pipeline durduruldu")
        except:
            pass

if __name__ == "__main__":
    print("🚀 Pipeline + Vosk STT Integration Test")
    print("=" * 50)
    
    asyncio.run(test_pipeline_with_vosk())
    
    print("\n✨ Test tamamlandı!") 