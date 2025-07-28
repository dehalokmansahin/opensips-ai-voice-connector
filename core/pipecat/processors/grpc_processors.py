"""
gRPC Service Integration Processors for Pipecat Pipeline
Bridges native pipecat framework with microservices
"""

import asyncio
import logging
from typing import Optional, Callable, Any, Dict
from ..pipeline.pipeline import FrameProcessor, AsyncFrameProcessor, AudioFrameProcessor, TextFrameProcessor
from ..frames.frames import Frame, AudioFrame, TextFrame, ErrorFrame, StartFrame, EndFrame
from ...grpc_clients import ASRClient, TTSClient, IntentClient

logger = logging.getLogger(__name__)

class ASRProcessor(AudioFrameProcessor):
    """ASR processor using gRPC ASR service"""
    
    def __init__(
        self,
        asr_client: ASRClient,
        on_transcript: Optional[Callable[[str], None]] = None,
        config: Optional[Dict[str, Any]] = None,
        name: str = "ASRProcessor"
    ):
        super().__init__(sample_rate=16000, name=name)
        self.asr_client = asr_client
        self.on_transcript = on_transcript
        self.config = config or {}
        self.streaming_session = None
        self._accumulator = bytearray()
        
    async def process_frame(self, frame: Frame) -> Optional[Frame]:
        """Process audio frames through ASR"""
        try:
            if isinstance(frame, StartFrame):
                await self._start_asr_session()
                return frame
                
            elif isinstance(frame, EndFrame):
                await self._stop_asr_session()
                return frame
                
            elif isinstance(frame, AudioFrame):
                if self.streaming_session:
                    # Accumulate audio for processing
                    self._accumulator.extend(frame.audio)
                    
                    # Process in chunks (e.g., 20ms frames)
                    chunk_size = (self.sample_rate * 20) // 1000  # 20ms chunks
                    while len(self._accumulator) >= chunk_size:
                        chunk = bytes(self._accumulator[:chunk_size])
                        self._accumulator = self._accumulator[chunk_size:]
                        
                        await self.streaming_session.add_audio(chunk)
                
                return frame
                
            else:
                return frame
                
        except Exception as e:
            logger.error(f"ASR processor error: {e}")
            return ErrorFrame(error=str(e))
    
    async def _start_asr_session(self):
        """Start ASR streaming session"""
        try:
            self.streaming_session = await self.asr_client.start_streaming_session(
                on_transcript=self._on_partial_transcript,
                on_final=self._on_final_transcript,
                config=self.config
            )
            await self.streaming_session.start()
            logger.info(f"ASR session started: {self.name}")
            
        except Exception as e:
            logger.error(f"Failed to start ASR session: {e}")
            raise
    
    async def _stop_asr_session(self):
        """Stop ASR streaming session"""
        try:
            if self.streaming_session:
                await self.streaming_session.stop()
                self.streaming_session = None
                logger.info(f"ASR session stopped: {self.name}")
                
        except Exception as e:
            logger.error(f"Error stopping ASR session: {e}")
    
    async def _on_partial_transcript(self, transcript: str):
        """Handle partial transcript"""
        try:
            logger.debug(f"Partial transcript: {transcript}")
            if self.on_transcript:
                if asyncio.iscoroutinefunction(self.on_transcript):
                    await self.on_transcript(transcript)
                else:
                    self.on_transcript(transcript)
                    
        except Exception as e:
            logger.error(f"Error handling partial transcript: {e}")
    
    async def _on_final_transcript(self, transcript: str):
        """Handle final transcript"""
        try:
            if transcript and transcript.strip():
                logger.info(f"Final transcript: {transcript}")
                
                # Create text frame and push to pipeline
                text_frame = TextFrame(text=transcript)
                await self.push_frame(text_frame)
                
                if self.on_transcript:
                    if asyncio.iscoroutinefunction(self.on_transcript):
                        await self.on_transcript(transcript)
                    else:
                        self.on_transcript(transcript)
                        
        except Exception as e:
            logger.error(f"Error handling final transcript: {e}")

