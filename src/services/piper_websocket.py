"""
Piper WebSocket TTS Service - Following Pipecat Implementations Document
Simplified implementation aligned with document specifications
"""

import asyncio
import json
import websockets
from typing import AsyncGenerator, Optional, AsyncIterator
import structlog

from voice_ai_core.frames import (
    Frame, AudioFrame, TextFrame, EndFrame, ErrorFrame, StartFrame,
    TTSAudioRawFrame, TTSStartedFrame, TTSStoppedFrame
)
from voice_ai_core.services import TTSService
from voice_ai_core.processors import FrameDirection

logger = structlog.get_logger()


class PiperWebsocketTTSService(TTSService):
    """
    Piper TTS service following document specifications
    Streams text → 22.05 kHz PCM audio as per implementation guide
    """
    
    def __init__(
        self,
        url: str,
        voice: str = "tr_TR-dfki-medium",
        sample_rate: int = 22050,
        **kwargs
    ):
        super().__init__(**kwargs)
        self._url = url
        self._voice = voice
        self.sample_rate = sample_rate
        self._websocket: Optional = None
        self._listener_task: Optional[asyncio.Task] = None
        self._is_connected = False
        
        logger.info("PiperTTSService initialized",
                   url=url,
                   voice=voice,
                   sample_rate=sample_rate,
                   pattern="document_compliant")

    async def start(self, frame: StartFrame = None):
        """Start the TTS service and WebSocket connection"""
        await super().start()
        await self._start_websocket_connection()

    async def stop(self, frame: EndFrame = None):
        """Stop the TTS service and WebSocket connection"""
        await self._stop_websocket_connection()
        await super().stop()

    async def cancel(self, frame: EndFrame = None):
        """Cancel the TTS service and WebSocket connection"""
        await self._stop_websocket_connection()
        # Note: FrameProcessor doesn't have a cancel method, so we just stop
        await super().stop()

    async def run_tts(self, text: str) -> AsyncGenerator[Frame, None]:
        """
        Main TTS method - converts text to audio frames
        This is called by the TTSService base class when processing text
        """
        if not self._websocket or not self._is_connected:
            logger.warning("No active Piper WebSocket connection for TTS")
            return
        
        if not text or not text.strip():
            logger.debug("Empty text provided for synthesis")
            return
        
        try:
            # Create TTS request following document pattern
            request = {
                "text": text.strip(),
                "voice": self._voice,
                "sample_rate": self.sample_rate,
                "format": "pcm16"  # Document specifies PCM output
            }
            
            # Send synthesis request
            await self._websocket.send(json.dumps(request))
            logger.debug("Sent text to Piper TTS", text_length=len(text))
            
            # Audio frames will be yielded by the WebSocket listener
            # We don't yield anything else here as the listener handles the audio frames
            
        except Exception as e:
            logger.error("Error sending text to Piper", error=str(e))
            yield ErrorFrame(error=f"Piper synthesis error: {e}")

    async def synthesize(self, text: str) -> AsyncIterator[AudioFrame]:
        """
        Required abstract method implementation for TTSService
        Synthesize text to audio - processes via WebSocket
        """
        # This method is required by the base class but our implementation
        # works through run_tts method which handles the actual synthesis
        # For compatibility, we'll delegate to run_tts and filter for audio frames
        async for frame in self.run_tts(text):
            if isinstance(frame, TTSAudioRawFrame):
                yield frame

    async def say(self, text: str):
        """
        Compatibility method for Pipecat-style TTS usage
        Queue text for synthesis and push frames to pipeline
        """
        if not text or not text.strip():
            logger.debug("Empty text provided to say method")
            return
        
        logger.info("📢 TTS say() called", text_preview=text[:50])
        
        # Process the text through run_tts and push frames to pipeline
        async for frame in self.run_tts(text):
            await self.push_frame(frame)

    async def _start_websocket_connection(self):
        """Start WebSocket connection following document pattern"""
        if not self._listener_task:
            self._listener_task = asyncio.create_task(self._websocket_listener())
            logger.info("Piper WebSocket listener started", pattern="document_compliant")

    async def _websocket_listener(self):
        """WebSocket listener following document specifications"""
        try:
            async with websockets.connect(self._url) as websocket:
                self._websocket = websocket
                self._is_connected = True
                
                logger.info("Piper WebSocket connected", url=self._url)

                # Listen for TTS audio responses (document pattern)
                async for message in self._websocket:
                    if not self._is_connected:
                        break
                        
                    try:
                        # Handle binary audio data
                        if isinstance(message, bytes):
                            # Create output audio frame as per document (22.05 kHz PCM)
                            audio_frame = TTSAudioRawFrame(
                                audio=message,
                                sample_rate=self.sample_rate,
                                num_channels=1
                            )
                            await self.push_frame(audio_frame)
                        
                        # Handle JSON status messages
                        elif isinstance(message, str):
                            try:
                                data = json.loads(message)
                                
                                status = data.get("status") or data.get("type")
                                if status in ("started", "start"):
                                    await self.push_frame(TTSStartedFrame())
                                elif status in ("completed", "end"):
                                    await self.push_frame(TTSStoppedFrame())
                                elif data.get("error"):
                                    await self.push_frame(ErrorFrame(error=f"Piper TTS error: {data['error']}"))
                                    
                            except json.JSONDecodeError:
                                # Not JSON, treat as raw text if needed
                                pass
                            
                    except Exception as e:
                        logger.error("Error processing Piper message", error=str(e))
                        await self.push_frame(ErrorFrame(error=f"Piper processing error: {e}"))

        except websockets.exceptions.ConnectionClosed:
            logger.info("Piper WebSocket connection closed")
        except Exception as e:
            logger.error("Piper WebSocket connection failed", error=str(e))
            await self.push_frame(ErrorFrame(error=f"Piper connection failed: {e}"))
        finally:
            self._websocket = None
            self._is_connected = False

    async def _stop_websocket_connection(self):
        """Stop WebSocket connection following document pattern"""
        self._is_connected = False
        
        if self._listener_task:
            self._listener_task.cancel()
            try:
                await self._listener_task
            except asyncio.CancelledError:
                pass
            self._listener_task = None 