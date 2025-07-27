"""
LLM gRPC Client for OpenSIPS AI Voice Connector
Communicates with LLM microservice for text generation
"""

import asyncio
import logging
import sys
import os
from typing import AsyncGenerator, Optional, Dict, Any, List
from grpc import aio as aio_grpc

# Import protobuf stubs
try:
    sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', 'services', 'llm-service', 'src'))
    import llm_service_pb2
    import llm_service_pb2_grpc
except ImportError as e:
    logger = logging.getLogger(__name__)
    logger.error(f"Failed to import LLM protobuf stubs: {e}")
    # Create minimal stub classes for development
    class llm_service_pb2:
        class GenerateRequest:
            def __init__(self):
                self.messages = []
                self.temperature = 0.7
                self.max_tokens = 150
                self.stream = False
        
        class GenerateResponse:
            def __init__(self):
                self.text = ""
                self.done = False
        
        class StreamGenerateRequest:
            def __init__(self):
                self.messages = []
                self.temperature = 0.7
                self.max_tokens = 150
        
        class StreamGenerateResponse:
            def __init__(self):
                self.chunk = ""
                self.done = False
    
    class llm_service_pb2_grpc:
        class LLMServiceStub:
            def __init__(self, channel): pass
            async def Generate(self, request): pass
            def StreamGenerate(self, request): pass

logger = logging.getLogger(__name__)

class LLMClient:
    """gRPC client for LLM service"""
    
    def __init__(self, service_registry):
        self.service_registry = service_registry
        self._streaming_tasks: List[asyncio.Task] = []
        
    async def generate(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 150,
        **kwargs
    ) -> Optional[str]:
        """Single shot text generation"""
        try:
            channel = self.service_registry.get_channel('llm')
            if not channel:
                logger.error("LLM service not available")
                return None
            
            stub = llm_service_pb2_grpc.LLMServiceStub(channel)
            
            # Create request
            request = llm_service_pb2.GenerateRequest()
            
            # Set messages
            for message in messages:
                if hasattr(request, 'messages'):
                    msg = request.messages.add()
                    msg.role = message.get('role', 'user')
                    msg.content = message.get('content', '')
            
            # Set parameters
            request.temperature = temperature
            request.max_tokens = max_tokens
            request.stream = False
            
            # Set additional parameters
            if 'use_rag' in kwargs:
                request.use_rag = kwargs['use_rag']
            
            # Make request
            response = await stub.Generate(request)
            
            if hasattr(response, 'text'):
                return response.text
            
            return None
            
        except Exception as e:
            logger.error(f"LLM generation error: {e}")
            return None
    
    async def stream_generate(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 150,
        on_token: Optional[callable] = None,
        on_complete: Optional[callable] = None,
        **kwargs
    ) -> AsyncGenerator[str, None]:
        """Streaming text generation"""
        try:
            channel = self.service_registry.get_channel('llm')
            if not channel:
                logger.error("LLM service not available")
                return
            
            stub = llm_service_pb2_grpc.LLMServiceStub(channel)
            
            # Create request
            request = llm_service_pb2.StreamGenerateRequest()
            
            # Set messages
            for message in messages:
                if hasattr(request, 'messages'):
                    msg = request.messages.add()
                    msg.role = message.get('role', 'user')
                    msg.content = message.get('content', '')
            
            # Set parameters
            request.temperature = temperature
            request.max_tokens = max_tokens
            
            # Set additional parameters
            if 'use_rag' in kwargs:
                request.use_rag = kwargs['use_rag']
            
            # Start streaming generation
            response_stream = stub.StreamGenerate(request)
            
            full_response = ""
            
            async for response in response_stream:
                if hasattr(response, 'chunk'):
                    chunk = response.chunk
                    if chunk:
                        full_response += chunk
                        
                        if on_token:
                            await on_token(chunk)
                        
                        yield chunk
                
                # Check if generation is complete
                if hasattr(response, 'done') and response.done:
                    if on_complete:
                        await on_complete(full_response)
                    break
                        
        except Exception as e:
            logger.error(f"LLM streaming error: {e}")
    
    async def create_conversation_context(
        self,
        system_prompt: str = "",
        conversation_history: List[Dict[str, str]] = None
    ) -> List[Dict[str, str]]:
        """Create conversation context with system prompt and history"""
        messages = []
        
        # Add system prompt
        if system_prompt:
            messages.append({
                "role": "system",
                "content": system_prompt
            })
        
        # Add conversation history
        if conversation_history:
            messages.extend(conversation_history)
        
        return messages
    
    async def add_user_message(
        self,
        messages: List[Dict[str, str]],
        user_text: str
    ) -> List[Dict[str, str]]:
        """Add user message to conversation context"""
        new_messages = messages.copy()
        new_messages.append({
            "role": "user", 
            "content": user_text
        })
        return new_messages
    
    async def add_assistant_message(
        self,
        messages: List[Dict[str, str]],
        assistant_text: str
    ) -> List[Dict[str, str]]:
        """Add assistant message to conversation context"""
        new_messages = messages.copy()
        new_messages.append({
            "role": "assistant",
            "content": assistant_text
        })
        return new_messages
    
    async def truncate_conversation(
        self,
        messages: List[Dict[str, str]],
        max_messages: int = 10
    ) -> List[Dict[str, str]]:
        """Truncate conversation to maintain context window"""
        if len(messages) <= max_messages:
            return messages
        
        # Keep system message if it exists
        system_messages = [msg for msg in messages if msg.get('role') == 'system']
        other_messages = [msg for msg in messages if msg.get('role') != 'system']
        
        # Keep the most recent messages
        truncated = system_messages + other_messages[-(max_messages - len(system_messages)):]
        
        return truncated
    
    async def health_check(self) -> bool:
        """Check LLM service health"""
        try:
            # Simple health check
            test_messages = [{"role": "user", "content": "Hello"}]
            result = await self.generate(test_messages, max_tokens=1)
            return result is not None
            
        except Exception as e:
            logger.error(f"LLM health check failed: {e}")
            return False
    
    async def cleanup(self):
        """Cleanup LLM client resources"""
        # Cancel streaming tasks
        for task in self._streaming_tasks:
            if not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        
        self._streaming_tasks.clear()
        logger.info("LLM client cleaned up")

