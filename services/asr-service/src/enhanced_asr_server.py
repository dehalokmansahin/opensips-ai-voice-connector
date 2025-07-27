#!/usr/bin/env python3
"""
Enhanced ASR Service - Integrated with new architecture
Uses common service base and improved configuration
"""

import asyncio
import json
import os
import sys
import time
import uuid
from pathlib import Path
from typing import Optional, Dict, Any

# Add common services to path
sys.path.append(str(Path(__file__).parent.parent.parent / "common"))

from service_base import BaseService, ServiceConfig

# Native Vosk imports
from vosk import Model, KaldiRecognizer

# gRPC imports
try:
    from . import asr_service_pb2
    from . import asr_service_pb2_grpc
except ImportError:
    import asr_service_pb2
    import asr_service_pb2_grpc

class ASRServiceConfig(ServiceConfig):
    """ASR service configuration"""
    
    def _load_service_config(self):
        """Load ASR-specific configuration"""
        self.model_path = os.getenv('VOSK_MODEL_PATH', 'model')
        self.sample_rate = float(os.getenv('VOSK_SAMPLE_RATE', '16000'))
        self.default_show_words = os.getenv('VOSK_SHOW_WORDS', 'true').lower() == 'true'
        self.max_alternatives = int(os.getenv('VOSK_MAX_ALTERNATIVES', '0'))

class NativeVoskASREngine:
    """Native Vosk ASR engine"""
    
    def __init__(self, model_path: str = "model", sample_rate: float = 16000):
        self.model_path = model_path
        self.sample_rate = sample_rate
        
        # Load Vosk model
        self.model = Model(model_path)
    
    def create_recognizer(self, sample_rate: float = None, config: Dict[str, Any] = None) -> KaldiRecognizer:
        """Create a new recognizer instance"""
        if sample_rate is None:
            sample_rate = self.sample_rate
        
        if config and config.get('phrase_list'):
            recognizer = KaldiRecognizer(
                self.model, 
                sample_rate, 
                json.dumps(config['phrase_list'], ensure_ascii=False)
            )
        else:
            recognizer = KaldiRecognizer(self.model, sample_rate)
        
        if config:
            recognizer.SetWords(config.get('show_words', True))
            recognizer.SetMaxAlternatives(config.get('max_alternatives', 0))
        
        return recognizer
    
    def process_audio_chunk(self, recognizer: KaldiRecognizer, audio_data: bytes) -> Dict[str, Any]:
        """Process audio chunk and return result"""
        try:
            if recognizer.AcceptWaveform(audio_data):
                result_json = recognizer.Result()
                return json.loads(result_json)
            else:
                partial_json = recognizer.PartialResult()
                return json.loads(partial_json)
        except Exception as e:
            return {"error": str(e)}
    
    def finalize_recognition(self, recognizer: KaldiRecognizer) -> Dict[str, Any]:
        """Get final recognition result"""
        try:
            final_json = recognizer.FinalResult()
            return json.loads(final_json)
        except Exception as e:
            return {"error": str(e)}

