#!/usr/bin/env python3
"""
Enhanced TTS Service - Integrated with new architecture
Uses common service base and improved configuration
"""

import asyncio
import json
import os
import sys
import time
import io
from pathlib import Path
from typing import Optional, Dict, Any

# Add common services to path
sys.path.append(str(Path(__file__).parent.parent.parent / "common"))

from service_base import BaseService, ServiceConfig

import numpy as np

# Native Piper imports
from piper import PiperVoice

# gRPC imports
try:
    from . import tts_service_pb2
    from . import tts_service_pb2_grpc
except ImportError:
    import tts_service_pb2
    import tts_service_pb2_grpc

class TTSServiceConfig(ServiceConfig):
    """TTS service configuration"""
    
    def _load_service_config(self):
        """Load TTS-specific configuration"""
        self.model_dir = os.getenv('PIPER_MODEL_DIR', 'model')
        self.model_name = os.getenv('PIPER_MODEL_NAME', 'tr_TR-fahrettin-medium')
        self.sample_rate = int(os.getenv('PIPER_SAMPLE_RATE', '22050'))
        self.default_voice = os.getenv('PIPER_DEFAULT_VOICE', 'tr_TR-fahrettin-medium')

class NativePiperTTSEngine:
    """Native Piper TTS engine using piper library directly"""
    
    def __init__(self, config: TTSServiceConfig):
        self.config = config
        self.model_dir = Path(config.model_dir)
        self.model_name = config.model_name
        self.sample_rate = config.sample_rate
        
        # Load voice model
        self.voice: Optional[PiperVoice] = None
        self._load_voice()
    
    def _load_voice(self):
        """Load the Piper voice model"""
        try:
            model_file = self.model_dir / f"{self.model_name}.onnx"
            config_file = self.model_dir / f"{self.model_name}.onnx.json"
            
            if not model_file.exists():
                raise FileNotFoundError(f"Model file not found: {model_file}")
            if not config_file.exists():
                raise FileNotFoundError(f"Config file not found: {config_file}")
            
            self.voice = PiperVoice.load(str(model_file), str(config_file))
            
        except Exception as e:
            raise Exception(f"Failed to load Piper voice model: {e}")
    
    def synthesize_text(self, text: str, voice: str = None) -> bytes:
        """Synthesize text to audio"""
        if not self.voice:
            raise Exception("Voice model not loaded")
        
        if not text or not text.strip():
            return b''
        
        try:
            # Synthesize audio
            audio_stream = io.BytesIO()
            self.voice.synthesize(text.strip(), audio_stream)
            
            # Get audio data
            audio_data = audio_stream.getvalue()
            audio_stream.close()
            
            return audio_data
            
        except Exception as e:
            raise Exception(f"TTS synthesis failed: {e}")
    
    async def synthesize_stream(self, text: str, voice: str = None, chunk_size: int = 4096):
        """Stream audio synthesis"""
        try:
            # For now, synthesize all at once and chunk the result
            # In a more advanced implementation, you could stream synthesis
            audio_data = self.synthesize_text(text, voice)
            
            # Yield audio in chunks
            for i in range(0, len(audio_data), chunk_size):
                chunk = audio_data[i:i + chunk_size]
                yield chunk
                
        except Exception as e:
            raise Exception(f"TTS streaming synthesis failed: {e}")

