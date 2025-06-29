"""
Vosk WebSocket STT Service - Düzeltilmiş versiyon
"""

import asyncio
import json
import logging
import websockets
from typing import Optional, Dict, Any
import structlog

from pipecat.frames.frames import (
    Frame,
    AudioRawFrame,
    InterimTranscriptionFrame,
    TranscriptionFrame,
)
from pipecat.services.ai_services import STTService

logger = structlog.get_logger()

class VoskWebsocketSTTService(STTService):
    """Vosk WebSocket tabanlı STT servisi"""
    
    def __init__(
        self, 
        url: str = "ws://localhost:2700",
        sample_rate: int = 16000,
        **kwargs
    ):
        super().__init__(**kwargs)
        self._url = url
        self._sample_rate = sample_rate
        self._websocket: Optional[websockets.WebSocketServerProtocol] = None
        self._connection_lock = asyncio.Lock()
        self._is_connected = False
        
        logger.info("VoskWebsocketSTTService initialized", 
                   url=self._url, 
                   sample_rate=self._sample_rate)
    
    async def start(self) -> None:
        """WebSocket bağlantısını başlat"""
        async with self._connection_lock:
            if self._is_connected:
                return
                
            try:
                logger.info("Connecting to Vosk WebSocket", url=self._url)
                self._websocket = await websockets.connect(self._url)
                
                # Vosk config mesajını gönder
                config_message = {
                    "config": {
                        "sample_rate": self._sample_rate,
                        "format": "json",
                        "words": True
                    }
                }
                
                await self._websocket.send(json.dumps(config_message))
                logger.info("Vosk config sent", config=config_message)
                
                self._is_connected = True
                logger.info("Vosk WebSocket connected successfully")
                
            except Exception as e:
                logger.error("Failed to connect to Vosk WebSocket", error=str(e))
                raise
    
    async def stop(self) -> None:
        """WebSocket bağlantısını kapat"""
        async with self._connection_lock:
            if not self._is_connected:
                return
                
            try:
                if self._websocket:
                    # EOS mesajı gönder
                    await self._websocket.send('{"eof": 1}')
                    await self._websocket.close()
                    logger.info("Vosk WebSocket connection closed")
                    
            except Exception as e:
                logger.warning("Error closing Vosk WebSocket", error=str(e))
            finally:
                self._websocket = None
                self._is_connected = False
    
    async def run_stt(self, audio: bytes) -> None:
        """STT işlemini çalıştır"""
        if not self._is_connected or not self._websocket:
            logger.warning("Vosk WebSocket not connected, skipping STT")
            return
        
        # Audio format validation
        if not audio or len(audio) == 0:
            logger.debug("Empty audio data, skipping")
            return
        
        # Ensure audio is bytes type
        if not isinstance(audio, bytes):
            logger.error(f"Audio data must be bytes, got {type(audio)}")
            return
            
        try:
            # Ses verisini gönder
            await self._websocket.send(audio)
            logger.debug(f"Sent {len(audio)} bytes to Vosk")
            
            # Yanıt bekle (non-blocking)
            try:
                response = await asyncio.wait_for(
                    self._websocket.recv(), 
                    timeout=0.1  # Kısa timeout
                )
                
                # JSON yanıtını parse et
                if isinstance(response, str):
                    result = json.loads(response)
                    await self._process_vosk_response(result)
                else:
                    logger.warning(f"Unexpected response type: {type(response)}")
                
            except asyncio.TimeoutError:
                # Timeout normal - Vosk her zaman hemen yanıt vermez
                pass
            except json.JSONDecodeError as e:
                logger.warning("Invalid JSON from Vosk", response=response, error=str(e))
                
        except Exception as e:
            logger.error("Error in Vosk STT processing", error=str(e))
    
    async def _process_vosk_response(self, result: Dict[str, Any]) -> None:
        """Vosk yanıtını işle ve frame'leri emit et"""
        
        # Partial (ara) sonuç
        if "partial" in result and result["partial"]:
            partial_text = result["partial"].strip()
            if partial_text:
                logger.debug("Vosk partial result", text=partial_text)
                frame = InterimTranscriptionFrame(
                    text=partial_text,
                    user_id="user",
                    timestamp=self.get_current_time()
                )
                await self.push_frame(frame)
        
        # Final (kesin) sonuç
        if "text" in result and result["text"]:
            final_text = result["text"].strip()
            if final_text:
                logger.info("Vosk final result", text=final_text)
                frame = TranscriptionFrame(
                    text=final_text,
                    user_id="user",
                    timestamp=self.get_current_time()
                )
                await self.push_frame(frame)
    
    async def process_audio_chunk(self, audio_chunk: bytes) -> Optional[str]:
        """Test için: ses chunk'ını işle ve sonuç döndür"""
        if not self._is_connected or not self._websocket:
            await self.start()
        
        try:
            # Ses verisini gönder
            await self._websocket.send(audio_chunk)
            
            # Yanıt bekle
            response = await asyncio.wait_for(
                self._websocket.recv(), 
                timeout=1.0
            )
            
            result = json.loads(response)
            
            # Partial veya text sonucunu döndür
            if "text" in result and result["text"]:
                return result["text"].strip()
            elif "partial" in result and result["partial"]:
                return f"[partial] {result['partial'].strip()}"
            
            return None
            
        except asyncio.TimeoutError:
            return None
        except Exception as e:
            logger.error("Error processing audio chunk", error=str(e))
            return None
    
    async def finalize(self) -> Optional[str]:
        """Final sonucu al"""
        if not self._is_connected or not self._websocket:
            return None
        
        try:
            # EOS gönder
            await self._websocket.send('{"eof": 1}')
            
            # Final yanıt bekle
            response = await asyncio.wait_for(
                self._websocket.recv(), 
                timeout=2.0
            )
            
            result = json.loads(response)
            
            if "text" in result and result["text"]:
                return result["text"].strip()
            
            return None
            
        except Exception as e:
            logger.error("Error finalizing STT", error=str(e))
            return None
    
    def get_current_time(self) -> str:
        """Şu anki zamanı string olarak döndür"""
        import time
        return str(int(time.time() * 1000)) 