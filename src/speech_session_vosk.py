from codec import get_codecs, PCMU, UnsupportedCodec
from vad_detector import VADDetector
from config import Config
import torch
import numpy as np
import asyncio
from ai import AIEngine
from queue import Empty
import json
import logging
from vosk_client import VoskClient
import torchaudio
import time
from pcmu_decoder import PCMUDecoder
import websockets
import traceback
import audioop  # For mu-law encoding
import random  # For simulated responses
from piper_client import PiperClient  # Import the new Piper client

# Wyoming client libraries for TTS are replaced with websockets
# from wyoming.client import AsyncTcpClient
# from wyoming.tts import Synthesize, SynthesizeVoice
# from wyoming.audio import AudioChunk, AudioStop

class AudioProcessor:
    """Audio processing utilities for speech recognition"""
    
    def __init__(self, target_sample_rate=16000, debug=False, session_id=""):
        self.target_sample_rate = target_sample_rate
        self.debug = debug
        self.session_id = session_id
        self.pcmu_decoder = PCMUDecoder()
        self.resampler = torchaudio.transforms.Resample(orig_freq=8000, new_freq=target_sample_rate)
    
    def tensor_to_bytes(self, tensor):
        """Convert audio tensor to bytes
        
        Args:
            tensor: Audio tensor
            
        Returns:
            bytes: Audio bytes
        """
        # Clamp to valid range and convert to int16 bytes
        processed_tensor = torch.clamp(tensor, -1.0, 1.0)
        return (processed_tensor * 32768.0).to(torch.int16).numpy().tobytes()
    
    def process_bytes_audio(self, audio):
        """Process raw audio bytes (PCMU) to tensor format
        
        Args:
            audio: Raw audio bytes (PCMU format)
            
        Returns:
            tuple: (resampled_tensor, audio_bytes) or (None, None) on error
        """
        if len(audio) == 0:
            logging.warning(f"{self.session_id}Received empty audio bytes. Skipping processing.")
            return None, None
            
        # Log input for debugging    
        if self.debug:
            logging.debug(f"{self.session_id}Raw input audio: {len(audio)} bytes")
        
        # Decode PCMU to PCM float32 NumPy array
        pcm32_samples_np = self.pcmu_decoder.decode(audio) # Returns np.ndarray(dtype=np.float32)

        if pcm32_samples_np is None or pcm32_samples_np.size == 0:
            logging.warning(f"{self.session_id}PCMU decoder returned empty result. Skipping processing.")
            return None, None
            
        # DETAILED LOG 1: After decoding PCMU to float32 samples
        # logging.debug(f"{self.session_id}Decoded PCM: {len(pcm16_samples)} bytes") # Old log
        logging.debug(f"{self.session_id}Decoded to float32 PCM samples: {len(pcm32_samples_np)}")
        
        # Ensure data is valid before conversion - check size now
        # if len(pcm16_samples) == 0:
        #     logging.warning(f"{self.session_id}Empty PCM after conversion. Skipping.")
        #     return None, None
        
        try:
            # Convert float32 NumPy array directly to float32 PyTorch tensor
            # No need for frombuffer or int16 conversion/scaling
            # audio_tensor = torch.frombuffer(bytearray(pcm16_samples), dtype=torch.int16).float() / 32768.0 # Old way
            audio_tensor = torch.from_numpy(pcm32_samples_np)
            # DETAILED LOG 2: After converting NumPy array to tensor
            # logging.debug(f"{self.session_id}Converted to 8kHz tensor: shape={audio_tensor.shape}, min={audio_tensor.min():.4f}, max={audio_tensor.max():.4f}") # Old log
            logging.debug(f"{self.session_id}Converted NumPy to 8kHz tensor: shape={audio_tensor.shape}, dtype={audio_tensor.dtype}, min={audio_tensor.min():.4f}, max={audio_tensor.max():.4f}")
            
            # Clean tensor if needed
            audio_tensor = self._clean_tensor(audio_tensor)
            
            # Normalize audio
            audio_tensor = self._normalize_audio(audio_tensor)
            
            # Resample to target rate (e.g., 16kHz)
            resampled_tensor = self.resampler(audio_tensor.unsqueeze(0)).squeeze(0)
            # DETAILED LOG 3: After resampling to target rate
            # logging.debug(f"{self.session_id}Resampled tensor: shape={resampled_tensor.shape}, min={resampled_tensor.min():.4f}, max={resampled_tensor.max():.4f}") # Old log
            logging.debug(f"{self.session_id}Resampled tensor: shape={resampled_tensor.shape}, dtype={resampled_tensor.dtype}, min={resampled_tensor.min():.4f}, max={resampled_tensor.max():.4f}")
            
            # Check the resampled audio validity
            if resampled_tensor.shape[0] == 0:
                logging.warning(f"{self.session_id}Resampling resulted in empty tensor. Skipping.")
                return None, None
            
            # Convert final float32 tensor to 16-bit PCM bytes for Vosk
            audio_bytes = self.tensor_to_bytes(resampled_tensor)
            
            # DETAILED LOG 4: Final bytes length before returning
            logging.debug(f"{self.session_id}Final processed audio bytes length: {len(audio_bytes)}")
            
            return resampled_tensor, audio_bytes
            
        except Exception as e:
            logging.error(f"{self.session_id}Error processing audio bytes: {str(e)}")
            logging.error(f"{self.session_id}Exception details: {traceback.format_exc()}")
            return None, None
    
    def _clean_tensor(self, tensor):
        """Clean tensor by removing NaN or Inf values
        
        Args:
            tensor: Audio tensor to clean
            
        Returns:
            torch.Tensor: Cleaned tensor
        """
        if torch.isnan(tensor).any() or torch.isinf(tensor).any():
            logging.warning(f"{self.session_id}Audio tensor contains NaN or Inf values. Cleaning tensor.")
            return torch.nan_to_num(tensor, nan=0.0, posinf=0.99, neginf=-0.99)
        return tensor
    
    def _normalize_audio(self, tensor):
        """Normalize audio levels for very quiet audio
        
        Args:
            tensor: Audio tensor to normalize
            
        Returns:
            torch.Tensor: Normalized tensor
        """
        audio_max = torch.max(torch.abs(tensor))
        
        # Only normalize very quiet audio
        if audio_max < 0.005:
            gain = min(0.2 / (audio_max + 1e-10), 5.0)
            tensor = tensor * gain
            logging.debug(f"{self.session_id}Applied normalization with gain: {gain:.2f}")
        
        return tensor