class TTSServiceImpl(tts_service_pb2_grpc.TTSServiceServicer):
    """Enhanced TTS Service implementation"""
    
    def __init__(self, base_service: 'TTSService'):
        self.base_service = base_service
        self.tts_engine = base_service.tts_engine
        self.logger = base_service.logger
    
    async def Synthesize(self, request, context):
        """Single text synthesis with enhanced logging"""
        try:
            self.base_service.increment_request_count()
            
            text = request.text.strip()
            voice = request.voice or self.base_service.config.default_voice
            
            if not text:
                response = tts_service_pb2.SynthesizeResponse()
                response.audio_data = b''
                response.done = True
                return response
            
            self.logger.debug(f"🔊 Synthesizing text: {text[:100]}... (voice: {voice})")
            
            # Synthesize audio
            audio_data = self.tts_engine.synthesize_text(text, voice)
            
            # Create response
            response = tts_service_pb2.SynthesizeResponse()
            response.audio_data = audio_data
            response.done = True
            
            self.logger.debug(f"🔊 Synthesis completed: {len(audio_data)} bytes")
            
            return response
            
        except Exception as e:
            self.logger.error(f"🔊 Synthesis error: {e}")
            self.base_service.increment_error_count()
            
            response = tts_service_pb2.SynthesizeResponse()
            response.audio_data = b''
            response.done = True
            return response
    
    async def StreamSynthesize(self, request, context):
        """Streaming text synthesis with enhanced logging"""
        try:
            self.base_service.increment_request_count()
            
            text = request.text.strip()
            voice = request.voice or self.base_service.config.default_voice
            
            if not text:
                response = tts_service_pb2.StreamSynthesizeResponse()
                response.audio_chunk = b''
                response.done = True
                yield response
                return
            
            self.logger.debug(f"🔊 Streaming synthesis for text: {text[:100]}... (voice: {voice})")
            
            # Stream audio synthesis
            async for audio_chunk in self.tts_engine.synthesize_stream(text, voice):
                response = tts_service_pb2.StreamSynthesizeResponse()
                response.audio_chunk = audio_chunk
                response.done = False
                yield response
            
            # Send completion signal
            final_response = tts_service_pb2.StreamSynthesizeResponse()
            final_response.audio_chunk = b''
            final_response.done = True
            yield final_response
            
            self.logger.debug("🔊 Streaming synthesis completed")
            
        except Exception as e:
            self.logger.error(f"🔊 Streaming synthesis error: {e}")
            self.base_service.increment_error_count()
            
            error_response = tts_service_pb2.StreamSynthesizeResponse()
            error_response.audio_chunk = b''
            error_response.done = True
            yield error_response
    
    async def ListVoices(self, request, context):
        """List available voices"""
        response = tts_service_pb2.ListVoicesResponse()
        
        # Add available voices (this would be expanded in a real implementation)
        voice = response.voices.add()
        voice.name = self.base_service.config.default_voice
        voice.language = "tr-TR"
        voice.gender = "MALE"
        voice.sample_rate = self.base_service.config.sample_rate
        
        return response
    
    async def HealthCheck(self, request, context):
        """Health check with enhanced status"""
        try:
            health_info = await self.base_service.health_check()
            
            response = tts_service_pb2.HealthResponse()
            response.status = (tts_service_pb2.HealthResponse.Status.SERVING 
                             if health_info['status'] == 'SERVING' 
                             else tts_service_pb2.HealthResponse.Status.NOT_SERVING)
            response.message = health_info['message']
            response.model_loaded = self.base_service.tts_engine.model_name
            
            return response
            
        except Exception as e:
            self.logger.error(f"Health check failed: {e}")
            response = tts_service_pb2.HealthResponse()
            response.status = tts_service_pb2.HealthResponse.Status.NOT_SERVING
            response.message = f"Health check error: {e}"
            return response
    
    async def GetStats(self, request, context):
        """Get service statistics"""
        stats = self.base_service.get_stats()
        
        response = tts_service_pb2.StatsResponse()
        response.total_requests = stats['total_requests']
        response.uptime_seconds = stats['uptime_seconds']
        response.model_info = self.base_service.tts_engine.model_name
        return response

class TTSService(BaseService):
    """Enhanced TTS Service using common base"""
    
    def __init__(self):
        config = TTSServiceConfig('tts')
        super().__init__('tts', config)
        self.tts_engine: Optional[NativePiperTTSEngine] = None
    
    async def initialize(self):
        """Initialize TTS service components"""
        try:
            self.logger.info("🔄 Loading Piper TTS model...")
            self.tts_engine = NativePiperTTSEngine(self.config)
            self.logger.info("✅ Piper TTS model loaded successfully!")
            
        except Exception as e:
            self.logger.error(f"❌ Failed to initialize TTS service: {e}")
            raise
    
    def create_servicer(self):
        """Create TTS servicer"""
        return TTSServiceImpl(self)
    
    def add_servicer_to_server(self, servicer, server):
        """Add TTS servicer to server"""
        tts_service_pb2_grpc.add_TTSServiceServicer_to_server(servicer, server)
    
    async def _service_specific_health_check(self) -> Dict[str, Any]:
        """TTS-specific health check"""
        try:
            if not self.tts_engine or not self.tts_engine.voice:
                return {
                    'healthy': False,
                    'message': 'TTS voice model not loaded',
                    'details': {}
                }
            
            # Test synthesis with simple text
            test_audio = self.tts_engine.synthesize_text("Test")
            
            return {
                'healthy': True,
                'message': 'TTS service healthy',
                'details': {
                    'model_name': self.tts_engine.model_name,
                    'sample_rate': self.tts_engine.sample_rate,
                    'test_audio_size': len(test_audio) if test_audio else 0
                }
            }
            
        except Exception as e:
            return {
                'healthy': False,
                'message': f'TTS health check failed: {e}',
                'details': {'error': str(e)}
            }

async def main():
    """Main entry point"""
    service = TTSService()
    await service.start()

if __name__ == '__main__':
    asyncio.run(main())