class IntentProcessor(TextFrameProcessor):
    """Intent recognition processor using REST intent service"""
    
    def __init__(
        self,
        intent_client: IntentClient,
        session_id: str,
        config: Optional[Dict[str, Any]] = None,
        name: str = "IntentProcessor"
    ):
        super().__init__(name=name)
        self.intent_client = intent_client
        self.session_id = session_id
        self.config = config or {}
        
    async def process_frame(self, frame: Frame) -> Optional[Frame]:
        """Process text frames through intent recognition"""
        try:
            if isinstance(frame, StartFrame):
                logger.info(f"Intent processor started: {self.name}")
                return frame
                
            elif isinstance(frame, EndFrame):
                logger.info(f"Intent processor ended: {self.name}")
                return frame
                
            elif isinstance(frame, TextFrame):
                # Process user input through intent recognition
                response = await self._get_intent_response(frame.text)
                if response:
                    # Create response text frame
                    response_frame = TextFrame(text=response)
                    await self.push_frame(response_frame)
                
                return frame
                
            else:
                return frame
                
        except Exception as e:
            logger.error(f"Intent processor error: {e}")
            return ErrorFrame(error=str(e))
    
    async def _get_intent_response(self, user_text: str) -> Optional[str]:
        """Get response from intent recognition service"""
        try:
            # Recognize intent from user text
            intent_result = await self.intent_client.recognize_intent(
                text=user_text,
                session_id=self.session_id
            )
            
            if intent_result and 'response' in intent_result:
                response = intent_result['response']
                logger.info(f"Intent response: {response}")
                return response
            else:
                logger.warning("No response from intent service")
                return "Üzgünüm, anlayamadım. Tekrar söyler misiniz?"
                
        except Exception as e:
            logger.error(f"Error getting intent response: {e}")
            return "Bir hata oluştu. Lütfen tekrar deneyin."

class TTSProcessor(TextFrameProcessor):
    """TTS processor using gRPC TTS service"""
    
    def __init__(
        self,
        tts_client: TTSClient,
        on_audio: Optional[Callable[[bytes], None]] = None,
        config: Optional[Dict[str, Any]] = None,
        name: str = "TTSProcessor"
    ):
        super().__init__(name=name)
        self.tts_client = tts_client
        self.on_audio = on_audio
        self.config = config or {}
        self.sentence_aggregator = None
        
    async def process_frame(self, frame: Frame) -> Optional[Frame]:
        """Process text frames through TTS"""
        try:
            if isinstance(frame, StartFrame):
                await self._initialize_tts()
                return frame
                
            elif isinstance(frame, EndFrame):
                await self._finalize_tts()
                return frame
                
            elif isinstance(frame, TextFrame):
                # Process text through TTS
                await self._synthesize_text(frame.text)
                return frame
                
            else:
                return frame
                
        except Exception as e:
            logger.error(f"TTS processor error: {e}")
            return ErrorFrame(error=str(e))
    
    async def _initialize_tts(self):
        """Initialize TTS aggregator"""
        try:
            from ...grpc_clients.tts_client import SentenceFlushAggregator
            
            self.sentence_aggregator = SentenceFlushAggregator(
                tts_client=self.tts_client,
                on_audio=self._on_tts_audio
            )
            
            logger.info(f"TTS aggregator initialized: {self.name}")
            
        except Exception as e:
            logger.error(f"Failed to initialize TTS: {e}")
            raise
    
    async def _finalize_tts(self):
        """Finalize TTS processing"""
        try:
            if self.sentence_aggregator:
                await self.sentence_aggregator.flush()
                
        except Exception as e:
            logger.error(f"Error finalizing TTS: {e}")
    
    async def _synthesize_text(self, text: str):
        """Synthesize text to audio"""
        try:
            if not self.sentence_aggregator:
                logger.warning("TTS aggregator not initialized")
                return
            
            await self.sentence_aggregator.add_text(text)
            await self.sentence_aggregator.flush()
            
        except Exception as e:
            logger.error(f"Error synthesizing text: {e}")
    
    async def _on_tts_audio(self, audio_data: bytes):
        """Handle TTS audio output"""
        try:
            # Create audio frame and push to pipeline
            audio_frame = AudioFrame(audio=audio_data, sample_rate=22050)
            await self.push_frame(audio_frame)
            
            # Call external callback if provided
            if self.on_audio:
                if asyncio.iscoroutinefunction(self.on_audio):
                    await self.on_audio(audio_data)
                else:
                    self.on_audio(audio_data)
                    
        except Exception as e:
            logger.error(f"Error handling TTS audio: {e}")

