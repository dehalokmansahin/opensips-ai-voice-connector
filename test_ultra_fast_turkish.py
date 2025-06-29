#!/usr/bin/env python3
"""
Ultra-Fast Türkçe LLM Test
"""

import sys
import os
import time
import asyncio

# Python path ekle
current_dir = os.path.dirname(os.path.abspath(__file__))
src_path = os.path.join(current_dir, "src")
pipecat_src_path = os.path.join(current_dir, "pipecat", "src")

if src_path not in sys.path:
    sys.path.insert(0, src_path)
if pipecat_src_path not in sys.path:
    sys.path.insert(0, pipecat_src_path)

# soxr stub
import numpy as np
if not hasattr(sys.modules, 'soxr'):
    class SoxrStub:
        def resample(self, *args, **kwargs):
            return np.array([])
    sys.modules['soxr'] = SoxrStub()

from services.ollama_llm import OllamaLLMService

async def test_ultra_fast_turkish():
    """Ultra-fast Türkçe optimizasyonları test et"""
    
    print("🚀 Ultra-Fast Türkçe LLM Test")
    print("=" * 40)
    print("🎯 Hedef: ≤400ms first token")
    print("🔧 Optimizasyonlar:")
    print("   • Temperature: 0.2 (ultra tutarlı)")
    print("   • Top_p: 0.7 (hızlı karar)")
    print("   • Max tokens: 50 (ultra kısa)")
    print("   • Context: 1024 (küçük)")
    print("   • Timeout: 2s (agresif)")
    print()
    
    service = OllamaLLMService()
    await service.start()
    
    # Hızlı test senaryoları
    fast_test_cases = [
        "Merhaba",
        "Kredi kartı",
        "Hesap bakiye",
        "Teşekkürler",
        "Yardım",
    ]
    
    under_400ms_count = 0
    total_tests = len(fast_test_cases)
    
    for i, test_input in enumerate(fast_test_cases, 1):
        print(f"⚡ Test {i}: {test_input}")
        
        start_time = time.time()
        first_token_time = None
        response_text = ""
        
        print("🤖 ", end="", flush=True)
        
        try:
            async for token in service.generate_response_streaming(test_input):
                if first_token_time is None:
                    first_token_time = time.time()
                    first_token_latency = (first_token_time - start_time) * 1000
                    
                    # Renk kodlaması
                    if first_token_latency <= 400:
                        color = "🟢"  # Yeşil - başarılı
                        under_400ms_count += 1
                    elif first_token_latency <= 600:
                        color = "🟡"  # Sarı - kabul edilebilir
                    else:
                        color = "🔴"  # Kırmızı - yavaş
                    
                    print(f"{color}[{first_token_latency:.0f}ms] ", end="", flush=True)
                
                print(token, end="", flush=True)
                response_text += token
            
            end_time = time.time()
            total_time = (end_time - start_time) * 1000
            print(f" [{total_time:.0f}ms]")
            
        except Exception as e:
            print(f"❌ Hata: {e}")
    
    # Sonuçlar
    success_rate = (under_400ms_count / total_tests) * 100
    
    print(f"\n📊 Ultra-Fast Sonuçları:")
    print(f"   🎯 ≤400ms Başarı: {under_400ms_count}/{total_tests} ({success_rate:.1f}%)")
    
    if success_rate >= 80:
        print("   🎉 MÜKEMMEL! Hedef başarıyla ulaşıldı!")
    elif success_rate >= 60:
        print("   ✅ İYİ! Hedef büyük ölçüde başarıldı!")
    elif success_rate >= 40:
        print("   ⚠️ ORTA! Daha fazla optimizasyon gerekli!")
    else:
        print("   ❌ DÜŞÜK! Ciddi optimizasyon gerekli!")
    
    await service.stop()

async def test_specific_optimizations():
    """Spesifik optimizasyon senaryoları"""
    
    print(f"\n🔬 Spesifik Optimizasyon Testleri")
    print("=" * 35)
    
    service = OllamaLLMService()
    await service.start()
    
    # Spesifik senaryolar
    scenarios = [
        {
            "name": "Basit Selamlama",
            "input": "Merhaba",
            "expected_tokens": ["Merhaba", "Size", "nasıl", "yardımcı"]
        },
        {
            "name": "Kredi Kartı",
            "input": "Kredi kartı başvurusu",
            "expected_tokens": ["Tabii", "kredi", "kartı", "başvuru"]
        },
        {
            "name": "Hesap Bilgi",
            "input": "Hesap bakiyem",
            "expected_tokens": ["Hesap", "bakiye", "için", "bilgi"]
        }
    ]
    
    for scenario in scenarios:
        print(f"\n🎭 {scenario['name']}: {scenario['input']}")
        
        start_time = time.time()
        first_token_time = None
        tokens_received = []
        
        print("🤖 ", end="", flush=True)
        
        try:
            async for token in service.generate_response_streaming(scenario['input']):
                if first_token_time is None:
                    first_token_time = time.time()
                    first_token_latency = (first_token_time - start_time) * 1000
                    print(f"[{first_token_latency:.0f}ms] ", end="", flush=True)
                
                tokens_received.append(token.strip())
                print(token, end="", flush=True)
            
            end_time = time.time()
            total_time = (end_time - start_time) * 1000
            print(f" [{total_time:.0f}ms]")
            
            # Beklenen token analizi
            response_text = "".join(tokens_received)
            expected_found = sum(1 for expected in scenario['expected_tokens'] 
                               if expected.lower() in response_text.lower())
            
            print(f"   📝 Beklenen kelimeler: {expected_found}/{len(scenario['expected_tokens'])}")
            
        except Exception as e:
            print(f"   ❌ Hata: {e}")
    
    await service.stop()

if __name__ == "__main__":
    print("🚀 Ultra-Fast Türkçe LLM Optimization Suite")
    print("=" * 50)
    
    asyncio.run(test_ultra_fast_turkish())
    asyncio.run(test_specific_optimizations())
    
    print(f"\n🎯 Ultra-Fast Optimizasyon Özeti:")
    print("✅ Temperature: 0.2 → Ultra tutarlı Türkçe")
    print("✅ Top_p: 0.7 → Hızlı ve odaklı kararlar")
    print("✅ Max tokens: 50 → Ultra kısa yanıtlar")
    print("✅ Context: 1024 → Küçük ve hızlı")
    print("✅ Timeout: 2s → Agresif zaman limiti")
    print("✅ Early stopping → Noktalama ile dur")
    print("✅ ChatML format → Structured prompting")
    
    print(f"\n🏆 Hedef: 400ms first token latency!") 