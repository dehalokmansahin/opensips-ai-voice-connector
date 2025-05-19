import asyncio
import websockets
import json
import logging
import traceback
from websockets.exceptions import ConnectionClosedError, ConnectionClosedOK
from typing import Optional, Dict, Any, Union, Callable, Tuple, Awaitable

class PiperClient:
    """Client for Piper TTS WebSocket server.
    
    This client provides methods to connect to a Piper TTS server
    and send text for synthesis.
    """
    
    def __init__(self, server_host="localhost", server_port=8000, session_id="", timeout_seconds=10):
        """Initialize the Piper TTS client.
        
        Args:
            server_host: Hostname or IP address of the Piper TTS server
            server_port: Port number of the Piper TTS server
            session_id: Optional session ID prefix for logging
            timeout_seconds: Connection timeout in seconds
        """
        self.server_url = f"ws://{server_host}:{server_port}/tts"
        self.session_id = session_id
        self.websocket = None
        self.is_connected = False
        self.timeout_seconds = timeout_seconds
        logging.info(f"{self.session_id}Initialized Piper TTS client for {self.server_url}")
    
    async def connect(self) -> bool:
        """Connect to the Piper TTS WebSocket server.
        
        Returns:
            bool: True if connection successful, False otherwise
        """
        try:
            logging.info(f"{self.session_id}Connecting to Piper TTS server at {self.server_url}")
            # Connect without timeout parameter - we'll handle timeouts separately
            self.websocket = await websockets.connect(self.server_url)
            self.is_connected = True
            logging.info(f"{self.session_id}Connected to Piper TTS server at {self.server_url}")
            return True
        except Exception as e:
            logging.error(f"{self.session_id}Failed to connect to Piper TTS server: {e}")
            self.is_connected = False
            return False

    async def synthesize(self, text: str, voice: str = None) -> bool:
        """Send text to synthesize.
        
        Args:
            text: The text to synthesize
            voice: Optional voice name (if server supports multiple voices)
            
        Returns:
            bool: True if request was sent successfully
        """
        if not self.is_connected or not self.websocket:
            logging.error(f"{self.session_id}Cannot synthesize text: Not connected to Piper TTS server")
            return False
        
        try:
            # Prepare request
            request = {"text": text}
            if voice:
                request["voice"] = voice
                
            # Send request
            logging.info(f"{self.session_id}Sending TTS request: '{text[:50]}{'...' if len(text) > 50 else ''}'")
            await self.websocket.send(json.dumps(request))
            return True
        except Exception as e:
            logging.error(f"{self.session_id}Failed to send text to Piper TTS server: {e}")
            self.is_connected = False
            return False
    
    async def process_stream(self, 
                           on_start: Callable[[Dict[str, Any]], Union[None, Awaitable[None]]] = None,
                           on_audio: Callable[[bytes], Union[None, Awaitable[None]]] = None, 
                           on_end: Callable[[Dict[str, Any]], Union[None, Awaitable[None]]] = None,
                           on_error: Callable[[Dict[str, Any]], Union[None, Awaitable[None]]] = None) -> bool:
        """Process the audio stream from the server.
        
        Args:
            on_start: Callback for start message (can be sync or async)
            on_audio: Callback for audio data (can be sync or async)
            on_end: Callback for end message (can be sync or async)
            on_error: Callback for error message (can be sync or async)
            
        Returns:
            bool: True if stream was processed successfully
        """
        if not self.is_connected or not self.websocket:
            logging.error(f"{self.session_id}Cannot process stream: Not connected to Piper TTS server")
            return False
        
        success = False
        try:
            # Get start message
            start_message = await self._wait_with_timeout(self.websocket.recv())
            if not start_message:
                logging.error(f"{self.session_id}Timed out waiting for start message from Piper TTS server")
                return False
            
            # Parse start message
            try:
                start_data = json.loads(start_message)
                msg_type = start_data.get("type")
                # Accept both 'start' and 'connected' as valid initial message types
                if msg_type in ["start", "connected"]:
                    logging.info(f"{self.session_id}TTS connection established: {start_data.get('message')}")
                    if on_start:
                        await self._maybe_await(on_start(start_data))
                else:
                    logging.warning(f"{self.session_id}Unexpected first message from TTS server: {start_data}")
            except json.JSONDecodeError:
                logging.warning(f"{self.session_id}Received non-JSON start message: {start_message[:50]}...")
                return False
            
            # Process stream
            while True:
                try:
                    # Wait for message with timeout
                    message = await self._wait_with_timeout(self.websocket.recv())
                    if not message:
                        logging.error(f"{self.session_id}Timed out waiting for audio data from Piper TTS server")
                        break
                    
                    # Handle JSON control messages (text)
                    if isinstance(message, str):
                        try:
                            data = json.loads(message)
                            msg_type = data.get("type")
                            
                            if msg_type == "end":
                                logging.info(f"{self.session_id}TTS stream complete: {data.get('message')}")
                                if on_end:
                                    await self._maybe_await(on_end(data))
                                success = True
                                break
                            elif msg_type == "error":
                                logging.error(f"{self.session_id}TTS error: {data.get('message')}")
                                if on_error:
                                    await self._maybe_await(on_error(data))
                                break
                        except json.JSONDecodeError:
                            logging.warning(f"{self.session_id}Received non-JSON text message: {message[:50]}...")
                    
                    # Handle binary audio data
                    elif isinstance(message, bytes):
                        if on_audio:
                            await self._maybe_await(on_audio(message))
                    
                except websockets.exceptions.ConnectionClosed as e:
                    logging.info(f"{self.session_id}TTS WebSocket connection closed with code {e.code}")
                    break
            
            return success
                
        except Exception as e:
            logging.error(f"{self.session_id}Error processing TTS stream: {e}")
            traceback.print_exc()
            return False
            
    async def _maybe_await(self, result):
        """Handle a result that may or may not be awaitable.
        
        Args:
            result: The result to handle
        """
        if result is not None and asyncio.iscoroutine(result):
            await result
    
    async def _wait_with_timeout(self, awaitable):
        """Wait for an awaitable with timeout.
        
        Args:
            awaitable: The awaitable to wait for
            
        Returns:
            The result of the awaitable or None on timeout
        """
        try:
            return await asyncio.wait_for(awaitable, timeout=self.timeout_seconds)
        except asyncio.TimeoutError:
            return None
    
    async def close(self):
        """Close the connection to the Piper TTS server."""
        if self.websocket:
            try:
                # Normal closure code
                await self.websocket.close(code=1000, reason="Normal closure")
                logging.info(f"{self.session_id}WebSocket connection closed gracefully")
            except Exception as e:
                logging.error(f"{self.session_id}Error closing WebSocket connection: {e}")
            finally:
                self.websocket = None
                self.is_connected = False
    
    async def disconnect(self):
        """Disconnect from the Piper TTS server (alias for close)."""
        await self.close()

    async def synthesize_and_process(self, text: str, voice: str = None) -> Tuple[bool, bytes]:
        """Synthesize text and collect all audio data.
        
        This is a convenience method that combines synthesize() and process_stream(),
        collecting all audio bytes into a single buffer.
        
        Args:
            text: The text to synthesize
            voice: Optional voice name
            
        Returns:
            Tuple[bool, bytes]: (success, audio_bytes)
        """
        if not await self.connect():
            return False, b''
        
        if not await self.synthesize(text, voice):
            await self.close()
            return False, b''
        
        all_audio = bytearray()
        
        def on_audio(audio_chunk):
            nonlocal all_audio
            all_audio.extend(audio_chunk)
        
        success = await self.process_stream(on_audio=on_audio)
        await self.close()
        
        return success, bytes(all_audio)

    async def stream_synthesize(self, text: str, chunk_callback: Callable[[bytes], None], voice: str = None) -> bool:
        """Synthesize text and stream audio chunks via callback.
        
        This method connects, synthesizes, and streams audio chunks to the provided callback.
        
        Args:
            text: The text to synthesize
            chunk_callback: Callback function for each audio chunk
            voice: Optional voice name
            
        Returns:
            bool: True if successful
        """
        if not await self.connect():
            return False
        
        if not await self.synthesize(text, voice):
            await self.close()
            return False
        
        success = await self.process_stream(on_audio=chunk_callback)
        await self.close()
        
        return success 