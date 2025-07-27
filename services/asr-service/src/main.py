#!/usr/bin/env python3
"""
ASR Service - gRPC ASR Service based on proven Vosk WebSocket implementation
Migrated from C:\Cursor\vosk-server legacy implementation
"""

import asyncio
import json
import logging
import os
import sys
import time
import uuid
from concurrent import futures
from typing import Dict, Any, Optional
import threading

import grpc
from grpc import aio as aio_grpc
import websockets

# Local imports (will be generated from proto)
try:
    from . import asr_service_pb2
    from . import asr_service_pb2_grpc
except ImportError:
    import asr_service_pb2
    import asr_service_pb2_grpc

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class VoskWebSocketClient:
    """WebSocket client for Vosk ASR server - based on legacy implementation"""
    
    def __init__(self, url: str = "ws://vosk-server:2700"):
        self.url = url
        self.websocket = None
        self.connected = False
        self.session_id = str(uuid.uuid4())
        
    async def connect(self):
        """Connect to Vosk WebSocket server"""
        try:
            self.websocket = await websockets.connect(self.url)
            self.connected = True
            logger.info(f"Connected to Vosk server: {self.url}")
            return True
        except Exception as e:
            logger.error(f"Failed to connect to Vosk: {e}")
            return False
    
    async def disconnect(self):
        """Disconnect from Vosk server"""
        if self.websocket and self.connected:
            try:
                await self.websocket.close()
            except Exception as e:
                logger.error(f"Error disconnecting: {e}")
        self.connected = False
        self.websocket = None
    
    async def send_config(self, config: Dict[str, Any]):
        """Send configuration to Vosk (like legacy asr_server.py)"""
        if not self.connected:
            return False
        
        try:
            config_message = json.dumps({"config": config})
            await self.websocket.send(config_message)
            return True
        except Exception as e:
            logger.error(f"Failed to send config: {e}")
            return False
    
    async def send_audio(self, audio_data: bytes) -> Optional[Dict[str, Any]]:
        """Send audio data and get recognition result"""
        if not self.connected:
            return None
        
        try:
            # Send audio data
            await self.websocket.send(audio_data)
            
            # Wait for response
            response = await asyncio.wait_for(
                self.websocket.recv(), 
                timeout=5.0
            )
            
            return json.loads(response)
            
        except asyncio.TimeoutError:
            logger.warning("Vosk response timeout")
            return {"error": "timeout"}
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON from Vosk: {e}")
            return {"error": "invalid_json"}
        except Exception as e:
            logger.error(f"Error sending audio: {e}")
            return {"error": str(e)}
    
    async def send_eof(self) -> Optional[Dict[str, Any]]:
        """Send EOF to get final result"""
        if not self.connected:
            return None
        
        try:
            await self.websocket.send('{"eof": 1}')
            response = await asyncio.wait_for(
                self.websocket.recv(),
                timeout=2.0
            )
            return json.loads(response)
        except Exception as e:
            logger.error(f"Error sending EOF: {e}")
            return {"error": str(e)}


