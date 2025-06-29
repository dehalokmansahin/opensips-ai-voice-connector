#!/usr/bin/env python3
"""
Ollama LLM entegrasyon testi
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

from services.ollama_llm import OllamaLLMService
from pipecat.frames.frames import TranscriptionFrame
import structlog

logger = structlog.get_logger()

async def test_ollama_connection():
    """Ollama bağlantısını test et"""
    
    print("🔗 Ollama LLM Bağlantı Testi...")
    
    try:
        # LLM servisini oluştur
        llm_service = OllamaLLMService()
        print("✅ OllamaLLMService oluşturuldu")
        
        # Servisi başlat
        await llm_service.start()
        print("✅ Ollama LLM servisi başlatıldı")
        
        # Servisi durdur
        await llm_service.stop()
        print("🔌 Ollama LLM servisi durduruldu")
        
        return True
        
    except Exception as e:
        print(f"❌ Ollama bağlantı hatası: {e}")
        return False

async def test_llm_generation():
    """LLM yanıt üretimi testi"""
    
    print("🤖 Ollama LLM Yanıt Üretimi Testi...")
    
    try:
        llm_service = OllamaLLMService()
        await llm_service.start()
        print("✅ LLM servisi başlatıldı")
        
        # Test soruları
        test_prompts = [
            "Merhaba, nasılsın?",
            "Adın ne?",
            "Bana yardım edebilir misin?",
            "Bugün hava nasıl?",
            "Teşekkür ederim"
        ]
        
        for i, prompt in enumerate(test_prompts, 1):
            print(f"\\n📝 Test {i}: {prompt}")
            
            start_time = asyncio.get_event_loop().time()
            response = await llm_service.generate_response(prompt)
            latency_ms = (asyncio.get_event_loop().time() - start_time) * 1000
            
            print(f"🤖 Yanıt: {response}")
            print(f"⏱️ Latency: {latency_ms:.2f}ms")
            
            # Latency kontrolü (hedef: ≤400ms)
            if latency_ms <= 400:
                print("✅ Latency hedefi karşılandı")
            else:
                print(f"⚠️ Latency hedefi aşıldı (hedef: ≤400ms)")
        
        await llm_service.stop()
        print("🔌 LLM servisi durduruldu")
        
        return True
        
    except Exception as e:
        print(f"❌ LLM yanıt üretim hatası: {e}")
        return False

async def test_conversation_context():
    """Konuşma geçmişi testi"""
    
    print("💬 Konuşma Geçmişi Testi...")
    
    try:
        llm_service = OllamaLLMService()
        await llm_service.start()
        print("✅ LLM servisi başlatıldı")
        
        # Konuşma senaryosu
        conversation = [
            "Merhaba, adım Ali.",
            "Bugün nasıl hissediyorsun?",
            "Benim adımı hatırlıyor musun?",
            "Teşekkür ederim, güle güle!"
        ]
        
        for i, user_input in enumerate(conversation, 1):
            print(f"\\n👤 Kullanıcı {i}: {user_input}")
            
            response = await llm_service.generate_response(user_input)
            print(f"🤖 Asistan {i}: {response}")
        
        # Context'i temizle
        llm_service.clear_context()
        print("\\n🧹 Konuşma geçmişi temizlendi")
        
        await llm_service.stop()
        print("🔌 LLM servisi durduruldu")
        
        return True
        
    except Exception as e:
        print(f"❌ Konuşma geçmişi test hatası: {e}")
        return False

async def test_llm_frames():
    """LLM frame üretimi testi"""
    
    print("📦 LLM Frame Üretimi Testi...")
    
    try:
        llm_service = OllamaLLMService()
        await llm_service.start()
        print("✅ LLM servisi başlatıldı")
        
        # Test metni
        test_text = "Merhaba, size nasıl yardımcı olabilirim?"
        print(f"📝 Test metni: {test_text}")
        
        # Frame'leri üret
        frames = await llm_service.run_llm(test_text)
        print(f"📦 Üretilen frame sayısı: {len(frames)}")
        
        for i, frame in enumerate(frames):
            print(f"Frame {i+1}: {type(frame).__name__}")
            if hasattr(frame, 'text'):
                print(f"  Metin: {frame.text[:100]}...")
        
        await llm_service.stop()
        print("🔌 LLM servisi durduruldu")
        
        return True
        
    except Exception as e:
        print(f"❌ LLM frame test hatası: {e}")
        return False

async def test_error_handling():
    """Hata yönetimi testi"""
    
    print("🚨 Hata Yönetimi Testi...")
    
    try:
        # Yanlış URL ile servis oluştur
        llm_service = OllamaLLMService(url="http://localhost:99999/api/generate")
        
        try:
            await llm_service.start()
            print("❌ Hatalı URL ile bağlantı başarılı olmamalıydı")
            return False
        except Exception as e:
            print(f"✅ Beklenen hata yakalandı: {e}")
        
        # Doğru servis ile timeout testi
        llm_service = OllamaLLMService(timeout=0.001)  # Çok kısa timeout
        await llm_service.start()
        
        response = await llm_service.generate_response("Test")
        print(f"🤖 Timeout yanıtı: {response}")
        
        await llm_service.stop()
        
        return True
        
    except Exception as e:
        print(f"❌ Hata yönetimi test hatası: {e}")
        return False

async def main():
    """Ana test fonksiyonu"""
    
    print("🚀 Ollama LLM Integration Test Suite")
    print("=" * 60)
    
    tests = [
        ("Bağlantı Testi", test_ollama_connection),
        ("Yanıt Üretimi", test_llm_generation),
        ("Konuşma Geçmişi", test_conversation_context),
        ("Frame Üretimi", test_llm_frames),
        ("Hata Yönetimi", test_error_handling),
    ]
    
    results = []
    
    for test_name, test_func in tests:
        print(f"\\n{len(results)+1}️⃣ {test_name}:")
        print("-" * 50)
        
        try:
            result = await test_func()
            results.append((test_name, result))
            
        except Exception as e:
            print(f"❌ Test hatası: {e}")
            results.append((test_name, False))
    
    # Sonuçları özetle
    print("\\n" + "=" * 60)
    print("📊 Test Sonuçları:")
    
    passed = 0
    for test_name, result in results:
        status = "✅" if result else "❌"
        print(f"  {status} {test_name}")
        if result:
            passed += 1
    
    print(f"\\n🎯 Başarı Oranı: {passed}/{len(results)} ({passed/len(results)*100:.1f}%)")
    
    if passed == len(results):
        print("🎉 Tüm LLM testleri başarılı! Ollama entegrasyonu hazır!")
    else:
        print("⚠️ Bazı testler başarısız. Ollama server'ın çalıştığından emin olun.")
    
    print("\\n✨ Ollama LLM test suite tamamlandı!")

if __name__ == "__main__":
    asyncio.run(main()) 