"""
Piper WebSocket TTS Service - Pipecat Native Uyumlu
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
    AudioRawFrame,
    TTSStartedFrame,
    TTSStoppedFrame,
    TextFrame,
    SystemFrame
)
from pipecat.services.tts_service import TTSService
from pipecat.processors.frame_processor import Frame, FrameDirection


logger = structlog.get_logger()

class PiperWebsocketTTSService(TTSService):
    """Piper WebSocket tabanlı TTS servisi, Pipecat ile tam uyumlu."""
    
    def __init__(
        self, 
        url: str,
        sample_rate: int = 22050,  # Piper's output sample rate
        target_sample_rate: int = 8000, # PSTN sample rate
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
                   source_sample_rate=self._sample_rate,
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
    
    async def run_tts(self, frame_iterator: AsyncGenerator[Frame, None]) -> AsyncGenerator[Frame, None]:
        """
        TTS işlemini çalıştırır, metin frame'lerini alır ve audio frame'leri üretir.
        """
        websocket = None
        try:
            async for frame in frame_iterator:
                if not isinstance(frame, TextFrame):
                    yield frame
                    continue
                
                text = frame.text.strip()
                if not text:
                    continue

                logger.info(f"Synthesizing text: {text}")
                yield TTSStartedFrame(text=text)

                try:
                    websocket = await websockets.connect(self._url)
                    
                    # Wait for welcome message (optional but good practice)
                    welcome = await asyncio.wait_for(websocket.recv(), timeout=5)
                    logger.debug(f"Piper welcome: {welcome}")

                    # Send text to synthesize
                    await websocket.send(text)

                    # Receive audio chunks
                    async for message in websocket:
                        if isinstance(message, bytes) and len(message) > 0:
                            # Piper default output: 22050Hz, 16-bit PCM mono
                            # Resample to 8000Hz for PSTN
                            resampled_audio, _ = audioop.ratecv(message, 2, 1, self._sample_rate, self._target_sample_rate, None)
                            
                            # Convert to PCMU (u-law) for PSTN
                            ulaw_audio = audioop.lin2ulaw(resampled_audio, 2)
                            
                            yield AudioRawFrame(audio=ulaw_audio, sample_rate=self._target_sample_rate)
                        elif isinstance(message, str):
                            # Handle potential JSON messages like 'end' or 'error'
                            try:
                                data = json.loads(message)
                                if data.get("type") == "end":
                                    logger.debug("TTS stream ended by server message.")
                                    break
                                elif data.get("type") == "error":
                                    logger.error(f"Piper TTS error: {data.get('message')}")
                                    break
                            except json.JSONDecodeError:
                                logger.warning(f"Received non-JSON text message from Piper: {message}")

                except websockets.exceptions.ConnectionClosed:
                    logger.info("Piper connection closed, assuming TTS for this text is complete.")
                except Exception as e:
                    logger.error(f"Error during Piper TTS synthesis for '{text}': {e}", exc_info=True)
                finally:
                    if websocket and not websocket.closed:
                        await websocket.close()
                    
                    yield TTSStoppedFrame(text=text)
                    logger.info(f"Finished synthesizing text: {text}")

        except Exception as e:
            logger.error(f"Error in Piper TTS service run_tts loop: {e}", exc_info=True)
        finally:
             logger.info("Piper TTS service stopped.")
    
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