class VADProcessor:
    """Voice Activity Detection processor"""
    
    def __init__(self, vad_detector, target_sample_rate, audio_processor, 
                 vad_buffer_chunk_ms=750, speech_detection_threshold=3, 
                 silence_detection_threshold=10, debug=False, session_id=""):
        self.vad = vad_detector
        self.target_sample_rate = target_sample_rate
        self.audio_processor = audio_processor  # Add reference to audio processor
        self.vad_buffer_chunk_ms = vad_buffer_chunk_ms
        self.speech_detection_threshold = speech_detection_threshold
        self.silence_detection_threshold = silence_detection_threshold
        self.debug = debug
        self.session_id = session_id
        
        # VAD buffer
        self._vad_buffer = bytearray()
        self._vad_buffer_size_samples = 0
        self._last_buffer_flush_time = time.time()
        self._vad_buffer_locks = asyncio.Lock()
        
        # Speech state
        self.consecutive_speech_packets = 0
        self.consecutive_silence_packets = 0
        self.speech_active = False
    
    def reset_vad_state(self, preserve_buffer=False):
        """Reset VAD state between requests
        
        Args:
            preserve_buffer: If True, preserve the current buffer contents;
                            if False (default), clear the buffer
                            
        Returns:
            None
        """
        # Reset speech detection state counters
        self.consecutive_speech_packets = 0
        self.consecutive_silence_packets = 0
        
        # Reset speech activity flag
        was_active = self.speech_active
        self.speech_active = False
        
        # Optionally clear buffer (not using lock since this method should be called 
        # when no audio processing is active)
        if not preserve_buffer:
            self._vad_buffer.clear()
            self._vad_buffer_size_samples = 0
            self._last_buffer_flush_time = time.time()
            
        logging.info(f"{self.session_id}VAD state reset. Previous active state: {was_active}")

    async def add_audio(self, audio_bytes, num_samples):
        """Add audio to VAD buffer and process if needed
        
        Args:
            audio_bytes: Audio bytes to add
            num_samples: Number of samples in audio
            
        Returns:
            tuple: (is_processed, is_speech, buffer_bytes) - indicates if buffer was processed,
                  if speech was detected, and the processed buffer bytes
        """
        async with self._vad_buffer_locks:
            # Add to buffer
            self._vad_buffer.extend(audio_bytes)
            self._vad_buffer_size_samples += num_samples
            
            # Calculate buffer duration in ms
            buffer_ms = (self._vad_buffer_size_samples / self.target_sample_rate) * 1000
            
            # Check if buffer has reached threshold
            if buffer_ms >= self.vad_buffer_chunk_ms:
                logging.debug(f"{self.session_id}VAD buffer reached {buffer_ms:.2f}ms, processing for VAD")
                is_speech, buffer_bytes = await self._process_buffer()
                return True, is_speech, buffer_bytes
                
            return False, False, None
    
    async def _process_buffer(self):
        """Process VAD buffer
        
        Returns:
            tuple: (is_speech, buffer_bytes) - indicates if speech was detected and buffer bytes
        """
        buffer_bytes = bytes(self._vad_buffer)
        send_to_stt = False
        
        try:
            # Convert buffer to tensor for VAD processing
            audio_tensor = torch.frombuffer(bytearray(buffer_bytes), dtype=torch.int16).float() / 32768.0
            
            # Apply VAD
            is_speech = self.vad.is_speech(audio_tensor)
            
            # Update speech state
            if is_speech:
                self.consecutive_speech_packets += 1
                self.consecutive_silence_packets = 0
                
                # If enough consecutive speech packets, activate speech mode
                if self.consecutive_speech_packets >= self.speech_detection_threshold and not self.speech_active:
                    self.speech_active = True
                    logging.info(f"{self.session_id}Speech started after {self.consecutive_speech_packets} consecutive speech packets")
            else:
                self.consecutive_silence_packets += 1
                self.consecutive_speech_packets = 0
                
                # If enough consecutive silence packets, deactivate speech mode
                logging.info(f"{self.session_id}VAD CHECK: consecutive_silence_packets={self.consecutive_silence_packets}, silence_detection_threshold={self.silence_detection_threshold}, speech_active={self.speech_active}")
                if self.consecutive_silence_packets >= self.silence_detection_threshold and self.speech_active:
                    self.speech_active = False
                    logging.info(f"{self.session_id}Speech ended after {self.consecutive_silence_packets} consecutive silence packets")
            
            # Determine if audio should be sent to STT
            send_to_stt = is_speech or self.speech_active
            
            if send_to_stt:
                logging.info(f"{self.session_id}VAD: speech={is_speech}, active={self.speech_active}")
            else:
                logging.debug(f"{self.session_id}No speech detected in chunk, not sending to STT")
            
            return send_to_stt, buffer_bytes
            
        except Exception as e:
            logging.error(f"{self.session_id}Error processing VAD buffer: {str(e)}")
            # Return false to indicate no speech detected on error
            return False, buffer_bytes
        finally:
            # Clear buffer after processing
            self._vad_buffer.clear()
            self._vad_buffer_size_samples = 0
            self._last_buffer_flush_time = time.time()
    
    async def process_final_buffer(self):
        """Process any remaining audio in the buffer
        
        Returns:
            tuple: (is_speech, buffer_bytes) or (False, None) if empty buffer
        """
        if len(self._vad_buffer) > 0:
            buffer_seconds = self._vad_buffer_size_samples / self.target_sample_rate
            logging.info(f"{self.session_id}Processing remaining VAD buffer: {buffer_seconds:.2f} seconds")
            return await self._process_buffer()
        return False, None

