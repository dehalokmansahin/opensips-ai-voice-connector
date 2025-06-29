#!/usr/bin/env python3
"""
Hata Düzeltmeli Türkçe LLM Test
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

async def test_fixed_turkish():
    """Hata düzeltmeli Türkçe test"""
    
    print("🔧 Hata Düzeltmeli Türkçe LLM Test")
    print("=" * 40)
    print("🔧 Düzeltmeler:")
    print("   • Timeout: 4s (2s'den artırıldı)")
    print("   • Max tokens: 80 (50'den artırıldı)")
    print("   • Connection keepalive eklendi")
    print("   • Stop tokens düzenlendi")
    print()
    
    service = OllamaLLMService()
    
    try:
        await service.start()
        print("✅ Servis başarıyla başlatıldı")
        
        # Test senaryoları
        test_cases = [
            "Merhaba",
            "Kredi kartı başvurusu",
            "Hesap bakiyem",
            "Teşekkürler",
            "Yardım lütfen",
        ]
        
        successful_tests = 0
        under_400ms = 0
        total_first_token_time = 0
        
        for i, test_input in enumerate(test_cases, 1):
            print(f"\n🧪 Test {i}: {test_input}")
            
            start_time = time.time()
            first_token_time = None
            response_text = ""
            
            print("🤖 Yanıt: ", end="", flush=True)
            
            try:
                token_count = 0
                async for token in service.generate_response_streaming(test_input):
                    if first_token_time is None:
                        first_token_time = time.time()
                        first_token_latency = (first_token_time - start_time) * 1000
                        total_first_token_time += first_token_latency
                        
                        # Renk kodlaması
                        if first_token_latency <= 400:
                            color = "🟢"
                            under_400ms += 1
                        elif first_token_latency <= 600:
                            color = "🟡"
                        else:
                            color = "🔴"
                        
                        print(f"{color}[{first_token_latency:.0f}ms] ", end="", flush=True)
                    
                    print(token, end="", flush=True)
                    response_text += token
                    token_count += 1
                
                end_time = time.time()
                total_time = (end_time - start_time) * 1000
                
                print(f" [{total_time:.0f}ms total, {token_count} tokens]")
                
                # Başarı kontrolü
                if len(response_text.strip()) > 0 and "Üzgünüm" not in response_text:
                    successful_tests += 1
                    print(f"   ✅ Başarılı yanıt: {len(response_text)} karakter")
                else:
                    print(f"   ⚠️ Sorunlu yanıt veya timeout")
                
            except Exception as e:
                print(f"   ❌ Hata: {e}")
        
        # Sonuçlar
        success_rate = (successful_tests / len(test_cases)) * 100
        avg_first_token = total_first_token_time / len(test_cases) if len(test_cases) > 0 else 0
        fast_response_rate = (under_400ms / len(test_cases)) * 100
        
        print(f"\n📊 Hata Düzeltme Sonuçları:")
        print(f"   ✅ Başarılı testler: {successful_tests}/{len(test_cases)} ({success_rate:.1f}%)")
        print(f"   🎯 ≤400ms yanıtlar: {under_400ms}/{len(test_cases)} ({fast_response_rate:.1f}%)")
        print(f"   ⏱️ Ortalama first token: {avg_first_token:.0f}ms")
        
        # Değerlendirme
        if success_rate >= 80 and fast_response_rate >= 40:
            print("   🎉 MÜKEMMEL! Hatalar başarıyla düzeltildi!")
        elif success_rate >= 60:
            print("   ✅ İYİ! Çoğu hata düzeltildi!")
        else:
            print("   ⚠️ Hala bazı sorunlar var!")
            
    except Exception as e:
        print(f"❌ Servis başlatma hatası: {e}")
    
    finally:
        await service.stop()
        print("\n🔧 Servis durduruldu")

async def test_stability():
    """Kararlılık testi"""
    
    print(f"\n🔄 Kararlılık Testi")
    print("=" * 25)
    
    service = OllamaLLMService()
    await service.start()
    
    # Aynı soruyu 5 kez sor
    test_question = "Merhaba nasılsınız?"
    
    for i in range(1, 6):
        print(f"\n🔄 Tekrar {i}: {test_question}")
        
        start_time = time.time()
        first_token_time = None
        
        print("🤖 ", end="", flush=True)
        
        try:
            async for token in service.generate_response_streaming(test_question):
                if first_token_time is None:
                    first_token_time = time.time()
                    latency = (first_token_time - start_time) * 1000
                    print(f"[{latency:.0f}ms] ", end="", flush=True)
                
                print(token, end="", flush=True)
            
            end_time = time.time()
            total_time = (end_time - start_time) * 1000
            print(f" [{total_time:.0f}ms]")
            
        except Exception as e:
            print(f"❌ Hata: {e}")
        
        # Kısa bekleme
        await asyncio.sleep(0.5)
    
    await service.stop()

if __name__ == "__main__":
    print("🔧 Hata Düzeltmeli Türkçe LLM Test Suite")
    print("=" * 45)
    
    asyncio.run(test_fixed_turkish())
    asyncio.run(test_stability())
    
    print(f"\n🎯 Uygulanan Düzeltmeler:")
    print("✅ Timeout: 2s → 4s (daha güvenli)")
    print("✅ Max tokens: 50 → 80 (tam yanıtlar)")
    print("✅ Connection keepalive eklendi")
    print("✅ Socket read timeout ayrıldı")
    print("✅ Stop tokens optimize edildi")
    print("✅ Error handling iyileştirildi")
    
    print(f"\n🏆 Hedef: Kararlı ve hızlı Türkçe yanıtlar!") 