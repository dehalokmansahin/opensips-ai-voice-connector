"""
Ollama LLM Service - Llama3.2:3b entegrasyonu
"""

import asyncio
import json
import logging
from typing import Optional, Dict, Any, List, Tuple, AsyncGenerator
import aiohttp
import structlog

from pipecat.frames.frames import (
    Frame,
    LLMFullResponseStartFrame,
    LLMFullResponseEndFrame,
    LLMTextFrame,
    TextFrame,
)

logger = structlog.get_logger()

class ConversationContext:
    """Konuşma geçmişi yönetimi"""
    
    def __init__(self, max_history: int = 10):
        self.history: List[Tuple[str, str]] = []  # [(user_text, assistant_text), ...]
        self.max_history = max_history
        logger.info("ConversationContext initialized", max_history=max_history)
    
    def add_exchange(self, user_text: str, assistant_text: str) -> None:
        """Konuşma değişimi ekle"""
        self.history.append((user_text, assistant_text))
        if len(self.history) > self.max_history:
            self.history.pop(0)
        logger.debug("Exchange added to context", 
                    user_text=user_text[:50], 
                    assistant_text=assistant_text[:50],
                    history_length=len(self.history))
    
    def get_context_prompt(self) -> str:
        """Geçmişi Türkçe-optimized prompt formatına dönüştür"""
        if not self.history:
            return ""
        
        context = "\\n\\n<|im_start|>context\\nÖnceki konuşma:\\n"
        for user_text, assistant_text in self.history[-2:]:  # Son 2 değişim (kısa tutmak için)
            context += f"Kullanıcı: {user_text}\\n"
            context += f"Asistan: {assistant_text}\\n"
        context += "<|im_end|>\\n"
        
        return context
    
    def clear(self) -> None:
        """Geçmişi temizle"""
        self.history.clear()
        logger.info("Conversation context cleared")

