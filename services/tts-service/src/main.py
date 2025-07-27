"""
TTS Service - Text-to-Speech Microservice
Extracted from working legacy Piper WebSocket implementation
"""

import asyncio
import json
import logging
import sys
import time
from typing import Dict, Any, Optional, List

import structlog
import grpc
from grpc import aio as aio_grpc
from concurrent import futures
import websockets
import numpy as np

# Generated gRPC code (will be created by proto-gen.sh)
from shared.proto_generated import common_pb2
try:
    from . import tts_service_pb2
    from . import tts_service_pb2_grpc
except ImportError:
    # Fallback for development
    import sys
    sys.path.append('.')
    import tts_service_pb2
    import tts_service_pb2_grpc

# Setup structured logging (same as legacy)
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        structlog.processors.JSONRenderer()
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    wrapper_class=structlog.stdlib.BoundLogger,
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger(__name__)


class PiperTTSEngine:
    """Piper TTS engine - extracted from proven legacy implementation"""
    
    def __init__(self,
                 url: str = "ws://piper-tts-server:8000/tts",
                 voice: str = "tr_TR-dfki-medium",
                 sample_rate: int = 22050):
        self.url = url
        self.voice = voice
        self.sample_rate = sample_rate
        self.websocket: Optional = None
        self.is_connected = False
        
    async def connect(self):
        """Connect to Piper WebSocket server (same as legacy)"""
        try:
            self.websocket = await websockets.connect(self.url)
            self.is_connected = True
            
            logger.info("Piper TTS engine connected",
                       url=self.url,
                       voice=self.voice,
                       sample_rate=self.sample_rate)
            
        except Exception as e:
            logger.error("Failed to connect to Piper server", url=self.url, error=str(e))
            raise
    
    async def disconnect(self):
        """Disconnect from Piper server"""
        if self.websocket and self.is_connected:
            try:
                await self.websocket.close()
            except Exception as e:
                logger.error("Error disconnecting from Piper", error=str(e))
        
        self.is_connected = False
        self.websocket = None
    
    async def synthesize_speech(self, text: str) -> Dict[str, Any]:
        """Synthesize speech using Piper (same logic as legacy)"""
        if not self.is_connected or not self.websocket:
            await self.connect()
        
        if not text or not text.strip():
            return {"error": "Empty text provided"}
        
        try:
            # Create TTS request (same format as legacy)
            request = {
                "text": text.strip(),
                "voice": self.voice,
                "sample_rate": self.sample_rate,
                "format": "pcm16"  # PCM output as per legacy
            }
            
            logger.debug("Sending text to Piper TTS",
                        text_length=len(text),
                        voice=self.voice,
                        sample_rate=self.sample_rate)
            
            # Send synthesis request
            await self.websocket.send(json.dumps(request))
            
            # Collect audio frames
            audio_chunks = []
            synthesis_complete = False
            
            # Wait for audio response with timeout
            timeout_start = time.time()
            timeout_seconds = 10.0
            
            while not synthesis_complete and (time.time() - timeout_start) < timeout_seconds:
                try:
                    message = await asyncio.wait_for(
                        self.websocket.recv(),
                        timeout=1.0
                    )
                    
                    # Handle binary audio data (same as legacy)
                    if isinstance(message, bytes):
                        audio_chunks.append(message)
                        logger.debug("Received audio chunk", size=len(message))
                    
                    # Handle JSON status messages (same as legacy)
                    elif isinstance(message, str):
                        try:
                            data = json.loads(message)
                            status = data.get("status") or data.get("type")
                            
                            if status in ("completed", "end"):
                                synthesis_complete = True
                                logger.debug("TTS synthesis completed")
                            elif status in ("started", "start"):
                                logger.debug("TTS synthesis started")
                            elif data.get("error"):
                                return {"error": f"Piper TTS error: {data['error']}"}
                        
                        except json.JSONDecodeError:
                            # Not JSON, might be raw audio
                            pass
                
                except asyncio.TimeoutError:
                    # Continue waiting if we've received some audio
                    if audio_chunks:
                        continue
                    else:
                        break
            
            if not audio_chunks:
                return {"error": "No audio received from Piper"}
            
            # Combine all audio chunks (same as legacy)
            combined_audio = b''.join(audio_chunks)
            
            logger.debug("TTS synthesis successful",
                        text_length=len(text),
                        audio_size=len(combined_audio),
                        chunks_count=len(audio_chunks))
            
            return {
                "audio": combined_audio,
                "sample_rate": self.sample_rate,
                "format": "pcm16",
                "voice": self.voice,
                "text": text
            }
            
        except Exception as e:
            logger.error("Piper synthesis failed", error=str(e))
            return {"error": f"Synthesis failed: {e}"}