class RTPInputProcessor(AsyncFrameProcessor):
    """RTP input processor - converts RTP audio to pipeline frames"""
    
    def __init__(
        self,
        rtp_transport,
        sample_rate: int = 8000,
        target_sample_rate: int = 16000,
        name: str = "RTPInputProcessor"
    ):
        super().__init__(name=name)
        self.rtp_transport = rtp_transport
        self.sample_rate = sample_rate
        self.target_sample_rate = target_sample_rate
        self._audio_queue = asyncio.Queue()
        self._processing_task = None
        
    async def process_frame(self, frame: Frame) -> Optional[Frame]:
        """Process frames and handle RTP setup"""
        try:
            if isinstance(frame, StartFrame):
                await self._start_audio_processing()
                return frame
                
            elif isinstance(frame, EndFrame):
                await self._stop_audio_processing()
                return frame
                
            else:
                return frame
                
        except Exception as e:
            logger.error(f"RTP input processor error: {e}")
            return ErrorFrame(error=str(e))
    
    async def _start_audio_processing(self):
        """Start audio processing from RTP"""
        try:
            # Set up RTP audio callback
            if self.rtp_transport:
                self.rtp_transport.on_audio_received = self._on_rtp_audio
            
            # Start processing task
            self._processing_task = await self.create_task(self._process_audio_queue())
            
            logger.info(f"RTP audio processing started: {self.name}")
            
        except Exception as e:
            logger.error(f"Failed to start RTP audio processing: {e}")
            raise
    
    async def _stop_audio_processing(self):
        """Stop audio processing"""
        try:
            # Remove RTP callback
            if self.rtp_transport:
                self.rtp_transport.on_audio_received = None
            
            # Stop processing task
            if self._processing_task and not self._processing_task.done():
                self._processing_task.cancel()
                try:
                    await self._processing_task
                except asyncio.CancelledError:
                    pass
            
            logger.info(f"RTP audio processing stopped: {self.name}")
            
        except Exception as e:
            logger.error(f"Error stopping RTP audio processing: {e}")
    
    async def _on_rtp_audio(self, audio_data: bytes):
        """Handle incoming RTP audio"""
        try:
            await self._audio_queue.put(audio_data)
            
        except Exception as e:
            logger.error(f"Error queuing RTP audio: {e}")
    
    async def _process_audio_queue(self):
        """Process audio from queue"""
        try:
            while True:
                audio_data = await self._audio_queue.get()
                
                # Process audio (format conversion, etc.)
                processed_audio = await self._process_audio(audio_data)
                
                if processed_audio:
                    # Create audio frame and push to pipeline
                    audio_frame = AudioFrame(
                        audio=processed_audio,
                        sample_rate=self.target_sample_rate
                    )
                    await self.push_frame(audio_frame)
                
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Error processing audio queue: {e}")
    
    async def _process_audio(self, audio_data: bytes) -> bytes:
        """Process RTP audio (format conversion, etc.)"""
        try:
            # For now, return audio as-is
            # In production, you might need:
            # - PCMU to PCM conversion
            # - Sample rate conversion (8kHz to 16kHz)
            # - Format normalization
            return audio_data
            
        except Exception as e:
            logger.error(f"Error processing audio: {e}")
            return b''

class RTPOutputProcessor(AudioFrameProcessor):
    """RTP output processor - converts pipeline audio frames to RTP"""
    
    def __init__(
        self,
        rtp_transport,
        sample_rate: int = 22050,
        target_sample_rate: int = 8000,
        name: str = "RTPOutputProcessor"
    ):
        super().__init__(sample_rate=sample_rate, name=name)
        self.rtp_transport = rtp_transport
        self.target_sample_rate = target_sample_rate
        
    async def process_frame(self, frame: Frame) -> Optional[Frame]:
        """Process audio frames for RTP output"""
        try:
            if isinstance(frame, AudioFrame):
                # Process and send audio via RTP
                await self._send_rtp_audio(frame.audio)
                return frame
                
            else:
                return frame
                
        except Exception as e:
            logger.error(f"RTP output processor error: {e}")
            return ErrorFrame(error=str(e))
    
    async def _send_rtp_audio(self, audio_data: bytes):
        """Send audio via RTP transport"""
        try:
            if not self.rtp_transport:
                logger.warning("No RTP transport available for audio output")
                return
            
            # Process audio for RTP (format conversion, etc.)
            processed_audio = await self._process_audio_for_rtp(audio_data)
            
            if processed_audio:
                await self.rtp_transport.send_audio(processed_audio)
                logger.debug(f"Audio sent via RTP: {len(processed_audio)} bytes")
                
        except Exception as e:
            logger.error(f"Error sending RTP audio: {e}")
    
    async def _process_audio_for_rtp(self, audio_data: bytes) -> bytes:
        """Process audio for RTP transmission"""
        try:
            # For now, return audio as-is
            # In production, you might need:
            # - Sample rate conversion (22kHz to 8kHz)
            # - PCM to PCMU conversion
            # - Format normalization
            return audio_data
            
        except Exception as e:
            logger.error(f"Error processing audio for RTP: {e}")
            return audio_data