#!/usr/bin/env python3
"""
Native gRPC TTS Service - Converted from legacy WebSocket implementation
Based on C:\Cursor\piper-tts working implementation
"""

import asyncio
import json
import logging
import os
import sys
import time
import io
from concurrent import futures
from pathlib import Path
from typing import Optional

import grpc
from grpc import aio as aio_grpc
import numpy as np

# Native Piper imports (from your working legacy)
from piper import PiperVoice

# gRPC imports - using simplified proto
try:
    from . import tts_service_pb2
    from . import tts_service_pb2_grpc
except ImportError:
    # Use simplified proto file
    sys.path.append(os.path.dirname(__file__))
    import tts_service_pb2
    import tts_service_pb2_grpc

# Configure logging (same as legacy)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("piper-tts-grpc")


class NativePiperTTSEngine:
    """Native Piper TTS engine using piper library directly (from legacy)"""
    
    def __init__(self, model_dir: str = "model", model_name: str = "tr_TR-fahrettin-medium", sample_rate: int = 22050):
        """Initialize Piper TTS engine with model loading (same as legacy)"""
        self.model_dir = Path(model_dir)
        self.model_name = model_name
        self.sample_rate = sample_rate
        
        # Model paths (same as legacy)
        self.model_path = self.model_dir / f"{model_name}.onnx"
        self.config_path = self.model_dir / f"{model_name}.onnx.json"
        
        logger.info(f"🔄 Loading Piper model: {self.model_path}")
        logger.info(f"🔄 Loading config: {self.config_path}")
        
        # Validate files exist (same as legacy)
        if not self.model_path.exists():
            raise FileNotFoundError(f"Model file not found: {self.model_path}")
        
        if not self.config_path.exists():
            raise FileNotFoundError(f"Config file not found: {self.config_path}")
        
        try:
            # Load Piper voice (same as legacy)
            self.voice = PiperVoice.load(
                str(self.model_path),
                config_path=str(self.config_path)
            )
            logger.info("✅ Piper model loaded successfully!")
        except Exception as e:
            logger.error(f"❌ Failed to load Piper model: {e}")
            raise
    
    def synthesize_to_chunks(self, text: str) -> list[bytes]:
        """Synthesize text and return audio chunks (adapted from legacy streaming logic)"""
        try:
            logger.info(f"🎵 Synthesizing text with Piper: '{text[:50]}{'...' if len(text) > 50 else ''}'")
            
            # Get voice config sample rate (same as legacy)
            voice_sample_rate = self.voice.config.sample_rate  # Usually 22050 Hz
            
            # Use synthesize_stream_raw for streaming audio (same as legacy)
            audio_stream = self.voice.synthesize_stream_raw(text)
            raw_audio = b"".join(audio_stream)  # Combine all audio bytes
            
            # Calculate 20ms chunks for RTP (same logic as legacy)
            samples_per_packet = int(voice_sample_rate * 0.02)  # 20ms worth of samples
            bytes_per_sample = 2  # 16-bit mono
            bytes_per_packet = samples_per_packet * bytes_per_sample
            
            # Split into chunks (same as legacy)
            audio_chunks = []
            for i in range(0, len(raw_audio), bytes_per_packet):
                chunk = raw_audio[i:i+bytes_per_packet]
                if chunk:
                    audio_chunks.append(chunk)
            
            # Audio statistics (same as legacy)
            total_samples = len(raw_audio) // bytes_per_sample
            audio_duration = total_samples / voice_sample_rate
            
            logger.info(f"🎵 Synthesis complete: {audio_duration:.2f}s, {len(audio_chunks)} chunks")
            logger.info(f"📊 Audio: {len(raw_audio)} bytes, {voice_sample_rate} Hz, 16-bit mono")
            
            return audio_chunks
            
        except Exception as e:
            logger.error(f"❌ Synthesis failed: {e}")
            raise


