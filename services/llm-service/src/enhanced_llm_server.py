#!/usr/bin/env python3
"""
Enhanced LLM Service - Integrated with new architecture
Uses common service base and improved configuration
"""

# CRITICAL: Set offline mode BEFORE any imports
import os
os.environ['TRANSFORMERS_OFFLINE'] = '1'
os.environ['HF_HUB_OFFLINE'] = '1'
os.environ['HF_HUB_DISABLE_TELEMETRY'] = '1'
os.environ['SENTENCE_TRANSFORMERS_HOME'] = os.path.join(os.getcwd(), 'rag_model')
os.environ['HF_HOME'] = os.path.join(os.getcwd(), 'rag_model')
os.environ['TORCH_HOME'] = os.path.join(os.getcwd(), 'rag_model')

import asyncio
import json
import sys
import time
import threading
from pathlib import Path
from typing import AsyncGenerator, Optional, Dict, Any

# Add common services to path
sys.path.append(str(Path(__file__).parent.parent.parent / "common"))

from service_base import BaseService, ServiceConfig

# Native LLM imports
from llama_cpp import Llama

# gRPC imports
try:
    from . import llm_service_pb2
    from . import llm_service_pb2_grpc
except ImportError:
    import llm_service_pb2
    import llm_service_pb2_grpc

class LLMServiceConfig(ServiceConfig):
    """LLM service configuration"""
    
    def _load_service_config(self):
        """Load LLM-specific configuration"""
        self.model_path = os.getenv('LLM_MODEL_PATH', 'model/llama-model.gguf')
        self.n_ctx = int(os.getenv('LLM_CONTEXT_SIZE', '2048'))
        self.n_threads = int(os.getenv('LLM_THREADS', '4'))
        self.n_gpu_layers = int(os.getenv('LLM_GPU_LAYERS', '0'))
        self.temperature = float(os.getenv('LLM_TEMPERATURE', '0.7'))
        self.max_tokens = int(os.getenv('LLM_MAX_TOKENS', '150'))
        self.use_mlock = os.getenv('LLM_USE_MLOCK', 'false').lower() == 'true'

class NativeLLMEngine:
    """Native LLM engine using llama-cpp directly"""
    
    def __init__(self, config: LLMServiceConfig):
        self.config = config
        self.model: Optional[Llama] = None
        self.model_lock = threading.Lock()
        
        # Load model
        self._load_model()
    
    def _load_model(self):
        """Load the LLM model"""
        try:
            self.model = Llama(
                model_path=self.config.model_path,
                n_ctx=self.config.n_ctx,
                n_threads=self.config.n_threads,
                n_gpu_layers=self.config.n_gpu_layers,
                use_mlock=self.config.use_mlock,
                verbose=False
            )
        except Exception as e:
            raise Exception(f"Failed to load LLM model: {e}")
    
    def generate_text(self, prompt: str, context: str = "", max_tokens: int = None, temperature: float = None) -> str:
        """Generate text response"""
        if not self.model:
            raise Exception("Model not loaded")
        
        # Combine context and prompt
        full_prompt = f"{context}\n\n{prompt}" if context else prompt
        
        max_tokens = max_tokens or self.config.max_tokens
        temperature = temperature if temperature is not None else self.config.temperature
        
        with self.model_lock:
            response = self.model(
                full_prompt,
                max_tokens=max_tokens,
                temperature=temperature,
                stop=["\\n\\n", "User:", "Assistant:"],
                echo=False
            )
        
        return response['choices'][0]['text'].strip()
    
    async def stream_generate(self, prompt: str, context: str = "", max_tokens: int = None, temperature: float = None) -> AsyncGenerator[str, None]:
        """Generate streaming text response"""
        if not self.model:
            raise Exception("Model not loaded")
        
        # Combine context and prompt
        full_prompt = f"{context}\n\n{prompt}" if context else prompt
        
        max_tokens = max_tokens or self.config.max_tokens
        temperature = temperature if temperature is not None else self.config.temperature
        
        def generate():
            with self.model_lock:
                for token in self.model(
                    full_prompt,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    stop=["\\n\\n", "User:", "Assistant:"],
                    stream=True,
                    echo=False
                ):
                    yield token['choices'][0]['text']
        
        # Run in thread to avoid blocking
        loop = asyncio.get_event_loop()
        
        def run_generation():
            return list(generate())
        
        tokens = await loop.run_in_executor(None, run_generation)
        
        for token in tokens:
            yield token