class TTSServiceImpl(tts_service_pb2_grpc.TTSServiceServicer):
    """TTS Service gRPC implementation using proven Piper WebSocket"""
    
    def __init__(self):
        # TTS engines per session (like legacy)
        self.session_engines: Dict[str, PiperTTSEngine] = {}
        self.session_stats: Dict[str, Dict[str, Any]] = {}
        
        # Default Piper server config
        self.default_tts_config = {
            "url": "ws://piper-tts-server:8000/tts",
            "voice": "tr_TR-dfki-medium",
            "sample_rate": 22050
        }
        
        # Available voices (based on legacy)
        self.available_voices = {
            "tr_TR-dfki-medium": {
                "display_name": "Turkish Female (DFKI)",
                "language_code": "tr-TR",
                "gender": "FEMALE",
                "age_group": "ADULT",
                "accent": "standard"
            },
            "tr_TR-fgl-medium": {
                "display_name": "Turkish Female (FGL)",
                "language_code": "tr-TR", 
                "gender": "FEMALE",
                "age_group": "ADULT",
                "accent": "standard"
            }
        }
        
        logger.info("TTS Service initialized with Piper WebSocket engine")
    
    async def SynthesizeSpeech(self, request, context):
        """Synthesize speech from text"""
        try:
            session_id = request.session_id
            text = request.text
            config = request.config
            
            start_time = time.time()
            
            # Get or create TTS engine for session
            if session_id not in self.session_engines:
                await self._create_session_engine(session_id, config)
            
            engine = self.session_engines[session_id]
            
            logger.debug("Processing TTS request",
                        session_id=session_id,
                        text=text,
                        voice=engine.voice)
            
            # Synthesize speech using Piper (same as legacy)
            piper_result = await engine.synthesize_speech(text)
            
            processing_time = (time.time() - start_time) * 1000
            
            # Update session stats
            self._update_session_stats(session_id, piper_result, processing_time)
            
            # Convert Piper result to protobuf response
            response = tts_service_pb2.SynthesizeSpeechResponse()
            response.session_id = session_id
            
            # Parse Piper response (same logic as legacy)
            if "audio" in piper_result:
                audio_data = piper_result["audio"]
                
                response.status.code = common_pb2.Status.OK
                
                # TTS result
                response.result.audio.data = audio_data
                response.result.audio.config.sample_rate = piper_result["sample_rate"]
                response.result.audio.config.channels = 1
                response.result.audio.config.encoding = "pcm16"
                response.result.synthesized_text = piper_result["text"]
                
                # Metadata
                response.result.metadata.voice_used = piper_result["voice"]
                response.result.metadata.engine_version = "piper-v1"
                response.result.metadata.character_count = len(text)
                response.result.metadata.actual_speaking_rate = 1.0
                
                logger.info("TTS synthesis completed",
                           session_id=session_id,
                           text_length=len(text),
                           audio_size=len(audio_data),
                           processing_time_ms=processing_time)
                
            elif "error" in piper_result:
                # Error occurred
                response.status.code = common_pb2.Status.INTERNAL
                response.status.message = piper_result["error"]
                logger.error("TTS synthesis error", session_id=session_id, error=piper_result["error"])
                
            else:
                # Unexpected response format
                response.status.code = common_pb2.Status.INTERNAL
                response.status.message = "Unexpected TTS response format"
                logger.error("Unexpected TTS response", session_id=session_id, response=piper_result)
            
            # Metrics
            response.metrics.processing_time_ms = processing_time
            if "audio" in piper_result:
                audio_duration = len(piper_result["audio"]) / (piper_result["sample_rate"] * 2)  # 16-bit PCM
                response.metrics.audio_duration_ms = audio_duration * 1000
                response.metrics.real_time_factor = processing_time / (audio_duration * 1000) if audio_duration > 0 else 0
                response.metrics.audio_bytes_generated = len(piper_result["audio"])
            
            response.metrics.characters_processed = len(text)
            response.metrics.model_used = engine.voice
            
            return response
            
        except Exception as e:
            logger.error("TTS synthesis failed", session_id=session_id, error=str(e))
            response = tts_service_pb2.SynthesizeSpeechResponse()
            response.status.code = common_pb2.Status.INTERNAL
            response.status.message = f"TTS synthesis failed: {str(e)}"
            return response
    
    async def SynthesizeSpeechStream(self, request, context):
        """Stream-based speech synthesis (placeholder - returns single response)"""
        response = await self.SynthesizeSpeech(request, context)
        yield response
    
    async def ConfigureTTS(self, request, context):
        """Configure TTS parameters for a session"""
        try:
            session_id = request.session_id
            config = request.config
            
            # Create new engine with updated config
            await self._create_session_engine(session_id, config)
            
            response = tts_service_pb2.ConfigureTTSResponse()
            response.status.code = common_pb2.Status.OK
            
            logger.info("TTS configuration updated", session_id=session_id)
            return response
            
        except Exception as e:
            logger.error("TTS configuration failed", session_id=session_id, error=str(e))
            response = tts_service_pb2.ConfigureTTSResponse()
            response.status.code = common_pb2.Status.INTERNAL
            response.status.message = f"Configuration failed: {str(e)}"
            return response
    
    async def GetAvailableVoices(self, request, context):
        """Get available voices"""
        try:
            language_filter = request.language_code
            engine_filter = request.engine_type
            
            response = tts_service_pb2.GetAvailableVoicesResponse()
            response.status.code = common_pb2.Status.OK
            
            # Add available voices
            for voice_id, voice_info in self.available_voices.items():
                # Apply filters
                if language_filter and voice_info["language_code"] != language_filter:
                    continue
                if engine_filter and engine_filter != "piper":
                    continue
                
                voice = response.voices.add()
                voice.voice_name = voice_id
                voice.display_name = voice_info["display_name"]
                voice.language_code = voice_info["language_code"]
                voice.language_name = "Turkish"
                voice.gender = voice_info["gender"]
                voice.age_group = voice_info["age_group"]
                voice.accent = voice_info["accent"]
                voice.engine_type = "piper"
                voice.supported_features.append("real_time")
                
                # Audio capabilities
                voice.capabilities.supported_sample_rates.extend([16000, 22050, 44100])
                voice.capabilities.supported_encodings.extend(["pcm16", "pcm24"])
                voice.capabilities.supports_streaming = True
                voice.capabilities.min_speaking_rate = 0.5
                voice.capabilities.max_speaking_rate = 2.0
            
            logger.debug("Available voices requested", count=len(response.voices))
            return response
            
        except Exception as e:
            logger.error("Get available voices failed", error=str(e))
            response = tts_service_pb2.GetAvailableVoicesResponse()
            response.status.code = common_pb2.Status.INTERNAL
            response.status.message = f"Failed to get voices: {str(e)}"
            return response
    
    async def HealthCheck(self, request, context):
        """Health check implementation"""
        try:
            # Test connection to Piper server
            test_engine = PiperTTSEngine(**self.default_tts_config)
            
            start_time = time.time()
            await test_engine.connect()
            
            # Test with simple text
            test_result = await test_engine.synthesize_speech("Test")
            
            await test_engine.disconnect()
            
            response_time = (time.time() - start_time) * 1000
            
            response = common_pb2.HealthCheckResponse()
            response.status = common_pb2.HealthCheckResponse.SERVING
            response.message = "TTS service operational"
            response.details["active_sessions"] = str(len(self.session_engines))
            response.details["test_response_time_ms"] = f"{response_time:.2f}"
            response.details["piper_url"] = self.default_tts_config["url"]
            response.details["default_voice"] = self.default_tts_config["voice"]
            response.details["available_voices"] = str(len(self.available_voices))
            
            logger.debug("TTS health check passed", response_time_ms=response_time)
            return response
            
        except Exception as e:
            logger.error("TTS health check failed", error=str(e))
            response = common_pb2.HealthCheckResponse()
            response.status = common_pb2.HealthCheckResponse.NOT_SERVING
            response.status.message = f"Health check failed: {str(e)}"
            return response
    
    async def _create_session_engine(self, session_id: str, config):
        """Create TTS engine for session"""
        try:
            # Use config or defaults
            engine_config = self.default_tts_config.copy()
            if config:
                if config.voice_name:
                    engine_config["voice"] = config.voice_name
                if config.voice_url:  # Custom URL if provided
                    engine_config["url"] = config.voice_url
                if config.audio_config and config.audio_config.sample_rate > 0:
                    engine_config["sample_rate"] = config.audio_config.sample_rate
            
            engine = PiperTTSEngine(**engine_config)
            await engine.connect()
            
            # Clean up old engine if exists
            if session_id in self.session_engines:
                await self.session_engines[session_id].disconnect()
            
            self.session_engines[session_id] = engine
            self.session_stats[session_id] = {
                'created_at': time.time(),
                'total_requests': 0,
                'successful_syntheses': 0,
                'total_characters': 0,
                'avg_processing_time': 0.0
            }
            
            logger.info("TTS engine created for session",
                       session_id=session_id,
                       voice=engine_config["voice"],
                       sample_rate=engine_config["sample_rate"])
            
        except Exception as e:
            logger.error("Failed to create TTS engine", session_id=session_id, error=str(e))
            raise
    
    def _update_session_stats(self, session_id: str, piper_result: Dict[str, Any], processing_time: float):
        """Update session statistics"""
        if session_id in self.session_stats:
            stats = self.session_stats[session_id]
            stats['total_requests'] += 1
            
            if "audio" in piper_result:
                stats['successful_syntheses'] += 1
                stats['total_characters'] += len(piper_result.get("text", ""))
            
            # Update average processing time
            total_time = stats['avg_processing_time'] * (stats['total_requests'] - 1)
            stats['avg_processing_time'] = (total_time + processing_time) / stats['total_requests']


async def serve():
    """Start the TTS gRPC server"""
    server = aio_grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    
    # Add TTS service
    tts_service_pb2_grpc.add_TTSServiceServicer_to_server(TTSServiceImpl(), server)
    
    # Configure server
    listen_addr = '[::]:50055'
    server.add_insecure_port(listen_addr)
    
    # Start server
    await server.start()
    logger.info("TTS Service started", address=listen_addr, voice="tr_TR-dfki-medium")
    
    try:
        await server.wait_for_termination()
    except KeyboardInterrupt:
        logger.info("TTS Service shutting down")
        await server.stop(grace=30)


if __name__ == '__main__':
    asyncio.run(serve())