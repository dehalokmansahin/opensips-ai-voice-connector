"""
Llama WebSocket LLM Service - Following Pipecat Implementations Document  
OpenAI ChatCompletion format compatible with updated server
"""

import asyncio
import json
import websockets
from typing import AsyncGenerator, Optional, List, Dict, Any
import structlog

from pipecat.frames.frames import (
    Frame, TextFrame, EndFrame, ErrorFrame, StartFrame,
    LLMFullResponseStartFrame, LLMFullResponseEndFrame, LLMTextFrame,
    LLMMessagesFrame
)
from pipecat.services.llm_service import LLMService
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor
from pipecat.processors.aggregators.openai_llm_context import OpenAILLMContext, OpenAILLMContextFrame
from pipecat.processors.aggregators.llm_response import (
    LLMUserContextAggregator,
    LLMAssistantContextAggregator,
)
from .websocket_base import WebsocketClientMixin

logger = structlog.get_logger()


class _LlamaContextAggregator:
    """A helper class that provides user and assistant context processors."""

    def __init__(self, context: OpenAILLMContext):
        self._context = context

    def user(self) -> FrameProcessor:
        return LLMUserContextAggregator(self._context)

    def assistant(self) -> FrameProcessor:
        return LLMAssistantContextAggregator(self._context)


