"""
TTS gRPC Client for OpenSIPS AI Voice Connector
Communicates with TTS microservice for speech synthesis
"""

import asyncio
import logging
import sys
import os
from typing import AsyncGenerator, Optional, Dict, Any, List
from grpc import aio as aio_grpc

# Import protobuf stubs (first try local grpc_clients directory)
try:
    # Try to import from local grpc_clients directory
    import tts_service_pb2
    import tts_service_pb2_grpc
except ImportError:
    try:
        # Fallback: Try to import from services directory
        sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', 'services', 'tts-service', 'src'))
        import tts_service_pb2
        import tts_service_pb2_grpc
    except ImportError as e:
        logger = logging.getLogger(__name__)
        logger.error(f"Failed to import TTS protobuf stubs: {e}")
    # Create minimal stub classes for development
    class tts_service_pb2:
        class SynthesizeRequest:
            def __init__(self):
                self.text = ""
                self.voice = ""
                self.sample_rate = 22050
                self.format = "pcm16"
        
        class SynthesizeResponse:
            def __init__(self):
                self.audio_data = b''
                self.done = False
        
        class StreamSynthesizeRequest:
            def __init__(self):
                self.text = ""
                self.voice = ""
                self.sample_rate = 22050
                self.format = "pcm16"
        
        class StreamSynthesizeResponse:
            def __init__(self):
                self.audio_chunk = b''
                self.done = False
    
    class tts_service_pb2_grpc:
        class TTSServiceStub:
            def __init__(self, channel): pass
            async def Synthesize(self, request): pass
            def StreamSynthesize(self, request): pass

logger = logging.getLogger(__name__)

class TTSClient:
    """gRPC client for TTS service"""
    
    def __init__(self, service_registry):
        self.service_registry = service_registry
        self._synthesis_tasks: List[asyncio.Task] = []
        
    async def synthesize(
        self,
        text: str,
        voice: str = "tr_TR-dfki-medium",
        sample_rate: int = 22050,
        format: str = "pcm16"
    ) -> Optional[bytes]:
        """Single shot text-to-speech synthesis"""
        try:
            channel = self.service_registry.get_channel('tts')
            if not channel:
                logger.error("TTS service not available")
                return None
            
            stub = tts_service_pb2_grpc.TTSServiceStub(channel)
            
            # Create request
            request = tts_service_pb2.SynthesizeRequest()
            request.text = text
            request.voice = voice
            request.sample_rate = sample_rate
            request.format = format
            
            # Make request
            response = await stub.Synthesize(request)
            
            if hasattr(response, 'audio_data'):
                return response.audio_data
            
            return None
            
        except Exception as e:
            logger.error(f"TTS synthesis error: {e}")
            return None
    
    async def stream_synthesize(
        self,
        text: str,
        voice: str = "tr_TR-dfki-medium",
        sample_rate: int = 22050,
        format: str = "pcm16",
        on_audio_chunk: Optional[callable] = None,
        on_complete: Optional[callable] = None
    ) -> AsyncGenerator[bytes, None]:
        """Streaming text-to-speech synthesis"""
        try:
            channel = self.service_registry.get_channel('tts')
            if not channel:
                logger.error("TTS service not available")
                return
            
            stub = tts_service_pb2_grpc.TTSServiceStub(channel)
            
            # Create request
            request = tts_service_pb2.StreamSynthesizeRequest()
            request.text = text
            request.voice = voice
            request.sample_rate = sample_rate
            request.format = format
            
            # Start streaming synthesis
            response_stream = stub.StreamSynthesize(request)
            
            full_audio = b""
            
            async for response in response_stream:
                if hasattr(response, 'audio_chunk'):
                    audio_chunk = response.audio_chunk
                    if audio_chunk:
                        full_audio += audio_chunk
                        
                        if on_audio_chunk:
                            await on_audio_chunk(audio_chunk)
                        
                        yield audio_chunk
                
                # Check if synthesis is complete
                if hasattr(response, 'done') and response.done:
                    if on_complete:
                        await on_complete(full_audio)
                    break
                        
        except Exception as e:
            logger.error(f"TTS streaming error: {e}")
    
    async def synthesize_queue(
        self,
        text_queue: asyncio.Queue,
        voice: str = "tr_TR-dfki-medium",
        sample_rate: int = 22050,
        on_audio_chunk: Optional[callable] = None
    ) -> AsyncGenerator[bytes, None]:
        """Synthesize text from a queue (for real-time streaming)"""
        try:
            while True:
                try:
                    # Get text from queue with timeout
                    text = await asyncio.wait_for(text_queue.get(), timeout=1.0)
                    
                    if text is None:  # Sentinel value to stop
                        break
                    
                    # Stream synthesis for this text
                    async for audio_chunk in self.stream_synthesize(
                        text=text,
                        voice=voice,
                        sample_rate=sample_rate,
                        on_audio_chunk=on_audio_chunk
                    ):
                        yield audio_chunk
                        
                except asyncio.TimeoutError:
                    continue
                except Exception as e:
                    logger.error(f"Queue synthesis error: {e}")
                    break
                    
        except Exception as e:
            logger.error(f"TTS queue processing error: {e}")
    
    async def get_available_voices(self) -> List[str]:
        """Get list of available voices"""
        try:
            # This would require a separate RPC method in the service
            # For now, return common Turkish voices
            return [
                "tr_TR-dfki-medium",
                "tr_TR-fgl-medium",
                "tr_TR-tugba-medium"
            ]
            
        except Exception as e:
            logger.error(f"Error getting voices: {e}")
            return ["tr_TR-dfki-medium"]  # Default fallback
    
    async def validate_text(self, text: str) -> bool:
        """Validate text for synthesis"""
        if not text or not text.strip():
            return False
        
        # Check text length (TTS services usually have limits)
        if len(text) > 5000:  # 5KB limit
            logger.warning(f"Text too long for synthesis: {len(text)} characters")
            return False
        
        return True
    
    async def health_check(self) -> bool:
        """Check TTS service health"""
        try:
            # Simple health check with minimal text
            test_audio = await self.synthesize("Test", sample_rate=22050)
            return test_audio is not None and len(test_audio) > 0
            
        except Exception as e:
            logger.error(f"TTS health check failed: {e}")
            return False
    
    async def cleanup(self):
        """Cleanup TTS client resources"""
        # Cancel synthesis tasks
        for task in self._synthesis_tasks:
            if not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        
        self._synthesis_tasks.clear()
        logger.info("TTS client cleaned up")

