"""
Vosk WebSocket STT Service - Following Pipecat Implementations Document
Simplified implementation aligned with document specifications
"""

import asyncio
import json
import websockets
from typing import AsyncGenerator, Optional
import structlog

from pipecat.frames.frames import (
    Frame, AudioRawFrame, EndFrame, ErrorFrame, 
    InterimTranscriptionFrame, StartFrame, TranscriptionFrame
)
from pipecat.services.stt_service import STTService
from pipecat.processors.frame_processor import FrameDirection

logger = structlog.get_logger()


class VoskWebsocketSTTService(STTService):
    """
    Vosk STT service following document specifications
    Streams audio → text via WebSocket as per implementation guide
    """
    
    def __init__(
        self,
        url: str,
        sample_rate: int = 16000,
        **kwargs
    ):
        super().__init__(**kwargs)
        self._url = url
        self._sample_rate = sample_rate
        self._websocket: Optional = None
        self._listener_task: Optional[asyncio.Task] = None
        self._is_connected = False
        
        logger.info("VoskSTTService initialized", 
                   url=url, 
                   sample_rate=sample_rate,
                   pattern="document_compliant")

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        """Process frames following document pattern"""
        await super().process_frame(frame, direction)

        if isinstance(frame, StartFrame):
            await self._start_websocket_connection()
        elif isinstance(frame, AudioRawFrame):
            await self._send_audio(frame.audio)
        elif isinstance(frame, EndFrame):
            await self._stop_websocket_connection()
            await self.push_frame(frame)
        else:
            await self.push_frame(frame, direction)

    async def _start_websocket_connection(self):
        """Start WebSocket connection and listener following document pattern"""
        if not self._listener_task:
            self._listener_task = asyncio.create_task(self._websocket_listener())
            logger.info("Vosk WebSocket listener started", pattern="document_compliant")

    async def _websocket_listener(self):
        """WebSocket listener following document specifications"""
        try:
            async with websockets.connect(self._url) as websocket:
                self._websocket = websocket
                self._is_connected = True
                
                logger.info("Vosk WebSocket connected", url=self._url)
                
                # Send initial configuration as per document
                config = {"config": {"sample_rate": self._sample_rate}}
                await self._websocket.send(json.dumps(config))

                # Listen for transcriptions (document pattern)
                async for message in self._websocket:
                    if not self._is_connected:
                        break
                        
                    try:
                        data = json.loads(message)
                        
                        # Handle final transcription
                        if data.get("text"):
                            await self.push_frame(
                                TranscriptionFrame(
                                    text=data["text"], 
                                    user_id="", 
                                    timestamp=""
                                )
                            )
                        
                        # Handle partial transcription
                        elif data.get("partial"):
                            await self.push_frame(
                                InterimTranscriptionFrame(
                                    text=data["partial"], 
                                    user_id="", 
                                    timestamp=""
                                )
                            )
                            
                    except json.JSONDecodeError as e:
                        logger.error("Invalid JSON from Vosk", error=str(e))
                    except Exception as e:
                        logger.error("Error processing Vosk message", error=str(e))
                        await self.push_frame(ErrorFrame(error=f"Vosk processing error: {e}"))

        except websockets.exceptions.ConnectionClosed:
            logger.info("Vosk WebSocket connection closed")
        except Exception as e:
            logger.error("Vosk WebSocket connection failed", error=str(e))
            await self.push_frame(ErrorFrame(error=f"Vosk connection failed: {e}"))
        finally:
            self._websocket = None
            self._is_connected = False

    async def _send_audio(self, audio: bytes):
        """Send audio data to Vosk following document pattern"""
        if self._websocket and self._is_connected:
            try:
                await self._websocket.send(audio)
            except Exception as e:
                logger.error("Error sending audio to Vosk", error=str(e))
        else:
            logger.warning("No active Vosk WebSocket connection for audio")

    async def _stop_websocket_connection(self):
        """Stop WebSocket connection following document pattern"""
        if self._websocket and self._is_connected:
            try:
                # Send EOF message as per document
                await self._websocket.send('{"eof": 1}')
                logger.info("Sent EOF to Vosk")
            except Exception as e:
                logger.error("Error sending EOF to Vosk", error=str(e))
        
        self._is_connected = False
        
        if self._listener_task:
            self._listener_task.cancel()
            try:
                await self._listener_task
            except asyncio.CancelledError:
                pass
            self._listener_task = None

    async def run_stt(self, audio: bytes) -> AsyncGenerator[Frame, None]:
        """
        Legacy compatibility method - not used in processor-based model
        Following document pattern for service compatibility
        """
        # Empty generator as per document guidance
        return
        yield  # Unreachable, just for generator syntax

    async def process_audio_chunk(self, audio_chunk: bytes) -> Optional[str]:
        """Test için: ses chunk'ını işle ve sonuç döndür"""
        if not self._is_connected or not self._websocket:
            await self._websocket_listener()
        
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