"""
Custom LLaMA WebSocket LLM Service
Kendi LLaMA model serveriniz ile entegrasyon
"""

import asyncio
import json
import websockets
from typing import AsyncGenerator, Optional
import structlog
from pipecat.frames.frames import (
    Frame,
    LLMFullResponseStartFrame,
    LLMFullResponseEndFrame, 
    TextFrame
)

logger = structlog.get_logger()

class LlamaWebsocketLLMService:
    """Custom LLaMA WebSocket LLM Service"""
    
    def __init__(self, url: str = "ws://llama-server:8765"):
        """
        Initialize LLaMA WebSocket service
        
        Args:
            url: WebSocket URL of your LLaMA server
        """
        self.url = url
        self.websocket = None
        self.running = False
        
        # Turkish system prompt optimized for customer service
        self.system_prompt = """Sen Türk Telekom müşteri hizmetleri asistanısın. Türkçe konuş, kısa ve net yanıtlar ver. Müşterilere yardımcı ol, sorunlarını çöz. Maksimum 2-3 cümle kullan."""
        
        logger.info("LLaMA WebSocket LLM service initialized", url=self.url)
    
    async def start(self):
        """Service'i başlat"""
        try:
            logger.info("Starting LLaMA WebSocket LLM service", url=self.url)
            
            # WebSocket bağlantısını test et
            async with websockets.connect(self.url) as websocket:
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
        Streaming response generation
        
        Args:
            prompt: User input text
            context: Conversation context (optional)
            
        Yields:
            str: Generated text chunks
        """
        start_time = asyncio.get_event_loop().time()
        
        try:
            logger.info("Generating LLaMA response", prompt=prompt[:50])
            
            # WebSocket bağlantısı kur
            async with websockets.connect(self.url) as websocket:
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
                response_text = ""
                
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
                            response_text += chunk
                            logger.debug("Received chunk", chunk=chunk[:30])
                            yield chunk
                        
                        # Stream tamamlandı
                        elif "done" in data and data["done"]:
                            total_time = (asyncio.get_event_loop().time() - start_time) * 1000
                            logger.info("LLaMA response completed", 
                                       total_latency_ms=round(total_time, 1),
                                       response_length=len(response_text))
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
        Pipecat frame processing
        
        Args:
            frame: Input frame
            
        Yields:
            Frame: Output frames
        """
        if isinstance(frame, TextFrame):
            user_text = frame.text.strip()
            
            if not user_text:
                return
            
            logger.info("Processing LLM request", text=user_text[:50])
            
            # Start response
            yield LLMFullResponseStartFrame()
            
            # Generate streaming response
            try:
                async for chunk in self.generate_response_streaming(user_text):
                    if chunk.strip():
                        yield TextFrame(text=chunk)
                
                # End response
                yield LLMFullResponseEndFrame()
                
            except Exception as e:
                logger.error("Error in LLM processing", error=str(e))
                yield TextFrame(text="Üzgünüm, bir hata oluştu.")
                yield LLMFullResponseEndFrame()
        else:
            # Pass through other frame types
            yield frame 