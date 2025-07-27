#!/usr/bin/env python3
"""
Native gRPC LLM Service - Converted from legacy WebSocket implementation
Based on C:\Cursor\llama-turkish-server working implementation
"""

# CRITICAL: Set offline mode BEFORE any imports (from legacy)
import os
os.environ['TRANSFORMERS_OFFLINE'] = '1'
os.environ['HF_HUB_OFFLINE'] = '1'
os.environ['HF_HUB_DISABLE_TELEMETRY'] = '1'
os.environ['SENTENCE_TRANSFORMERS_HOME'] = os.path.join(os.getcwd(), 'rag_model')
os.environ['HF_HOME'] = os.path.join(os.getcwd(), 'rag_model')
os.environ['TORCH_HOME'] = os.path.join(os.getcwd(), 'rag_model')

import asyncio
import json
import logging
import sys
import time
import threading
from concurrent import futures
from typing import AsyncGenerator, Optional, Dict, Any

import grpc
from grpc import aio as aio_grpc

# Native LLM imports (from your working legacy)
from llama_cpp import Llama

# gRPC imports
try:
    from . import llm_service_pb2
    from . import llm_service_pb2_grpc
except ImportError:
    import llm_service_pb2
    import llm_service_pb2_grpc

# Configure logging (same as legacy)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class NativeLLMEngine:
    """Native LLM engine using llama-cpp directly (from legacy llm_stream.py)"""
    
    def __init__(self, model_path: str = None, **kwargs):
        """Initialize LLM engine with model loading (same as legacy)"""
        if model_path is None:
            model_dir = os.getenv('MODEL_DIR', 'model/')
            # Find the first .gguf file in the model directory (same as legacy)
            for file in os.listdir(model_dir):
                if file.endswith('.gguf'):
                    model_path = os.path.join(model_dir, file)
                    break
            
            if model_path is None:
                raise FileNotFoundError(f"No .gguf model found in {model_dir}")
        
        logger.info(f"🔄 Loading model from: {model_path}")
        logger.info("🔄 This happens ONLY ONCE during server startup...")
        
        # Default parameters (same as legacy)
        default_kwargs = {
            'n_ctx': 4096,      # Context window size
            'n_threads': 4,     # Number of threads
            'n_gpu_layers': 0,  # Number of layers to offload to GPU (0 = CPU only)
            'verbose': False    # Reduce verbose output
        }
        
        # Update with user-provided kwargs
        default_kwargs.update(kwargs)
        
        try:
            self.llm = Llama(model_path=model_path, **default_kwargs)
            logger.info("✅ Model loaded successfully and ready for all gRPC connections!")
        except Exception as e:
            logger.error(f"❌ Failed to load model: {e}")
            raise
    
    async def stream_generate(self, prompt: str, system_prompt: str = "", **kwargs) -> AsyncGenerator[str, None]:
        """Generate streaming text response (adapted from legacy)"""
        # Combine system and user prompts (same as legacy)
        if system_prompt:
            full_prompt = f"System: {system_prompt}\n\nUser: {prompt}\n\nAssistant:"
        else:
            full_prompt = f"User: {prompt}\n\nAssistant:"
        
        # Default generation parameters (same as legacy)
        default_params = {
            'max_tokens': 80,   # Shorter for IVR responses (from legacy config)
            'temperature': 0.2, # Low temperature for consistent banking responses
            'top_p': 0.9,
            'stop': ["\n\nUser:", "\n\nSystem:"],
            'stream': True
        }
        
        # Update with user-provided parameters
        default_params.update(kwargs)
        
        logger.debug(f"🔀 Using SHARED model instance for prompt: {prompt[:50]}...")
        
        try:
            # Generate streaming response using the shared model instance (same as legacy)
            for output in self.llm(full_prompt, **default_params):
                # Debug: Log the output structure (same as legacy)
                logger.debug(f"🔍 Raw output: {output}")
                
                if output is None:
                    logger.warning("⚠️ Received None output from model, skipping...")
                    continue
                
                # Extract text token (same logic as legacy)
                if isinstance(output, dict):
                    if 'choices' in output and output['choices']:
                        choice = output['choices'][0]
                        if 'text' in choice:
                            text_chunk = choice['text']
                            if text_chunk:
                                yield text_chunk
                        elif 'delta' in choice and 'content' in choice['delta']:
                            text_chunk = choice['delta']['content']
                            if text_chunk:
                                yield text_chunk
                
        except Exception as e:
            logger.error(f"❌ Generation error: {e}")
            yield f"Error: {str(e)}"


