"""
ASR gRPC Client for OpenSIPS AI Voice Connector
Communicates with ASR microservice for speech recognition
"""

import asyncio
import logging
import sys
import os
from typing import AsyncGenerator, Optional, Dict, Any, List
from grpc import aio as aio_grpc

# Import protobuf stubs (assuming they exist in services directory)
try:
    # Try to import from services directory
    sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', 'services', 'asr-service', 'src'))
    import asr_service_pb2
    import asr_service_pb2_grpc
except ImportError as e:
    logger = logging.getLogger(__name__)
    logger.error(f"Failed to import ASR protobuf stubs: {e}")
    # Create minimal stub classes for development
    class asr_service_pb2:
        class RecognizeRequest:
            def __init__(self):
                self.config = None
                self.audio_data = b''
        
        class StreamingRecognizeRequest:
            def __init__(self):
                pass
            
            def HasField(self, field): return False
        
        class RecognizeResponse:
            def __init__(self):
                self.result = type('Result', (), {'text': '', 'confidence': 0.0})()
        
        class StreamingRecognizeResponse:
            def __init__(self):
                self.result = type('Result', (), {'text': '', 'confidence': 0.0})()
                self.is_final = False
                self.end_of_utterance = False
    
    class asr_service_pb2_grpc:
        class ASRServiceStub:
            def __init__(self, channel): pass
            async def Recognize(self, request): pass
            def StreamingRecognize(self, request_stream): pass

logger = logging.getLogger(__name__)

class ASRClient:
    """gRPC client for ASR service"""
    
    def __init__(self, service_registry):
        self.service_registry = service_registry
        self._streaming_tasks: List[asyncio.Task] = []
        
    async def recognize(self, audio_data: bytes, config: Optional[Dict[str, Any]] = None) -> Optional[str]:
        """Single shot recognition"""
        try:
            channel = self.service_registry.get_channel('asr')
            if not channel:
                logger.error("ASR service not available")
                return None
            
            stub = asr_service_pb2_grpc.ASRServiceStub(channel)
            
            # Create request
            request = asr_service_pb2.RecognizeRequest()
            
            # Set configuration if provided
            if config:
                # Configure recognition parameters
                if hasattr(request, 'config'):
                    request.config.sample_rate = config.get('sample_rate', 16000)
                    request.config.show_words = config.get('show_words', True)
                    request.config.max_alternatives = config.get('max_alternatives', 0)
            
            # Set audio data
            request.audio_data = audio_data
            
            # Make request
            response = await stub.Recognize(request)
            
            if hasattr(response, 'result') and hasattr(response.result, 'text'):
                return response.result.text
            
            return None
            
        except Exception as e:
            logger.error(f"ASR recognition error: {e}")
            return None
    
    async def stream_recognize(
        self, 
        audio_stream: AsyncGenerator[bytes, None],
        config: Optional[Dict[str, Any]] = None,
        on_transcript: Optional[callable] = None,
        on_final: Optional[callable] = None
    ) -> AsyncGenerator[str, None]:
        """Streaming recognition"""
        try:
            channel = self.service_registry.get_channel('asr')
            if not channel:
                logger.error("ASR service not available")
                return
            
            stub = asr_service_pb2_grpc.ASRServiceStub(channel)
            
            # Create request stream
            async def request_generator():
                # Send configuration first
                config_request = asr_service_pb2.StreamingRecognizeRequest()
                if config and hasattr(config_request, 'config'):
                    config_request.config.sample_rate = config.get('sample_rate', 16000)
                    config_request.config.show_words = config.get('show_words', True)
                    config_request.config.max_alternatives = config.get('max_alternatives', 0)
                    
                    if 'phrase_list' in config:
                        for phrase in config['phrase_list']:
                            config_request.config.phrase_list.append(phrase)
                
                yield config_request
                
                # Send audio data
                async for audio_chunk in audio_stream:
                    audio_request = asr_service_pb2.StreamingRecognizeRequest()
                    audio_request.audio_data = audio_chunk
                    yield audio_request
            
            # Start streaming recognition
            response_stream = stub.StreamingRecognize(request_generator())
            
            async for response in response_stream:
                if hasattr(response, 'result') and hasattr(response.result, 'text'):
                    text = response.result.text
                    
                    if text:  # Only yield non-empty results
                        is_final = getattr(response, 'is_final', False)
                        
                        if is_final:
                            if on_final:
                                await on_final(text)
                            yield f"[FINAL] {text}"
                        else:
                            if on_transcript:
                                await on_transcript(text)
                            yield f"[PARTIAL] {text}"
                        
        except Exception as e:
            logger.error(f"ASR streaming error: {e}")
    
    async def create_audio_stream(self, audio_chunks: List[bytes]) -> AsyncGenerator[bytes, None]:
        """Create audio stream from audio chunks"""
        for chunk in audio_chunks:
            yield chunk
    
    async def start_streaming_session(
        self,
        on_transcript: Optional[callable] = None,
        on_final: Optional[callable] = None,
        config: Optional[Dict[str, Any]] = None
    ) -> 'StreamingSession':
        """Start a new streaming recognition session"""
        return StreamingSession(
            asr_client=self,
            on_transcript=on_transcript,
            on_final=on_final,
            config=config
        )
    
    async def health_check(self) -> bool:
        """Check ASR service health"""
        try:
            # Simple health check using empty audio
            test_audio = b'\x00' * 3200  # 100ms of silence at 16kHz
            result = await self.recognize(test_audio)
            return True  # If no exception, service is healthy
            
        except Exception as e:
            logger.error(f"ASR health check failed: {e}")
            return False
    
    async def cleanup(self):
        """Cleanup ASR client resources"""
        # Cancel streaming tasks
        for task in self._streaming_tasks:
            if not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        
        self._streaming_tasks.clear()
        logger.info("ASR client cleaned up")

