"""
Piper WebSocket TTS Service
"""

import asyncio
import json
import logging
from typing import Optional, AsyncGenerator
import websockets
import structlog
import audioop

from pipecat.frames.frames import (
    Frame,
    TTSAudioRawFrame,
    TTSStartedFrame,
    TTSStoppedFrame,
)
from pipecat.services.ai_services import TTSService

logger = structlog.get_logger()

class PiperWebsocketTTSService(TTSService):
    """Piper WebSocket tabanlı TTS servisi"""
    
    def __init__(
        self, 
        url: str = "ws://localhost:8000/tts",
        sample_rate: int = 22050,
        target_sample_rate: int = 8000,
        **kwargs
    ):
        super().__init__(**kwargs)
        self._url = url
        self._sample_rate = sample_rate
        self._target_sample_rate = target_sample_rate
        self._websocket: Optional[websockets.WebSocketClientProtocol] = None
        self._connection_lock = asyncio.Lock()
        self._is_connected = False
        self._task: Optional[asyncio.Task] = None
        
        logger.info("PiperWebsocketTTSService initialized", 
                   url=self._url, 
                   sample_rate=self._sample_rate,
                   target_sample_rate=self._target_sample_rate)
    
    async def start(self) -> None:
        """WebSocket bağlantısını başlat"""
        async with self._connection_lock:
            if self._is_connected:
                return
                
            try:
                logger.info("Connecting to Piper TTS WebSocket", url=self._url)
                self._websocket = await websockets.connect(self._url)
                
                # Welcome mesajını bekle
                welcome = await self._websocket.recv()
                welcome_data = json.loads(welcome)
                logger.info("Piper TTS connected", message=welcome_data)
                
                self._is_connected = True
                logger.info("Piper TTS WebSocket connected successfully")
                
            except Exception as e:
                logger.error("Failed to connect to Piper TTS WebSocket", error=str(e))
                raise
    
    async def stop(self) -> None:
        """WebSocket bağlantısını kapat"""
        async with self._connection_lock:
            if not self._is_connected:
                return
                
            try:
                if self._websocket:
                    await self._websocket.close()
                    logger.info("Piper TTS WebSocket connection closed")
                    
            except Exception as e:
                logger.warning("Error closing Piper TTS WebSocket", error=str(e))
            finally:
                self._websocket = None
                self._is_connected = False
    
    async def run_tts(self, text: str) -> AsyncGenerator[Frame, None]:
        """TTS işlemini çalıştır ve audio frame'leri üret"""
        if not self._is_connected or not self._websocket:
            logger.warning("Piper TTS WebSocket not connected, skipping TTS")
            return
            
        try:
            logger.info("Starting TTS synthesis", text=text[:50] + "..." if len(text) > 50 else text)
            
            # TTS başladı frame'ini emit et
            yield TTSStartedFrame()
            
            # TTS isteğini gönder
            await self._websocket.send(text)
            logger.debug("TTS request sent")
            
            # Audio chunk'larını al
            async for message in self._websocket:
                try:
                    # JSON mesaj mı kontrol et
                    if isinstance(message, str):
                        data = json.loads(message)
                        message_type = data.get("type")
                        
                        if message_type == "start":
                            logger.debug("TTS audio stream started")
                            continue
                        elif message_type == "end":
                            logger.debug("TTS audio stream ended")
                            break
                        elif message_type == "error":
                            logger.error("TTS error", message=data.get("message"))
                            break
                        else:
                            logger.debug("TTS message", type=message_type, data=data)
                            continue
                    
                    # Binary audio data
                    elif isinstance(message, bytes):
                        if len(message) > 0:
                            logger.debug("Received audio chunk", size=len(message))
                            
                            # Ham ses verisini işle
                            # Piper'dan gelen ses 22050Hz, mono, 16-bit PCM.
                            # Bunu 8000Hz'e düşürmemiz gerekiyor.
                            resampled_audio = audioop.ratecv(message, 2, 1, self._sample_rate, self._target_sample_rate, None)[0]
                            
                            # PCMU (ulaw) formatına dönüştür
                            ulaw_audio = audioop.lin2ulaw(resampled_audio, 2)

                            # Audio frame oluştur
                            audio_frame = TTSAudioRawFrame(
                                audio=ulaw_audio, 
                                sample_rate=self._target_sample_rate,
                                num_channels=1
                            )
                            
                            yield audio_frame
                        
                except json.JSONDecodeError:
                    # Binary data olarak treat et
                    if isinstance(message, bytes) and len(message) > 0:
                        logger.debug("Received binary audio chunk", size=len(message))
                        
                        audio_frame = TTSAudioRawFrame(
                            audio=message,
                            sample_rate=self._sample_rate,
                            num_channels=1
                        )
                        
                        yield audio_frame
                        
                except Exception as e:
                    logger.error("Error processing TTS response", error=str(e))
                    break
            
            # TTS bitti frame'ini emit et
            yield TTSStoppedFrame()
            logger.info("TTS synthesis completed")
                
        except Exception as e:
            logger.error("Error in TTS processing", error=str(e))
    
    async def synthesize_text(self, text: str) -> bytes:
        """Test için: metni sese çevir ve tüm audio'yu döndür"""
        if not self._is_connected or not self._websocket:
            await self.start()
        
        try:
            # TTS isteğini gönder
            await self._websocket.send(text)
            
            audio_data = b''
            
            # Audio chunk'larını topla
            async for message in self._websocket:
                try:
                    if isinstance(message, str):
                        data = json.loads(message)
                        message_type = data.get("type")
                        
                        if message_type == "end":
                            break
                        elif message_type == "error":
                            logger.error("TTS synthesis error", message=data.get("message"))
                            return b''
                        
                    elif isinstance(message, bytes):
                        audio_data += message
                        
                except json.JSONDecodeError:
                    if isinstance(message, bytes):
                        audio_data += message
            
            logger.info("TTS synthesis completed", audio_size=len(audio_data))
            return audio_data
            
        except Exception as e:
            logger.error("Error synthesizing text", error=str(e))
            return b''
    
    def get_current_time(self) -> str:
        """Şu anki zamanı string olarak döndür"""
        import time
        return str(int(time.time() * 1000)) 

    def can_generate_audio(self) -> bool:
        return True 