import asyncio
import websockets
import json
import logging
# import traceback # Unused import
from websockets.exceptions import ConnectionClosedError, ConnectionClosedOK
from typing import Optional

class VoskClient:
    """
    A WebSocket client for interacting with a Vosk STT (Speech-to-Text) server.

    This class handles connecting to the Vosk server, sending audio data for transcription,
    and receiving transcription results. It manages the WebSocket connection lifecycle
    and provides methods for sending configuration, audio chunks, and EOF signals.
    """
    def __init__(self, server_url: str, timeout: float = 5.0):
        """
        Initializes the VoskClient.

        Args:
            server_url: The URL of the Vosk WebSocket server (e.g., "ws://localhost:2700").
            timeout: The timeout in seconds for WebSocket read operations.
        """
        self.server_url: str = server_url
        self.websocket: Optional[websockets.WebSocketClientProtocol] = None
        self.is_connected: bool = False
        self.read_timeout: float = timeout  # Read timeout in seconds

    async def connect(self) -> bool:
        """
        Connects to the Vosk WebSocket server.

        Sets `self.is_connected` to True on success, False otherwise.

        Returns:
            True if the connection was successful, False otherwise.
        """
        try:
            self.websocket = await websockets.connect(self.server_url)
            self.is_connected = True
            logging.info(f"Connected to Vosk server at {self.server_url}")
            return True
        except Exception as e:
            logging.error(f"Failed to connect to Vosk server: {e}")
            self.is_connected = False
            return False

    async def send(self, data: dict | str) -> bool:
        """
        Sends a message (typically JSON configuration) to the Vosk server.

        Args:
            data: Data to send. Can be a dictionary (which will be dumped to JSON)
                  or a pre-formatted JSON string.
            
        Returns:
            True if the data was sent successfully, False otherwise.
        """
        if not self.is_connected or not self.websocket:
            logging.error("Cannot send data: Not connected to Vosk server.")
            return False

        try:
            message_to_send = json.dumps(data) if isinstance(data, dict) else data
            await self.websocket.send(message_to_send)
            return True
        except Exception as e:
            logging.error(f"Failed to send data to Vosk server: {e}. Data: {str(data)[:100]}")
            # Consider if connection is always broken here. Vosk might be strict.
            self.is_connected = False 
            return False

    async def send_audio(self, audio_bytes: bytes) -> bool:
        """
        Sends raw audio bytes to the Vosk server.

        Args:
            audio_bytes: The audio data to send, as bytes.
            
        Returns:
            True if the audio data was sent successfully, False otherwise.
        """
        if not self.is_connected or not self.websocket:
            logging.error("Cannot send audio: Not connected to Vosk server.")
            return False

        if not isinstance(audio_bytes, bytes):
            logging.warning(f"Audio data must be bytes, got {type(audio_bytes).__name__}. Skipping send.")
            return False
            
        if not audio_bytes: # Check for empty bytes
            logging.warning("Cannot send empty audio data to Vosk. Skipping send.")
            return False
            
        # Debug log includes length and a preview of the audio data
        if logging.getLogger().isEnabledFor(logging.DEBUG):
            hex_preview = ' '.join([f'{b:02x}' for b in audio_bytes[:20]])
            logging.debug(f"Sending audio: {len(audio_bytes)} bytes, first 20 bytes (hex): {hex_preview}")

        try:
            await self.websocket.send(audio_bytes)
            return True
        except Exception as e:
            logging.error(f"Failed to send audio data to Vosk server: {e}")
            self.is_connected = False # Assume connection is compromised if send fails
            return False

    async def send_eof(self) -> bool:
        """
        Sends an EOF (End Of File/Stream) signal to the Vosk server.

        This typically indicates that no more audio will be sent for the current utterance.
        
        Returns:
            True if the EOF signal was sent successfully, False otherwise.
        """
        if not self.is_connected or not self.websocket:
            logging.error("Cannot send EOF: Not connected to Vosk server.")
            return False

        try:
            logging.info("Sending EOF message to Vosk server.")
            await self.websocket.send(json.dumps({"eof": 1}))
            # Brief pause to allow server to process EOF; behavior might vary by server implementation.
            await asyncio.sleep(0.1) 
            return True
        except Exception as e:
            logging.error(f"Failed to send EOF to Vosk server: {e}")
            self.is_connected = False
            return False

    async def receive_result(self) -> Optional[str]:
        """
        Receives a transcription result or message from the Vosk server.

        This method waits for a message with a configured timeout (`self.read_timeout`).
        It handles JSON parsing of results and logs different types of messages
        (partial, final, EOF).

        Returns:
            The raw message string received from the server if successful, 
            None if a timeout occurs or if the connection is closed/lost.
        """
        if not self.is_connected or not self.websocket:
            logging.error("Cannot receive result: Not connected to Vosk server.")
            return None

        try:
            message: Optional[str] = None
            try:
                # Wait for a message from the WebSocket with the specified timeout
                message = await asyncio.wait_for(
                    self.websocket.recv(), 
                    timeout=self.read_timeout
                )
                if logging.getLogger().isEnabledFor(logging.DEBUG):
                    logging.debug(f"Received raw WebSocket message: {str(message)[:100]}...") # Ensure message is str for slicing
                
                # Attempt to parse if it's a JSON message for more detailed logging
                try:
                    result = json.loads(str(message)) # Ensure message is str for json.loads
                    if "text" in result and result["text"]:
                        # Log final transcriptions at INFO level
                        logging.info(f"Vosk: Final transcript: \"{result['text']}\"")
                    elif "partial" in result and result["partial"]:
                        # Log partial transcriptions at DEBUG level
                        logging.debug(f"Vosk: Partial transcript: \"{result['partial']}\"")
                    elif "eof" in result:
                        logging.info("Vosk: EOF acknowledgment received from server.")
                    # Add other specific Vosk message types if needed
                except json.JSONDecodeError:
                    # If not JSON, or if JSON structure is unexpected, log as a general message
                    logging.debug(f"Vosk: Received non-JSON or unknown structure message: {str(message)[:70]}...")
                except Exception as e_parse:
                    # Catch errors during the parsing/logging phase but still return the original message
                    logging.error(f"Error processing/logging received message: {e_parse}")
                
                return str(message) # Return the raw message string
                
            except asyncio.TimeoutError:
                # This is an expected event during periods of silence
                logging.debug(f"Timeout ({self.read_timeout}s) waiting for message from Vosk server.")
                return None # Return None to indicate no message received within timeout
            
        except websockets.exceptions.ConnectionClosed as e:
            # Handle WebSocket connection closed scenarios
            if e.code == 1000: # Normal closure
                logging.info(f"WebSocket connection to Vosk closed normally (code {e.code}).")
            elif e.code == 1001: # Going away
                logging.info(f"WebSocket connection to Vosk server is going away (code {e.code}).")
            else: # Other closure codes
                logging.warning(f"WebSocket connection to Vosk closed unexpectedly (code {e.code}, reason: {e.reason}).")
            self.is_connected = False
            return None
        except Exception as e:
            # Catch any other exceptions during receive
            logging.error(f"Error receiving result from Vosk server: {e}", exc_info=True)
            self.is_connected = False
            return None

    async def disconnect(self):
        """
        Disconnects from the Vosk server. This is an alias for `close()`.
        """
        await self.close()

    async def close(self):
        """
        Closes the WebSocket connection to the Vosk server gracefully.
        
        Sets `self.is_connected` to False and `self.websocket` to None.
        """
        if self.websocket:
            try:
                # Attempt to close with a normal closure code
                await self.websocket.close(code=1000, reason="Normal client closure")
                logging.info("WebSocket connection to Vosk closed gracefully.")
            except Exception as e:
                logging.error(f"Error closing WebSocket connection to Vosk: {e}")
            finally:
                self.websocket = None
                self.is_connected = False
        else:
            logging.debug("Close called but WebSocket was already None.")