class StreamingSession:
    """ASR streaming session manager"""
    
    def __init__(self, asr_client: ASRClient, on_transcript=None, on_final=None, config=None):
        self.asr_client = asr_client
        self.on_transcript = on_transcript
        self.on_final = on_final
        self.config = config or {}
        
        self._audio_queue = asyncio.Queue()
        self._streaming_task: Optional[asyncio.Task] = None
        self._is_active = False
    
    async def start(self):
        """Start streaming session"""
        if self._is_active:
            return
        
        self._is_active = True
        
        # Create audio stream from queue
        async def audio_stream():
            while self._is_active:
                try:
                    audio_chunk = await asyncio.wait_for(self._audio_queue.get(), timeout=1.0)
                    yield audio_chunk
                except asyncio.TimeoutError:
                    continue
                except Exception as e:
                    logger.error(f"Audio stream error: {e}")
                    break
        
        # Start streaming recognition
        self._streaming_task = asyncio.create_task(
            self._process_streaming_recognition(audio_stream())
        )
        
        logger.info("ASR streaming session started")
    
    async def _process_streaming_recognition(self, audio_stream):
        """Process streaming recognition results"""
        try:
            async for result in self.asr_client.stream_recognize(
                audio_stream=audio_stream,
                config=self.config,
                on_transcript=self.on_transcript,
                on_final=self.on_final
            ):
                logger.debug(f"ASR result: {result}")
                
        except Exception as e:
            logger.error(f"Streaming recognition error: {e}")
    
    async def add_audio(self, audio_data: bytes):
        """Add audio data to streaming session"""
        if self._is_active:
            await self._audio_queue.put(audio_data)
    
    async def stop(self):
        """Stop streaming session"""
        self._is_active = False
        
        if self._streaming_task and not self._streaming_task.done():
            self._streaming_task.cancel()
            try:
                await self._streaming_task
            except asyncio.CancelledError:
                pass
        
        # Clear queue
        while not self._audio_queue.empty():
            try:
                self._audio_queue.get_nowait()
            except asyncio.QueueEmpty:
                break
        
        logger.info("ASR streaming session stopped")