#!/usr/bin/env python
#
# Copyright (C) 2024 SIP Point Consulting SRL
#
# This file is part of the OpenSIPS AI Voice Connector project
# (see https://github.com/OpenSIPS/opensips-ai-voice-connector-ce).
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program. If not, see <http://www.gnu.org/licenses/>.
#

"""
LLM WebSocket Client for OpenSIPS AI Voice Connector

Connects to LLM WebSocket server, receives streaming text responses,
and integrates with the speech processing pipeline for sentence-by-sentence TTS.
"""

import asyncio
import json
import re
import logging
import websockets
from typing import Optional, Callable, Awaitable

logger = logging.getLogger(__name__)

# Regex to detect sentence boundaries (Turkish punctuation aware)
SENTENCE_END_RE = re.compile(r'.*?[\.!\?](?:\s|$)', re.DOTALL)

class LLMClient:
    """
    WebSocket client for streaming LLM responses with sentence splitting.
    Integrates with OAVC speech processing pipeline.
    """
    
    def __init__(self, 
                 server_uri: str = "ws://localhost:8765",
                 sentence_callback: Optional[Callable[[str], Awaitable[None]]] = None,
                 session_id: str = "",
                 debug: bool = False):
        """
        Initialize LLM client.
        
        Args:
            server_uri: WebSocket server URI  
            sentence_callback: Async function to call with complete sentences
            session_id: Session ID for logging
            debug: Enable debug logging
        """
        self.server_uri = server_uri
        self.sentence_callback = sentence_callback
        self.session_id = session_id
        self.debug = debug
        self._buffer = ""
        self._connected = False
        
    async def generate_response(self, 
                              system_prompt: str, 
                              user_prompt: str,
                              max_tokens: int = 256,
                              temperature: float = 0.7) -> bool:
        """
        Generate streaming response from LLM server and process sentences.
        
        Args:
            system_prompt: System instruction for the LLM
            user_prompt: User message/query
            max_tokens: Maximum tokens to generate
            temperature: Sampling temperature
            
        Returns:
            bool: True if successful, False if failed
        """
        try:
            async with websockets.connect(self.server_uri) as ws:
                self._connected = True
                logger.info(f"{self.session_id}LLM: Connected to server: {self.server_uri}")
                
                # Send initial request
                request = {
                    "system_prompt": system_prompt,
                    "prompt": user_prompt,
                    "max_tokens": max_tokens,
                    "temperature": temperature
                }
                await ws.send(json.dumps(request))
                
                if self.debug:
                    logger.debug(f"{self.session_id}LLM: Sent request: {user_prompt[:50]}...")
                
                # Reset buffer for new generation
                self._buffer = ""
                
                # Receive streaming response
                async for message in ws:
                    try:
                        data = json.loads(message)
                        
                        if data.get("done"):
                            logger.info(f"{self.session_id}LLM: Generation completed")
                            break
                            
                        if "error" in data:
                            logger.error(f"{self.session_id}LLM: Server error: {data['error']}")
                            return False
                            
                        if "chunk" in data:
                            chunk = data["chunk"]
                            await self._process_chunk(chunk)
                            
                    except json.JSONDecodeError as e:
                        logger.error(f"{self.session_id}LLM: Failed to parse message: {e}")
                        continue
                
                # Process any remaining buffer content
                await self._flush_buffer()
                return True
                
        except websockets.exceptions.ConnectionClosed:
            logger.warning(f"{self.session_id}LLM: Server connection closed unexpectedly")
            return False
        except Exception as e:
            logger.error(f"{self.session_id}LLM: Client error: {e}")
            return False
        finally:
            self._connected = False
            
    async def _process_chunk(self, chunk: str) -> None:
        """
        Process incoming text chunk and extract complete sentences.
        
        Args:
            chunk: Text chunk from LLM
        """
        self._buffer += chunk
        
        # Extract complete sentences from buffer
        while True:
            match = SENTENCE_END_RE.match(self._buffer)
            if not match:
                break
                
            sentence = match.group(0).strip()
            if sentence:
                if self.debug:
                    logger.debug(f"{self.session_id}LLM: Complete sentence: {sentence}")
                    
                if self.sentence_callback:
                    await self.sentence_callback(sentence)
                    
            # Remove processed sentence from buffer
            self._buffer = self._buffer[match.end():]
            
    async def _flush_buffer(self) -> None:
        """
        Flush any remaining content in buffer as final sentence.
        """
        if self._buffer.strip():
            if self.debug:
                logger.debug(f"{self.session_id}LLM: Final sentence: {self._buffer.strip()}")
                
            if self.sentence_callback:
                await self.sentence_callback(self._buffer.strip())
            self._buffer = ""
            
    def is_connected(self) -> bool:
        """Check if client is currently connected to LLM server."""
        return self._connected

# vim: tabstop=8 expandtab shiftwidth=4 softtabstop=4 