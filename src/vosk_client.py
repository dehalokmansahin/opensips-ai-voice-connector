import asyncio
import websockets
import json
import logging
import traceback
from websockets.exceptions import ConnectionClosedError, ConnectionClosedOK
from typing import Optional

class VoskClient:
    def __init__(self, server_url, timeout=5.0):
        self.server_url = server_url
        self.websocket = None
        self.is_connected = False
        self.receiving = False
        self.read_timeout = timeout  # saniye olarak okuma zaman aşımı

    async def connect(self):
        try:
            self.websocket = await websockets.connect(self.server_url)
            self.is_connected = True
            logging.info(f"Connected to Vosk server at {self.server_url}")
            return True
        except Exception as e:
            logging.error(f"Failed to connect to Vosk server: {e}")
            self.is_connected = False
            return False

    async def send(self, data):
        """Send a message to the Vosk server
        
        Args:
            data: Data to send (dict or JSON string)
            
        Returns:
            bool: True if successful, False otherwise
        """
        if not self.is_connected or not self.websocket:
            logging.error("Cannot send data: Not connected to Vosk server")
            return False

        try:
            if isinstance(data, dict):
                data = json.dumps(data)
            await self.websocket.send(data)
            return True
        except Exception as e:
            logging.error(f"Failed to send data to Vosk server: {e}")
            self.is_connected = False
            return False

    async def send_audio(self, audio_bytes: bytes):
        if not self.is_connected or not self.websocket:
            logging.error("Cannot send audio: Not connected to Vosk server")
            return False

        if not isinstance(audio_bytes, bytes):
            logging.error(f"Audio data must be bytes, got {type(audio_bytes).__name__}")
            return False
            
        # Debug log the audio data details
        audio_len = len(audio_bytes)
        if audio_len == 0:
            logging.error("Cannot send empty audio data to Vosk")
            return False
            
        # Add hex dump of first few bytes for debugging
        if audio_len > 0:
            hex_preview = ' '.join([f'{b:02x}' for b in audio_bytes[:20]])
            logging.debug(f"Sending audio: {audio_len} bytes, first 20 bytes: {hex_preview}")

        try:
            await self.websocket.send(audio_bytes)
            return True
        except Exception as e:
            logging.error(f"Failed to send audio data to Vosk server: {e}")
            self.is_connected = False
            return False

    async def send_eof(self):
        if not self.is_connected or not self.websocket:
            logging.error("Cannot send EOF: Not connected to Vosk server")
            return False

        try:
            logging.info("Sending EOF message to Vosk server")
            await self.websocket.send(json.dumps({"eof": 1}))
            # Sunucuya EOF işlenmesi için kısa bir süre tanı
            await asyncio.sleep(0.1)
            return True
        except Exception as e:
            logging.error(f"Failed to send EOF to Vosk server: {e}")
            self.is_connected = False
            return False

    async def receive_result(self) -> Optional[str]:
        if not self.is_connected or not self.websocket:
            logging.error("Cannot receive result: Not connected to Vosk server")
            return None

        try:
            # Zaman aşımı ile mesaj bekleme
            self.receiving = True
            message = None
            try:
                message = await asyncio.wait_for(
                    self.websocket.recv(), 
                    timeout=self.read_timeout
                )
                logging.debug(f"Received raw WebSocket message: {message[:100]}...")
                
                # JSON mesajı ise, içeriği kontrol et
                try:
                    result = json.loads(message)
                    if "text" in result and result["text"]:
                        logging.info(f"Transcription received from Vosk: {result['text']}")
                    elif "partial" in result and result["partial"]:
                        logging.debug(f"Partial transcription: {result['partial']}")
                    elif "eof" in result:
                        logging.info("EOF acknowledgment received from Vosk server")
                    else:
                        logging.debug(f"Other message received: {message[:50]}...")
                except json.JSONDecodeError:
                    logging.warning(f"Received non-JSON message: {message[:50]}...")
                except Exception as e:
                    logging.error(f"Error processing message: {e}")
                
                return message
                
            except asyncio.TimeoutError:
                logging.debug("Timeout while waiting for message from Vosk server")
                return None
            
        except websockets.exceptions.ConnectionClosed as e:
            if e.code == 1000:
                logging.info(f"WebSocket connection closed normally with code {e.code}")
            elif e.code == 1001:
                logging.info(f"WebSocket connection going away with code {e.code}")
            else:
                logging.warning(f"WebSocket connection closed with code {e.code}: {e.reason}")
            self.is_connected = False
            return None
        except Exception as e:
            logging.error(f"Error receiving result from Vosk server: {e}")
            self.is_connected = False
            return None
        finally:
            self.receiving = False

    async def disconnect(self):
        """Disconnect from the Vosk server (alias for close)"""
        await self.close()

    async def close(self):
        if self.websocket:
            try:
                # Normal kapatma kodu ile WebSocket'i kapatıyoruz
                await self.websocket.close(code=1000, reason="Normal closure")
                logging.info("WebSocket connection closed gracefully")
            except Exception as e:
                logging.error(f"Error closing WebSocket connection: {e}")
            finally:
                self.websocket = None
                self.is_connected = False