class TranscriptHandler:
    """Handles transcript processing and callbacks"""
    
    def __init__(self, session_id=""):
        self.last_partial_transcript = ""
        self.last_final_transcript = ""
        self.on_partial_transcript = None
        self.on_final_transcript = None
        self.session_id = session_id
    
    async def handle_message(self, message):
        """Process transcript message from STT service
        
        Args:
            message: JSON message from STT service
            
        Returns:
            bool: True if message was processed successfully
        """
        try:
            # Parse JSON response
            response = json.loads(message)
            
            # Process partial transcript
            if "partial" in response:
                partial_text = response.get("partial", "")
                # Store last partial transcript
                self.last_partial_transcript = partial_text
                
                # Log the partial transcript if it's not empty
                if partial_text:
                    logging.info(f"{self.session_id}Partial transcript: {partial_text}") 
                
                if partial_text and self.on_partial_transcript:
                    await self.on_partial_transcript(partial_text)
            
            # Process final transcript
            if "text" in response:
                final_text = response.get("text", "")
                # Store last final transcript
                self.last_final_transcript = final_text
                
                # Log the final transcript if it's not empty
                if final_text:
                    logging.info(f"{self.session_id}FINAL transcript: {final_text}")
                    
                if final_text and self.on_final_transcript:
                    # Use asyncio.create_task to avoid blocking transcript receiver
                    asyncio.create_task(self.on_final_transcript(final_text))
                    
            return True
                
        except json.JSONDecodeError:
            logging.error(f"{self.session_id}Invalid JSON response: {message}")
            return False
        except Exception as e:
            logging.error(f"{self.session_id}Error processing transcript: {str(e)}")
            return False
    
    def get_final_transcript(self):
        """Get the last final transcript
        
        Returns:
            str: Last final transcript or partial if no final available
        """
        if self.last_final_transcript:
            logging.debug(f"{self.session_id}Returning final transcript: {self.last_final_transcript[:50]}...")
            return self.last_final_transcript
        elif self.last_partial_transcript:
            # If no final transcript but partial available, return partial
            logging.debug(f"{self.session_id}No final transcript available, returning partial: {self.last_partial_transcript[:50]}...")
            return self.last_partial_transcript
        else:
            # If no transcript available, return empty string
            logging.debug(f"{self.session_id}No transcript available, returning empty string")
            return ""

