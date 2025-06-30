"""
Custom LLaMA WebSocket LLM Service
Kendi LLaMA model serveriniz ile entegrasyon
Streaming sentence segmentation ile TTS optimizasyonu
"""

import asyncio
import json
import websockets
import re
from typing import AsyncGenerator, Optional
import structlog
from pipecat.frames.frames import (
    Frame,
    LLMFullResponseStartFrame,
    LLMFullResponseEndFrame, 
    TextFrame
)
from pipecat.services.ai_services import LLMService

logger = structlog.get_logger()

class StreamingSentenceSegmenter:
    """Streaming text'i cümle bazında segmentlere ayırır"""
    
    def __init__(self):
        self.buffer = ""
        self.sentence_endings = re.compile(r'[.!?]+')
        
    def add_chunk(self, chunk: str) -> list[str]:
        """
        Chunk ekle ve tamamlanan cümleleri döndür
        
        Args:
            chunk: Yeni text chunk'ı
            
        Returns:
            list[str]: Tamamlanan cümleler listesi
        """
        self.buffer += chunk
        sentences = []
        
        # Noktalama işaretlerini ara
        matches = list(self.sentence_endings.finditer(self.buffer))
        
        if matches:
            # Son match'in sonuna kadar olan kısmı al
            last_match = matches[-1]
            end_pos = last_match.end()
            
            # Cümleyi çıkar
            sentence = self.buffer[:end_pos].strip()
            if sentence:
                sentences.append(sentence)
            
            # Buffer'ı güncelle
            self.buffer = self.buffer[end_pos:].strip()
        
        return sentences
    
    def get_remaining(self) -> str:
        """Buffer'da kalan metni döndür"""
        remaining = self.buffer.strip()
        self.buffer = ""
        return remaining
    
    def reset(self):
        """Segmenter'ı sıfırla"""
        self.buffer = ""