class LLMServiceImpl(llm_service_pb2_grpc.LLMServiceServicer):
    """Enhanced LLM Service implementation"""
    
    def __init__(self, base_service: 'LLMService'):
        self.base_service = base_service
        self.model_engine = base_service.model_engine
        self.logger = base_service.logger
    
    async def Generate(self, request, context):
        """Single text generation with enhanced logging"""
        try:
            self.base_service.increment_request_count()
            
            # Extract request parameters
            messages = [{"role": msg.role, "content": msg.content} for msg in request.messages]
            prompt = messages[-1]["content"] if messages else ""
            
            # Build context from conversation history
            context_text = ""
            for msg in messages[:-1]:
                role = "User" if msg["role"] == "user" else "Assistant"
                context_text += f"{role}: {msg['content']}\\n"
            
            self.logger.debug(f"🤖 Generating response for prompt: {prompt[:100]}...")
            
            # Generate response
            response_text = self.model_engine.generate_text(
                prompt=prompt,
                context=context_text,
                max_tokens=request.max_tokens or 150,
                temperature=request.temperature or 0.7
            )
            
            # Create response
            response = llm_service_pb2.TextResponse()
            response.text = response_text
            response.done = True
            
            self.logger.debug(f"🤖 Generated response: {response_text[:100]}...")
            
            return response
            
        except Exception as e:
            self.logger.error(f"🤖 Generation error: {e}")
            self.base_service.increment_error_count()
            
            response = llm_service_pb2.TextResponse()
            response.text = f"Error: {str(e)}"
            response.done = True
            return response
    
    async def StreamGenerate(self, request, context):
        """Streaming text generation with enhanced logging"""
        try:
            self.base_service.increment_request_count()
            
            # Extract request parameters
            messages = [{"role": msg.role, "content": msg.content} for msg in request.messages]
            prompt = messages[-1]["content"] if messages else ""
            
            # Build context from conversation history
            context_text = ""
            for msg in messages[:-1]:
                role = "User" if msg["role"] == "user" else "Assistant"
                context_text += f"{role}: {msg['content']}\\n"
            
            self.logger.debug(f"🤖 Streaming response for prompt: {prompt[:100]}...")
            
            # Stream response
            async for token in self.model_engine.stream_generate(
                prompt=prompt,
                context=context_text,
                max_tokens=request.max_tokens or 150,
                temperature=request.temperature or 0.7
            ):
                response = llm_service_pb2.TextResponse()
                response.chunk = token
                response.done = False
                yield response
            
            # Send completion signal
            final_response = llm_service_pb2.TextResponse()
            final_response.chunk = ""
            final_response.done = True
            yield final_response
            
            self.logger.debug("🤖 Streaming generation completed")
            
        except Exception as e:
            self.logger.error(f"🤖 Streaming error: {e}")
            self.base_service.increment_error_count()
            
            error_response = llm_service_pb2.TextResponse()
            error_response.chunk = f"Error: {str(e)}"
            error_response.done = True
            yield error_response
    
    async def UpdateContext(self, request, context):
        """Update context (placeholder)"""
        response = llm_service_pb2.ContextResponse()
        response.success = True
        response.message = "Context handling managed by conversation history"
        return response
    
    async def HealthCheck(self, request, context):
        """Health check with enhanced status"""
        try:
            health_info = await self.base_service.health_check()
            
            response = llm_service_pb2.HealthResponse()
            response.status = (llm_service_pb2.HealthResponse.Status.SERVING 
                             if health_info['status'] == 'SERVING' 
                             else llm_service_pb2.HealthResponse.Status.NOT_SERVING)
            response.message = health_info['message']
            response.model_loaded = "llama-model"
            
            return response
            
        except Exception as e:
            self.logger.error(f"Health check failed: {e}")
            response = llm_service_pb2.HealthResponse()
            response.status = llm_service_pb2.HealthResponse.Status.NOT_SERVING
            response.message = f"Health check error: {e}"
            return response
    
    async def GetStats(self, request, context):
        """Get service statistics"""
        stats = self.base_service.get_stats()
        
        response = llm_service_pb2.StatsResponse()
        response.total_requests = stats['total_requests']
        response.uptime_seconds = stats['uptime_seconds']
        response.model_info = "llama-model"
        return response

class LLMService(BaseService):
    """Enhanced LLM Service using common base"""
    
    def __init__(self):
        config = LLMServiceConfig('llm')
        super().__init__('llm', config)
        self.model_engine: Optional[NativeLLMEngine] = None
    
    async def initialize(self):
        """Initialize LLM service components"""
        try:
            self.logger.info("🔄 Loading LLM model...")
            self.model_engine = NativeLLMEngine(self.config)
            self.logger.info("✅ LLM model loaded successfully!")
            
        except Exception as e:
            self.logger.error(f"❌ Failed to initialize LLM service: {e}")
            raise
    
    def create_servicer(self):
        """Create LLM servicer"""
        return LLMServiceImpl(self)
    
    def add_servicer_to_server(self, servicer, server):
        """Add LLM servicer to server"""
        llm_service_pb2_grpc.add_LLMServiceServicer_to_server(servicer, server)
    
    async def _service_specific_health_check(self) -> Dict[str, Any]:
        """LLM-specific health check"""
        try:
            if not self.model_engine or not self.model_engine.model:
                return {
                    'healthy': False,
                    'message': 'LLM model not loaded',
                    'details': {}
                }
            
            # Test generation with simple prompt
            test_response = self.model_engine.generate_text("Test", max_tokens=5)
            
            return {
                'healthy': True,
                'message': 'LLM service healthy',
                'details': {
                    'model_path': self.model_engine.config.model_path,
                    'context_size': self.model_engine.config.n_ctx,
                    'test_response': test_response[:50] if test_response else "empty"
                }
            }
            
        except Exception as e:
            return {
                'healthy': False,
                'message': f'LLM health check failed: {e}',
                'details': {'error': str(e)}
            }

async def main():
    """Main entry point"""
    service = LLMService()
    await service.start()

if __name__ == '__main__':
    asyncio.run(main())