class LlamaWebsocketLLMService(LLMService, WebsocketClientMixin):
    """
    Llama LLM service using OpenAI ChatCompletion format
    Compatible with updated server supporting both OpenAI and legacy formats
    """
    
    def __init__(
        self,
        url: str,
        model: str = "llama3.2:3b-instruct-turkish",
        temperature: float = 0.2,
        max_tokens: int = 80,
        use_rag: bool = True,
        **kwargs
    ):
        LLMService.__init__(self, **kwargs)
        WebsocketClientMixin.__init__(self)
        self._url = url
        self._model = model
        self._temperature = temperature  
        self._max_tokens = max_tokens
        self._use_rag = use_rag
        self._websocket: Optional = None
        self._listener_task: Optional[asyncio.Task] = None
        self._is_connected = False
        
        logger.info("LlamaLLMService initialized",
                   url=url,
                   model=model,
                   temperature=temperature,
                   max_tokens=max_tokens,
                   use_rag=use_rag,
                   pattern="openai_compatible")

    def create_context_aggregator(self, context: OpenAILLMContext) -> "_LlamaContextAggregator":
        """Create a context aggregator to manage conversation history."""
        return _LlamaContextAggregator(context)

    async def start(self, frame: StartFrame):
        """Start the LLM service and WebSocket connection"""
        await super().start(frame)
        await self._start_websocket_connection()

    async def stop(self, frame: EndFrame):
        """Stop the LLM service and WebSocket connection"""
        await self._stop_websocket_connection()
        await super().stop(frame)

    async def cancel(self, frame: EndFrame):
        """Cancel the LLM service and WebSocket connection"""
        await self._stop_websocket_connection()
        await super().cancel(frame)

    async def _send_request(self, context: OpenAILLMContext):
        """Send LLM request to the websocket using OpenAI chat format"""
        messages = context.messages

        request = {
            "messages": messages,
            "temperature": self._temperature,
            "max_tokens": self._max_tokens,
            "stream": True,
            "use_rag": self._use_rag,
        }

        logger.info("📤 Sending LLM request", message_count=len(messages), url=self._url)
        await self._websocket.send(json.dumps(request))
        logger.debug("✅ LLM request sent", bytes=len(json.dumps(request)))

    async def _process_context(self, context: OpenAILLMContext):
        """High-level entry – mirrors OpenAI service behaviour."""
        # Currently we don't gather token usage; just send the request.
        await self._send_request(context)

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        """Handle incoming frames and trigger LLM requests when a context arrives."""
        await super().process_frame(frame, direction)

        context: Optional[OpenAILLMContext] = None
        if isinstance(frame, OpenAILLMContextFrame):
            context = frame.context
        elif isinstance(frame, LLMMessagesFrame):
            context = OpenAILLMContext.from_messages(frame.messages)
        else:
            # Forward any other frame unchanged
            await self.push_frame(frame, direction)
            return

        if context:
            # Start of full response
            await self.push_frame(LLMFullResponseStartFrame())
            logger.debug("🚀 Triggering LLM processing for context", messages=len(context.messages))
            try:
                await self._process_context(context)
                # EndFrame will be emitted by listener upon 'done'.
            except Exception as e:
                logger.error("❌ LLM processing error", error=str(e))
                await self.push_frame(ErrorFrame(error=f"LLM processing error: {e}"))

    async def _start_websocket_connection(self):
        """Start WebSocket connection following document pattern"""
        if not self._listener_task:
            self._listener_task = asyncio.create_task(self._websocket_listener())
            logger.info("Llama WebSocket listener started", pattern="openai_compatible")

    async def _websocket_listener(self):
        """WebSocket listener for OpenAI compatible responses"""
        try:
            logger.info("🔌 Attempting to connect to Llama WebSocket", url=self._url)
            async with websockets.connect(self._url) as websocket:
                self._websocket = websocket
                self._is_connected = True
                
                logger.info("✅ Llama WebSocket connected successfully", 
                           url=self._url, 
                           format="openai_compatible")

                # Listen for LLM responses
                async for message in self._websocket:
                    if not self._is_connected:
                        logger.info("🔌 WebSocket listener stopping (disconnected)")
                        break
                    
                    logger.debug("📨 Received message from Llama server", 
                               message_preview=message[:100] if len(message) > 100 else message)
                        
                    try:
                        data = json.loads(message)
                        logger.debug("📥 Parsed JSON response", data_keys=list(data.keys()))
                        
                        # Handle RAG context info (optional)
                        if "rag_context" in data:
                            logger.info("📖 Received RAG context info", 
                                       context_length=data.get("context_length", 0))
                            continue
                        
                        # Handle streaming response tokens
                        if "chunk" in data:
                            token = data["chunk"]
                            logger.debug("💬 Received LLM chunk", token=token[:50])
                            
                            # Emit streaming token frame
                            await self.push_frame(LLMTextFrame(token))
                        
                        # Handle completion
                        elif data.get("done", False):
                            logger.info("✅ LLM response completed")
                            await self.push_frame(LLMFullResponseEndFrame())
                        
                        # Handle errors from server
                        elif "error" in data:
                            error_msg = data["error"]
                            logger.error("❌ Server returned error", error=error_msg)
                            await self.push_frame(ErrorFrame(error=f"Server error: {error_msg}"))
                        
                        else:
                            logger.warning("❓ Unknown message format from server", data=data)
                            
                    except json.JSONDecodeError as e:
                        logger.error("❌ Invalid JSON from Llama server", 
                                   error=str(e), 
                                   raw_message=message[:200])
                    except Exception as e:
                        logger.error("❌ Error processing Llama message", 
                                   error=str(e),
                                   error_type=type(e).__name__)
                        await self.push_frame(ErrorFrame(error=f"Llama processing error: {e}"))

        except websockets.exceptions.ConnectionClosed:
            logger.warning("🔌 Llama WebSocket connection closed")
        except websockets.exceptions.InvalidURI:
            logger.error("❌ Invalid WebSocket URI", url=self._url)
        except websockets.exceptions.InvalidHandshake:
            logger.error("❌ WebSocket handshake failed", url=self._url)
        except Exception as e:
            logger.error("❌ Llama WebSocket connection failed", 
                        error=str(e),
                        error_type=type(e).__name__,
                        url=self._url)
            await self.push_frame(ErrorFrame(error=f"Llama connection failed: {e}"))
        finally:
            logger.info("🔌 WebSocket listener cleanup")
            self._websocket = None
            self._is_connected = False

    async def _stop_websocket_connection(self):
        """Stop WebSocket connection"""
        self._is_connected = False
        
        if self._listener_task:
            self._listener_task.cancel()
            try:
                await self._listener_task
            except asyncio.CancelledError:
                pass
            self._listener_task = None