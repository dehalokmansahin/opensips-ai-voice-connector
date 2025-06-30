"""
Custom LLaMA WebSocket LLM Service - Pipecat Native Uyumlu
Kendi LLaMA model serveriniz ile entegrasyon
Streaming sentence segmentation ile TTS optimizasyonu
"""

import asyncio
import json
import websockets
import re
from typing import AsyncGenerator
import structlog
from pipecat.frames.frames import (
    Frame,
    LLMFullResponseStartFrame,
    LLMFullResponseEndFrame,
    LLMTextFrame,
    TranscriptionFrame,
    SystemFrame,
    StartFrame,
    EndFrame,
    TextFrame,
    LLMMessagesFrame
)
from pipecat.services.llm_service import LLMService
from loguru import logger

logger = structlog.get_logger()

class StreamingSentenceSegmenter:
    """Streaming text'i cümle bazında segmentlere ayırır"""
    
    def __init__(self):
        self.buffer = ""
        # Türkçe için daha iyi çalışan bir regex
        self.sentence_endings = re.compile(r'(?<=[\.!?])\s+')
        
    def add_chunk(self, chunk: str) -> list[str]:
        """Chunk ekle ve tamamlanan cümleleri döndür."""
        self.buffer += chunk
        sentences = []
        
        parts = self.sentence_endings.split(self.buffer)
        
        if len(parts) > 1:
            # Son parça hariç hepsi tamamlanmış cümledir
            completed_sentences = parts[:-1]
            self.buffer = parts[-1] # Kalan parça buffer olur
            
            for sentence in completed_sentences:
                sentence = sentence.strip()
                if sentence:
                    sentences.append(sentence)
        
        return sentences
    
    def get_remaining(self) -> str:
        """Buffer'da kalan metni döndür"""
        remaining = self.buffer.strip()
        self.buffer = ""
        return remaining
    
    def reset(self):
        """Segmenter'ı sıfırla"""
        self.buffer = ""

class LlamaWebsocketLLMService(LLMService):
    """
    LLaMA LLM service that uses a WebSocket connection.
    """
    def __init__(self, url: str, model: str, **kwargs):
        super().__init__(**kwargs)
        self._url = url
        self._model = model
        self._websocket = None
        self._listener_task = None
        
        logger.info(f"LLaMA WebSocket LLM service initialized with url: {self._url}")

    async def start(self, frame: StartFrame):
        await self.start_listening()

    async def stop(self, frame: EndFrame):
        await self.stop_listening()

    async def _process_frame(self, frame, direction):
        await super()._process_frame(frame, direction)

        if isinstance(frame, LLMMessagesFrame):
            messages = frame.messages
            
            if not self._websocket:
                logger.error("WebSocket not connected.")
                return

            try:
                payload = {
                    "model": self._model,
                    "messages": messages,
                    "stream": True
                }
                await self._websocket.send(json.dumps(payload))
                logger.debug(f"Sent messages to LLaMA model: {messages}")
            except Exception as e:
                logger.error(f"Error sending messages to LLaMA: {e}")
        elif isinstance(frame, EndFrame):
            await self.push_frame(frame)

    async def _listener(self):
        """Listens for messages from the WebSocket and pushes them as frames."""
        while True:
            try:
                message = await self._websocket.recv()
                data = json.loads(message)
                
                if data.get("done"):
                    logger.info("LLaMA streaming complete.")
                    # Potentially push an LLMResponseEndFrame here if needed
                
                content = data.get("message", {}).get("content", "")
                if content:
                    await self.push_frame(TextFrame(text=content))

            except websockets.exceptions.ConnectionClosed:
                logger.warning("LLaMA WebSocket connection closed.")
                break
            except Exception as e:
                logger.error(f"Error in LLaMA listener: {e}")
                break

    async def start_listening(self):
        if not self._websocket:
            try:
                self._websocket = await websockets.connect(self._url)
                logger.info("Connected to LLaMA WebSocket.")
                self._listener_task = asyncio.create_task(self._listener())
            except Exception as e:
                logger.error(f"Failed to connect to LLaMA WebSocket: {e}")

    async def stop_listening(self):
        if self._listener_task:
            self._listener_task.cancel()
            try:
                await self._listener_task
            except asyncio.CancelledError:
                pass
            self._listener_task = None

        if self._websocket:
            await self._websocket.close()
            self._websocket = None
            logger.info("Disconnected from LLaMA WebSocket.")
            
    async def run_llm(self, frame_iterator: AsyncGenerator[Frame, None]) -> AsyncGenerator[Frame, None]:
        # This processor style service does not use run_llm
        pass 