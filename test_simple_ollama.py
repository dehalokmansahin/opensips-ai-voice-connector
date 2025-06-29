#!/usr/bin/env python3
"""
Basit Ollama bağlantı testi
"""

import requests
import json

def test_ollama():
    """Basit Ollama API testi"""
    
    print("🔗 Ollama API Bağlantı Testi...")
    
    url = "http://localhost:11434/api/generate"
    payload = {
        "model": "llama3.2:3b",
        "prompt": "Merhaba, nasılsın?",
        "stream": False
    }
    
    try:
        print(f"📡 İstek gönderiliyor: {url}")
        print(f"📦 Payload: {payload}")
        
        response = requests.post(url, json=payload, timeout=10)
        
        print(f"📊 Status Code: {response.status_code}")
        print(f"📄 Response Headers: {dict(response.headers)}")
        
        if response.status_code == 200:
            result = response.json()
            print(f"✅ Başarılı yanıt!")
            print(f"🤖 Model: {result.get('model', 'N/A')}")
            print(f"💬 Yanıt: {result.get('response', 'N/A')}")
            print(f"⏱️ Süre: {result.get('total_duration', 0) / 1000000:.2f}ms")
            return True
        else:
            print(f"❌ HTTP Hatası: {response.status_code}")
            print(f"📄 Yanıt: {response.text}")
            return False
            
    except requests.exceptions.ConnectionError as e:
        print(f"❌ Bağlantı Hatası: {e}")
        print("💡 Ollama server çalışmıyor olabilir")
        return False
        
    except requests.exceptions.Timeout as e:
        print(f"❌ Timeout Hatası: {e}")
        return False
        
    except Exception as e:
        print(f"❌ Genel Hata: {e}")
        return False

if __name__ == "__main__":
    success = test_ollama()
    if success:
        print("🎉 Ollama API test başarılı!")
    else:
        print("⚠️ Ollama API test başarısız!") 