class LlamaWebsocketLLMService(LLMService):
    """Custom LLaMA WebSocket LLM Service with Sentence Segmentation"""
    
    def __init__(self, url: str, model: str, **kwargs):
        super().__init__(**kwargs)
        self._url = url
        self._model = model
        self.websocket = None
        self.running = False
        
        # Turkish system prompt optimized for customer service
        self.system_prompt = """Sen Türk Telekom müşteri hizmetleri asistanısın. Türkçe konuş, kısa ve net yanıtlar ver. Müşterilere yardımcı ol, sorunlarını çöz. Maksimum 2-3 cümle kullan."""
        
        logger.info("LLaMA WebSocket LLM service initialized", url=self._url)
    
    async def start(self):
        """Service'i başlat"""
        try:
            logger.info("Starting LLaMA WebSocket LLM service", url=self._url)
            
            # WebSocket bağlantısını test et
            async with websockets.connect(self._url) as websocket:
                logger.info("✅ LLaMA WebSocket connection test successful")
            
            self.running = True
            logger.info("LLaMA WebSocket LLM service started successfully")
            
        except Exception as e:
            logger.error("Failed to start LLaMA WebSocket service", error=str(e))
            raise
    
    async def stop(self):
        """Service'i durdur"""
        self.running = False
        if self.websocket:
            await self.websocket.close()
        logger.info("LLaMA WebSocket LLM service stopped")
    
    async def generate_response_streaming(self, prompt: str, context: list = None) -> AsyncGenerator[str, None]:
        """
        Streaming response generation with sentence segmentation
        
        Args:
            prompt: User input text
            context: Conversation context (optional)
            
        Yields:
            str: Generated text chunks (sentence by sentence)
        """
        start_time = asyncio.get_event_loop().time()
        segmenter = StreamingSentenceSegmenter()
        
        try:
            logger.info("Generating LLaMA response with sentence segmentation", prompt=prompt[:50])
            
            # WebSocket bağlantısı kur
            async with websockets.connect(self._url) as websocket:
                # Request payload hazırla
                request_data = {
                    "prompt": prompt,
                    "system_prompt": self.system_prompt,
                    "max_tokens": 80,
                    "temperature": 0.2,
                    "top_p": 0.7,
                    "stream": True,
                    "stop": ["User:", "System:", "\n\n"]
                }
                
                # Request gönder
                await websocket.send(json.dumps(request_data))
                logger.debug("Request sent to LLaMA server", request=request_data)
                
                first_token = True
                first_sentence = True
                total_response = ""
                
                # Streaming response al
                async for message in websocket:
                    try:
                        data = json.loads(message)
                        
                        if first_token:
                            first_token_time = (asyncio.get_event_loop().time() - start_time) * 1000
                            logger.info("First token received", latency_ms=round(first_token_time, 1))
                            first_token = False
                        
                        # Response chunk'ı işle
                        if "chunk" in data and data["chunk"]:
                            chunk = data["chunk"]
                            total_response += chunk
                            
                            # Chunk'ı segmenter'a ekle
                            completed_sentences = segmenter.add_chunk(chunk)
                            
                            # Tamamlanan cümleleri yield et
                            for sentence in completed_sentences:
                                if sentence.strip():
                                    if first_sentence:
                                        first_sentence_time = (asyncio.get_event_loop().time() - start_time) * 1000
                                        logger.info("First sentence completed", 
                                                   sentence=sentence[:50],
                                                   latency_ms=round(first_sentence_time, 1))
                                        first_sentence = False
                                    
                                    logger.debug("Yielding completed sentence", sentence=sentence[:50])
                                    yield sentence
                        
                        # Stream tamamlandı
                        elif "done" in data and data["done"]:
                            # Kalan buffer'ı kontrol et
                            remaining = segmenter.get_remaining()
                            if remaining:
                                logger.debug("Yielding remaining text", text=remaining[:50])
                                yield remaining
                            
                            total_time = (asyncio.get_event_loop().time() - start_time) * 1000
                            logger.info("LLaMA response completed", 
                                       total_latency_ms=round(total_time, 1),
                                       response_length=len(total_response))
                            break
                            
                    except json.JSONDecodeError as e:
                        logger.warning("Invalid JSON from LLaMA server", message=message, error=str(e))
                        continue
                    except Exception as e:
                        logger.error("Error processing LLaMA response", error=str(e))
                        break
                
        except websockets.exceptions.ConnectionClosed:
            logger.error("LLaMA WebSocket connection closed")
            yield "Bağlantı hatası oluştu."
        except asyncio.TimeoutError:
            logger.error("LLaMA request timeout")
            yield "Zaman aşımı hatası."
        except Exception as e:
            logger.error("LLaMA generation error", error=str(e))
            yield "Sistem hatası oluştu."
    
    async def process_frame(self, frame: Frame) -> AsyncGenerator[Frame, None]:
        """
        Pipecat frame processing with sentence-based streaming
        
        Args:
            frame: Input frame
            
        Yields:
            Frame: Output frames (sentence by sentence)
        """
        if isinstance(frame, TextFrame):
            user_text = frame.text.strip()
            
            if not user_text:
                return
            
            logger.info("Processing LLM request with sentence segmentation", text=user_text[:50])
            
            # Start response
            yield LLMFullResponseStartFrame()
            
            # Generate streaming response sentence by sentence
            try:
                sentence_count = 0
                async for sentence in self.generate_response_streaming(user_text):
                    if sentence.strip():
                        sentence_count += 1
                        logger.info("Sending sentence to TTS", 
                                   sentence_num=sentence_count,
                                   sentence=sentence[:50])
                        yield TextFrame(text=sentence)
                
                # End response
                logger.info("LLM response completed", total_sentences=sentence_count)
                yield LLMFullResponseEndFrame()
                
            except Exception as e:
                logger.error("Error in LLM processing", error=str(e))
                yield TextFrame(text="Üzgünüm, bir hata oluştu.")
                yield LLMFullResponseEndFrame()
        else:
            # Pass through other frame types
            yield frame 