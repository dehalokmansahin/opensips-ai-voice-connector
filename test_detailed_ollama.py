#!/usr/bin/env python3
"""
Detaylı Ollama LLM Test
"""

import sys
import os

# Python path ekle
current_dir = os.path.dirname(os.path.abspath(__file__))
src_path = os.path.join(current_dir, "src")
pipecat_src_path = os.path.join(current_dir, "pipecat", "src")

if src_path not in sys.path:
    sys.path.insert(0, src_path)
    print(f"Added to Python path: {src_path}")

if pipecat_src_path not in sys.path:
    sys.path.insert(0, pipecat_src_path)
    print(f"Added to Python path: {pipecat_src_path}")

# soxr stub oluştur
import numpy as np
if not hasattr(sys.modules, 'soxr'):
    class SoxrStub:
        def resample(self, *args, **kwargs):
            return np.array([])
    
    sys.modules['soxr'] = SoxrStub()
    print("✅ soxr stub module created")

import requests
import json
import time
import asyncio

# Import edebilir miyiz test edelim
try:
    from services.ollama_llm import OllamaLLMService, ConversationContext
    print("✅ Ollama service import başarılı")
except ImportError as e:
    print(f"❌ Import hatası: {e}")
    sys.exit(1)

def test_direct_ollama_api():
    """Direct Ollama API testi"""
    
    print("\n🔗 Direct Ollama API Test...")
    
    url = "http://localhost:11434/api/generate"
    
    test_prompts = [
        "Merhaba, adın ne?",
        "Türkiye'nin başkenti neresi?",
        "5 + 3 kaç eder?",
        "Kısa bir şaka anlat",
        "Bu günün tarihi nedir?"
    ]
    
    for i, prompt in enumerate(test_prompts, 1):
        print(f"\n📝 Test {i}: {prompt}")
        
        payload = {
            "model": "llama3.2:3b",
            "prompt": prompt,
            "stream": False
        }
        
        start_time = time.time()
        
        try:
            response = requests.post(url, json=payload, timeout=15)
            end_time = time.time()
            
            if response.status_code == 200:
                result = response.json()
                duration = (end_time - start_time) * 1000
                
                print(f"✅ Başarılı - {duration:.0f}ms")
                print(f"🤖 Yanıt: {result.get('response', 'N/A')[:100]}...")
                print(f"📊 Token sayısı: {result.get('eval_count', 0)}")
                
            else:
                print(f"❌ HTTP Hatası: {response.status_code}")
                
        except Exception as e:
            print(f"❌ Hata: {e}")

async def test_ollama_service():
    """OllamaLLMService sınıfı testi"""
    
    print("\n🔧 OllamaLLMService Sınıf Testi...")
    
    # Context artık service içinde yönetiliyor
    service = OllamaLLMService()
    
    await service.start()
    
    test_messages = [
        "Merhaba, ben bir müşteriyim",
        "Hesap bakiyemi öğrenebilir miyim?",
        "Kredi kartı başvurusu yapmak istiyorum",
        "Teşekkürler, iyi günler"
    ]
    
    for i, message in enumerate(test_messages, 1):
        print(f"\n💬 Mesaj {i}: {message}")
        
        start_time = time.time()
        
        try:
            response = await service.generate_response(message)
            end_time = time.time()
            
            duration = (end_time - start_time) * 1000
            
            print(f"✅ Yanıt alındı - {duration:.0f}ms")
            print(f"🤖 LLM: {response}")
            print(f"📚 Context: {len(service._context.history)} mesaj")
            
        except Exception as e:
            print(f"❌ Hata: {e}")
    
    await service.stop()

async def test_conversation_flow():
    """Konuşma akışı testi"""
    
    print("\n💭 Konuşma Akışı Testi...")
    
    service = OllamaLLMService()
    
    await service.start()
    
    conversation = [
        ("Müşteri", "Merhaba, kredi kartı başvurusu yapmak istiyorum"),
        ("Müşteri", "Aylık gelirim 15.000 TL"),
        ("Müşteri", "Evet, çalışma belgem var"),
        ("Müşteri", "Ne kadar sürer onay süreci?"),
        ("Müşteri", "Teşekkürler, başvurumu yapabilirsiniz")
    ]
    
    for i, (speaker, message) in enumerate(conversation, 1):
        print(f"\n🗣️ {speaker}: {message}")
        
        start_time = time.time()
        
        try:
            response = await service.generate_response(message)
            end_time = time.time()
            
            duration = (end_time - start_time) * 1000
            
            print(f"🤖 Asistan ({duration:.0f}ms): {response}")
            
            # Context'i kontrol et
            print(f"📊 Context durumu: {len(service._context.history)} mesaj, son güncelleme: {service._context.last_update}")
            
        except Exception as e:
            print(f"❌ Hata: {e}")
            break
    
    await service.stop()

if __name__ == "__main__":
    print("🧪 Detaylı Ollama LLM Test Suite")
    print("=" * 50)
    
    # 1. Direct API test
    test_direct_ollama_api()
    
    # 2. Service class test
    asyncio.run(test_ollama_service())
    
    # 3. Conversation flow test
    asyncio.run(test_conversation_flow())
    
    print("\n🎉 Tüm testler tamamlandı!") 