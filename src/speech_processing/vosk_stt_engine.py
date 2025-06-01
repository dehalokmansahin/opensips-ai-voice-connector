import asyncio
import websockets
import json
import logging
from websockets.exceptions import ConnectionClosedError, ConnectionClosedOK
from typing import Optional, Dict, Any

from .stt_engine_base import STTEngineBase

class VoskSTTEngine(STTEngineBase):
    """
    A WebSocket client for interacting with a Vosk STT (Speech-to-Text) server,
    implementing the STTEngineBase interface.
    """
    def __init__(self, server_url: str, timeout: float = 5.0):
        """
        Initializes the VoskSTTEngine.

        Args:
            server_url: The URL of the Vosk WebSocket server (e.g., "ws://localhost:2700").
            timeout: The timeout in seconds for WebSocket read operations.
        """
        self.server_url: str = server_url
        self.websocket: Optional[websockets.WebSocketClientProtocol] = None
        self._is_connected_status: bool = False # Internal flag for connection status
        self.read_timeout: float = timeout

    async def connect(self) -> bool:
        """
        Connects to the Vosk WebSocket server.
        """
        try:
            self.websocket = await websockets.connect(self.server_url)
            self._is_connected_status = True
            logging.info(f"Connected to Vosk server at {self.server_url}")
            return True
        except Exception as e:
            logging.error(f"Failed to connect to Vosk server: {e}")
            self._is_connected_status = False
            return False

    # New private helper methods
    def _ensure_connected(self, action: str) -> bool:
        """Return True if websocket is connected, log and return False otherwise."""
        if not self.is_connected() or not self.websocket:
            logging.error(f"Cannot {action}: Not connected to Vosk server.")
            return False
        return True

    def _log_debug(self, prefix: str, data: Any) -> None:
        """Log debugging information if debug logging is enabled."""
        if logging.getLogger().isEnabledFor(logging.DEBUG):
            logging.debug(f"{prefix}{data}")

    async def _recv_message(self) -> Optional[str]:
        """Receive a message with timeout and return its string or None."""
        try:
            data = await asyncio.wait_for(self.websocket.recv(), timeout=self.read_timeout)
            return str(data)
        except asyncio.TimeoutError:
            logging.debug(f"Timeout ({self.read_timeout}s) waiting for message from Vosk server.")
            return None
        except websockets.exceptions.ConnectionClosed as e:
            if e.code in (1000, 1001):
                logging.info(f"WebSocket closed during recv: code {e.code}")
            else:
                logging.warning(f"WebSocket closed unexpectedly during recv: code {e.code}, reason: {e.reason}")
            self._is_connected_status = False
            return None
        except Exception as e:
            logging.error(f"Error receiving from Vosk server: {e}", exc_info=True)
            self._is_connected_status = False
            return None

    async def send_config(self, config: Dict[str, Any]) -> bool:
        """
        Sends configuration parameters to the Vosk server.
        For Vosk, this typically involves sending a JSON string with a "config" key.
        Example: {"config": {"sample_rate": 16000, "num_channels": 1}}
        """
        if not self._ensure_connected("send config"):
            return False

        try:
            # Vosk expects configuration to be under a 'config' key if it's about sample rate etc.
            # If the passed 'config' is already the complete message, this might need adjustment
            # or the caller should format it correctly.
            # For now, assuming 'config' IS the dictionary to be sent (e.g. `{"config": {"sample_rate": ...}}`)
            message_to_send = json.dumps(config)
            await self.websocket.send(message_to_send)
            logging.info(f"Sent configuration to Vosk server: {message_to_send[:100]}")
            return True
        except Exception as e:
            logging.error(f"Failed to send config to Vosk server: {e}. Config: {str(config)[:100]}")
            self._is_connected_status = False
            return False

    async def send_audio(self, audio_bytes: bytes) -> bool:
        """
        Sends raw audio bytes to the Vosk server.
        """
        if not self._ensure_connected("send audio"):
            return False

        if not isinstance(audio_bytes, bytes):
            logging.warning(f"Audio data must be bytes, got {type(audio_bytes).__name__}. Skipping send.")
            return False
            
        if not audio_bytes:
            logging.warning("Cannot send empty audio data to Vosk. Skipping send.")
            return False
            
        self._log_debug("Sending audio: ", f"{len(audio_bytes)} bytes, preview={audio_bytes[:20].hex()}...")

        try:
            await self.websocket.send(audio_bytes)
            return True
        except Exception as e:
            logging.error(f"Failed to send audio data to Vosk server: {e}")
            self._is_connected_status = False
            return False

    async def send_eof(self) -> bool:
        """
        Sends an EOF (End Of File/Stream) signal to the Vosk server.
        """
        if not self._ensure_connected("send EOF"):
            return False

        try:
            logging.info("Sending EOF message to Vosk server.")
            await self.websocket.send(json.dumps({"eof": 1}))
            await asyncio.sleep(0.1) 
            return True
        except Exception as e:
            logging.error(f"Failed to send EOF to Vosk server: {e}")
            self._is_connected_status = False
            return False

    async def receive_result(self) -> Optional[str]:
        """
        Receives a transcription result or message from the Vosk server.
        """
        if not self._ensure_connected("receive result"):
            return None

        try:
            message_str = await self._recv_message()
            if message_str is None:
                return None

            self._log_debug("Received raw message: ", message_str[:100])

            # Attempt JSON parse and log accordingly
            try:
                result = json.loads(message_str)
                if text := result.get("text"):
                    logging.info(f"Vosk: Final transcript: \"{text}\"")
                elif partial := result.get("partial"):
                    logging.debug(f"Vosk: Partial transcript: \"{partial}\"")
                elif result.get("eof"):
                    logging.info("Vosk: EOF acknowledgment received.")
            except json.JSONDecodeError:
                self._log_debug("Non-JSON message received: ", message_str[:70])
            except Exception as e_parse:
                logging.error(f"Error logging received message: {e_parse}", exc_info=True)
            
            return message_str
            
        except websockets.exceptions.ConnectionClosed as e:
            if e.code == 1000:
                logging.info(f"WebSocket connection to Vosk closed normally (code {e.code}).")
            elif e.code == 1001:
                logging.info(f"WebSocket connection to Vosk server is going away (code {e.code}).")
            else:
                logging.warning(f"WebSocket connection to Vosk closed unexpectedly (code {e.code}, reason: {e.reason}).")
            self._is_connected_status = False
            return None
        except Exception as e:
            logging.error(f"Error receiving result from Vosk server: {e}", exc_info=True)
            self._is_connected_status = False
            return None

    async def disconnect(self) -> None:
        """
        Closes the WebSocket connection to the Vosk server gracefully.
        """
        if self.websocket:
            try:
                if self._is_connected_status: # Only attempt close if we think we are connected
                    await self.websocket.close(code=1000, reason="Normal client disconnect")
                    logging.info("WebSocket connection to Vosk closed gracefully.")
            except Exception as e:
                logging.error(f"Error closing WebSocket connection to Vosk: {e}")
            finally:
                self.websocket = None
                self._is_connected_status = False
        else:
            logging.debug("Disconnect called but WebSocket was already None.")
        self._is_connected_status = False # Ensure status is false

    def is_connected(self) -> bool:
        """
        Checks the current connection status to the STT service.
        """
        # Check websocket state too, in case of abrupt disconnection
        if self.websocket and hasattr(self.websocket, 'closed'):
            # For older websockets library versions
            if self.websocket.closed:
                self._is_connected_status = False
        elif self.websocket:
            # For newer websockets library versions
            try:
                # Check if we can access any attribute that would raise an exception if disconnected
                # or use our internal status flag
                if not self._is_connected_status:
                    return False
            except Exception:
                self._is_connected_status = False
        return self._is_connected_status

    # Keep original send method if it's used internally or for other purposes,
    # but STTEngineBase uses send_config specifically.
    # If not needed, it can be removed or aliased.
    async def send(self, data: dict | str) -> bool:
        """
        Generic send method. For STTEngineBase compliance, use send_config for configs.
        Sends a message (typically JSON configuration) to the Vosk server.
        """
        if not self.is_connected() or not self.websocket:
            logging.error("Cannot send data: Not connected to Vosk server.")
            return False
        try:
            message_to_send = json.dumps(data) if isinstance(data, dict) else data
            await self.websocket.send(message_to_send)
            return True
        except Exception as e:
            logging.error(f"Failed to send data to Vosk server: {e}. Data: {str(data)[:100]}")
            self._is_connected_status = False
            return False

    # Keep original close method, aliased by disconnect for STTEngineBase
    async def close(self):
        """
        Alias for disconnect for backward compatibility if internal calls use `close()`.
        """
        await self.disconnect()
