"""
VAD Service - Voice Activity Detection Microservice
Extracted from working legacy implementation using SileroVADAnalyzer
"""

import asyncio
import logging
import sys
from typing import Dict, Any, Optional
import time

import structlog
import grpc
from grpc import aio as aio_grpc
from concurrent import futures
import numpy as np

# Pipecat VAD imports - proven working from legacy
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.audio.vad.vad_analyzer import VADParams, VADState

# Generated gRPC code (will be created by proto-gen.sh)
from shared.proto_generated import common_pb2
try:
    from . import vad_service_pb2
    from . import vad_service_pb2_grpc
except ImportError:
    # Fallback for development
    import sys
    sys.path.append('.')
    import vad_service_pb2
    import vad_service_pb2_grpc

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


class VADServiceImpl(vad_service_pb2_grpc.VADServiceServicer):
    """VAD Service gRPC implementation using proven SileroVADAnalyzer"""
    
    def __init__(self):
        # VAD analyzers per session (like legacy implementation)
        self.session_analyzers: Dict[str, SileroVADAnalyzer] = {}
        self.session_stats: Dict[str, Dict[str, Any]] = {}
        
        logger.info("VAD Service initialized with SileroVADAnalyzer")
    
    async def DetectVoiceActivity(self, request, context):
        """Process single audio chunk for voice activity detection"""
        try:
            session_id = request.session_id
            audio_chunk = request.audio_chunk
            config = request.config
            
            start_time = time.time()
            
            # Get or create VAD analyzer for session
            if session_id not in self.session_analyzers:
                await self._create_session_analyzer(session_id, config)
            
            analyzer = self.session_analyzers[session_id]
            
            # Convert protobuf audio to bytes (same format as legacy)
            audio_data = audio_chunk.data
            sample_rate = audio_chunk.config.sample_rate
            
            logger.debug("Processing VAD audio chunk",
                        session_id=session_id,
                        audio_size=len(audio_data),
                        sample_rate=sample_rate)
            
            # Analyze audio using proven Silero VAD (same as legacy)
            vad_state = await asyncio.get_event_loop().run_in_executor(
                None, analyzer.analyze_audio, audio_data
            )
            
            # Calculate audio properties (same analysis as legacy)
            audio_properties = self._analyze_audio_properties(audio_data)
            
            # Create VAD result
            processing_time = (time.time() - start_time) * 1000
            
            # Update session stats
            self._update_session_stats(session_id, vad_state, processing_time)
            
            # Convert VAD state to protobuf response
            response = vad_service_pb2.DetectVoiceActivityResponse()
            response.status.code = common_pb2.Status.OK
            response.session_id = session_id
            
            # VAD result
            response.result.voice_detected = (vad_state == VADState.SPEAKING)
            response.result.confidence = analyzer.params.confidence
            
            # Voice activity type
            if vad_state == VADState.SPEAKING:
                response.result.activity.type = vad_service_pb2.VoiceActivity.VOICE_CONTINUE
            else:
                response.result.activity.type = vad_service_pb2.VoiceActivity.SILENCE
            
            response.result.activity.duration_ms = processing_time
            
            # Audio properties
            response.result.audio_properties.volume_level = audio_properties['volume_level']
            response.result.audio_properties.signal_to_noise_ratio = audio_properties['snr']
            response.result.audio_properties.clipping_detected = audio_properties['clipping']
            
            # Metrics
            response.metrics.processing_time_ms = processing_time
            response.metrics.audio_chunk_duration_ms = len(audio_data) / (sample_rate * 2) * 1000  # 16-bit PCM
            response.metrics.samples_processed = len(audio_data) // 2
            response.metrics.model_version = "silero_v4"
            
            logger.debug("VAD analysis completed",
                        session_id=session_id,
                        voice_detected=response.result.voice_detected,
                        processing_time_ms=processing_time)
            
            return response
            
        except Exception as e:
            logger.error("VAD analysis failed", session_id=session_id, error=str(e))
            response = vad_service_pb2.DetectVoiceActivityResponse()
            response.status.code = common_pb2.Status.INTERNAL
            response.status.message = f"VAD analysis failed: {str(e)}"
            return response
    
    async def DetectVoiceActivityStream(self, request_iterator, context):
        """Stream-based VAD processing (same pattern as legacy)"""
        session_id = None
        
        try:
            async for request in request_iterator:
                session_id = request.session_id
                
                # Process each chunk
                response = await self.DetectVoiceActivity(request, context)
                yield response
                
        except Exception as e:
            logger.error("VAD stream processing failed", session_id=session_id, error=str(e))
            response = vad_service_pb2.DetectVoiceActivityResponse()
            response.status.code = common_pb2.Status.INTERNAL
            response.status.message = f"VAD stream failed: {str(e)}"
            yield response
    
    async def ConfigureVAD(self, request, context):
        """Configure VAD parameters for a session"""
        try:
            session_id = request.session_id
            config = request.config
            
            # Create new analyzer with updated config
            await self._create_session_analyzer(session_id, config)
            
            response = vad_service_pb2.ConfigureVADResponse()
            response.status.code = common_pb2.Status.OK
            
            logger.info("VAD configuration updated", session_id=session_id)
            return response
            
        except Exception as e:
            logger.error("VAD configuration failed", session_id=session_id, error=str(e))
            response = vad_service_pb2.ConfigureVADResponse()
            response.status.code = common_pb2.Status.INTERNAL
            response.status.message = f"Configuration failed: {str(e)}"
            return response
    
    async def HealthCheck(self, request, context):
        """Health check implementation"""
        try:
            service_name = request.service or "vad-service"
            
            # Check if Silero VAD is working
            test_audio = np.random.randint(-1000, 1000, 320, dtype=np.int16).tobytes()  # 20ms at 16kHz
            
            # Create test analyzer
            test_analyzer = SileroVADAnalyzer(
                params=VADParams(confidence=0.3, start_secs=0.05, stop_secs=0.3)
            )
            
            # Test VAD analysis
            start_time = time.time()
            vad_state = await asyncio.get_event_loop().run_in_executor(
                None, test_analyzer.analyze_audio, test_audio
            )
            response_time = (time.time() - start_time) * 1000
            
            response = common_pb2.HealthCheckResponse()
            response.status = common_pb2.HealthCheckResponse.SERVING
            response.message = "VAD service operational"
            response.details["active_sessions"] = str(len(self.session_analyzers))
            response.details["test_response_time_ms"] = f"{response_time:.2f}"
            response.details["model_type"] = "silero_v4"
            
            logger.debug("VAD health check passed", response_time_ms=response_time)
            return response
            
        except Exception as e:
            logger.error("VAD health check failed", error=str(e))
            response = common_pb2.HealthCheckResponse()
            response.status = common_pb2.HealthCheckResponse.NOT_SERVING
            response.message = f"Health check failed: {str(e)}"
            return response
    
    async def _create_session_analyzer(self, session_id: str, config):
        """Create VAD analyzer for session (same params as legacy)"""
        try:
            # Use same optimized params as legacy implementation
            vad_params = VADParams(
                confidence=config.confidence_threshold if config else 0.15,  # Very sensitive like legacy
                start_secs=config.start_threshold_seconds if config else 0.1,  # 100ms like legacy
                stop_secs=config.stop_threshold_seconds if config else 0.25,   # 250ms like legacy
                min_volume=config.min_volume_threshold if config else 0.0     # Disable volume gating like legacy
            )
            
            analyzer = SileroVADAnalyzer(params=vad_params)
            
            self.session_analyzers[session_id] = analyzer
            self.session_stats[session_id] = {
                'created_at': time.time(),
                'total_chunks': 0,
                'voice_chunks': 0,
                'silence_chunks': 0,
                'avg_processing_time': 0.0
            }
            
            logger.info("VAD analyzer created for session",
                       session_id=session_id,
                       confidence=vad_params.confidence,
                       start_secs=vad_params.start_secs,
                       stop_secs=vad_params.stop_secs)
            
        except Exception as e:
            logger.error("Failed to create VAD analyzer", session_id=session_id, error=str(e))
            raise
    
    def _analyze_audio_properties(self, audio_data: bytes) -> Dict[str, Any]:
        """Analyze audio properties (same analysis as legacy)"""
        try:
            # Convert to numpy array (same as legacy)
            audio_array = np.frombuffer(audio_data, dtype=np.int16)
            
            if len(audio_array) == 0:
                return {
                    'volume_level': 0.0,
                    'snr': 0.0,
                    'clipping': False
                }
            
            # Calculate RMS volume (same as legacy)
            audio_rms = np.sqrt(np.mean(audio_array.astype(np.float32) ** 2))
            volume_level = audio_rms / 32768.0  # Normalize to 0-1
            
            # Simple SNR estimation
            audio_max = np.max(np.abs(audio_array))
            noise_floor = np.std(audio_array) * 0.1  # Rough noise estimation
            snr = audio_max / max(noise_floor, 1.0)
            
            # Clipping detection
            clipping = (audio_max >= 32767) or (np.min(audio_array) <= -32768)
            
            return {
                'volume_level': float(volume_level),
                'snr': float(snr),
                'clipping': bool(clipping)
            }
            
        except Exception as e:
            logger.error("Audio analysis failed", error=str(e))
            return {
                'volume_level': 0.0,
                'snr': 0.0, 
                'clipping': False
            }
    
    def _update_session_stats(self, session_id: str, vad_state: VADState, processing_time: float):
        """Update session statistics"""
        if session_id in self.session_stats:
            stats = self.session_stats[session_id]
            stats['total_chunks'] += 1
            
            if vad_state == VADState.SPEAKING:
                stats['voice_chunks'] += 1
            else:
                stats['silence_chunks'] += 1
            
            # Update average processing time
            total_time = stats['avg_processing_time'] * (stats['total_chunks'] - 1)
            stats['avg_processing_time'] = (total_time + processing_time) / stats['total_chunks']


async def serve():
    """Start the VAD gRPC server"""
    server = aio_grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    
    # Add VAD service
    vad_service_pb2_grpc.add_VADServiceServicer_to_server(VADServiceImpl(), server)
    
    # Configure server
    listen_addr = '[::]:50052'
    server.add_insecure_port(listen_addr)
    
    # Start server
    await server.start()
    logger.info("VAD Service started", address=listen_addr, model="silero_v4")
    
    try:
        await server.wait_for_termination()
    except KeyboardInterrupt:
        logger.info("VAD Service shutting down")
        await server.stop(grace=30)


if __name__ == '__main__':
    asyncio.run(serve())