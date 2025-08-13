"""
Vosk WebSocket STT Service - Following Pipecat Implementations Document
Simplified implementation aligned with document specifications
"""

import asyncio
import json
import websockets
from typing import AsyncGenerator, Optional
import structlog
import numpy as np

from voice_ai_core.frames import (
    Frame, AudioRawFrame, EndFrame, ErrorFrame, 
    InterimTranscriptionFrame, StartFrame, TranscriptionFrame,
    UserStartedSpeakingFrame, UserStoppedSpeakingFrame,
    VADUserStartedSpeakingFrame, VADUserStoppedSpeakingFrame
)
from voice_ai_core.services import STTService
from voice_ai_core.processors import FrameDirection

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
        chunk_ms: int = 300,
        silence_timeout_ms: int = 1000,
        **kwargs
    ):
        super().__init__(**kwargs)
        self._url = url
        
        # 🔧 CRITICAL FIX: Sample rate validation based on docs/VOSK.md
        if sample_rate not in [8000, 16000, 22050, 44100, 48000]:
            logger.warning("Unusual sample rate for Vosk STT",
                          sample_rate=sample_rate,
                          recommended_rates=[8000, 16000, 22050, 44100, 48000])
        
        if sample_rate < 8000:
            raise ValueError(f"Sample rate {sample_rate} too low for Vosk STT (minimum: 8000)")
        
        self._sample_rate = sample_rate
        self._websocket: Optional = None
        self._listener_task: Optional[asyncio.Task] = None
        self._is_connected = False
        
        # Buffering settings
        self._chunk_ms = chunk_ms
        self._chunk_bytes = int(self._sample_rate * 2 * (self._chunk_ms / 1000.0))  # 16-bit PCM
        self._audio_buffer = bytearray()
        
        # Silence detection
        self._silence_timeout_ms = silence_timeout_ms
        self._silence_task: Optional[asyncio.Task] = None
        
        logger.info("VoskSTTService initialized", 
                   url=url, 
                   sample_rate=sample_rate,
                   pattern="document_compliant",
                   validation_passed=True)

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        """Process frames following document pattern"""
        await super().process_frame(frame, direction)

        if isinstance(frame, StartFrame):
            await self._start_websocket_connection()
        elif isinstance(frame, AudioRawFrame):
            # Buffer audio until we reach chunk size
            self._audio_buffer.extend(frame.audio)
            if len(self._audio_buffer) >= self._chunk_bytes:
                await self._send_audio(bytes(self._audio_buffer))
                self._audio_buffer.clear()
            # Audio received, cancel silence timer if running
            if self._silence_task and not self._silence_task.done():
                self._silence_task.cancel()
        elif isinstance(frame, EndFrame):
            # Flush remaining buffered audio before closing
            if self._audio_buffer:
                await self._send_audio(bytes(self._audio_buffer))
                self._audio_buffer.clear()
            await self._stop_websocket_connection()
            await self.push_frame(frame)
        else:
            # 🔧 DEBUG: Log VAD-related frames to track speech detection
            if isinstance(frame, UserStartedSpeakingFrame):
                logger.info("🎤 USER STARTED SPEAKING detected by VAD!", 
                           emulated=getattr(frame, 'emulated', False))
                # Cancel silence timer when user starts speaking again
                if self._silence_task and not self._silence_task.done():
                    self._silence_task.cancel()
            elif isinstance(frame, UserStoppedSpeakingFrame):
                logger.info("🔇 USER STOPPED SPEAKING detected by VAD!", 
                           emulated=getattr(frame, 'emulated', False))
                # Start silence timer – if no further audio within timeout, flush / send EOF
                if self._silence_timeout_ms > 0:
                    if self._silence_task and not self._silence_task.done():
                        self._silence_task.cancel()
                    self._silence_task = asyncio.create_task(self._on_silence_timeout())
            elif isinstance(frame, VADUserStartedSpeakingFrame):
                logger.debug("🎯 VAD raw started speaking frame")
                if self._silence_task and not self._silence_task.done():
                    self._silence_task.cancel()
            elif isinstance(frame, VADUserStoppedSpeakingFrame):
                logger.debug("🎯 VAD raw stopped speaking frame")
                if self._silence_timeout_ms > 0:
                    if self._silence_task and not self._silence_task.done():
                        self._silence_task.cancel()
                    self._silence_task = asyncio.create_task(self._on_silence_timeout())
            
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
                # 🔧 CRITICAL FIX: Enhanced config validation based on docs/VOSK.md
                config_message = {
                    "config": {
                        "sample_rate": 16000,
                        "num_channels": 1
                    }
                }
                
                logger.info("Sending Vosk configuration", 
                           config=config_message,
                           sample_rate=self._sample_rate,
                           expected_sample_rate=16000,
                           note="Vosk STT requires 16kHz for optimal Turkish recognition")
                           
                await self._websocket.send(json.dumps(config_message))
                
                # Wait a moment for configuration acknowledgment
                await asyncio.sleep(0.1)

                # Listen for transcriptions (document pattern)
                async for message in self._websocket:
                    if not self._is_connected:
                        break
                        
                    # 🔧 DEBUG: Log ALL raw messages from Vosk for debugging
                    logger.debug("🎯 RAW Vosk response received", 
                               message=message[:200] if len(message) > 200 else message,
                               message_length=len(message))
                        
                    try:
                        data = json.loads(message)
                        
                        # 🔧 DEBUG: Log parsed JSON structure
                        logger.debug("🎯 Parsed Vosk JSON", 
                                   keys=list(data.keys()),
                                   data_structure=data)
                        
                        # Handle final transcription
                        if data.get("text"):
                            text = data["text"].strip()
                            if text:  # Only process non-empty results
                                logger.info("🎉 Vosk final transcription", text=text)
                                await self.push_frame(
                                    TranscriptionFrame(
                                        text=text, 
                                        user_id="", 
                                        timestamp=""
                                    )
                                )
                            else:
                                logger.debug("🔍 Vosk sent empty final text")
                        
                        # Handle partial transcription
                        elif data.get("partial"):
                            partial_text = data["partial"].strip()
                            if partial_text:  # Only process non-empty partials
                                logger.debug("🔄 Vosk partial transcription", partial=partial_text)
                                await self.push_frame(
                                    InterimTranscriptionFrame(
                                        text=partial_text, 
                                        user_id="", 
                                        timestamp=""
                                    )
                                )
                            else:
                                logger.debug("🔍 Vosk sent empty partial text")
                        
                        # Handle configuration acknowledgment
                        elif "status" in data:
                            logger.info("⚙️ Vosk configuration status", status=data)
                        
                        # Handle any other response types for debugging    
                        else:
                            #TODO: handle this
                            logger.debug("🤔 Unknown Vosk response format", 
                                       data=data,
                                       available_keys=list(data.keys()))
                            
                    except json.JSONDecodeError as e:
                        logger.error("❌ Invalid JSON from Vosk", 
                                   error=str(e), 
                                   raw_message=message[:100])
                    except Exception as e:
                        logger.error("❌ Error processing Vosk message", error=str(e))
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
        """Send audio data to Vosk following document pattern with format validation"""
        if not self._websocket or not self._is_connected:
            logger.warning("No active Vosk WebSocket connection for audio")
            return
            
        try:
            # 🔧 CRITICAL FIX: Audio format validation based on docs/VOSK.md
            
            # Ensure audio data is in bytes format
            if not isinstance(audio, bytes):
                logger.error("Audio data must be bytes format for Vosk", 
                           actual_type=type(audio).__name__)
                return
            
            # Validate audio data size (should be reasonable for 16kHz PCM)
            if len(audio) == 0:
                logger.warning("Empty audio data, skipping")
                return
                
            # Log audio data info for debugging
            if len(audio) % 2 != 0:
                logger.warning("Audio data length is not even - potential 16-bit PCM issue",audio_length=len(audio))
            
            # Debug audio data characteristics
            audio_array = np.frombuffer(audio, dtype=np.int16)
            audio_rms = np.sqrt(np.mean(audio_array.astype(np.float32) ** 2))
            audio_max = np.max(np.abs(audio_array))
            
            logger.debug("🎵 Sending audio to Vosk", 
                       audio_size=len(audio),
                       samples=len(audio_array),
                       rms=f"{audio_rms:.2f}",
                       max_amplitude=audio_max,
                       sample_rate=self._sample_rate,
                       audio_hex=audio[:20].hex())
           
            # Send audio to Vosk WebSocket
            await self._websocket.send(audio)
            logger.debug("✅ Audio sent to Vosk successfully", size=len(audio))
            
        except Exception as e:
            logger.error("Error sending audio to Vosk", error=str(e))
            # Don't re-raise to avoid breaking the pipeline

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

    async def _on_silence_timeout(self):
        """Wait for configured silence timeout then send EOF to Vosk to trigger final transcription."""
        try:
            await asyncio.sleep(self._silence_timeout_ms / 1000.0)
            if self._audio_buffer:
                await self._send_audio(bytes(self._audio_buffer))
                self._audio_buffer.clear()
            if self._websocket and self._is_connected:
                logger.info("🔕 Silence timeout reached – sending EOF to Vosk")
                await self._websocket.send('{"eof": 1}')
        except asyncio.CancelledError:
            pass 