class TTSQueue:
    """Queue-based TTS synthesis for real-time streaming"""
    
    def __init__(self, tts_client: TTSClient, voice: str = "tr_TR-dfki-medium"):
        self.tts_client = tts_client
        self.voice = voice
        self.text_queue = asyncio.Queue()
        self.audio_queue = asyncio.Queue()
        self._synthesis_task: Optional[asyncio.Task] = None
        self._is_active = False
    
    async def start(self):
        """Start TTS queue processing"""
        if self._is_active:
            return
        
        self._is_active = True
        
        # Start synthesis task
        self._synthesis_task = asyncio.create_task(self._process_synthesis())
        
        logger.info("TTS queue started")
    
    async def _process_synthesis(self):
        """Process TTS synthesis from queue"""
        try:
            async for audio_chunk in self.tts_client.synthesize_queue(
                text_queue=self.text_queue,
                voice=self.voice,
                on_audio_chunk=self._on_audio_chunk
            ):
                await self.audio_queue.put(audio_chunk)
                
        except Exception as e:
            logger.error(f"TTS queue processing error: {e}")
    
    async def _on_audio_chunk(self, audio_chunk: bytes):
        """Handle audio chunk from synthesis"""
        # Additional processing could be done here
        pass
    
    async def add_text(self, text: str):
        """Add text to synthesis queue"""
        if self._is_active and text and text.strip():
            await self.text_queue.put(text)
    
    async def get_audio(self) -> Optional[bytes]:
        """Get audio chunk from queue"""
        try:
            return await asyncio.wait_for(self.audio_queue.get(), timeout=1.0)
        except asyncio.TimeoutError:
            return None
    
    async def stop(self):
        """Stop TTS queue processing"""
        self._is_active = False
        
        # Send sentinel to stop synthesis
        await self.text_queue.put(None)
        
        if self._synthesis_task and not self._synthesis_task.done():
            try:
                await asyncio.wait_for(self._synthesis_task, timeout=5.0)
            except asyncio.TimeoutError:
                self._synthesis_task.cancel()
                try:
                    await self._synthesis_task
                except asyncio.CancelledError:
                    pass
        
        # Clear queues
        while not self.text_queue.empty():
            try:
                self.text_queue.get_nowait()
            except asyncio.QueueEmpty:
                break
        
        while not self.audio_queue.empty():
            try:
                self.audio_queue.get_nowait()
            except asyncio.QueueEmpty:
                break
        
        logger.info("TTS queue stopped")

class SentenceFlushAggregator:
    """Aggregate text and synthesize on sentence boundaries"""
    
    def __init__(self, tts_client: TTSClient, on_audio: Optional[callable] = None):
        self.tts_client = tts_client
        self.on_audio = on_audio
        self.buffer = ""
        self.sentence_endings = ['.', '!', '?', '...', '。', '！', '？']
    
    async def add_text(self, text: str):
        """Add text to buffer and synthesize complete sentences"""
        self.buffer += text
        
        # Check for sentence endings
        while self._has_complete_sentence():
            sentence = self._extract_sentence()
            if sentence.strip():
                await self._synthesize_sentence(sentence)
    
    def _has_complete_sentence(self) -> bool:
        """Check if buffer contains a complete sentence"""
        for ending in self.sentence_endings:
            if ending in self.buffer:
                return True
        return False
    
    def _extract_sentence(self) -> str:
        """Extract first complete sentence from buffer"""
        earliest_pos = len(self.buffer)
        
        for ending in self.sentence_endings:
            pos = self.buffer.find(ending)
            if pos != -1 and pos < earliest_pos:
                earliest_pos = pos
        
        if earliest_pos < len(self.buffer):
            sentence = self.buffer[:earliest_pos + 1]
            self.buffer = self.buffer[earliest_pos + 1:].lstrip()
            return sentence
        
        return ""
    
    async def _synthesize_sentence(self, sentence: str):
        """Synthesize a complete sentence"""
        try:
            async for audio_chunk in self.tts_client.stream_synthesize(sentence):
                if self.on_audio:
                    await self.on_audio(audio_chunk)
                    
        except Exception as e:
            logger.error(f"Sentence synthesis error: {e}")
    
    async def flush(self):
        """Synthesize any remaining text in buffer"""
        if self.buffer.strip():
            await self._synthesize_sentence(self.buffer)
            self.buffer = ""