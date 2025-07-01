"""
Vosk WebSocket STT Service - Pipecat Native Uyumlu Versiyon
"""

import asyncio
import json
import logging
import websockets
from typing import AsyncGenerator, Optional, Dict, Any
import structlog

from pipecat.frames.frames import (
    Frame,
    AudioRawFrame,
    EndFrame,
    ErrorFrame,
    InterimTranscriptionFrame,
    StartFrame,
    SystemFrame,
    TranscriptionFrame,
    TextFrame,
)
from pipecat.services.stt_service import STTService
from pipecat.processors.frame_processor import FrameDirection

from loguru import logger

class VoskWebsocketSTTService(STTService):
    """
    Vosk STT service that uses a WebSocket connection.
    This service connects to a Vosk server, sends audio data,
    and pushes TranscriptionFrames back into the pipeline.
    """
    def __init__(
            self,
            url: str,
            sample_rate: int = 16000,
            **kwargs):
        super().__init__(**kwargs)
        self._url = url
        self._sample_rate = sample_rate
        self._websocket = None
        self._listener_task = None

    async def _listener(self):
        logger.info(f"Connecting to Vosk WebSocket at {self._url}")
        try:
            async with websockets.connect(self._url) as websocket:
                self._websocket = websocket
                logger.info("Vosk WebSocket connected")
                
                # Send config to Vosk server
                config = {"config": {"sample_rate": self._sample_rate}}
                await self._websocket.send(json.dumps(config))

                # Listen for transcriptions until the connection is closed
                while True:
                    try:
                        message = await self._websocket.recv()
                        data = json.loads(message)

                        if data.get("text"):
                            await self.push_frame(TranscriptionFrame(text=data["text"], user_id="", timestamp=""))
                        elif data.get("partial"):
                             await self.push_frame(InterimTranscriptionFrame(text=data["partial"], user_id="", timestamp=""))

                    except websockets.exceptions.ConnectionClosed:
                        logger.warning("Vosk WebSocket connection closed.")
                        break
                    except Exception as e:
                        logger.error(f"Error in Vosk listener: {e}")
                        await self.push_frame(ErrorFrame(error=f"Vosk error: {e}"))
                        break
        except Exception as e:
            logger.error(f"Failed to connect to Vosk WebSocket: {e}")
            await self.push_frame(ErrorFrame(error=f"Vosk connection failed: {e}"))
        finally:
            self._websocket = None
            logger.info("Vosk WebSocket disconnected.")

    async def _process_frame(self, frame: Frame, direction: FrameDirection):
        await super()._process_frame(frame, direction)

        if isinstance(frame, StartFrame):
            # Start listening for transcriptions
            if not self._listener_task:
                self._listener_task = self.create_task(self._listener())
        
        elif isinstance(frame, AudioRawFrame):
            if self._websocket:
                try:
                    await self._websocket.send(frame.audio)
                except Exception as e:
                    logger.error(f"Error sending audio data to Vosk: {e}")
            else:
                # This can happen if audio arrives before the websocket is connected.
                # You might want to buffer it, but for now, we'll log a warning.
                logger.warning("No active Vosk websocket to send audio to. Frame might be lost.")
        
        elif isinstance(frame, EndFrame):
            # Send EOF message if websocket is still open
            if self._websocket:
                try:
                    await self._websocket.send('{"eof" : 1}')
                    logger.info("Sent EOF to Vosk")
                except Exception as e:
                    logger.error(f"Error sending EOF to Vosk: {e}")
            
            # Stop the listener task
            if self._listener_task:
                await self.cancel_task(self._listener_task)
                self._listener_task = None
            
            # Forward the EndFrame to signal pipeline completion
            await self.push_frame(frame)
        else:
            # Forward other frames like UserStartedSpeaking, etc.
            await self.push_frame(frame, direction)

    def run_stt(self, frame_iterator: AsyncGenerator[Frame, None]) -> AsyncGenerator[Frame, None]:
        # This method is not used in the processor-based service model.
        # All logic is handled by _process_frame and _listener.
        logger.warning("run_stt is deprecated for this service implementation.")
        pass

    async def process_audio_chunk(self, audio_chunk: bytes) -> Optional[str]:
        """Test için: ses chunk'ını işle ve sonuç döndür"""
        if not self._is_connected or not self._websocket:
            await self._listener()
        
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