class ConversationManager:
    """Manages LLM conversations with context"""
    
    def __init__(self, llm_client: LLMClient, system_prompt: str = ""):
        self.llm_client = llm_client
        self.system_prompt = system_prompt
        self.conversation_history: List[Dict[str, str]] = []
        self.max_history = 10
        
        # Initialize with system prompt
        if system_prompt:
            self.conversation_history.append({
                "role": "system",
                "content": system_prompt
            })
    
    async def send_message(
        self,
        user_text: str,
        temperature: float = 0.7,
        max_tokens: int = 150,
        **kwargs
    ) -> Optional[str]:
        """Send user message and get assistant response"""
        try:
            # Add user message
            self.conversation_history.append({
                "role": "user",
                "content": user_text
            })
            
            # Generate response
            response = await self.llm_client.generate(
                messages=self.conversation_history,
                temperature=temperature,
                max_tokens=max_tokens,
                **kwargs
            )
            
            if response:
                # Add assistant response to history
                self.conversation_history.append({
                    "role": "assistant",
                    "content": response
                })
                
                # Truncate if needed
                await self._truncate_history()
            
            return response
            
        except Exception as e:
            logger.error(f"Conversation error: {e}")
            return None
    
    async def stream_message(
        self,
        user_text: str,
        temperature: float = 0.7,
        max_tokens: int = 150,
        on_token: Optional[callable] = None,
        **kwargs
    ) -> AsyncGenerator[str, None]:
        """Send user message and stream assistant response"""
        try:
            # Add user message
            self.conversation_history.append({
                "role": "user",
                "content": user_text
            })
            
            full_response = ""
            
            # Stream response
            async for token in self.llm_client.stream_generate(
                messages=self.conversation_history,
                temperature=temperature,
                max_tokens=max_tokens,
                on_token=on_token,
                **kwargs
            ):
                full_response += token
                yield token
            
            # Add complete response to history
            if full_response:
                self.conversation_history.append({
                    "role": "assistant",
                    "content": full_response
                })
                
                # Truncate if needed
                await self._truncate_history()
                
        except Exception as e:
            logger.error(f"Streaming conversation error: {e}")
    
    async def _truncate_history(self):
        """Truncate conversation history to maintain context window"""
        self.conversation_history = await self.llm_client.truncate_conversation(
            self.conversation_history,
            self.max_history
        )
    
    def get_conversation_summary(self) -> str:
        """Get a summary of the conversation"""
        user_messages = [msg['content'] for msg in self.conversation_history if msg['role'] == 'user']
        assistant_messages = [msg['content'] for msg in self.conversation_history if msg['role'] == 'assistant']
        
        return f"Conversation: {len(user_messages)} user messages, {len(assistant_messages)} assistant messages"
    
    def clear_history(self, keep_system: bool = True):
        """Clear conversation history"""
        if keep_system and self.system_prompt:
            self.conversation_history = [{
                "role": "system",
                "content": self.system_prompt
            }]
        else:
            self.conversation_history = []