class ASRServiceImpl(asr_service_pb2_grpc.ASRServiceServicer):
    """gRPC ASR Service implementation using Vosk WebSocket backend"""
    
    def __init__(self):
        self.vosk_url = os.getenv('VOSK_SERVER_URL', 'ws://vosk-server:2700')
        self.session_clients: Dict[str, VoskWebSocketClient] = {}
        self.start_time = time.time()
        logger.info(f"ASR Service initialized with Vosk server: {self.vosk_url}")
    
    async def StreamingRecognize(self, request_iterator, context):
        """Streaming recognition - main method based on legacy Vosk pattern"""
        client = None
        session_id = str(uuid.uuid4())
        
        try:
            # Connect to Vosk server
            client = VoskWebSocketClient(self.vosk_url)
            await client.connect()
            
            if not client.connected:
                response = asr_service_pb2.StreamingRecognizeResponse()
                response.result.text = ""
                response.is_final = True
                response.end_of_utterance = True
                yield response
                return
            
            # Process streaming requests
            config_sent = False
            
            async for request in request_iterator:
                if request.HasField('config'):
                    # Send configuration to Vosk (first message)
                    config = {
                        "sample_rate": int(request.config.sample_rate),
                        "model": request.config.model_path or "model",
                        "words": request.config.show_words,
                        "max_alternatives": request.config.max_alternatives or 0,
                        "phrase_list": list(request.config.phrase_list) if request.config.phrase_list else None
                    }
                    
                    await client.send_config(config)
                    config_sent = True
                    logger.info(f"Vosk config sent: {config}")
                    
                elif request.HasField('audio_data'):
                    # Process audio data
                    if not config_sent:
                        # Send default config if not sent
                        await client.send_config({"sample_rate": 16000})
                        config_sent = True
                    
                    result = await client.send_audio(request.audio_data)
                    
                    if result:
                        response = asr_service_pb2.StreamingRecognizeResponse()
                        
                        if "text" in result and result["text"]:
                            # Final result
                            response.result.text = result["text"]
                            response.result.confidence = 0.9
                            response.is_final = True
                            response.end_of_utterance = False
                            logger.info(f"Final ASR result: {result['text']}")
                            
                        elif "partial" in result and result["partial"]:
                            # Partial result
                            response.result.text = result["partial"]
                            response.result.confidence = 0.7
                            response.is_final = False
                            response.end_of_utterance = False
                            logger.debug(f"Partial ASR result: {result['partial']}")
                            
                        else:
                            # Empty or error result
                            response.result.text = ""
                            response.is_final = False
                            response.end_of_utterance = False
                        
                        yield response
                        
                elif request.HasField('control_message'):
                    # Handle control messages like EOF
                    control = json.loads(request.control_message)
                    
                    if control.get("eof") == 1:
                        # Send EOF and get final result
                        final_result = await client.send_eof()
                        
                        response = asr_service_pb2.StreamingRecognizeResponse()
                        if final_result and "text" in final_result:
                            response.result.text = final_result["text"]
                            response.result.confidence = 0.9
                        else:
                            response.result.text = ""
                            response.result.confidence = 0.0
                        
                        response.is_final = True
                        response.end_of_utterance = True
                        yield response
                        break
                        
        except Exception as e:
            logger.error(f"StreamingRecognize error: {e}")
            response = asr_service_pb2.StreamingRecognizeResponse()
            response.result.text = ""
            response.is_final = True
            response.end_of_utterance = True
            yield response
            
        finally:
            if client:
                await client.disconnect()
    
    async def Recognize(self, request, context):
        """Single shot recognition"""
        client = None
        
        try:
            # Connect to Vosk
            client = VoskWebSocketClient(self.vosk_url)
            await client.connect()
            
            if not client.connected:
                response = asr_service_pb2.RecognizeResponse()
                response.result.text = ""
                return response
            
            # Send config
            config = {
                "sample_rate": int(request.config.sample_rate) if request.config.sample_rate else 16000,
                "words": request.config.show_words
            }
            await client.send_config(config)
            
            # Send audio and get result
            result = await client.send_audio(request.audio_data)
            
            # Send EOF to finalize
            final_result = await client.send_eof()
            
            response = asr_service_pb2.RecognizeResponse()
            
            if final_result and "text" in final_result and final_result["text"]:
                response.result.text = final_result["text"]
                response.result.confidence = 0.9
                logger.info(f"Single recognition result: {final_result['text']}")
            else:
                response.result.text = ""
                response.result.confidence = 0.0
            
            return response
            
        except Exception as e:
            logger.error(f"Recognize error: {e}")
            response = asr_service_pb2.RecognizeResponse()
            response.result.text = ""
            return response
            
        finally:
            if client:
                await client.disconnect()
    
    async def Configure(self, request, context):
        """Configure recognition parameters"""
        response = asr_service_pb2.ConfigureResponse()
        response.success = True
        response.message = "Configuration accepted"
        return response
    
    async def HealthCheck(self, request, context):
        """Health check"""
        try:
            # Test connection to Vosk
            client = VoskWebSocketClient(self.vosk_url)
            connected = await client.connect()
            
            if connected:
                await client.disconnect()
                response = asr_service_pb2.HealthResponse()
                response.status = asr_service_pb2.HealthResponse.Status.SERVING
                response.message = "ASR service healthy"
                response.model_loaded = "vosk-model-tr"
            else:
                response = asr_service_pb2.HealthResponse()
                response.status = asr_service_pb2.HealthResponse.Status.NOT_SERVING
                response.message = "Cannot connect to Vosk server"
                response.model_loaded = ""
            
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
        response.active_connections = len(self.session_clients)
        response.total_connections = len(self.session_clients)  # Simplified
        response.uptime_seconds = int(time.time() - self.start_time)
        response.model_info = "vosk-model-tr"
        return response


async def serve():
    """Start the gRPC ASR server"""
    server = aio_grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    
    # Add ASR service
    asr_service_pb2_grpc.add_ASRServiceServicer_to_server(ASRServiceImpl(), server)
    
    # Listen on port
    listen_addr = os.getenv('ASR_SERVICE_LISTEN_ADDR', '[::]:50053')
    server.add_insecure_port(listen_addr)
    
    # Start server
    await server.start()
    logger.info(f"🎤 ASR Service started on {listen_addr}")
    logger.info(f"🔗 Connected to Vosk server at {os.getenv('VOSK_SERVER_URL', 'ws://vosk-server:2700')}")
    
    try:
        await server.wait_for_termination()
    except KeyboardInterrupt:
        logger.info("🛑 ASR Service shutting down")
        await server.stop(grace=30)


if __name__ == '__main__':
    asyncio.run(serve())