class TTSServiceImpl(tts_service_pb2_grpc.TTSServiceServicer):
    """Native gRPC TTS Service implementation"""
    
    def __init__(self):
        # Initialize the shared Piper model (same as legacy approach)
        self.piper_engine = None
        self._initialize_model()
        
        self.start_time = time.time()
        self.total_syntheses = 0
        
        logger.info("🎵 Native TTS Service initialized with shared Piper model")
    
    def _initialize_model(self):
        """Initialize the shared Piper model instance (same pattern as legacy)"""
        try:
            logger.info("🔄 Pre-loading Piper TTS model (this happens ONLY ONCE)...")
            
            # Model configuration from environment or defaults (same as legacy)
            model_dir = os.getenv('PIPER_MODEL_DIR', 'model')
            model_name = os.getenv('PIPER_MODEL_NAME', 'tr_TR-fahrettin-medium')
            sample_rate = int(os.getenv('PIPER_SAMPLE_RATE', '22050'))
            
            self.piper_engine = NativePiperTTSEngine(
                model_dir=model_dir,
                model_name=model_name,
                sample_rate=sample_rate
            )
            
            logger.info("✅ Piper TTS model loaded and ready! All future gRPC calls will use this shared instance.")
        except Exception as e:
            logger.error(f"❌ Failed to initialize Piper model: {e}")
            raise
    
    async def SynthesizeText(self, request, context):
        """Synthesize text to speech (streaming audio chunks)"""
        try:
            text = request.text
            voice = request.voice or "tr_TR-fahrettin-medium"
            sample_rate = request.sample_rate or 22050
            
            if not text or not text.strip():
                # Send error response
                error_response = tts_service_pb2.SynthesizeResponse()
                error_response.error.error_message = "Empty text provided"
                error_response.error.error_code = "EMPTY_TEXT"
                yield error_response
                return
            
            logger.info(f"🎵 TTS request: '{text[:50]}...', voice: {voice}")
            
            self.total_syntheses += 1
            start_time = time.time()
            
            # Send synthesis started signal (matching legacy WebSocket pattern)
            started_response = tts_service_pb2.SynthesizeResponse()
            started_response.started.message = "Starting audio stream"
            started_response.started.audio_info.sample_rate = sample_rate
            started_response.started.audio_info.channels = 1
            started_response.started.audio_info.bit_depth = 16
            started_response.started.audio_info.format = f"PCM 16-bit mono, {sample_rate} Hz"
            yield started_response
            
            # Generate audio chunks using shared Piper model (same as legacy)
            audio_chunks = self.piper_engine.synthesize_to_chunks(text)
            
            # Stream audio chunks (same as legacy)
            for chunk in audio_chunks:
                chunk_response = tts_service_pb2.SynthesizeResponse()
                chunk_response.audio_chunk = chunk
                yield chunk_response
            
            # Send synthesis completed signal (matching legacy WebSocket pattern)
            processing_time = (time.time() - start_time) * 1000
            total_bytes = sum(len(chunk) for chunk in audio_chunks)
            audio_duration = total_bytes / (sample_rate * 2)  # 16-bit mono
            
            completed_response = tts_service_pb2.SynthesizeResponse()
            completed_response.completed.message = "Audio stream complete"
            completed_response.completed.stats.audio_duration_seconds = audio_duration
            completed_response.completed.stats.total_bytes = total_bytes
            completed_response.completed.stats.packet_count = len(audio_chunks)
            completed_response.completed.stats.processing_time_ms = processing_time
            yield completed_response
            
            logger.info(f"✅ TTS synthesis completed: {processing_time:.2f}ms, {len(audio_chunks)} chunks")
            
        except Exception as e:
            logger.error(f"❌ TTS synthesis error: {e}")
            error_response = tts_service_pb2.SynthesizeResponse()
            error_response.error.error_message = f"Synthesis error: {str(e)}"
            error_response.error.error_code = "SYNTHESIS_ERROR"
            yield error_response
    
    async def SynthesizeSingle(self, request, context):
        """Single shot synthesis (for small texts)"""
        # Collect all chunks into a single response
        chunks = []
        async for response in self.SynthesizeText(request, context):
            if response.HasField('audio_chunk'):
                chunks.append(response.audio_chunk)
            elif response.HasField('error'):
                return response
        
        # Combine all audio chunks
        combined_audio = b''.join(chunks)
        
        single_response = tts_service_pb2.SynthesizeResponse()
        single_response.audio_chunk = combined_audio
        return single_response
    
    async def Configure(self, request, context):
        """Configure TTS parameters"""
        response = tts_service_pb2.ConfigureResponse()
        response.success = True
        response.message = f"Configuration accepted for voice: {request.voice}"
        return response
    
    async def GetVoices(self, request, context):
        """Get available voices"""
        response = tts_service_pb2.VoicesResponse()
        
        # Add available Turkish voices (same as legacy)
        voice1 = response.voices.add()
        voice1.name = "tr_TR-fahrettin-medium"
        voice1.display_name = "Turkish Male (Fahrettin)"
        voice1.language = "tr-TR"
        voice1.gender = "MALE"
        voice1.description = "Turkish male voice, medium quality"
        voice1.supported_rates.extend([16000, 22050, 44100])
        
        voice2 = response.voices.add()
        voice2.name = "tr_TR-dfki-medium"
        voice2.display_name = "Turkish Female (DFKI)"
        voice2.language = "tr-TR"
        voice2.gender = "FEMALE"
        voice2.description = "Turkish female voice, medium quality"
        voice2.supported_rates.extend([16000, 22050, 44100])
        
        return response
    
    async def HealthCheck(self, request, context):
        """Health check"""
        try:
            # Test synthesis with short text
            test_chunks = self.piper_engine.synthesize_to_chunks("Test")
            
            response = tts_service_pb2.HealthResponse()
            if test_chunks:
                response.status = tts_service_pb2.HealthResponse.Status.SERVING
                response.message = "TTS service healthy"
                response.voice_model = self.piper_engine.model_name
            else:
                response.status = tts_service_pb2.HealthResponse.Status.NOT_SERVING
                response.message = "Synthesis test failed"
                response.voice_model = ""
            
            return response
            
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            response = tts_service_pb2.HealthResponse()
            response.status = tts_service_pb2.HealthResponse.Status.NOT_SERVING
            response.message = f"Health check error: {e}"
            return response
    
    async def GetStats(self, request, context):
        """Get service statistics"""
        response = tts_service_pb2.StatsResponse()
        response.total_syntheses = self.total_syntheses
        response.uptime_seconds = int(time.time() - self.start_time)
        response.voice_model = self.piper_engine.model_name
        return response


async def serve():
    """Start the native gRPC TTS server"""
    server = aio_grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    
    # Add TTS service
    tts_service_pb2_grpc.add_TTSServiceServicer_to_server(TTSServiceImpl(), server)
    
    # Listen on port
    listen_addr = os.getenv('TTS_SERVICE_LISTEN_ADDR', '[::]:50053')
    server.add_insecure_port(listen_addr)
    
    # Start server
    await server.start()
    logger.info(f"🎵 Native TTS Service started on {listen_addr}")
    logger.info(f"📊 Piper model loaded and ready for synthesis")
    
    try:
        await server.wait_for_termination()
    except KeyboardInterrupt:
        logger.info("🛑 TTS Service shutting down")
        await server.stop(grace=30)


if __name__ == '__main__':
    asyncio.run(serve())