class ASRServiceImpl(asr_service_pb2_grpc.ASRServiceServicer):
    """Enhanced ASR Service implementation"""
    
    def __init__(self, base_service: 'ASRService'):
        self.base_service = base_service
        self.vosk_engine = base_service.vosk_engine
        self.logger = base_service.logger
    
    async def StreamingRecognize(self, request_iterator, context):
        """Streaming recognition with enhanced logging"""
        recognizer = None
        session_id = str(uuid.uuid4())
        
        try:
            self.base_service.increment_request_count()
            self.logger.info(f"🎤 New ASR streaming session: {session_id}")
            
            config_received = False
            
            async for request in request_iterator:
                if request.HasField('config'):
                    # Handle configuration
                    config = {
                        "sample_rate": request.config.sample_rate or 16000,
                        "model_path": request.config.model_path or "model",
                        "show_words": request.config.show_words,
                        "max_alternatives": request.config.max_alternatives or 0,
                        "phrase_list": list(request.config.phrase_list) if request.config.phrase_list else None
                    }
                    
                    recognizer = self.vosk_engine.create_recognizer(
                        sample_rate=config["sample_rate"],
                        config=config
                    )
                    config_received = True
                    self.logger.debug(f"🎤 ASR config received: {config}")
                    
                elif request.HasField('audio_data'):
                    # Process audio data
                    if not config_received or not recognizer:
                        recognizer = self.vosk_engine.create_recognizer()
                        config_received = True
                    
                    result = self.vosk_engine.process_audio_chunk(recognizer, request.audio_data)
                    
                    # Send response
                    response = asr_service_pb2.StreamingRecognizeResponse()
                    
                    if "text" in result and result["text"]:
                        response.result.text = result["text"]
                        response.result.confidence = 0.9
                        response.is_final = True
                        response.end_of_utterance = False
                        self.logger.debug(f"🎤 Final ASR result: {result['text']}")
                        
                    elif "partial" in result and result["partial"]:
                        response.result.text = result["partial"]
                        response.result.confidence = 0.7
                        response.is_final = False
                        response.end_of_utterance = False
                        
                    elif "error" in result:
                        response.result.text = ""
                        response.result.confidence = 0.0
                        response.is_final = True
                        response.end_of_utterance = True
                        self.logger.error(f"ASR error: {result['error']}")
                        self.base_service.increment_error_count()
                        
                    else:
                        response.result.text = ""
                        response.result.confidence = 0.0
                        response.is_final = False
                        response.end_of_utterance = False
                    
                    # Add word-level information if available
                    if "result" in result and isinstance(result["result"], list):
                        for word_info in result["result"]:
                            if isinstance(word_info, dict) and "word" in word_info:
                                word = response.result.words.add()
                                word.word = word_info["word"]
                                word.confidence = word_info.get("conf", 0.9)
                                word.start = word_info.get("start", 0.0)
                                word.end = word_info.get("end", 0.0)
                    
                    yield response
                    
                elif request.HasField('control_message'):
                    # Handle control messages
                    try:
                        control = json.loads(request.control_message)
                        
                        if control.get("eof") == 1:
                            if recognizer:
                                final_result = self.vosk_engine.finalize_recognition(recognizer)
                                
                                response = asr_service_pb2.StreamingRecognizeResponse()
                                if final_result and "text" in final_result:
                                    response.result.text = final_result["text"]
                                    response.result.confidence = 0.9
                                    self.logger.debug(f"🎤 Final result after EOF: {final_result['text']}")
                                else:
                                    response.result.text = ""
                                    response.result.confidence = 0.0
                                
                                response.is_final = True
                                response.end_of_utterance = True
                                yield response
                            break
                            
                        elif control.get("reset") == 1:
                            if recognizer:
                                final_result = self.vosk_engine.finalize_recognition(recognizer)
                                recognizer = self.vosk_engine.create_recognizer()
                                self.logger.debug("🎤 ASR recognizer reset")
                                
                    except json.JSONDecodeError:
                        self.logger.warning(f"Invalid control message: {request.control_message}")
                        
        except Exception as e:
            self.logger.error(f"🎤 StreamingRecognize error: {e}")
            self.base_service.increment_error_count()
            response = asr_service_pb2.StreamingRecognizeResponse()
            response.result.text = ""
            response.is_final = True
            response.end_of_utterance = True
            yield response
        
        finally:
            self.logger.info(f"🎤 ASR streaming session ended: {session_id}")
    
    async def Recognize(self, request, context):
        """Single shot recognition with enhanced logging"""
        try:
            self.base_service.increment_request_count()
            
            config = {
                "sample_rate": request.config.sample_rate or 16000,
                "show_words": request.config.show_words
            }
            
            recognizer = self.vosk_engine.create_recognizer(
                sample_rate=config["sample_rate"],
                config=config
            )
            
            result = self.vosk_engine.process_audio_chunk(recognizer, request.audio_data)
            final_result = self.vosk_engine.finalize_recognition(recognizer)
            
            response = asr_service_pb2.RecognizeResponse()
            
            if final_result and "text" in final_result and final_result["text"]:
                response.result.text = final_result["text"]
                response.result.confidence = 0.9
                self.logger.debug(f"🎤 Single recognition result: {final_result['text']}")
            else:
                response.result.text = ""
                response.result.confidence = 0.0
            
            return response
            
        except Exception as e:
            self.logger.error(f"🎤 Single recognition error: {e}")
            self.base_service.increment_error_count()
            response = asr_service_pb2.RecognizeResponse()
            response.result.text = ""
            response.result.confidence = 0.0
            return response
    
    async def Configure(self, request, context):
        """Configure recognition parameters"""
        response = asr_service_pb2.ConfigureResponse()
        response.success = True
        response.message = "Configuration accepted"
        return response
    
    async def HealthCheck(self, request, context):
        """Health check with enhanced status"""
        try:
            health_info = await self.base_service.health_check()
            
            response = asr_service_pb2.HealthResponse()
            response.status = (asr_service_pb2.HealthResponse.Status.SERVING 
                             if health_info['status'] == 'SERVING' 
                             else asr_service_pb2.HealthResponse.Status.NOT_SERVING)
            response.message = health_info['message']
            response.model_loaded = os.path.basename(self.vosk_engine.model_path)
            
            return response
            
        except Exception as e:
            self.logger.error(f"Health check failed: {e}")
            response = asr_service_pb2.HealthResponse()
            response.status = asr_service_pb2.HealthResponse.Status.NOT_SERVING
            response.message = f"Health check error: {e}"
            return response
    
    async def GetStats(self, request, context):
        """Get service statistics"""
        stats = self.base_service.get_stats()
        
        response = asr_service_pb2.StatsResponse()
        response.total_connections = stats['total_requests']
        response.uptime_seconds = stats['uptime_seconds']
        response.model_info = os.path.basename(self.vosk_engine.model_path)
        return response

