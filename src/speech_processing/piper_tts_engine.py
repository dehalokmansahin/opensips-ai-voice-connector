import asyncio
import websockets
import json
import logging
import traceback # Keep for now, might be useful in refactored stream processing
from websockets.exceptions import ConnectionClosedError, ConnectionClosedOK
from typing import Optional, Dict, Any, Union, Callable, Tuple, Awaitable, AsyncGenerator

from .tts_engine_base import TTSEngineBase

class PiperTTSEngine(TTSEngineBase):
    """
    Client for Piper TTS WebSocket server, implementing TTSEngineBase.

    This client provides methods to connect to a Piper TTS server,
    send text for synthesis, and stream audio data.
    """

    def __init__(self, server_host="localhost", server_port=8000, session_id="", timeout_seconds=10):
        """Initialize the PiperTTSEngine.

        Args:
            server_host: Hostname or IP address of the Piper TTS server
            server_port: Port number of the Piper TTS server
            session_id: Optional session ID prefix for logging
            timeout_seconds: Connection and receive timeout in seconds
        """
        self.server_url = f"ws://{server_host}:{server_port}/tts"
        self.session_id = session_id
        self.websocket: Optional[websockets.WebSocketClientProtocol] = None
        self._is_connected_status: bool = False # Internal flag for connection status
        self.timeout_seconds: float = timeout_seconds
        logging.info(f"{self.session_id}Initialized PiperTTSEngine for {self.server_url}")

    async def connect(self) -> bool:
        """Connect to the Piper TTS WebSocket server.

        Returns:
            bool: True if connection successful, False otherwise
        """
        if self._is_connected_status and self.websocket:
            if hasattr(self.websocket, 'closed') and not self.websocket.closed:
                logging.info(f"{self.session_id}Already connected to Piper TTS server.")
                return True
            elif not hasattr(self.websocket, 'closed'):
                # For newer websockets library where 'closed' doesn't exist
                logging.info(f"{self.session_id}Already connected to Piper TTS server.")
                return True
        try:
            logging.info(f"{self.session_id}Connecting to Piper TTS server at {self.server_url}")
            self.websocket = await websockets.connect(self.server_url, open_timeout=self.timeout_seconds)
            self._is_connected_status = True
            logging.info(f"{self.session_id}Connected to Piper TTS server at {self.server_url}")
            return True
        except Exception as e:
            logging.error(f"{self.session_id}Failed to connect to Piper TTS server: {e}")
            self._is_connected_status = False
            self.websocket = None # Ensure websocket is None on failed connect
            return False

    async def _send_synthesis_request(self, text: str, voice: Optional[str] = None, output_format: Optional[str] = None) -> bool:
        """Helper to send the synthesis request to Piper."""
        if not self.is_connected() or not self.websocket:
            logging.error(f"{self.session_id}Cannot synthesize text: Not connected to Piper TTS server")
            return False

        try:
            request = {"text": text}
            if voice:
                request["voice"] = voice
            # output_format is noted but Piper typically has a fixed output per voice/server.
            # If Piper API evolves to support this, it can be added to the request.
            if output_format:
                logging.info(f"{self.session_id}Output format '{output_format}' requested (note: Piper may use server default).")
                # request["output_format"] = output_format # Example if Piper supports it

            logging.info(f"{self.session_id}Sending TTS request: '{text[:50]}{'...' if len(text) > 50 else ''}'")
            await self.websocket.send(json.dumps(request))
            return True
        except Exception as e:
            logging.error(f"{self.session_id}Failed to send text to Piper TTS server: {e}")
            # If send fails, connection might be compromised
            await self.disconnect() # Clear connection status
            return False

    async def synthesize_speech(
        self,
        text: str,
        voice: str, # Made voice non-optional as per typical TTS usage
        output_format: str = "pcm_16000" # Default, but Piper's output is usually fixed by server
    ) -> AsyncGenerator[bytes, None]:
        """
        Synthesizes speech from the given text using the specified voice and format.
        Streams audio chunks as they become available.
        """
        if not self.is_connected():
            logging.error(f"{self.session_id}Cannot synthesize: Not connected. Please connect first.")
            # Yield nothing if not connected, or could raise an error.
            # An empty generator is one way to handle this.
            if False: # pragma: no cover
                yield b""
            return

        if not await self._send_synthesis_request(text, voice, output_format):
            # Failed to send request, error already logged.
            if False: # pragma: no cover
                yield b""
            return

        try:
            # Handle initial message (start or connected)
            initial_message_data = await self._wait_with_timeout(self.websocket.recv())
            if not initial_message_data:
                logging.error(f"{self.session_id}Timed out waiting for initial message from Piper TTS server after request.")
                return # Stop generation

            try:
                start_data = json.loads(initial_message_data)
                msg_type = start_data.get("type")
                if msg_type in ["start", "connected", "audio_start"]: # 'audio_start' observed in some Piper versions
                    logging.info(f"{self.session_id}TTS stream started: {start_data.get('message', '')}")
                else:
                    logging.warning(f"{self.session_id}Unexpected first message from TTS server: {start_data}")
                    # Depending on strictness, might want to return or raise here.
            except json.JSONDecodeError:
                # If the first message isn't JSON, it might be audio data directly (less common for Piper)
                if isinstance(initial_message_data, bytes):
                    logging.debug(f"{self.session_id}Received initial binary data, assuming audio.")
                    yield initial_message_data
                else:
                    logging.warning(f"{self.session_id}Received non-JSON/non-binary initial message: {str(initial_message_data)[:70]}...")
                    return # Stop generation

            # Process subsequent audio stream and control messages
            while True:
                message = await self._wait_with_timeout(self.websocket.recv())
                if message is None: # Timeout
                    logging.error(f"{self.session_id}Timed out waiting for audio data from Piper TTS server.")
                    break

                if isinstance(message, str): # JSON control messages
                    try:
                        data = json.loads(message)
                        msg_type = data.get("type")

                        if msg_type == "end" or msg_type == "audio_end": # 'audio_end' observed
                            logging.info(f"{self.session_id}TTS stream complete: {data.get('message', '')}")
                            break # End of stream
                        elif msg_type == "error":
                            logging.error(f"{self.session_id}TTS error from server: {data.get('message')}")
                            # Consider raising an exception here
                            break
                        else:
                            logging.debug(f"{self.session_id}Received other JSON message: {data}")
                    except json.JSONDecodeError:
                        logging.warning(f"{self.session_id}Received non-JSON text message during stream: {message[:70]}...")

                elif isinstance(message, bytes): # Binary audio data
                    yield message

        except websockets.exceptions.ConnectionClosed as e:
            logging.info(f"{self.session_id}TTS WebSocket connection closed during stream with code {e.code}")
            self._is_connected_status = False
            self.websocket = None
        except asyncio.TimeoutError: # Should be caught by _wait_with_timeout, but as a safeguard
            logging.error(f"{self.session_id}Asyncio timeout error during TTS stream processing.")
        except Exception as e:
            logging.error(f"{self.session_id}Error processing TTS stream: {e}", exc_info=True)
            # Ensure connection is marked as closed on unexpected error
            await self.disconnect()
        finally:
            # This generator should not be responsible for closing the connection by default.
            # The caller of synthesize_speech should manage connect/disconnect.
            logging.debug(f"{self.session_id}TTS synthesize_speech generator finished.")

    async def _wait_with_timeout(self, awaitable):
        """Wait for an awaitable with timeout."""
        if not self.is_connected() or not self.websocket:
             logging.warning(f"{self.session_id}_wait_with_timeout called while not connected.")
             return None
        try:
            return await asyncio.wait_for(awaitable, timeout=self.timeout_seconds)
        except asyncio.TimeoutError:
            logging.debug(f"{self.session_id}Timeout waiting for awaitable.")
            return None
        except websockets.exceptions.ConnectionClosed: # Catch if connection closes during wait
            logging.info(f"{self.session_id}Connection closed while waiting for awaitable.")
            self._is_connected_status = False
            self.websocket = None
            return None


    async def disconnect(self) -> None:
        """Close the connection to the Piper TTS server."""
        if self.websocket:
            try:
                if hasattr(self.websocket, 'closed'):
                    if not self.websocket.closed:
                        await self.websocket.close(code=1000, reason="Normal client disconnect")
                        logging.info(f"{self.session_id}Piper TTS WebSocket connection closed gracefully.")
                else:
                    # For newer websockets library where 'closed' doesn't exist
                    await self.websocket.close(code=1000, reason="Normal client disconnect")
                    logging.info(f"{self.session_id}Piper TTS WebSocket connection closed gracefully.")
            except Exception as e:
                logging.error(f"{self.session_id}Error closing Piper TTS WebSocket connection: {e}")
            finally:
                self.websocket = None
        self._is_connected_status = False # Ensure status is false regardless of errors

    def is_connected(self) -> bool:
        """Check the current connection status to the TTS service."""
        if self._is_connected_status and self.websocket:
            if hasattr(self.websocket, 'closed') and self.websocket.closed:
                # If status is true but websocket says closed, update internal status
                logging.warning(f"{self.session_id}PiperTTSEngine: Connection status mismatch, websocket is closed.")
                self._is_connected_status = False
        return self._is_connected_status

    # Original methods like synthesize_and_process and stream_synthesize can be removed
    # as their functionality is now covered by TTSEngineBase's synthesize_speech.
    # The old process_stream is integrated into synthesize_speech.
    # The old synthesize is now _send_synthesis_request.
    # The old close is now disconnect.
    # The old _maybe_await is not directly needed if callbacks are not used in synthesize_speech.

    # For compatibility, if any internal logic still uses 'close', we can alias it.
    async def close(self):
        await self.disconnect()
