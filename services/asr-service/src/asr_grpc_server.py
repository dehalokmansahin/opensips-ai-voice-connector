#!/usr/bin/env python3
"""
Native gRPC ASR Service - Converted from legacy WebSocket implementation
Based on C:\Cursor\vosk-server working implementation
"""

import asyncio
import json
import logging
import os
import sys
import time
import uuid
from concurrent import futures
from typing import Optional, Dict, Any

import grpc
from grpc import aio as aio_grpc

# Native Vosk imports (from your working legacy)
from vosk import Model, KaldiRecognizer

# gRPC imports - using simplified proto
try:
    from . import asr_service_pb2
    from . import asr_service_pb2_grpc
except ImportError:
    # Use simplified proto file
    sys.path.append(os.path.dirname(__file__))
    import asr_service_pb2
    import asr_service_pb2_grpc

# Configure logging (same as legacy)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("vosk-asr-grpc")


class NativeVoskASREngine:
    """Native Vosk ASR engine using vosk library directly (from legacy)"""
    
    def __init__(self, model_path: str = "model", sample_rate: float = 16000):
        """Initialize Vosk ASR engine with model loading (same as legacy)"""
        self.model_path = model_path
        self.sample_rate = sample_rate
        
        logger.info(f"🔄 Loading Vosk model from: {model_path}")
        logger.info(f"🔄 Sample rate: {sample_rate} Hz")
        
        try:
            # Load Vosk model (same as legacy)
            self.model = Model(model_path)
            logger.info("✅ Vosk model loaded successfully!")
        except Exception as e:
            logger.error(f"❌ Failed to load Vosk model: {e}")
            raise
    
    def create_recognizer(self, sample_rate: float = None, config: Dict[str, Any] = None) -> KaldiRecognizer:
        """Create a new recognizer instance (same as legacy pattern)"""
        if sample_rate is None:
            sample_rate = self.sample_rate
        
        # Create recognizer (same as legacy)
        if config and config.get('phrase_list'):
            # Use phrase list for better recognition (same as legacy)
            recognizer = KaldiRecognizer(
                self.model, 
                sample_rate, 
                json.dumps(config['phrase_list'], ensure_ascii=False)
            )
        else:
            recognizer = KaldiRecognizer(self.model, sample_rate)
        
        # Configure recognizer options (same as legacy)
        if config:
            recognizer.SetWords(config.get('show_words', True))
            recognizer.SetMaxAlternatives(config.get('max_alternatives', 0))
        
        return recognizer
    
    def process_audio_chunk(self, recognizer: KaldiRecognizer, audio_data: bytes) -> Dict[str, Any]:
        """Process audio chunk and return result (same logic as legacy)"""
        try:
            if recognizer.AcceptWaveform(audio_data):
                # Final result available
                result_json = recognizer.Result()
                return json.loads(result_json)
            else:
                # Partial result
                partial_json = recognizer.PartialResult()
                return json.loads(partial_json)
        except Exception as e:
            logger.error(f"Error processing audio: {e}")
            return {"error": str(e)}
    
    def finalize_recognition(self, recognizer: KaldiRecognizer) -> Dict[str, Any]:
        """Get final recognition result (same as legacy)"""
        try:
            final_json = recognizer.FinalResult()
            return json.loads(final_json)
        except Exception as e:
            logger.error(f"Error finalizing recognition: {e}")
            return {"error": str(e)}


