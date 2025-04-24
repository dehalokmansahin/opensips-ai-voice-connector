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
Integration with Vosk Speech-to-Text service via WebSocket
"""

import json
import asyncio
import logging
from enum import Enum
import websockets
from websockets.exceptions import ConnectionClosed, ConnectionClosedError

from config import Config


class VoskSTTState(Enum):
    """Represents the state of the Vosk STT connection"""
    DISCONNECTED = 0
    CONNECTING = 1
    CONNECTED = 2
    TRANSCRIBING = 3
    FAILED = 4


class VoskSTT:
    """
    Handles speech-to-text conversion using Vosk via WebSocket
    """

    def __init__(self, callback_func=None):
        """
        Initialize the Vosk STT client
        
        Args:
            callback_func: Function to call when transcription is available
        """
        self.config = Config.get("vosk")
        self.ws_url = self.config.get("ws_url", "VOSK_WS_URL", "ws://localhost:2700")
        self.sample_rate = int(self.config.get("sample_rate", "VOSK_SAMPLE_RATE", "8000"))
        self.reconnect_delay = int(self.config.get("reconnect_delay", "VOSK_RECONNECT_DELAY", "5"))
        self.max_reconnect_attempts = int(self.config.get("max_reconnect_attempts", "VOSK_MAX_RECONNECT_ATTEMPTS", "3"))
        
        self.websocket = None
        self.state = VoskSTTState.DISCONNECTED
        self.reconnect_attempts = 0
        self.callback_func = callback_func
        self.reconnect_task = None

    async def connect(self):
        """
        Establish a WebSocket connection to the Vosk server
        """
        if self.state in (VoskSTTState.CONNECTED, VoskSTTState.TRANSCRIBING):
            return True
        
        if self.state == VoskSTTState.CONNECTING:
            # Wait for the connection to establish
            while self.state == VoskSTTState.CONNECTING:
                await asyncio.sleep(0.1)
            return self.state == VoskSTTState.CONNECTED
        
        self.state = VoskSTTState.CONNECTING
        logging.info(f"Connecting to Vosk server at {self.ws_url}")
        
        try:
            self.websocket = await websockets.connect(
                self.ws_url,
                ping_timeout=30,
                ping_interval=10,
                close_timeout=10
            )
            
            # Send configuration to Vosk
            await self.websocket.send(json.dumps({
                "config": {
                    "sample_rate": self.sample_rate
                }
            }))
            
            # Start the listener
            asyncio.create_task(self._listen_for_results())
            
            self.state = VoskSTTState.CONNECTED
            self.reconnect_attempts = 0
            logging.info("Connected to Vosk STT server")
            return True
            
        except (ConnectionRefusedError, OSError, TimeoutError) as e:
            logging.error(f"Failed to connect to Vosk server: {str(e)}")
            self.state = VoskSTTState.FAILED
            await self._handle_reconnection()
            return False
    
    async def _listen_for_results(self):
        """
        Listen for transcription results from the WebSocket
        """
        try:
            async for message in self.websocket:
                try:
                    result = json.loads(message)
                    
                    # Handle different result types
                    if 'text' in result:
                        # Final transcription
                        if self.callback_func and result['text']:
                            await self.callback_func(result['text'], final=True)
                    
                    elif 'partial' in result:
                        # Partial transcription
                        if self.callback_func and result['partial']:
                            await self.callback_func(result['partial'], final=False)
                    
                except json.JSONDecodeError:
                    logging.warning(f"Received invalid JSON from Vosk: {message}")
                
        except ConnectionClosed as e:
            logging.warning(f"Vosk WebSocket connection closed: {str(e)}")
            self.state = VoskSTTState.DISCONNECTED
            await self._handle_reconnection()
        
        except Exception as e:
            logging.error(f"Error in Vosk listener: {str(e)}")
            self.state = VoskSTTState.FAILED
            await self._handle_reconnection()
    
    async def _handle_reconnection(self):
        """
        Handle reconnection attempts to the Vosk server
        """
        if self.reconnect_task and not self.reconnect_task.done():
            return
        
        self.reconnect_task = asyncio.create_task(self._reconnect())
    
    async def _reconnect(self):
        """
        Attempt to reconnect to the Vosk server
        """
        if self.reconnect_attempts >= self.max_reconnect_attempts:
            logging.error(f"Failed to reconnect to Vosk server after {self.reconnect_attempts} attempts")
            self.state = VoskSTTState.FAILED
            return
        
        self.reconnect_attempts += 1
        logging.info(f"Attempting to reconnect to Vosk server (attempt {self.reconnect_attempts})")
        
        await asyncio.sleep(self.reconnect_delay)
        await self.connect()
    
    async def transcribe(self, audio_data):
        """
        Send audio data to the Vosk server for transcription
        
        Args:
            audio_data: Audio bytes to transcribe
        
        Returns:
            bool: True if the audio was sent successfully, False otherwise
        """
        if not await self.connect():
            return False
        
        try:
            if self.state == VoskSTTState.CONNECTED:
                self.state = VoskSTTState.TRANSCRIBING
            
            await self.websocket.send(audio_data)
            return True
            
        except (ConnectionClosedError, ConnectionClosed) as e:
            logging.error(f"Connection to Vosk server closed while sending audio: {str(e)}")
            self.state = VoskSTTState.DISCONNECTED
            await self._handle_reconnection()
            return False
            
        except Exception as e:
            logging.error(f"Error sending audio to Vosk: {str(e)}")
            return False
    
    async def close(self):
        """
        Close the WebSocket connection to the Vosk server
        """
        try:
            if self.reconnect_task:
                self.reconnect_task.cancel()
            
            if self.websocket:
                await self.websocket.close()
                self.websocket = None
            
            self.state = VoskSTTState.DISCONNECTED
            logging.info("Closed connection to Vosk STT server")
            
        except Exception as e:
            logging.error(f"Error closing Vosk connection: {str(e)}") 