class VoskSTT(AIEngine):
    """Vosk API'yi kullanan konuşma tanıma motoru"""
    
    def __init__(self, call, cfg):
        """Vosk temelli konuşma tanıma motorunu başlat
        
        Args:
            call: OpenSIPS çağrısı
            cfg: Genel sistem yapılandırması
        """
        # Get Vosk-specific config
        self.cfg = Config.get("vosk", cfg)
        
        # Session ID olarak B2B Key'i kullan
        self.b2b_key = call.b2b_key if hasattr(call, 'b2b_key') else None
        self.session_id = f"[Session:{self.b2b_key}] " if self.b2b_key else ""
        self.queue = call.rtp
        # Load configuration
        self._load_config()
        
        # Initialize components
        self._init_components(call)
        
        # Task states
        self.receive_task = None
        self.tts_task = None  # New: Task for handling TTS processing
        
        # Closing state
        self._is_closing = False
        
        # Setup logging
        self._setup_logging()
        
        logging.info(f"{self.session_id}VoskSTT initialized. bypass_vad = {self.bypass_vad}")

    def _load_config(self):
        """Load configuration parameters from config"""
        # --- STT Configuration ---

            
        self.vosk_server_url = self.cfg.get("url", "url", "ws://localhost:2700")
        self.websocket_timeout = self.cfg.get("websocket_timeout", "websocket_timeout", 5.0)
        self.target_sample_rate = int(self.cfg.get("sample_rate", "sample_rate", 16000))
        self.channels = self.cfg.get("channels", "channels", 1)
        self.send_eof = self.cfg.get("send_eof", "send_eof", True)
        self.debug = self.cfg.get("debug", "debug", False)
        
        # VAD configuration
        self.bypass_vad = self.cfg.get("bypass_vad", "bypass_vad", False)
        self.vad_threshold = self.cfg.get("vad_threshold", "vad_threshold", 0.25)
        self.vad_min_speech_ms = self.cfg.get("vad_min_speech_ms", "vad_min_speech_ms", 350)
        self.vad_min_silence_ms = self.cfg.get("vad_min_silence_ms", "vad_min_silence_ms", 450)
        self.vad_buffer_chunk_ms = self.cfg.get("vad_buffer_chunk_ms", "vad_buffer_chunk_ms", 600)
        self.vad_buffer_max_seconds = self.cfg.get("vad_buffer_max_seconds", "vad_buffer_max_seconds", 2.0)
        self.speech_detection_threshold = self.cfg.get("speech_detection_threshold", "speech_detection_threshold", 1)
        self.silence_detection_threshold = self.cfg.get("silence_detection_threshold", "silence_detection_threshold", 2)


            
        self.tts_server_host = self.cfg.get("host", "TTS_HOST", "localhost")
        self.tts_server_port = int(self.cfg.get("port", "TTS_PORT", 8000))
        self.tts_voice = self.cfg.get("voice", "TTS_VOICE", "tr_TR-fahrettin-medium")
        self.tts_target_output_rate = 8000  # Target rate for RTP queue is always 8000Hz (PCMU requirement)
        # We'll determine actual input rate from the first audio chunk received from Piper
        
        logging.info(f"{self.session_id}Vosk URL: {self.vosk_server_url}, Target STT Rate: {self.target_sample_rate}")
        logging.info(f"{self.session_id}TTS Host: {self.tts_server_host}:{self.tts_server_port}, Voice: {self.tts_voice}")

    def _init_components(self, call):
        """Initialize required components
        
        Args:
            call: OpenSIPS call object
        """
        # Store call info
        self.call = call
        self.client_addr = call.client_addr
        self.client_port = call.client_port
        
        # Initialize codec from SDP
        self.codec = self.choose_codec(call.sdp)
        
        # Initialize audio processor
        self.audio_processor = AudioProcessor(
            target_sample_rate=self.target_sample_rate,
            debug=self.debug,
            session_id=self.session_id
        )
        
        # Initialize VAD detector
        vad_detector = VADDetector(
            sample_rate=self.target_sample_rate,
            threshold=self.vad_threshold,
            min_speech_duration_ms=self.vad_min_speech_ms,
            min_silence_duration_ms=self.vad_min_silence_ms
        )
        
        # Initialize VAD processor
        self.vad_processor = VADProcessor(
            vad_detector=vad_detector,
            target_sample_rate=self.target_sample_rate,
            audio_processor=self.audio_processor,
            vad_buffer_chunk_ms=self.vad_buffer_chunk_ms,
            speech_detection_threshold=self.speech_detection_threshold,
            silence_detection_threshold=self.silence_detection_threshold,
            debug=self.debug,
            session_id=self.session_id
        )
        
        # Set speech active if VAD is bypassed
        if self.bypass_vad:
            self.vad_processor.speech_active = True
        
        # Initialize transcript handler
        self.transcript_handler = TranscriptHandler(session_id=self.session_id)
        
        # Initialize Vosk client
        self.vosk_client = VoskClient(self.vosk_server_url, timeout=self.websocket_timeout)
        
        # --- TTS Setup ---
        # No WebSocket URL setup needed, PiperClient handles this
        logging.info(f"{self.session_id}Initializing Piper TTS client for {self.tts_server_host}:{self.tts_server_port}")
        # TTS resampler to be initialized when first TTS chunk arrives
        self.tts_resampler = None
        self.tts_input_rate = 22050  # Default Piper sample rate is 22050Hz
        # Lock to prevent concurrent TTS processing
        self.tts_processing_lock = asyncio.Lock()
        
        # --- Set Transcript Callback ---
        # When final transcript is received, trigger TTS
        self.transcript_handler.on_final_transcript = self._handle_final_transcript

    def _setup_logging(self):
        """Set up logging configuration"""
        # Set default logging level to INFO
        logging.basicConfig(level=logging.INFO)
        
        # Set debug level if enabled
        if self.debug:
            logging.getLogger().setLevel(logging.DEBUG)
            logging.debug(f"{self.session_id}Debug logging enabled")

    def choose_codec(self, sdp):
        """ SDP içinden PCMU codec'ini seçer """
        codecs = get_codecs(sdp)
        for c in codecs:
            if c.payloadType == 0:  # PCMU
                return PCMU(c)
        raise UnsupportedCodec("No supported codec (PCMU) found in SDP.")

    async def start(self):
        """STT motoru başlat ve bağlantıyı kur."""
        logging.info(f"{self.session_id}Vosk sunucusuna bağlanılıyor: {self.vosk_server_url}")
        
        try:
            # Reset closing flag when starting
            self._is_closing = False
            
            # Connect to Vosk server
            await self.vosk_client.connect()
            
            # Send initial configuration
            config = {
                "config": {
                    "sample_rate": self.target_sample_rate,
                    "num_channels": self.channels
                }
            }
            await self.vosk_client.send(config)
            
            # Start transcript receiver task
            self.receive_task = asyncio.create_task(self.receive_transcripts())
            
            logging.info(f"{self.session_id}Vosk STT motoru başarıyla başlatıldı")
            return True
        except Exception as e:
            logging.error(f"{self.session_id}Vosk motorunu başlatırken hata: {str(e)}")
            return False
    
    async def stop(self):
        """STT motorunu durdur ve bağlantıyı kapat."""
        logging.info(f"{self.session_id}Vosk STT motoru durduruluyor")
        
        try:
            # Send EOF if enabled
            await self._send_eof_if_enabled()
            
            # Close WebSocket connection
            if self.vosk_client.is_connected:
                await self.vosk_client.disconnect()
            
            # Cancel receive task
            await self._cancel_receive_task()
            
            logging.info(f"{self.session_id}Vosk STT motoru başarıyla durduruldu")
            return True
        except Exception as e:
            logging.error(f"{self.session_id}Vosk STT motorunu durdururken hata: {str(e)}")
            return False

    async def _manage_task(self, task, timeout=2.0):
        """Utility method to manage async tasks, stopping them gracefully
        
        Args:
            task: The asyncio task to manage
            timeout: Timeout in seconds before cancelling the task
            
        Returns:
            bool: True if task was cleanly stopped, False if it had to be cancelled
        """
        if task and not task.done():
            try:
                await asyncio.wait_for(task, timeout=timeout)
                return True
            except asyncio.TimeoutError:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
                return False
        return True

    async def _cancel_receive_task(self):
        """Cancel the transcript receive task"""
        await self._manage_task(self.receive_task)

    async def _send_eof_if_enabled(self):
        """Send EOF to Vosk if enabled"""
        if self.send_eof and self.vosk_client.is_connected:
            try:
                logging.debug(f"{self.session_id}Vosk'a EOF işareti gönderiliyor")
                await self.vosk_client.send(json.dumps({"eof": 1}))
                # Sunucunun EOF'u işlemesi için kısa bir süre bekle
                await asyncio.sleep(0.1)
            except Exception as e:
                logging.error(f"{self.session_id}EOF gönderirken hata: {str(e)}")

    async def process_audio(self, audio_data):
        """Ses verisini işle ve Vosk'a gönder
        
        Args:
            audio_data: İşlenecek raw ses verisi (PCM 16-bit)
            
        Returns:
            bool: İşleme başarılı olduysa True
        """
        if not self.vosk_client.is_connected:
            logging.warning(f"{self.session_id}Ses verisini işleyemiyorum: Vosk ile bağlantı kurulamadı")
            return False
            
        try:
            # Ses verisini Vosk'a gönder
            await self.vosk_client.send_audio(audio_data)
            return True
        except Exception as e:
            logging.error(f"{self.session_id}Ses verisini işlerken hata: {str(e)}")
            return False

    async def send(self, audio):
        """Sends audio to Vosk"""
        if not self.vosk_client.is_connected:
            logging.warning(f"{self.session_id}WebSocket not connected, cannot send audio")
            return
            
        try:
            if isinstance(audio, bytes):
                # Process bytes audio
                resampled_tensor, audio_bytes = self.audio_processor.process_bytes_audio(audio)
                if resampled_tensor is None or audio_bytes is None:
                    return
                
                await self._handle_processed_audio(resampled_tensor, audio_bytes)
            else:
                # Log a warning if the input is not bytes, as this shouldn't happen
                logging.warning(f"{self.session_id}Unexpected audio type received: {type(audio)}, expected bytes. Skipping.")
                
        except Exception as e:
            logging.error(f"{self.session_id}Error sending audio to Vosk: {str(e)}")
            logging.error(f"{self.session_id}Exception details: {traceback.format_exc()}")

    async def _handle_processed_audio(self, tensor, audio_bytes):
        """Handle processed audio
        
        Args:
            tensor: Processed audio tensor
            audio_bytes: Processed audio bytes
        """
        # DETAILED LOG 5: Bytes entering _handle_processed_audio
        logging.debug(f"{self.session_id}Handling processed audio: {len(audio_bytes)} bytes")
        
        if self.bypass_vad:
            # In bypass mode, send directly to Vosk
            # DETAILED LOG 6: Bytes just before sending (VAD bypassed)
            hex_preview = ' '.join([f'{b:02x}' for b in audio_bytes[:20]])
            logging.debug(f"{self.session_id}Sending audio bytes directly (VAD bypassed): len={len(audio_bytes)}, start_hex={hex_preview}")
            await self.vosk_client.send_audio(audio_bytes)
        else:
            # Add to VAD buffer for speech detection
            was_processed, is_speech, buffer_bytes = await self.vad_processor.add_audio(
                audio_bytes, tensor.shape[0])
                
            # If buffer was processed and speech detected, send to Vosk
            if was_processed and is_speech and buffer_bytes:
                # DETAILED LOG 7: Bytes just before sending (after VAD)
                hex_preview_vad = ' '.join([f'{b:02x}' for b in buffer_bytes[:20]])
                logging.debug(f"{self.session_id}Sending VAD buffer bytes: len={len(buffer_bytes)}, start_hex={hex_preview_vad}")
                await self.vosk_client.send_audio(buffer_bytes)

    async def receive_transcripts(self):
        """Vosk'dan transcript alır ve callback fonksiyonlarını çağırır"""
        try:
            reconnect_attempts = 0
            max_reconnect_attempts = 5  # Maximum number of reconnection attempts
            
            while True:
                try:
                    # Receive message from Vosk
                    message = await self.vosk_client.receive_result()
                    
                    if self.debug:
                        logging.debug(f"{self.session_id}Vosk yanıtı alındı: {message}")
                    
                    if message is None:
                        # This usually means a timeout occurred in receive_result, 
                        # which is normal during periods of silence.
                        # Log at DEBUG level instead of WARNING.
                        logging.debug(f"{self.session_id}Timeout or no new message from Vosk (normal during silence).") 
                        # logging.warning(f"{self.session_id}Vosk'dan boş yanıt alındı") # Old warning
                        
                        # Check if the connection is still valid
                        if not self.vosk_client.is_connected:
                            logging.error(f"{self.session_id}WebSocket connection lost during transcript reception")
                            
                            # Don't try to reconnect if we're closing
                            if self._is_closing or self.call.terminated:
                                logging.info(f"{self.session_id}Session is closing, not attempting to reconnect")
                                break
                                
                            # Try to reconnect
                            success = await self._try_reconnect(reconnect_attempts, max_reconnect_attempts)
                            if success:
                                reconnect_attempts = 0
                            else:
                                reconnect_attempts += 1
                                if reconnect_attempts >= max_reconnect_attempts:
                                    logging.error(f"{self.session_id}Maximum reconnection attempts reached. Giving up.")
                                    break
                        continue
                    
                    # Successful message received, reset reconnection attempts
                    reconnect_attempts = 0
                    
                    # Process transcript message
                    await self.transcript_handler.handle_message(message)
                    
                except websockets.exceptions.ConnectionClosed as conn_err:
                    # 1000 kodu normal kapatma, 1001 "going away"
                    if conn_err.code in (1000, 1001) and self.call.terminated:
                        logging.info(f"{self.session_id}WebSocket bağlantısı normal şekilde kapandı: {conn_err.code}")
                        break  # Çağrı sonlandırıldıysa ve bağlantı normal kapandıysa döngüden çık
                    
                    # Don't try to reconnect if we're closing
                    if self._is_closing or self.call.terminated:
                        logging.info(f"{self.session_id}Session is closing, not attempting to reconnect after connection closed with code {conn_err.code}")
                        break
                    
                    logging.error(f"{self.session_id}WebSocket connection closed: {conn_err}")
                    self.vosk_client.is_connected = False
                    
                    # Try to reconnect
                    success = await self._try_reconnect(reconnect_attempts, max_reconnect_attempts)
                    if success:
                        reconnect_attempts = 0
                    else:
                        reconnect_attempts += 1
                        if reconnect_attempts >= max_reconnect_attempts:
                            logging.error(f"{self.session_id}Maximum reconnection attempts reached. Giving up.")
                            break
                
        except asyncio.CancelledError:
            logging.info(f"{self.session_id}Transkript alma görevi iptal edildi")
            raise
        except Exception as e:
            logging.error(f"{self.session_id}Transkript alırken beklenmeyen hata: {str(e)}")
            logging.error(f"{self.session_id}Traceback: {traceback.format_exc()}")
            
            # Close WebSocket if still connected
            if self.vosk_client.is_connected:
                try:
                    await self.vosk_client.disconnect()
                except Exception:
                    pass

    async def _try_reconnect(self, attempts, max_attempts):
        """Try to reconnect to Vosk server
        
        Args:
            attempts: Current number of attempts
            max_attempts: Maximum number of attempts
            
        Returns:
            bool: True if reconnection was successful
        """
        if attempts >= max_attempts:
            logging.error(f"{self.session_id}Maximum reconnection attempts ({max_attempts}) reached. Giving up.")
            return False
            
        attempt_number = attempts + 1
        backoff_time = min(2 * attempt_number, 10)
            
        logging.info(f"{self.session_id}Attempting to reconnect to Vosk server... (attempt {attempt_number}/{max_attempts})")
        
        try:
            reconnected = await self.vosk_client.connect()
            if reconnected:
                logging.info(f"{self.session_id}Successfully reconnected to Vosk server")
                
                # Reset closing flag when reconnecting successfully
                self._is_closing = False
                
                # Resend config
                config = {
                    "config": {
                        "sample_rate": self.target_sample_rate,
                        "num_channels": self.channels
                    }
                }
                await self.vosk_client.send(config)
                return True
            else:
                logging.error(f"{self.session_id}Failed to reconnect to Vosk server")
        except Exception as reconnect_error:
            logging.error(f"{self.session_id}Error during reconnection attempt: {reconnect_error}")
        
        # If we got here, reconnection failed
        logging.info(f"{self.session_id}Waiting {backoff_time} seconds before next attempt")
        await asyncio.sleep(backoff_time)
        return False

    async def close(self):
        """Closes the VoskSTT session"""
        if self._is_closing:
            logging.info(f"{self.session_id}Close already in progress.")
            return
        logging.info(f"{self.session_id}Closing VoskSTT+TTS session")
        
        # Set closing flag to prevent reconnection attempts
        self._is_closing = True
        
        # 1. Cancel ongoing TTS tasks if any
        if hasattr(self, 'tts_task') and self.tts_task and not self.tts_task.done():
            self.tts_task.cancel()
            logging.info(f"{self.session_id}Cancelling active TTS task.")
        
        # 2. Process any remaining audio in VAD buffer
        if not self.bypass_vad:
            try:
                await self._process_final_vad_buffer()
            except Exception as e:
                logging.error(f"{self.session_id}Error processing final VAD buffer: {e}")
        
        # 3. Use last partial as final if no final transcript
        self._finalize_transcript()
        
        # 4. Send EOF and close Vosk connection
        if self.vosk_client.is_connected:
            try:
                if self.send_eof:
                    logging.debug(f"{self.session_id}Sending EOF to Vosk")
                    await self.vosk_client.send(json.dumps({"eof": 1}))
                    # Give server time to process EOF
                    await asyncio.sleep(0.2)
                await self.vosk_client.disconnect()
                logging.info(f"{self.session_id}Disconnected from Vosk")
            except Exception as e:
                logging.error(f"{self.session_id}Error disconnecting from Vosk: {e}")
        
        # 5. Cancel Vosk receive task
        if self.receive_task and not self.receive_task.done():
            self.receive_task.cancel()
            try:
                await self.receive_task
            except asyncio.CancelledError:
                logging.info(f"{self.session_id}Vosk receive task cancelled")
            except Exception as e:
                logging.error(f"{self.session_id}Error cancelling Vosk receive task: {e}")
        
        # 6. TTS client uses websockets context manager, no explicit closing needed
        
        logging.info(f"{self.session_id}VoskSTT+TTS session closed successfully")

    def _finalize_transcript(self):
        """Ensure we have a final transcript (use partial if no final available)"""
        if not self.transcript_handler.last_final_transcript and self.transcript_handler.last_partial_transcript:
            logging.info(f"{self.session_id}No final transcript received, using last partial as final: {self.transcript_handler.last_partial_transcript[:50]}...")
            self.transcript_handler.last_final_transcript = self.transcript_handler.last_partial_transcript
        
        # Log final transcript
        if self.transcript_handler.last_final_transcript:
            logging.info(f"{self.session_id}Final transcript result: {self.transcript_handler.last_final_transcript}")

    def terminate_call(self):
        """ Terminates the call """
        logging.info(f"{self.session_id}Terminating call")
        self.call.terminated = True

    def set_log_level(self, level):
        """Sets the logging level
        
        Args:
            level: The logging level (e.g. logging.INFO, logging.DEBUG)
        """
        logging.getLogger().setLevel(level)
        logging.info(f"{self.session_id}Set logging level to {logging._levelToName.get(level, level)}")
        
        # Update debug flag if setting to DEBUG
        if level == logging.DEBUG:
            self.debug = True
            self.audio_processor.debug = True
        elif level == logging.INFO:
            self.debug = False
            self.audio_processor.debug = False

    async def _process_final_vad_buffer(self):
        """Process final VAD buffer before closing"""
        try:
            is_speech, buffer_bytes = await self.vad_processor.process_final_buffer()
            
            if buffer_bytes:
                buffer_seconds = len(buffer_bytes) / (2 * self.target_sample_rate)  # 2 bytes per sample
                
                # Track last partial transcript
                last_partial = None
                
                # Save original callbacks
                original_on_partial = self.transcript_handler.on_partial_transcript
                original_on_final = self.transcript_handler.on_final_transcript
                
                # Create tracking callback
                async def track_partial(text):
                    nonlocal last_partial
                    last_partial = text
                    logging.info(f"{self.session_id}Got partial after final buffer: {text[:50]}...")
                    logging.info(f"{self.session_id}Complete partial result after final buffer: {text}")
                    
                    # Call original handler
                    if original_on_partial and callable(original_on_partial):
                        await original_on_partial(text)
                
                # Install tracking callback
                self.transcript_handler.on_partial_transcript = track_partial
                
                # Send buffer to Vosk if speech detected
                if is_speech:
                    await self.vosk_client.send_audio(buffer_bytes)
                
                # Wait briefly for response
                wait_time = min(buffer_seconds * 0.4 + 0.2, 0.5)  # Max 0.5 seconds
                logging.info(f"{self.session_id}Waiting {wait_time:.2f} seconds for final response...")
                await asyncio.sleep(wait_time)
                
                # Use last partial as final
                if last_partial and original_on_final and callable(original_on_final):
                    logging.info(f"{self.session_id}Using last partial as final: {last_partial[:50]}...")
                    self.transcript_handler.last_final_transcript = last_partial
                    await original_on_final(last_partial)
                
                # Restore original callbacks
                self.transcript_handler.on_partial_transcript = original_on_partial
                self.transcript_handler.on_final_transcript = original_on_final
                
        except Exception as e:
            logging.error(f"{self.session_id}Error handling final buffer: {e}")

    def get_final_transcript(self):
        """Son tanınan final transkript metnini döndürür.
        
        Returns:
            str: Son alınan final transkript metni
        """
        return self.transcript_handler.get_final_transcript()

    async def _handle_final_transcript(self, final_text):
        """Handles final transcript: Gets LLM response, sends to TTS, converts, queues audio."""
        # Prevent multiple TTS requests running concurrently
        async with self.tts_processing_lock:
            logging.info(f"{self.session_id}Final transcript for TTS: '{final_text}'")
            
            # 1. Get LLM Response (Simulated)
            # PLACEHOLDER: Replace with actual LLM call
            turkish_sentences = [
                "Merhaba, size nasıl yardımcı olabilirim? Bu konuşma sistemimiz sayesinde isteklerinizi sesli olarak iletebilirsiniz. Ben sizin sorularınızı yanıtlamak, bilgi vermek ve çeşitli işlemlerinizi gerçekleştirmek için buradayım. Herhangi bir konuda yardıma ihtiyacınız olursa lütfen belirtin. Size en iyi şekilde yardımcı olmak için elimden geleni yapacağım. Sesli asistanınız olarak size hizmet vermekten mutluluk duyuyorum.", 
                "Lütfen isteğinizi belirtin. Sorularınızı mümkün olduğunca açık ve net bir şekilde ifade ederseniz size daha doğru ve hızlı bir şekilde yardımcı olabilirim. Detaylı bilgiye ihtiyacım olursa ek sorular sorabilirim. İhtiyacınızı tam olarak anlayabilmem için gerekli tüm detayları paylaşmanız önemlidir. Karmaşık konularda adım adım ilerlememiz gerekebilir. Hangi konuda yardıma ihtiyacınız olduğunu lütfen anlatın.",
                "Anlıyorum, isteğiniz işleniyor. Bu işlem birkaç saniye sürebilir, lütfen sabırla bekleyin. Sisteme erişim sağlanıyor ve gerekli bilgiler toplanıyor. Bilgileriniz güvenli bir şekilde işleniyor ve işlem süreci devam ediyor. İşlem tamamlandığında size hemen bilgi vereceğim. Eğer ek bilgiye ihtiyacımız olursa, sizinle tekrar iletişime geçeceğim. Bu süreçte başka bir sorunuz veya isteğiniz olursa lütfen belirtin.", 
                "Bir saniye lütfen, kontrol ediyorum. Talebiniz doğrultusunda sistem kayıtlarına erişiyor ve gerekli bilgileri topluyorum. Bu işlem biraz zaman alabilir, sistem yanıt verene kadar lütfen bekleyin. Veritabanımızda arama yapılıyor ve ilgili bilgiler toplanıyor. Arama algoritması en güncel ve doğru bilgileri bulmak için çalışıyor. Sorgulama işlemi tamamlanmak üzere, sonuçları hemen sizinle paylaşacağım.",
                "İşleminiz başarıyla tamamlandı. Talebiniz sistem tarafından onaylandı ve gerekli tüm adımlar yerine getirildi. Herhangi bir sorun veya hata tespit edilmedi. İşleminize dair tüm detaylar kayıt altına alındı ve sistem güncellemesi gerçekleştirildi. Değişiklikler şu andan itibaren aktif ve geçerlidir. İsterseniz işleminizle ilgili detaylı bir rapor sunabilirim. İşlem sonucu memnun kaldıysanız, size başka konularda da yardımcı olabilirim.", 
                "Başka bir isteğiniz var mı? Size farklı bir konuda da yardımcı olmaktan memnuniyet duyarım. Ek sorularınız veya bilgi almak istediğiniz başka konular varsa lütfen belirtin. Önceki işleminizle ilgili herhangi bir ek bilgiye ihtiyacınız varsa, detaylandırmaktan çekinmeyin. Sistemimizin sunduğu diğer hizmetler hakkında bilgi almak isterseniz bunu da sağlayabilirim. Her türlü talebiniz için buradayım ve size yardımcı olmak için hazırım. Lütfen nasıl yardımcı olabileceğimi belirtin.",
                "Üzgünüm, isteğinizi anlayamadım. Kullandığınız ifade veya soru formatı sistemimiz tarafından doğru şekilde işlenemedi. Farklı bir şekilde ifade etmeyi veya daha açık bir dille talep oluşturmayı deneyebilirsiniz. Bazı özel terimler veya teknik ifadeler bazen zorluk yaratabilir, bu durumda daha genel terimler kullanmanız daha iyi olabilir. Konuşma tanıma sistemi bazen arka plan gürültüsünden veya ses kalitesinden etkilenebilir. Talebinizi daha net ve yavaş bir şekilde tekrarlamanız yardımcı olabilir.", 
                "Tekrar deneyebilir misiniz? Son talebiniz ses tanıma sistemimiz tarafından tam olarak algılanamadı veya anlaşılamadı. Lütfen daha yüksek sesle ve net bir şekilde konuşmayı deneyiniz. Bulunduğunuz ortamda ses kalitesini etkileyebilecek gürültüler varsa, daha sessiz bir ortama geçmek faydalı olabilir. Bazen belirli cümle yapıları veya terimler sistemimiz için zorlayıcı olabilir, bu durumda talebinizi daha basit bir dille ifade etmeyi deneyebilirsiniz. Birkaç kelime ile kısa ve öz bir şekilde ne istediğinizi belirtmek de yardımcı olabilir.",
                "Yardımcı olabileceğim başka bir konu var mı? Bugün sizin için başka hangi işlemleri gerçekleştirebilirim? Sistemimiz birçok farklı konuda hizmet sunmaktadır ve sizin için daha fazla bilgi sağlamaktan veya farklı konularda yardımcı olmaktan memnuniyet duyarım. Hesap işlemleri, bilgi sorgulama, randevu oluşturma veya iptal etme gibi çeşitli hizmetlerimizden faydalanabilirsiniz. Ayrıca ürünlerimiz ve hizmetlerimiz hakkında detaylı bilgi almak isterseniz, bu konuda da size kapsamlı bilgi sunabilirim. İhtiyaçlarınız doğrultusunda size en iyi şekilde yardımcı olmak için buradayım.", 
                "Görüşmek üzere, iyi günler! Bugün bizi tercih ettiğiniz ve hizmetimizden yararlandığınız için teşekkür ederiz. Umarım tüm sorularınıza tatmin edici yanıtlar alabilmişsinizdir. Tekrar görüşmek dileğiyle, size güzel ve verimli bir gün diliyorum. Herhangi bir sorunuz veya ihtiyacınız olduğunda tekrar bizi aramanız yeterli olacaktır. Sizinle tekrar görüşmeyi umuyoruz. Her zaman hizmetinizdeyiz. Bizden tekrar yardım almak istediğinizde çağrı merkezimizi arayabilir veya web sitemiz üzerinden bizimle iletişime geçebilirsiniz. Kendinize iyi bakın!",
            ]
            llm_response_text = random.choice(turkish_sentences)
            logging.info(f"{self.session_id}Simulated LLM response: '{llm_response_text}'")

            # NOW reset VAD state AFTER getting LLM response but BEFORE TTS processing
            if not self.bypass_vad:
                self.vad_processor.reset_vad_state(preserve_buffer=False)
                logging.info(f"{self.session_id}VAD state reset after LLM response, before TTS processing")

            # --- Drain RTP queue before playing TTS ---
            # Avoid playing TTS over residual user speech or previous TTS fragments
            q_size = self.queue.qsize()
            if q_size > 0:
                logging.info(f"{self.session_id}Draining {q_size} packets from RTP queue before TTS playback.")
                while not self.queue.empty():
                    try:
                        self.queue.get_nowait()
                    except Empty:
                        break
            # --- End Drain ---

            # 2. Connect to TTS service and process audio stream using PiperClient
            tts_success = False
            try:
                # Create Piper client instance
                piper_client = PiperClient(
                    server_host=self.tts_server_host,
                    server_port=self.tts_server_port,
                    session_id=self.session_id
                )
                
                # Set up audio handling callback
                cumulative_pcmu_bytes = bytearray()
                chunk_size = 160  # 20ms at 8kHz
                
                # Flag to track first audio chunk for resampler initialization
                first_audio_chunk = True
                
                # Audio handling callback - MAKE THIS ASYNC
                async def on_audio(audio_bytes):
                    nonlocal cumulative_pcmu_bytes, first_audio_chunk
                    
                    try:
                        # Initialize resampler on first audio chunk if needed
                        if first_audio_chunk:
                            first_audio_chunk = False
                            
                            # Create resampler if needed
                            if self.tts_resampler is None and self.tts_input_rate != self.tts_target_output_rate:
                                logging.info(f"{self.session_id}Initializing TTS resampler: {self.tts_input_rate}Hz -> {self.tts_target_output_rate}Hz")
                                self.tts_resampler = torchaudio.transforms.Resample(
                                    orig_freq=self.tts_input_rate,
                                    new_freq=self.tts_target_output_rate
                                )
                            else:
                                logging.info(f"{self.session_id}TTS output rate matches target rate ({self.tts_target_output_rate}Hz). No resampling needed.")
                        
                        # Process audio chunk
                        # a. Convert bytes to tensor (S16LE PCM to float32 tensor)
                        input_tensor = torch.frombuffer(bytearray(audio_bytes), dtype=torch.int16).float() / 32768.0
                        
                        # b. Resample if needed
                        if self.tts_resampler:
                            resampled_tensor = self.tts_resampler(input_tensor.unsqueeze(0)).squeeze(0)
                        else:
                            resampled_tensor = input_tensor  # No resampling needed
                        
                        # c. Convert tensor back to S16LE PCM bytes
                        resampled_tensor_clamped = torch.clamp(resampled_tensor, -1.0, 1.0)
                        pcm_s16le_bytes = (resampled_tensor_clamped * 32768.0).to(torch.int16).numpy().tobytes()
                        
                        # d. Convert S16LE PCM to PCMU (μ-law)
                        pcmu_chunk_bytes = audioop.lin2ulaw(pcm_s16le_bytes, 2)
                        cumulative_pcmu_bytes.extend(pcmu_chunk_bytes)
                        
                        # e. Queue audio in RTP-sized chunks (160 bytes = 20ms at 8kHz)
                        while len(cumulative_pcmu_bytes) >= chunk_size:
                            rtp_payload = cumulative_pcmu_bytes[:chunk_size]
                            self.queue.put_nowait(bytes(rtp_payload))
                            logging.debug(f"{self.session_id}Queued {len(rtp_payload)} bytes of TTS audio for RTP.")
                            # Remove queued data from buffer
                            cumulative_pcmu_bytes = cumulative_pcmu_bytes[chunk_size:]
                            
                            # Yield control occasionally to allow other tasks to run
                            await asyncio.sleep(0)
                            
                    except Exception as audio_e:
                        logging.error(f"{self.session_id}Error processing TTS audio: {audio_e}", exc_info=True)
                
                # Status callbacks - Make these async too
                async def on_start(data):
                    logging.info(f"{self.session_id}TTS stream starting: {data.get('message')}")
                    
                async def on_end(data):
                    nonlocal tts_success
                    tts_success = True
                    logging.info(f"{self.session_id}TTS stream complete: {data.get('message')}")
                    
                async def on_error(data):
                    logging.error(f"{self.session_id}TTS error: {data.get('message')}")
                
                # Execute the full TTS workflow - connect, synthesize, and process
                if await piper_client.connect():
                    if await piper_client.synthesize(llm_response_text, voice=self.tts_voice):
                        await piper_client.process_stream(
                            on_start=on_start,
                            on_audio=on_audio,
                            on_end=on_end,
                            on_error=on_error
                        )
                    
                    # Ensure client is properly closed
                    await piper_client.close()
                
                # Handle any remaining audio bytes (padding to full chunk if needed)
                if cumulative_pcmu_bytes:
                    logging.debug(f"{self.session_id}Processing remaining {len(cumulative_pcmu_bytes)} TTS PCMU bytes.")
                    if len(cumulative_pcmu_bytes) < chunk_size:
                        # Pad with PCMU silence (0xFF)
                        final_payload = bytes(cumulative_pcmu_bytes).ljust(chunk_size, b'\xff')
                    else:
                        final_payload = bytes(cumulative_pcmu_bytes)
                    self.queue.put_nowait(final_payload)
                    logging.debug(f"{self.session_id}Queued final {len(final_payload)} bytes of TTS audio.")
                
            except Exception as e:
                logging.error(f"{self.session_id}Error during TTS processing: {e}", exc_info=True)