class OllamaLLMService:
    """Ollama LLM servisi - Llama3.2:3b ile Türkçe konuşma"""
    
    def __init__(
        self, 
        url: str = "http://localhost:11434/api/generate",
        model: str = "llama3.2:3b",
        timeout: float = 4.0,  # 2s'den 4s'ye çıkar - daha güvenli
        **kwargs
    ):
        self._url = url
        self._model = model
        self._timeout = timeout
        self._session: Optional[aiohttp.ClientSession] = None
        self._context = ConversationContext()
        
        # Türkçe-optimized sistem promptu
        self._system_prompt = """<|im_start|>system
Sen Türkçe konuşan bir müşteri hizmetleri asistanısın. SADECE Türkçe yanıt ver.

LANGUAGE: Turkish (TR)
CONTEXT: Telefon müşteri hizmetleri
STYLE: Kısa, net, profesyonel

Kurallar:
- SADECE Türkçe kullan
- Maksimum 1-2 cümle yanıt ver
- Saygılı ve yardımsever ol
- Hızlı ve net yanıtlar ver

Örnekler:
Kullanıcı: "Merhaba"
Asistan: "Merhaba! Size nasıl yardımcı olabilirim?"

Kullanıcı: "Kredi kartı başvurusu"
Asistan: "Tabii, kredi kartı başvurunuz için gerekli bilgileri alalım."
<|im_end|>"""
        
        logger.info("OllamaLLMService initialized", 
                   url=url, model=model, timeout=timeout)
    
    async def start(self) -> None:
        """LLM servisini başlat"""
        try:
            connector = aiohttp.TCPConnector(
                limit=10, 
                limit_per_host=5,
                keepalive_timeout=30,  # Keep-alive bağlantı
                enable_cleanup_closed=True  # Kapalı bağlantıları temizle
            )
            timeout = aiohttp.ClientTimeout(
                total=self._timeout,
                connect=2.0,  # Bağlantı timeout'u ayrı
                sock_read=self._timeout  # Socket read timeout
            )
            self._session = aiohttp.ClientSession(
                connector=connector,
                timeout=timeout
            )
            
            # Bağlantı testi
            await self._test_connection()
            logger.info("Ollama LLM service started successfully")
            
        except Exception as e:
            logger.error("Failed to start Ollama LLM service", error=str(e))
            raise
    
    async def stop(self) -> None:
        """LLM servisini durdur"""
        if self._session:
            await self._session.close()
            self._session = None
        logger.info("Ollama LLM service stopped")
    
    async def _test_connection(self) -> None:
        """Ollama bağlantısını test et"""
        if not self._session:
            raise RuntimeError("Session not initialized")
        
        test_payload = {
            "model": self._model,
            "prompt": "Test",
            "stream": False,
            "options": {
                "temperature": 0.7,
                "top_p": 0.9,
                "max_tokens": 10
            }
        }
        
        try:
            async with self._session.post(self._url, json=test_payload) as response:
                if response.status == 200:
                    result = await response.json()
                    logger.info("Ollama connection test successful", 
                               model=self._model, response_length=len(result.get("response", "")))
                else:
                    raise RuntimeError(f"Ollama API returned status {response.status}")
                    
        except Exception as e:
            logger.error("Ollama connection test failed", error=str(e))
            raise
    
    async def generate_response(self, user_text: str) -> str:
        """Kullanıcı metnine yanıt üret"""
        if not self._session:
            raise RuntimeError("LLM service not started")
        
        try:
            # Türkçe-optimized prompt oluştur
            context = self._context.get_context_prompt()
            full_prompt = f"{self._system_prompt}\\n{context}\\n<|im_start|>user\\n{user_text}<|im_end|>\\n<|im_start|>assistant\\n"
            
            payload = {
                "model": self._model,
                "prompt": full_prompt,
                "stream": False,
                "options": {
                    "temperature": 0.2,      # Daha düşük - ultra tutarlı Türkçe
                    "top_p": 0.7,           # Daha odaklı - hızlı karar
                    "max_tokens": 80,       # Biraz daha uzun - güvenli
                    "num_predict": 80,      # Tahmin limiti - güvenli
                    "repeat_penalty": 1.2,  # Daha yüksek - tekrar önleme
                    "stop": ["\\nKullanıcı:", "\\n\\n", "<|im_end|>", "Kullanıcı:", "User:", ".", "!", "?"],
                    "num_ctx": 1024,        # Daha küçük context - hızlı
                    "num_thread": -1,       # Tüm CPU thread'leri kullan
                    "mirostat": 2,          # Türkçe için iyi çalışan sampling
                    "mirostat_tau": 3.0,    # Daha düşük entropy - hızlı
                    "mirostat_eta": 0.2     # Daha yüksek learning rate - hızlı
                }
            }
            
            logger.debug("Sending request to Ollama", 
                        prompt_length=len(full_prompt),
                        user_text=user_text[:100])
            
            start_time = asyncio.get_event_loop().time()
            
            async with self._session.post(self._url, json=payload) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise RuntimeError(f"Ollama API error {response.status}: {error_text}")
                
                result = await response.json()
                assistant_response = result.get("response", "").strip()
                
                # Latency hesapla
                latency_ms = (asyncio.get_event_loop().time() - start_time) * 1000
                
                if not assistant_response:
                    assistant_response = "Anlayamadım, tekrar söyler misiniz?"
                
                # Context'e ekle
                self._context.add_exchange(user_text, assistant_response)
                
                logger.info("LLM response generated", 
                           latency_ms=round(latency_ms, 2),
                           user_text=user_text[:50],
                           assistant_response=assistant_response[:50],
                           response_length=len(assistant_response))
                
                return assistant_response
                
        except asyncio.TimeoutError:
            logger.error("LLM request timeout", timeout=self._timeout)
            return "Üzgünüm, yanıt vermekte geciktim. Tekrar dener misiniz?"
            
        except Exception as e:
            logger.error("LLM generation error", error=str(e), user_text=user_text[:100])
            return "Bir hata oluştu. Tekrar dener misiniz?"
    
    async def generate_response_streaming(self, user_text: str) -> AsyncGenerator[str, None]:
        """Kullanıcı metnine streaming yanıt üret"""
        if not self._session:
            raise RuntimeError("LLM service not started")
        
        try:
            # Türkçe-optimized streaming prompt oluştur
            context = self._context.get_context_prompt()
            full_prompt = f"{self._system_prompt}\\n{context}\\n<|im_start|>user\\n{user_text}<|im_end|>\\n<|im_start|>assistant\\n"
            
            payload = {
                "model": self._model,
                "prompt": full_prompt,
                "stream": True,  # Streaming enable
                "options": {
                    "temperature": 0.2,      # Daha düşük - ultra tutarlı Türkçe
                    "top_p": 0.7,           # Daha odaklı - hızlı karar
                    "max_tokens": 80,       # Biraz daha uzun - güvenli
                    "num_predict": 80,      # Tahmin limiti - güvenli
                    "repeat_penalty": 1.2,  # Daha yüksek - tekrar önleme
                    "stop": ["\\nKullanıcı:", "\\n\\n", "<|im_end|>", "Kullanıcı:", "User:", ".", "!", "?"],
                    "num_ctx": 1024,        # Daha küçük context - hızlı
                    "num_thread": -1,       # Tüm CPU thread'leri kullan
                    "mirostat": 2,          # Türkçe için iyi çalışan sampling
                    "mirostat_tau": 3.0,    # Daha düşük entropy - hızlı
                    "mirostat_eta": 0.2     # Daha yüksek learning rate - hızlı
                }
            }
            
            logger.debug("Starting streaming request to Ollama", 
                        prompt_length=len(full_prompt),
                        user_text=user_text[:100])
            
            start_time = asyncio.get_event_loop().time()
            first_token_time = None
            full_response = ""
            
            async with self._session.post(self._url, json=payload) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise RuntimeError(f"Ollama API error {response.status}: {error_text}")
                
                async for line in response.content:
                    if line:
                        try:
                            # JSON parse
                            data = json.loads(line.decode('utf-8'))
                            
                            if 'response' in data:
                                token = data['response']
                                if token:
                                    # İlk token timing
                                    if first_token_time is None:
                                        first_token_time = asyncio.get_event_loop().time()
                                        first_token_latency = (first_token_time - start_time) * 1000
                                        logger.info("First token received", 
                                                   latency_ms=round(first_token_latency, 2))
                                    
                                    full_response += token
                                    yield token
                            
                            # Son mesaj kontrolü
                            if data.get('done', False):
                                break
                                
                        except json.JSONDecodeError:
                            continue
            
            # Context'e ekle
            if full_response.strip():
                self._context.add_exchange(user_text, full_response.strip())
            
            total_latency = (asyncio.get_event_loop().time() - start_time) * 1000
            logger.info("Streaming response completed", 
                       total_latency_ms=round(total_latency, 2),
                       first_token_ms=round((first_token_time - start_time) * 1000, 2) if first_token_time else 0,
                       response_length=len(full_response))
                
        except asyncio.TimeoutError:
            logger.error("LLM streaming timeout", timeout=self._timeout)
            yield "Üzgünüm, yanıt vermekte geciktim. Tekrar dener misiniz?"
            
        except Exception as e:
            logger.error("LLM streaming error", error=str(e), user_text=user_text[:100])
            yield "Bir hata oluştu. Tekrar dener misiniz?"

    async def run_llm(self, user_text: str) -> AsyncGenerator[Frame, None]:
        """LLM çalıştır ve streaming frame'leri döndür"""
        try:
            logger.info("Starting streaming LLM processing", text=user_text)
            
            # Başlangıç frame'i
            yield LLMFullResponseStartFrame()
            
            # Streaming yanıt
            async for token in self.generate_response_streaming(user_text):
                if token.strip():  # Boş token'ları atla
                    yield LLMTextFrame(text=token)
            
            # Bitiş frame'i
            yield LLMFullResponseEndFrame()
            
            logger.info("Streaming LLM processing completed")
            
        except Exception as e:
            logger.error("Error in streaming LLM processing", error=str(e))
            # Hata durumunda varsayılan yanıt
            yield LLMFullResponseStartFrame()
            yield LLMTextFrame(text="Bir sorun yaşadım. Tekrar dener misiniz?")
            yield LLMFullResponseEndFrame()
    
    def clear_context(self) -> None:
        """Konuşma geçmişini temizle"""
        self._context.clear()
        logger.info("LLM context cleared") 