class ASRService(BaseService):
    """Enhanced ASR Service using common base"""
    
    def __init__(self):
        config = ASRServiceConfig('asr')
        super().__init__('asr', config)
        self.vosk_engine: Optional[NativeVoskASREngine] = None
    
    async def initialize(self):
        """Initialize ASR service components"""
        try:
            self.logger.info("🔄 Loading Vosk model...")
            self.vosk_engine = NativeVoskASREngine(
                model_path=self.config.model_path,
                sample_rate=self.config.sample_rate
            )
            self.logger.info("✅ Vosk model loaded successfully!")
            
        except Exception as e:
            self.logger.error(f"❌ Failed to initialize ASR service: {e}")
            raise
    
    def create_servicer(self):
        """Create ASR servicer"""
        return ASRServiceImpl(self)
    
    def add_servicer_to_server(self, servicer, server):
        """Add ASR servicer to server"""
        asr_service_pb2_grpc.add_ASRServiceServicer_to_server(servicer, server)
    
    async def _service_specific_health_check(self) -> Dict[str, Any]:
        """ASR-specific health check"""
        try:
            if not self.vosk_engine:
                return {
                    'healthy': False,
                    'message': 'Vosk engine not initialized',
                    'details': {}
                }
            
            # Test recognition with silence
            recognizer = self.vosk_engine.create_recognizer()
            test_audio = b'\\x00' * 3200  # 100ms of silence at 16kHz
            result = self.vosk_engine.process_audio_chunk(recognizer, test_audio)
            
            return {
                'healthy': True,
                'message': 'ASR service healthy',
                'details': {
                    'model_path': self.vosk_engine.model_path,
                    'sample_rate': self.vosk_engine.sample_rate,
                    'test_result': 'passed'
                }
            }
            
        except Exception as e:
            return {
                'healthy': False,
                'message': f'ASR health check failed: {e}',
                'details': {'error': str(e)}
            }

async def main():
    """Main entry point"""
    service = ASRService()
    await service.start()

if __name__ == '__main__':
    asyncio.run(main())