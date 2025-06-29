#!/usr/bin/env python3
"""
Basit pipeline testi - import sorunları çözülmüş
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

# Direct imports
from pipeline.manager import PipelineManager
import structlog

logger = structlog.get_logger()

async def test_simple_pipeline():
    """Basit pipeline testi"""
    
    print("🚀 Basit Pipeline Testi...")
    
    try:
        # Pipeline manager'ı oluştur
        pipeline_manager = PipelineManager()
        print("✅ PipelineManager oluşturuldu")
        
        # Pipeline'ı başlat
        await pipeline_manager.start()
        print("✅ Pipeline başlatıldı")
        
        # Basit test verisi
        import numpy as np
        duration = 1.0
        sample_rate = 16000
        samples = int(sample_rate * duration)
        
        # 500Hz ton oluştur
        t = np.linspace(0, duration, samples, False)
        tone = np.sin(2 * np.pi * 500 * t) * 0.1
        pcm_data = (tone * 32767).astype(np.int16).tobytes()
        
        print(f"📊 Test ses verisi: {len(pcm_data)} bytes")
        
        # Pipeline'a gönder
        await pipeline_manager.push_audio(pcm_data)
        print("📤 Ses verisi pipeline'a gönderildi")
        
        # İşleme zamanı ver
        await asyncio.sleep(2.0)
        print("⏳ Pipeline işleme tamamlandı")
        
    except Exception as e:
        print(f"❌ Pipeline test hatası: {e}")
        logger.exception("Pipeline test failed")
        
    finally:
        try:
            await pipeline_manager.stop()
            print("🔌 Pipeline durduruldu")
        except Exception as e:
            print(f"⚠️ Pipeline durdurma hatası: {e}")

if __name__ == "__main__":
    print("🚀 Basit Pipeline Test")
    print("=" * 40)
    
    asyncio.run(test_simple_pipeline())
    
    print("\n✨ Test tamamlandı!") 