class LLMServiceImpl(llm_service_pb2_grpc.LLMServiceServicer):
    """Native gRPC LLM Service implementation"""
    
    def __init__(self):
        # Initialize the shared LLM model (same as legacy approach)
        self.model_engine = None
        self._initialize_model()
        
        self.start_time = time.time()
        self.total_requests = 0
        
        # Banking system prompt (improved from legacy)
        self.banking_system_prompt = (
            "Sen Garanti BBVA IVR hattında, Türkçe TTS için konuşma metni üreten bir dil modelisin.\n\n"
            "Kurallar:\n"
            "1. Kısa-orta uzunlukta, net ve resmi cümleler yaz (en çok 20 kelime).\n"
            "2. Türkçe imlâyı tam uygula (ç, ğ, ı, ö, ş, ü).\n"
            "3. Tarihleri \"2 Haziran 2025\", saatleri \"14.30\" biçiminde yaz.\n"
            "4. Kritik sayıları tam ver: \"₺250\", \"1234\".\n"
            "5. Gereksiz sembol, yabancı kelime, ünlem ve jargon kullanma.\n"
            "6. Yalnızca TTS'ye okunacak metni döndür; fazladan açıklama ekleme."
        )
        
        logger.info("🤖 Native LLM Service initialized with shared model")
    
    def _initialize_model(self):
        """Initialize the shared model instance (same pattern as legacy)"""
        try:
            logger.info("🔄 Pre-loading LLM model (this happens ONLY ONCE)...")
            self.model_engine = NativeLLMEngine()
            logger.info("✅ LLM model loaded and ready! All future gRPC calls will use this shared instance.")
        except Exception as e:
            logger.error(f"❌ Failed to initialize model: {e}")
            raise
    
    async def ProcessText(self, request, context):
        """Process text and generate streaming response"""
        session_id = str(int(time.time() * 1000))  # Simple session ID
        
        try:
            text = request.text
            system_prompt = request.system_prompt or self.banking_system_prompt
            
            # Extract generation parameters (same as legacy WebSocket format)
            generation_params = {}
            if hasattr(request, 'temperature') and request.temperature > 0:
                generation_params['temperature'] = request.temperature
            if hasattr(request, 'max_tokens') and request.max_tokens > 0:
                generation_params['max_tokens'] = request.max_tokens
            
            logger.info(f"🤖 Processing request: prompt='{text[:50]}...'")
            
            self.total_requests += 1
            
            # Generate streaming response using shared model (same as legacy)
            async for chunk in self.model_engine.stream_generate(text, system_prompt, **generation_params):
                response = llm_service_pb2.TextResponse()
                response.chunk = chunk
                response.done = False
                yield response
            
            # Send completion signal (same as legacy WebSocket pattern)
            completion = llm_service_pb2.TextResponse()
            completion.chunk = ""
            completion.done = True
            yield completion
            
            logger.info(f"✅ Completed request for session {session_id}")
            
        except Exception as e:
            logger.error(f"❌ Processing error: {e}")
            error_response = llm_service_pb2.TextResponse()
            error_response.chunk = f"Error: {str(e)}"
            error_response.done = True
            yield error_response
    
    async def UpdateContext(self, request, context):
        """Update context (placeholder - context handled in conversation history)"""
        response = llm_service_pb2.ContextResponse()
        response.success = True
        response.message = "Context handling managed by conversation history"
        return response
    
    async def HealthCheck(self, request, context):
        """Health check"""
        try:
            # Test model with simple prompt
            test_generated = False
            async for chunk in self.model_engine.stream_generate("Test", "", max_tokens=5):
                test_generated = True
                break  # Just test that generation works
            
            response = llm_service_pb2.HealthResponse()
            if test_generated:
                response.status = llm_service_pb2.HealthResponse.Status.SERVING
                response.message = "LLM service healthy"
                response.model_loaded = "llama-model"
            else:
                response.status = llm_service_pb2.HealthResponse.Status.NOT_SERVING
                response.message = "Model test failed"
                response.model_loaded = ""
            
            return response
            
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            response = llm_service_pb2.HealthResponse()
            response.status = llm_service_pb2.HealthResponse.Status.NOT_SERVING
            response.message = f"Health check error: {e}"
            return response
    
    async def GetStats(self, request, context):
        """Get service statistics"""
        response = llm_service_pb2.StatsResponse()
        response.total_requests = self.total_requests
        response.uptime_seconds = int(time.time() - self.start_time)
        response.model_info = "llama-model"
        return response


async def serve():
    """Start the native gRPC LLM server"""
    server = aio_grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    
    # Add LLM service
    llm_service_pb2_grpc.add_LLMServiceServicer_to_server(LLMServiceImpl(), server)
    
    # Listen on port
    listen_addr = os.getenv('LLM_SERVICE_LISTEN_ADDR', '[::]:50051')
    server.add_insecure_port(listen_addr)
    
    # Start server
    await server.start()
    logger.info(f"🤖 Native LLM Service started on {listen_addr}")
    logger.info(f"📊 Model loaded and ready for streaming responses")
    
    try:
        await server.wait_for_termination()
    except KeyboardInterrupt:
        logger.info("🛑 LLM Service shutting down")
        await server.stop(grace=30)


if __name__ == '__main__':
    asyncio.run(serve())