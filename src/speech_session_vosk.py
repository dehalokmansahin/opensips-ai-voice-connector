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
        
        # Yapılandırmayı al
        self.vosk_server_url = self.cfg.get("url","url" ,"ws://localhost:2700")
        self.websocket_timeout = self.cfg.get("websocket_timeout","websocket_timeout", 5.0)
        self.target_sample_rate = int(self.cfg.get("sample_rate", "sample_rate", 16000))
        self.channels = self.cfg.get("channels", "channels", 1)
        self.send_eof = self.cfg.get("send_eof", "send_eof", True)
        self.debug = self.cfg.get("debug", "debug", False)
        
        # Son transkript sonuçlarını saklamak için değişkenler
        self.last_partial_transcript = ""  # Son alınan partial transkript
        self.last_final_transcript = ""    # Son alınan final transkript
        
        # VAD Setup - RTP packet'lari için optimize edilmiş değerler
        vad_threshold = self.cfg.get("vad_threshold", "vad_threshold", 0.12)  # Daha hassas değer
        vad_min_speech_ms = self.cfg.get("vad_min_speech_ms", "vad_min_speech_ms", 40)  # 20ms RTP paketleri için uygun değer
        vad_min_silence_ms = self.cfg.get("vad_min_silence_ms", "vad_min_silence_ms", 200)
        
        # Add bypass_vad option
        self.bypass_vad = self.cfg.get("bypass_vad", "bypass_vad", False)
        
        # VAD buffer ayarları - 200ms için optimize edildi (Madde 7)
        self.vad_buffer_chunk_ms = 200  # 200ms chunk size for VAD processing
        self.vad_buffer_max_seconds = self.cfg.get("vad_buffer_max_seconds", "vad_buffer_max_seconds", 1.0)
        
        # Yeni konsekütif (ardışık) RTP paket sayacı - VAD için
        self.consecutive_speech_packets = 0
        self.consecutive_silence_packets = 0
        self.speech_detection_threshold = self.cfg.get("speech_detection_threshold", "speech_detection_threshold", 3)  # Kaç ardışık paket konuşma olarak algılanmalı
        self.silence_detection_threshold = self.cfg.get("silence_detection_threshold", "silence_detection_threshold", 10)  # Kaç ardışık paket sessizlik olarak algılanmalı
        
        # Konuşma durumu
        self.speech_active = False
        
        # Geri çağırma fonksiyonları
        self.on_partial_transcript = None  # Kısmi transkript için geri çağırma
        self.on_final_transcript = None    # Tam transkript için geri çağırma
        
        # PCM-U Decoderı hazırla
        self.pcmu_decoder = PCMUDecoder()
        
        # Bağlantı için VoskClient oluştur (bağlantı start() metodunda kurulacak)
        self.vosk_client = VoskClient(self.vosk_server_url, timeout=self.websocket_timeout)
        
        # Durum
        self.receive_task = None
        self.queue_processor_task = None
        self._queue_processor_running = False
        
        # Set default logging level to INFO
        logging.basicConfig(level=logging.INFO)
        
        # Debugging için
        if self.debug:
            logging.getLogger().setLevel(logging.DEBUG)
            logging.debug("Debug logging enabled")
            
        if self.bypass_vad:
            logging.info("VAD bypassed - all audio will be sent to Vosk")
            # VAD bypass durumunda otomatik olarak konuşma modunu etkinleştir
            self.speech_active = True

        # Call içinden alınan bilgiler
        self.queue = call.rtp
        self.client_addr = call.client_addr
        self.client_port = call.client_port
        self.call = call

        # SDP içinden codec seçimi
        self.codec = self.choose_codec(call.sdp)

        # Initialize VAD detector
        self.vad = VADDetector(
            sample_rate=self.target_sample_rate,
            threshold=vad_threshold,
            min_speech_duration_ms=vad_min_speech_ms,
            min_silence_duration_ms=vad_min_silence_ms
        )

        # VAD için ses buffer
        self._vad_buffer = bytearray()
        self._vad_buffer_size_samples = 0  # Buffer'daki örnek sayısı
        self._last_buffer_flush_time = time.time()  # Son buffer gönderme zamanı
        self._vad_buffer_locks = asyncio.Lock()  # Eşzamanlı erişim için kilit

        # Resampler for audio
        self.resampler = torchaudio.transforms.Resample(orig_freq=8000, new_freq=self.target_sample_rate)
        
        # Log the bypass_vad setting
        logging.info(f"VoskSTT initialized. bypass_vad = {self.bypass_vad}")

    def choose_codec(self, sdp):
        """ SDP içinden PCMU codec'ini seçer """
        codecs = get_codecs(sdp)
        for c in codecs:
            if c.payloadType == 0:  # PCMU
                return PCMU(c)
        raise UnsupportedCodec("No supported codec (PCMU) found in SDP.")

    async def start(self):
        """STT motoru başlat ve bağlantıyı kur."""
        logging.info(f"Vosk sunucusuna bağlanılıyor: {self.vosk_server_url}")
        
        try:
            # WebSocket bağlantısını kur
            await self.vosk_client.connect()
            
            # Başlangıç konfigürasyon mesajını gönder
            config = {
                "config": {
                    "sample_rate": self.target_sample_rate,
                    "num_channels": self.channels
                }
            }
            await self.vosk_client.send(config)
            
            # Transcript alma işini başlat
            self.receive_task = asyncio.create_task(self.receive_transcripts())
            
            # Kuyruk işleyici task'ı başlat
            self._queue_processor_running = True
            self.queue_processor_task = asyncio.create_task(self._process_queue())
            
            logging.info("Vosk STT motoru başarıyla başlatıldı")
            return True
        except Exception as e:
            logging.error(f"Vosk motorunu başlatırken hata: {str(e)}")
            return False
    
    async def stop(self):
        """STT motorunu durdur ve bağlantıyı kapat."""
        logging.info("Vosk STT motoru durduruluyor")
        
        try:
            # Queue processor'ı durdur
            self._queue_processor_running = False
            if self.queue_processor_task and not self.queue_processor_task.done():
                try:
                    # Queue processor task'ini bekle
                    await asyncio.wait_for(self.queue_processor_task, timeout=2.0)
                except asyncio.TimeoutError:
                    # Zaman aşımında task'ı iptal et
                    self.queue_processor_task.cancel()
                    try:
                        await self.queue_processor_task
                    except asyncio.CancelledError:
                        pass
            
            # Eğer send_eof etkinse, Vosk'a EOF işareti gönder
            if self.send_eof and self.vosk_client.is_connected:
                try:
                    logging.debug("Vosk'a EOF işareti gönderiliyor")
                    await self.vosk_client.send({"eof": 1})
                except Exception as e:
                    logging.error(f"EOF gönderirken hata: {str(e)}")
            
            # WebSocket bağlantısını kapat
            if self.vosk_client.is_connected:
                await self.vosk_client.disconnect()
            
            # Varsa receive_task'i iptal et
            if self.receive_task and not self.receive_task.done():
                self.receive_task.cancel()
                try:
                    await self.receive_task
                except asyncio.CancelledError:
                    pass
            
            logging.info("Vosk STT motoru başarıyla durduruldu")
            return True
        except Exception as e:
            logging.error(f"Vosk STT motorunu durdururken hata: {str(e)}")
            return False
            
    async def process_audio(self, audio_data):
        """Ses verisini işle ve Vosk'a gönder
        
        Args:
            audio_data: İşlenecek raw ses verisi (PCM 16-bit)
            
        Returns:
            bool: İşleme başarılı olduysa True
        """
        if not self.vosk_client.is_connected:
            logging.warning("Ses verisini işleyemiyorum: Vosk ile bağlantı kurulamadı")
            return False
            
        try:
            # Ses verisini Vosk'a gönder
            await self.vosk_client.send_audio(audio_data)
            return True
        except Exception as e:
            logging.error(f"Ses verisini işlerken hata: {str(e)}")
            return False

    async def send(self, audio):
        """Sends audio to Vosk"""
        if not self.vosk_client.is_connected:
            logging.warning("WebSocket not connected, cannot send audio")
            return
            
        try:
            # Decode (PCMU to PCM) if needed
            if isinstance(audio, bytes):
                # Check if audio is empty
                if len(audio) == 0:
                    logging.warning("Received empty audio bytes. Skipping processing.")
                    return
                    
                # Log input for debugging    
                if self.debug:
                    logging.debug(f"Raw input audio: {len(audio)} bytes")
                
                # Decode PCMU to PCM (Adım 5)
                pcm16_samples = self.pcmu_decoder.decode(audio)
                
                if pcm16_samples is None or len(pcm16_samples) == 0:
                    logging.warning("PCMU decoder returned empty result. Skipping processing.")
                    return
                logging.debug(f"Decoded PCM: {len(pcm16_samples)} bytes") # Log after decode
                
                # Create a copy to ensure we don't modify original data
                pcm16_samples_copy = pcm16_samples.copy().tobytes()
                
                # Ensure data is valid before conversion
                if len(pcm16_samples_copy) == 0:
                    logging.warning("Empty PCM after copy conversion. Skipping.")
                    return
                
                # Convert to float tensor for resampling
                try:
                    audio_tensor = torch.frombuffer(pcm16_samples_copy, dtype=torch.int16).float() / 32768.0
                    logging.debug(f"Converted to tensor: shape={audio_tensor.shape}, min={audio_tensor.min():.4f}, max={audio_tensor.max():.4f}") # Log after tensor conversion
                    
                    # Check for NaN or Inf values
                    if torch.isnan(audio_tensor).any() or torch.isinf(audio_tensor).any():
                        logging.warning("Audio tensor contains NaN or Inf values. Cleaning tensor.")
                        audio_tensor = torch.nan_to_num(audio_tensor, nan=0.0, posinf=0.99, neginf=-0.99)

                    # Normalize - optimize edilmiş kısım
                    audio_max = torch.max(torch.abs(audio_tensor))
                    
                    # Sadece çok düşük sesleri normalize et
                    if audio_max < 0.01:  # Daha düşük eşik
                        gain = min(0.3 / (audio_max + 1e-10), 10.0)
                        audio_tensor = audio_tensor * gain
                        logging.info(f"Applied normalization with gain: {gain:.2f}")
                    
                    # Resample to target rate (Adım 6)
                    resampled_tensor = self.resampler(audio_tensor.unsqueeze(0)).squeeze(0)
                    logging.debug(f"Resampled tensor: shape={resampled_tensor.shape}, min={resampled_tensor.min():.4f}, max={resampled_tensor.max():.4f}") # Log after resampling
                    
                    # Check the resampled audio validity
                    if resampled_tensor.shape[0] == 0:
                        logging.warning("Resampling resulted in empty tensor. Skipping.")
                        return
                    
                    # Add to VAD buffer for 200ms accumulation (Adım 7)
                    if not self.bypass_vad:
                        # Convert to audio bytes for buffer
                        audio_bytes = (torch.clamp(resampled_tensor, -1.0, 1.0) * 32768.0).to(torch.int16).numpy().tobytes()
                        await self._add_to_vad_buffer(audio_bytes, resampled_tensor.shape[0])
                    else:
                        # In bypass mode, send directly
                        processed_tensor = torch.clamp(resampled_tensor, -1.0, 1.0)
                        audio_bytes = (processed_tensor * 32768.0).to(torch.int16).numpy().tobytes()
                        await self.vosk_client.send_audio(audio_bytes)
                    
                except Exception as e:
                    logging.error(f"Error processing audio tensor: {str(e)}")
                    logging.error(f"Exception details: {traceback.format_exc()}") # Add traceback here too
                    
            elif isinstance(audio, torch.Tensor):
                logging.debug("Processing audio as torch.Tensor")
                # For tensors, use directly (assuming it's already at target sample rate)
                # Ensure tensor has valid values
                if torch.isnan(audio).any() or torch.isinf(audio).any():
                    logging.warning("Input tensor contains NaN or Inf values. Cleaning.")
                    audio = torch.nan_to_num(audio, nan=0.0, posinf=0.99, neginf=-0.99)
                
                # Validate tensor
                if audio.numel() == 0:
                    logging.warning("Empty audio tensor received. Skipping.")
                    return
                
                # Normalize - optimize edilmiş kısım
                audio_max = torch.max(torch.abs(audio))
                
                # Sadece çok düşük sesleri normalize et
                if audio_max < 0.01:  # Daha düşük eşik
                    # Hızlı max-based normalization
                    gain = min(0.3 / (audio_max + 1e-10), 10.0)
                    audio = audio * gain
                    logging.info(f"Applied normalization with gain: {gain:.2f}")
                
                # Add to VAD buffer for 200ms accumulation (Adım 7)
                if not self.bypass_vad:
                    # Convert to audio bytes for buffer
                    audio_bytes = (torch.clamp(audio, -1.0, 1.0) * 32768.0).to(torch.int16).numpy().tobytes()
                    await self._add_to_vad_buffer(audio_bytes, audio.shape[0])
                else:
                    # In bypass mode, send directly
                    audio = torch.clamp(audio, -1.0, 1.0)
                    audio_bytes = (audio * 32768.0).to(torch.int16).numpy().tobytes()
                    await self.vosk_client.send_audio(audio_bytes)
            else:
                logging.warning(f"Unexpected audio type: {type(audio)}, skipping")
                
        except Exception as e:
            logging.error(f"Error sending audio to Vosk: {str(e)}")
            logging.error(f"Exception details: {traceback.format_exc()}")

    async def _add_to_vad_buffer(self, audio_bytes, num_samples):
        """VAD buffer'a ses ekler ve 200ms'ye ulaştığında işler (Adım 7-8)
        
        Args:
            audio_bytes: Eklenecek ses verisi
            num_samples: Eklenen ses verisindeki örnek sayısı
        """
        async with self._vad_buffer_locks:
            # Buffer'a ekle
            self._vad_buffer.extend(audio_bytes)
            self._vad_buffer_size_samples += num_samples
            
            # Calculate buffer duration in ms
            buffer_ms = (self._vad_buffer_size_samples / self.target_sample_rate) * 1000
            
            # Check if buffer has reached 200ms (Adım 7)
            if buffer_ms >= self.vad_buffer_chunk_ms:
                logging.debug(f"VAD buffer reached 200ms ({buffer_ms:.2f}ms), processing for VAD")
                await self._process_vad_buffer()

    async def _process_vad_buffer(self):
        """VAD buffer'ı 200ms chunk olarak işler ve gerekirse Vosk'a gönderir (Adım 8-9)"""
        # Convert buffer to tensor for VAD processing
        buffer_bytes = bytes(self._vad_buffer)
        try:
            audio_tensor = torch.frombuffer(buffer_bytes, dtype=torch.int16).float() / 32768.0
            
            # Apply VAD to detect speech (Adım 8)
            is_speech = self.vad.is_speech(audio_tensor)
            
            # Update consecutive packet counters based on VAD result
            if is_speech:
                self.consecutive_speech_packets += 1
                self.consecutive_silence_packets = 0
                
                # If enough consecutive speech packets, activate speech mode
                if self.consecutive_speech_packets >= self.speech_detection_threshold and not self.speech_active:
                    self.speech_active = True
                    logging.info(f"Speech started after {self.consecutive_speech_packets} consecutive speech packets")
            else:
                self.consecutive_silence_packets += 1
                self.consecutive_speech_packets = 0
                
                # If enough consecutive silence packets, deactivate speech mode
                if self.consecutive_silence_packets >= self.silence_detection_threshold and self.speech_active:
                    self.speech_active = False
                    logging.info(f"Speech ended after {self.consecutive_silence_packets} consecutive silence packets")
            
            # Send to Vosk if speech is detected or we're in active speech mode (Adım 9)
            if is_speech or self.speech_active:
                logging.info(f"Sending 200ms chunk to Vosk: speech={is_speech}, active={self.speech_active}")
                await self.vosk_client.send_audio(buffer_bytes)
            else:
                logging.debug("No speech detected in 200ms chunk, not sending to Vosk")
                
        except Exception as e:
            logging.error(f"Error processing VAD buffer: {str(e)}")
        finally:
            # Clear buffer after processing
            self._vad_buffer.clear()
            self._vad_buffer_size_samples = 0
            self._last_buffer_flush_time = time.time()

    async def receive_transcripts(self):
        """Vosk'dan transcript alır ve callback fonksiyonlarını çağırır (Adım 10-11)"""
        try:
            reconnect_attempts = 0
            max_reconnect_attempts = 5  # Maximum number of reconnection attempts
            
            while True:
                # Vosk'dan cevap bekle
                message = await self.vosk_client.receive_result()
                
                if self.debug:
                    logging.debug(f"Vosk yanıtı alındı: {message}")
                
                if message is None:
                    logging.warning("Vosk'dan boş yanıt alındı")
                    # Check if the connection is still valid
                    if not self.vosk_client.is_connected:
                        logging.error("WebSocket connection lost during transcript reception")
                        # Attempt to reconnect
                        try:
                            if reconnect_attempts >= max_reconnect_attempts:
                                logging.error(f"Maximum reconnection attempts ({max_reconnect_attempts}) reached. Giving up.")
                                break
                                
                            reconnect_attempts += 1
                            logging.info(f"Attempting to reconnect to Vosk server... (attempt {reconnect_attempts}/{max_reconnect_attempts})")
                            
                            reconnected = await self.vosk_client.connect()
                            if reconnected:
                                logging.info("Successfully reconnected to Vosk server")
                                # Reset reconnection counter on success
                                reconnect_attempts = 0
                                
                                # Resend config
                                config = {
                                    "config": {
                                        "sample_rate": self.target_sample_rate,
                                        "num_channels": self.channels
                                    }
                                }
                                await self.vosk_client.send(config)
                            else:
                                logging.error("Failed to reconnect to Vosk server")
                                # Wait before next attempt - increasing backoff
                                await asyncio.sleep(min(2 * reconnect_attempts, 10))
                        except Exception as reconnect_error:
                            logging.error(f"Error during reconnection attempt: {reconnect_error}")
                            await asyncio.sleep(min(2 * reconnect_attempts, 10))
                    continue
                
                try:
                    # JSON mesajını ayrıştır
                    response = json.loads(message)
                    
                    # Kısmi transkript (partial) işleme (Adım 11)
                    if "partial" in response:
                        partial_text = response.get("partial", "")
                        # Son partial transkripti sakla
                        self.last_partial_transcript = partial_text
                        
                        if partial_text and self.on_partial_transcript:
                            await self.on_partial_transcript(partial_text)
                    
                    # Tam transkript (final) işleme (Adım 11)
                    if "text" in response:
                        final_text = response.get("text", "")
                        # Son final transkripti sakla
                        self.last_final_transcript = final_text
                        
                        if final_text and self.on_final_transcript:
                            await self.on_final_transcript(final_text)
                            
                except json.JSONDecodeError:
                    logging.error(f"Geçersiz JSON yanıtı: {message}")
                except Exception as e:
                    logging.error(f"Transkript işlenirken hata: {str(e)}")
                
        except websockets.exceptions.ConnectionClosed as conn_err:
            logging.error(f"WebSocket connection closed: {conn_err}")
            self.vosk_client.is_connected = False
            
            # Attempt to reconnect once - but don't create an infinite reconnection loop
            try:
                logging.info("Attempting to reconnect after connection closed...")
                await asyncio.sleep(1)  # Brief delay before reconnecting
                reconnected = await self.vosk_client.connect()
                if reconnected:
                    logging.info("Successfully reconnected after connection closed")
                    # Start a new receive task
                    asyncio.create_task(self.receive_transcripts())
                    return  # End this task since we created a new one
                else:
                    logging.error("Failed to reconnect after connection closed")
                    return  # End this task to avoid cascading reconnection loops
            except Exception as reconnect_error:
                logging.error(f"Error during reconnection attempt: {reconnect_error}")
                return  # End this task to avoid cascading reconnection loops
                
        except asyncio.CancelledError:
            logging.info("Transkript alma görevi iptal edildi")
            raise
        except Exception as e:
            logging.error(f"Transkript alırken beklenmeyen hata: {str(e)}")
            traceback_str = traceback.format_exc()
            logging.error(f"Traceback: {traceback_str}")
            
            # WebSocket kapandıysa, bağlantıyı kapat
            if self.vosk_client.is_connected:
                try:
                    await self.vosk_client.disconnect()
                except Exception:
                    pass

    async def _process_queue(self):
        """RTP kuyruğundan ses verilerini işleyen metod."""
        logging.info("Queue processor started for VoskSTT")
        
        while self._queue_processor_running:
            try:
                # get_nowait() ile kuyruktaki bir sonraki ses verisini al
                audio_chunk = self.queue.get_nowait()
                
                if self.debug:
                    logging.debug(f"Processing audio chunk from queue: {len(audio_chunk)} bytes")
                
                # Ses verisini send() metoduna gönder
                try:
                    await self.send(audio_chunk)
                except Exception as e:
                    logging.error(f"Error sending audio chunk from queue: {str(e)}")
                    logging.error(f"Exception details: {traceback.format_exc()}")
                
                # İşi tamamlandı olarak işaretle
                self.queue.task_done()
                
            except Empty:
                # Kuyruk boşsa, kısa bir süre bekle ve tekrar dene
                await asyncio.sleep(0.01)  # CPU kullanımını azaltmak için kısa bir bekleme
                
                # Eğer çağrı sonlandırıldıysa döngüden çık
                if self.call.terminated or not self._queue_processor_running:
                    logging.info("Call terminated or processor stopped, ending queue processor")
                    break
            
            except Exception as e:
                logging.error(f"Unexpected error in queue processor: {str(e)}")
                logging.error(f"Exception details: {traceback.format_exc()}")
                await asyncio.sleep(0.1)  # Hata durumunda biraz daha uzun bekle
        
        logging.info("Queue processor finished")

    async def close(self):
        """Closes the VoskSTT session"""
        logging.info("Closing VoskSTT session")
        
        # Stop queue processor
        self._queue_processor_running = False
        if self.queue_processor_task and not self.queue_processor_task.done():
            try:
                # Queue processor task'ini bekle
                await asyncio.wait_for(self.queue_processor_task, timeout=1.0)
            except asyncio.TimeoutError:
                # Zaman aşımında task'ı iptal et
                self.queue_processor_task.cancel()
                try:
                    await self.queue_processor_task
                except asyncio.CancelledError:
                    pass
        
        # Flush any remaining audio in the VAD buffer
        if not self.bypass_vad and len(self._vad_buffer) > 0:
            try:
                buffer_seconds = self._vad_buffer_size_samples / self.target_sample_rate
                logging.info(f"Processing remaining VAD buffer before closing: {buffer_seconds:.2f} seconds")
                
                # Process the final buffer for VAD
                await self._process_vad_buffer()
                
                # Track the last partial text
                last_partial = None
                
                # Save original callbacks
                original_on_partial = self.on_partial_transcript
                original_on_final = self.on_final_transcript
                
                # Create tracking callback
                async def track_partial(text):
                    nonlocal last_partial
                    last_partial = text
                    logging.info(f"Got partial after final buffer: {text[:50]}...")
                    # Print complete result - requested by user
                    logging.info(f"Complete partial result after final buffer: {text}")
                    
                    # Also call the original partial handler
                    if original_on_partial and callable(original_on_partial):
                        await original_on_partial(text)
                
                # Install tracking callback
                self.on_partial_transcript = track_partial
                
                # Wait briefly for response - daha kısa bekleme süresi (optimize edildi)
                wait_time = min(buffer_seconds * 0.4 + 0.2, 0.5)  # Maksimum 0.5 saniye bekle
                logging.info(f"Waiting {wait_time:.2f} seconds for final response...")
                await asyncio.sleep(wait_time)  # Optimized wait time
                
                # Use the last partial as final
                if last_partial and original_on_final and callable(original_on_final):
                    logging.info(f"Using last partial as final: {last_partial[:50]}...")
                    self.last_final_transcript = last_partial  # Son partial'ı final olarak kaydet
                    await original_on_final(last_partial)
                
                # Restore original callbacks
                self.on_partial_transcript = original_on_partial
                self.on_final_transcript = original_on_final
                
            except Exception as e:
                logging.error(f"Error handling final buffer: {e}")
        
        # Eğer final transcript yoksa ve partial transcript varsa, onu final olarak kaydet
        if not self.last_final_transcript and self.last_partial_transcript:
            logging.info(f"No final transcript received, using last partial as final: {self.last_partial_transcript[:50]}...")
            self.last_final_transcript = self.last_partial_transcript
        
        # Son transkript sonuçlarını logla
        if self.last_final_transcript:
            logging.info(f"Final transcript result: {self.last_final_transcript}")
        
        # Send EOF signal
        if self.send_eof and self.vosk_client.is_connected:
            try:
                logging.info("Sending EOF message to Vosk server")
                await self.vosk_client.send_eof()
            except Exception as e:
                logging.warning(f"Could not send final EOF: {e}")
        
        # Stop the receive task if running
        if self.receive_task and not self.receive_task.done():
            self.receive_task.cancel()
            try:
                await self.receive_task
            except asyncio.CancelledError:
                pass
        
        # Close WebSocket connection
        if self.vosk_client.is_connected:
            await self.vosk_client.disconnect()
        
        logging.info("VoskSTT session closed successfully")

    def get_final_transcript(self):
        """Son tanınan final transkript metnini döndürür.
        
        Returns:
            str: Son alınan final transkript metni
        """
        if self.last_final_transcript:
            return self.last_final_transcript
        elif self.last_partial_transcript:
            # Eğer final transkript yoksa ama partial varsa, partial'ı döndür
            return self.last_partial_transcript
        else:
            # Hiç transkript alınmadıysa boş string döndür
            return ""

    def terminate_call(self):
        """ Terminates the call """
        self.call.terminated = True

    def set_log_level(self, level):
        """Sets the logging level
        
        Args:
            level: The logging level (e.g. logging.INFO, logging.DEBUG)
        """
        logging.getLogger().setLevel(level)
        logging.info(f"Set logging level to {logging._levelToName.get(level, level)}")
        
        # Update debug flag if setting to DEBUG
        if level == logging.DEBUG:
            self.debug = True
        elif level == logging.INFO:
            self.debug = False

