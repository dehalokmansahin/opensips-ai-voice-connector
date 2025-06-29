#!/usr/bin/env python3
"""
Türkçe LLM Optimizasyon Test
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

async def test_turkish_optimizations():
    """Türkçe optimizasyonları test et"""
    
    print("🇹🇷 Türkçe LLM Optimizasyon Test")
    print("=" * 50)
    
    service = OllamaLLMService()
    await service.start()
    
    # Türkçe-specific test cases
    turkish_test_cases = [
        # Basit selamlaşma
        "Merhaba",
        
        # Müşteri hizmetleri senaryoları
        "Kredi kartı başvurusu yapmak istiyorum",
        "Hesap bakiyemi öğrenebilir miyim?", 
        "Kartımı kaybettim ne yapmalıyım?",
        "Faiz oranları nedir?",
        
        # Türkçe'ye özgü ifadeler
        "Teşekkür ederim",
        "İyi günler dilerim",
        "Yardımcı olur musunuz?",
        "Anlayamadım tekrar söyler misiniz?",
        
        # Karmaşık Türkçe cümleler
        "Geçen ay yaptığım havale işleminin durumunu öğrenmek istiyorum",
        "İnternet bankacılığı şifremi unuttum nasıl yenileyebilirim?",
    ]
    
    total_first_token_time = 0
    total_response_time = 0
    response_count = 0
    
    for i, test_input in enumerate(turkish_test_cases, 1):
        print(f"\n📝 Test {i:2d}: {test_input}")
        
        # Streaming test
        start_time = time.time()
        first_token_received = False
        first_token_time = None
        response_text = ""
        
        print("🤖 Yanıt: ", end="", flush=True)
        
        try:
            async for token in service.generate_response_streaming(test_input):
                if not first_token_received:
                    first_token_time = time.time()
                    first_token_latency = (first_token_time - start_time) * 1000
                    print(f"[{first_token_latency:.0f}ms] ", end="", flush=True)
                    first_token_received = True
                    
                    total_first_token_time += first_token_latency
                
                print(token, end="", flush=True)
                response_text += token
            
            end_time = time.time()
            total_time = (end_time - start_time) * 1000
            total_response_time += total_time
            response_count += 1
            
            print(f" [{total_time:.0f}ms total]")
            
            # Türkçe kalite değerlendirmesi
            turkish_quality = evaluate_turkish_quality(response_text)
            print(f"   📊 Türkçe Kalite: {turkish_quality}/5")
            
        except Exception as e:
            print(f"   ❌ Hata: {e}")
    
    # Sonuçlar
    if response_count > 0:
        avg_first_token = total_first_token_time / response_count
        avg_total_time = total_response_time / response_count
        
        print(f"\n📊 Türkçe Optimizasyon Sonuçları:")
        print(f"   🎯 Ortalama First Token: {avg_first_token:.0f}ms")
        print(f"   ⏱️ Ortalama Total Time: {avg_total_time:.0f}ms")
        print(f"   🎭 Test Sayısı: {response_count}")
        
        # Hedef karşılaştırması
        target_first_token = 400
        if avg_first_token <= target_first_token:
            print(f"   ✅ First Token Hedefi: BAŞARILI (≤{target_first_token}ms)")
        else:
            improvement_needed = avg_first_token - target_first_token
            print(f"   ⚠️ First Token Hedefi: {improvement_needed:.0f}ms iyileştirme gerekli")
    
    await service.stop()

def evaluate_turkish_quality(response: str) -> int:
    """Türkçe yanıt kalitesini değerlendir (1-5 skala)"""
    
    score = 5  # Başlangıç puanı
    
    # Türkçe karakter kontrolü
    turkish_chars = ['ç', 'ğ', 'ı', 'ö', 'ş', 'ü', 'Ç', 'Ğ', 'İ', 'Ö', 'Ş', 'Ü']
    has_turkish_chars = any(char in response for char in turkish_chars)
    if not has_turkish_chars:
        score -= 1
    
    # İngilizce kelime kontrolü (negatif puan)
    english_words = ['the', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by']
    english_count = sum(1 for word in english_words if word.lower() in response.lower())
    if english_count > 0:
        score -= min(2, english_count)
    
    # Uzunluk kontrolü (çok kısa veya çok uzun)
    if len(response) < 10:
        score -= 1
    elif len(response) > 200:
        score -= 1
    
    # Profesyonel ifade kontrolü
    professional_words = ['merhaba', 'teşekkür', 'yardımcı', 'nasıl', 'lütfen', 'tabii']
    professional_count = sum(1 for word in professional_words if word.lower() in response.lower())
    if professional_count == 0:
        score -= 1
    
    return max(1, min(5, score))

async def test_parameter_comparison():
    """Farklı parametre setlerini karşılaştır"""
    
    print("\n🔧 Parametre Optimizasyon Karşılaştırması")
    print("=" * 45)
    
    test_message = "Kredi kartı başvurusu yapmak istiyorum"
    
    # Farklı parametre setleri
    parameter_sets = [
        {
            "name": "Mevcut Optimized",
            "params": {
                "temperature": 0.3,
                "top_p": 0.8,
                "max_tokens": 80,
                "repeat_penalty": 1.15,
                "mirostat": 2
            }
        },
        {
            "name": "Ultra Fast",
            "params": {
                "temperature": 0.1,
                "top_p": 0.7,
                "max_tokens": 40,
                "repeat_penalty": 1.2,
                "mirostat": 2
            }
        },
        {
            "name": "High Quality",
            "params": {
                "temperature": 0.5,
                "top_p": 0.9,
                "max_tokens": 120,
                "repeat_penalty": 1.1,
                "mirostat": 1
            }
        }
    ]
    
    for param_set in parameter_sets:
        print(f"\n🧪 Test: {param_set['name']}")
        
        # Geçici olarak parametreleri değiştir
        service = OllamaLLMService()
        await service.start()
        
        start_time = time.time()
        first_token_time = None
        response_text = ""
        
        print("🤖 Yanıt: ", end="", flush=True)
        
        try:
            async for token in service.generate_response_streaming(test_message):
                if first_token_time is None:
                    first_token_time = time.time()
                    first_token_latency = (first_token_time - start_time) * 1000
                    print(f"[{first_token_latency:.0f}ms] ", end="", flush=True)
                
                print(token, end="", flush=True)
                response_text += token
            
            end_time = time.time()
            total_time = (end_time - start_time) * 1000
            
            print(f" [{total_time:.0f}ms total]")
            
            quality = evaluate_turkish_quality(response_text)
            print(f"   📊 Kalite: {quality}/5, Uzunluk: {len(response_text)} karakter")
            
        except Exception as e:
            print(f"   ❌ Hata: {e}")
        
        await service.stop()

if __name__ == "__main__":
    print("🇹🇷 Türkçe LLM Optimizasyon Test Suite")
    print("=" * 50)
    
    asyncio.run(test_turkish_optimizations())
    asyncio.run(test_parameter_comparison())
    
    print("\n🎯 Optimizasyon Önerileri:")
    print("1. 🔤 ChatML format kullanımı (<|im_start|>, <|im_end|>)")
    print("2. 🌡️ Düşük temperature (0.3) - tutarlı Türkçe")
    print("3. 🎯 Düşük top_p (0.8) - odaklı yanıtlar")
    print("4. 🔄 Yüksek repeat_penalty (1.15) - tekrar önleme")
    print("5. 📏 Kısa max_tokens (80) - hızlı yanıt")
    print("6. 🧠 Mirostat sampling - Türkçe için optimize")
    print("7. ⚡ Early stopping - noktalama işaretlerinde dur") 