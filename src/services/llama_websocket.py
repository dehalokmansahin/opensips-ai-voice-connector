"""
Llama WebSocket LLM Service - Following Pipecat Implementations Document  
Simplified implementation aligned with document specifications
"""

import asyncio
import json
import websockets
from typing import AsyncGenerator, Optional, List, Dict, Any
import structlog

from pipecat.frames.frames import (
    Frame, TextFrame, EndFrame, ErrorFrame, StartFrame,
    LLMFullResponseStartFrame, LLMFullResponseEndFrame, LLMTextFrame
)
from pipecat.services.llm_service import LLMService
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor
from pipecat.processors.aggregators.openai_llm_context import OpenAILLMContext
from pipecat.processors.aggregators.llm_response import (
    LLMUserContextAggregator,
    LLMAssistantContextAggregator,
)

logger = structlog.get_logger()


class _LlamaContextAggregator:
    """A helper class that provides user and assistant context processors."""

    def __init__(self, context: OpenAILLMContext):
        self._context = context

    def user(self) -> FrameProcessor:
        return LLMUserContextAggregator(self._context)

    def assistant(self) -> FrameProcessor:
        return LLMAssistantContextAggregator(self._context)


class LlamaWebsocketLLMService(LLMService):
    """
    Llama LLM service following document specifications
    Generates assistant text with streaming tokens as per implementation guide
    """
    
    def __init__(
        self,
        url: str,
        model: str = "llama3.2:3b-instruct-turkish",
        temperature: float = 0.2,
        max_tokens: int = 80,
        **kwargs
    ):
        super().__init__(**kwargs)
        self._url = url
        self._model = model
        self._temperature = temperature  
        self._max_tokens = max_tokens
        self._websocket: Optional = None
        self._listener_task: Optional[asyncio.Task] = None
        self._is_connected = False
        
        logger.info("LlamaLLMService initialized",
                   url=url,
                   model=model,
                   temperature=temperature,
                   max_tokens=max_tokens,
                   pattern="document_compliant")

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

    async def run_llm(self, context: OpenAILLMContext) -> AsyncGenerator[Frame, None]:
        """
        Main LLM method - processes context and generates response
        This is called by the LLMService base class when processing conversations
        """
        if not self._websocket or not self._is_connected:
            logger.warning("No active Llama WebSocket connection for LLM processing")
            return

        try:
            messages = context.messages

            # Send request to Llama
            request = {
                "model": self._model,
                "messages": messages,
                "temperature": self._temperature,
                "max_tokens": self._max_tokens,
                "stream": True,
            }

            # Signal start of response
            yield LLMFullResponseStartFrame()
            
            await self._websocket.send(json.dumps(request))
            
            logger.debug("Sent context to Llama LLM", message_count=len(messages))
            
        except Exception as e:
            logger.error("Error sending text to Llama", error=str(e))
            yield ErrorFrame(error=f"Llama request error: {e}")

    async def _start_websocket_connection(self):
        """Start WebSocket connection following document pattern"""
        if not self._listener_task:
            self._listener_task = asyncio.create_task(self._websocket_listener())
            logger.info("Llama WebSocket listener started", pattern="document_compliant")

    async def _websocket_listener(self):
        """WebSocket listener following document specifications"""
        try:
            async with websockets.connect(self._url) as websocket:
                self._websocket = websocket
                self._is_connected = True
                
                logger.info("Llama WebSocket connected", url=self._url)

                # Listen for LLM responses (document pattern)
                async for message in self._websocket:
                    if not self._is_connected:
                        break
                        
                    try:
                        data = json.loads(message)
                        
                        # Handle streaming response tokens
                        if data.get("response"):
                            token = data["response"]
                            
                            # Emit streaming token frame
                            await self.push_frame(LLMTextFrame(token))
                        
                        # Handle completion
                        elif data.get("done", False):
                            await self.push_frame(LLMFullResponseEndFrame())
                            
                    except json.JSONDecodeError as e:
                        logger.error("Invalid JSON from Llama", error=str(e))
                    except Exception as e:
                        logger.error("Error processing Llama message", error=str(e))
                        await self.push_frame(ErrorFrame(error=f"Llama processing error: {e}"))

        except websockets.exceptions.ConnectionClosed:
            logger.info("Llama WebSocket connection closed")
        except Exception as e:
            logger.error("Llama WebSocket connection failed", error=str(e))
            await self.push_frame(ErrorFrame(error=f"Llama connection failed: {e}"))
        finally:
            self._websocket = None
            self._is_connected = False

    def _create_prompt(self, text: str) -> str:
        """Create prompt for Llama following document pattern"""
        # This function is no longer used with stateful context.
        # Kept for potential legacy use or simple tests.
        system_prompt = "Sen Türk bankacılık sistemi için yardımcı bir asistansın. Kısa ve net cevaplar ver."
        
        return f"{system_prompt}\\n\\nKullanıcı: {text}\\nAsistan:"

    async def _stop_websocket_connection(self):
        """Stop WebSocket connection following document pattern"""
        self._is_connected = False
        
        if self._listener_task:
            self._listener_task.cancel()
            try:
                await self._listener_task
            except asyncio.CancelledError:
                pass
            self._listener_task = None

    # This legacy method is replaced by the new run_llm
    # async def run_llm(self, messages: List[Dict[str, Any]]) -> AsyncGenerator[Frame, None]:
    #     """
    #     Legacy compatibility method - not used in processor-based model
    #     Following document pattern for service compatibility
    #     """
    #     # Empty generator as per document guidance
    #     return
    #     yield  # Unreachable, just for generator syntax 