class ASRServiceImpl(asr_service_pb2_grpc.ASRServiceServicer):
    """Native gRPC ASR Service implementation"""
    
    def __init__(self):
        # Initialize the shared Vosk model (same as legacy approach)
        self.vosk_engine = None
        self._initialize_model()
        
        self.start_time = time.time()
        self.total_connections = 0
        
        logger.info("🎤 Native ASR Service initialized with shared Vosk model")
    
    def _initialize_model(self):
        """Initialize the shared Vosk model instance (same pattern as legacy)"""
        try:
            logger.info("🔄 Pre-loading Vosk ASR model (this happens ONLY ONCE)...")
            
            # Model configuration from environment or defaults (same as legacy)
            model_path = os.getenv('VOSK_MODEL_PATH', 'model')
            sample_rate = float(os.getenv('VOSK_SAMPLE_RATE', '16000'))
            
            self.vosk_engine = NativeVoskASREngine(
                model_path=model_path,
                sample_rate=sample_rate
            )
            
            logger.info("✅ Vosk ASR model loaded and ready! All future gRPC calls will use this shared instance.")
        except Exception as e:
            logger.error(f"❌ Failed to initialize Vosk model: {e}")
            raise
    
    async def StreamingRecognize(self, request_iterator, context):
        """Streaming recognition - main method based on legacy Vosk pattern"""
        recognizer = None
        session_id = str(uuid.uuid4())
        
        try:
            self.total_connections += 1
            logger.info(f"🎤 New ASR streaming session: {session_id}")
            
            # Process streaming requests (same pattern as legacy WebSocket)
            config_received = False
            
            async for request in request_iterator:
                if request.HasField('config'):
                    # Handle configuration (first message, same as legacy)
                    config = {
                        "sample_rate": request.config.sample_rate or 16000,
                        "model_path": request.config.model_path or "model",
                        "show_words": request.config.show_words,
                        "max_alternatives": request.config.max_alternatives or 0,
                        "phrase_list": list(request.config.phrase_list) if request.config.phrase_list else None
                    }
                    
                    # Create recognizer with config (same as legacy)
                    recognizer = self.vosk_engine.create_recognizer(
                        sample_rate=config["sample_rate"],
                        config=config
                    )
                    config_received = True
                    
                    logger.info(f"🎤 ASR config received: {config}")
                    
                elif request.HasField('audio_data'):
                    # Process audio data (same as legacy)
                    if not config_received or not recognizer:
                        # Create default recognizer if config not sent
                        recognizer = self.vosk_engine.create_recognizer()
                        config_received = True
                    
                    # Process audio chunk (same logic as legacy)
                    result = self.vosk_engine.process_audio_chunk(recognizer, request.audio_data)
                    
                    # Send response (same format as legacy)
                    response = asr_service_pb2.StreamingRecognizeResponse()
                    
                    if "text" in result and result["text"]:
                        # Final result
                        response.result.text = result["text"]
                        response.result.confidence = 0.9  # Vosk doesn't provide confidence
                        response.is_final = True
                        response.end_of_utterance = False
                        logger.info(f"🎤 Final ASR result: {result['text']}")
                        
                    elif "partial" in result and result["partial"]:
                        # Partial result
                        response.result.text = result["partial"]
                        response.result.confidence = 0.7
                        response.is_final = False
                        response.end_of_utterance = False
                        logger.debug(f"🎤 Partial ASR result: {result['partial']}")
                        
                    elif "error" in result:
                        # Error result
                        response.result.text = ""
                        response.result.confidence = 0.0
                        response.is_final = True
                        response.end_of_utterance = True
                        logger.error(f"ASR error: {result['error']}")
                        
                    else:
                        # Empty result
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
                    # Handle control messages (same as legacy)
                    try:
                        control = json.loads(request.control_message)
                        
                        if control.get("eof") == 1:
                            # Finalize recognition (same as legacy)
                            if recognizer:
                                final_result = self.vosk_engine.finalize_recognition(recognizer)
                                
                                response = asr_service_pb2.StreamingRecognizeResponse()
                                if final_result and "text" in final_result:
                                    response.result.text = final_result["text"]
                                    response.result.confidence = 0.9
                                    logger.info(f"🎤 Final result after EOF: {final_result['text']}")
                                else:
                                    response.result.text = ""
                                    response.result.confidence = 0.0
                                
                                response.is_final = True
                                response.end_of_utterance = True
                                yield response
                            break
                            
                        elif control.get("reset") == 1:
                            # Reset recognizer (same as legacy)
                            if recognizer:
                                final_result = self.vosk_engine.finalize_recognition(recognizer)
                                # Create new recognizer for next utterance
                                recognizer = self.vosk_engine.create_recognizer()
                                logger.debug("🎤 ASR recognizer reset")
                                
                    except json.JSONDecodeError:
                        logger.warning(f"Invalid control message: {request.control_message}")
                        
        except Exception as e:
            logger.error(f"🎤 StreamingRecognize error: {e}")
            response = asr_service_pb2.StreamingRecognizeResponse()
            response.result.text = ""
            response.is_final = True
            response.end_of_utterance = True
            yield response
        
        finally:
            logger.info(f"🎤 ASR streaming session ended: {session_id}")
    
    async def Recognize(self, request, context):
        """Single shot recognition"""
        try:
            # Create recognizer for this request
            config = {
                "sample_rate": request.config.sample_rate or 16000,
                "show_words": request.config.show_words
            }
            
            recognizer = self.vosk_engine.create_recognizer(
                sample_rate=config["sample_rate"],
                config=config
            )
            
            # Process audio data
            result = self.vosk_engine.process_audio_chunk(recognizer, request.audio_data)
            
            # Finalize recognition
            final_result = self.vosk_engine.finalize_recognition(recognizer)
            
            response = asr_service_pb2.RecognizeResponse()
            
            if final_result and "text" in final_result and final_result["text"]:
                response.result.text = final_result["text"]
                response.result.confidence = 0.9
                logger.info(f"🎤 Single recognition result: {final_result['text']}")
            else:
                response.result.text = ""
                response.result.confidence = 0.0
            
            return response
            
        except Exception as e:
            logger.error(f"🎤 Single recognition error: {e}")
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
        """Health check"""
        try:
            # Test recognition with silence (minimal test)
            recognizer = self.vosk_engine.create_recognizer()
            test_audio = b'\x00' * 3200  # 100ms of silence at 16kHz
            result = self.vosk_engine.process_audio_chunk(recognizer, test_audio)
            
            response = asr_service_pb2.HealthResponse()
            response.status = asr_service_pb2.HealthResponse.Status.SERVING
            response.message = "ASR service healthy"
            response.model_loaded = os.path.basename(self.vosk_engine.model_path)
            
            return response
            
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            response = asr_service_pb2.HealthResponse()
            response.status = asr_service_pb2.HealthResponse.Status.NOT_SERVING
            response.message = f"Health check error: {e}"
            return response
    
    async def GetStats(self, request, context):
        """Get service statistics"""
        response = asr_service_pb2.StatsResponse()
        response.total_connections = self.total_connections
        response.uptime_seconds = int(time.time() - self.start_time)
        response.model_info = os.path.basename(self.vosk_engine.model_path)
        return response


async def serve():
    """Start the native gRPC ASR server"""
    server = aio_grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    
    # Add ASR service
    asr_service_pb2_grpc.add_ASRServiceServicer_to_server(ASRServiceImpl(), server)
    
    # Listen on port
    listen_addr = os.getenv('ASR_SERVICE_LISTEN_ADDR', '[::]:50053')
    server.add_insecure_port(listen_addr)
    
    # Start server
    await server.start()
    logger.info(f"🎤 Native ASR Service started on {listen_addr}")
    logger.info(f"📊 Vosk model loaded and ready for recognition")
    
    try:
        await server.wait_for_termination()
    except KeyboardInterrupt:
        logger.info("🛑 ASR Service shutting down")
        await server.stop(grace=30)


if __name__ == '__main__':
    asyncio.run(serve())