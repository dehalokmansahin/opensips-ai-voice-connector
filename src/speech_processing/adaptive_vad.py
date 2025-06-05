import torch
import numpy as np
import webrtcvad
import logging
import time
from typing import Any, Dict, List, Optional, Tuple

from .vad_detector import VADDetector

class AdaptiveVADDetector(VADDetector):
    """
    Enhanced Voice Activity Detector (VAD) with adaptive calibration and echo cancellation.
    
    This class extends the basic Silero VAD with:
    1. Voice calibration - Dynamically adjusts VAD sensitivity based on audio levels
    2. Adaptive VAD - Learns from ambient noise conditions
    3. Echo cancellation - Prevents TTS audio from being detected as user speech
    4. Debouncing - Prevents rapid on/off switching in noisy environments
    """

    def __init__(self, 
                 sample_rate: int = 16000, 
                 initial_threshold: float = 0.30,  # Daha yüksek başlangıç eşiği
                 min_speech_duration_ms: int = 300, 
                 min_silence_duration_ms: int = 500,
                 calibration_window_ms: int = 4000, 
                 webrtc_aggressiveness: int = 3,  # En yüksek aggressiveness değeri
                 auto_calibration: bool = True,
                 speech_debounce_frames: int = 3,
                 silence_debounce_frames: int = 2):
        """
        Initializes the AdaptiveVADDetector.

        Args:
            sample_rate: The sample rate of the audio to be processed (e.g., 16000 Hz).
            initial_threshold: Initial VAD sensitivity threshold. Will be adjusted if auto_calibration is True.
            min_speech_duration_ms: Minimum duration (in ms) of a speech segment to be considered speech.
            min_silence_duration_ms: Minimum duration (in ms) of silence after a speech segment.
            calibration_window_ms: Duration (in ms) of audio to use for calibration.
            webrtc_aggressiveness: WebRTC VAD aggressiveness level (0-3).
            auto_calibration: Whether to automatically calibrate the VAD threshold.
            speech_debounce_frames: Number of consecutive speech frames needed to confirm speech.
            silence_debounce_frames: Number of consecutive silence frames needed to confirm silence.
        """
        super().__init__(
            sample_rate=sample_rate,
            threshold=initial_threshold,
            min_speech_duration_ms=min_speech_duration_ms,
            min_silence_duration_ms=min_silence_duration_ms
        )
        
        # Calibration parameters
        self.auto_calibration = auto_calibration
        self.calibration_window_ms = calibration_window_ms
        self.calibration_window_samples = int(sample_rate * calibration_window_ms / 1000)
        self.audio_history = []  # Store recent audio for calibration
        self.audio_history_timestamps = []
        self.calibration_history = []  # Store threshold adjustments for analysis
        self.last_calibration_time = 0
        self.min_threshold = 0.15  # En düşük eşik değeri
        self.max_threshold = 0.60  # Maksimum eşik değeri arttırıldı (0.55 -> 0.60) - aşırı gürültülü ortamlar için
        
        # Echo cancellation using WebRTC VAD
        try:
            self.webrtc_vad = webrtcvad.Vad(webrtc_aggressiveness)
            logging.info(f"WebRTC VAD initialized with aggressiveness level {webrtc_aggressiveness}")
        except Exception as e:
            logging.error(f"Failed to initialize WebRTC VAD: {e}")
            self.webrtc_vad = None
            
        # TTS audio tracking for echo cancellation
        self.recent_tts_audio = []  # Store recent TTS audio for echo cancellation
        self.is_tts_active = False
        self.tts_cooldown_ms = 300  # Time to wait after TTS before accepting VAD decisions
        self.last_tts_end_time = 0
        
        # Debouncing mechanism to prevent rapid on/off switching
        self.speech_debounce_frames = speech_debounce_frames
        self.silence_debounce_frames = silence_debounce_frames
        self.consecutive_speech_frames = 0
        self.consecutive_silence_frames = 0
        self.debounced_speech_state = False
        
        # VAD state tracking for debugging
        self.last_detected_noise = False
        self.noise_tracking_start_time = time.time()
        self.noise_events_count = 0
        
        logging.info(
            f"AdaptiveVADDetector initialized with auto_calibration={auto_calibration}, "
            f"initial_threshold={initial_threshold}, speech_debounce={speech_debounce_frames}, "
            f"silence_debounce={silence_debounce_frames}"
        )

    def register_tts_audio(self, tts_audio: torch.Tensor) -> None:
        """
        Register TTS audio to prevent echo detection.
        
        Args:
            tts_audio: Tensor containing TTS audio that was sent to the user
        """
        self.recent_tts_audio.append(tts_audio.detach().clone())
        self.is_tts_active = True
        self.last_tts_end_time = time.time() * 1000  # Convert to ms
        
        # Keep only the last 5 seconds of TTS audio
        max_history = 5 * self.sample_rate
        if sum(t.shape[0] for t in self.recent_tts_audio) > max_history:
            self.recent_tts_audio.pop(0)
            
        logging.debug(f"Registered TTS audio for echo cancellation, length: {tts_audio.shape[0]} samples")

    def tts_finished(self) -> None:
        """Mark TTS as finished, starting the cooldown period"""
        self.is_tts_active = False
        self.last_tts_end_time = time.time() * 1000  # Convert to ms
        logging.debug("TTS finished, starting cooldown period")

    def _should_ignore_due_to_echo(self, audio_tensor: torch.Tensor) -> bool:
        """
        Determine if the current audio is likely an echo of our TTS output.
        
        Args:
            audio_tensor: The current audio tensor being processed
            
        Returns:
            True if the audio should be ignored as an echo
        """
        # If TTS is not active and cooldown period has passed
        current_time_ms = time.time() * 1000
        if not self.is_tts_active and (current_time_ms - self.last_tts_end_time) > self.tts_cooldown_ms:
            return False
            
        # If WebRTC VAD is available, use it for additional verification
        if self.webrtc_vad and audio_tensor.shape[0] >= 320:  # WebRTC needs minimum 10ms audio
            # Convert to 16-bit PCM bytes for WebRTC VAD
            audio_bytes = (audio_tensor * 32767).to(torch.int16).numpy().tobytes()
            
            # WebRTC VAD works with specific frame sizes (10, 20, or 30 ms)
            frame_size = 320  # 20ms at 16kHz
            num_frames = min(len(audio_bytes) // (2 * frame_size), 5)  # Check up to 5 frames
            
            speech_frames = 0
            for i in range(num_frames):
                frame = audio_bytes[i*2*frame_size:(i+1)*2*frame_size]
                try:
                    if self.webrtc_vad.is_speech(frame, self.sample_rate):
                        speech_frames += 1
                except Exception as e:
                    logging.warning(f"WebRTC VAD error: {e}")
                    
            # If WebRTC VAD detects significant speech during TTS or cooldown
            if speech_frames > num_frames // 2:
                logging.debug(f"WebRTC VAD detected {speech_frames}/{num_frames} speech frames during TTS/cooldown")
                return False  # This is probably real speech, not an echo
                
        # Default: ignore audio during TTS or cooldown
        return True

    def _update_calibration(self, audio_tensor: torch.Tensor) -> None:
        """
        Update VAD calibration based on recent audio.
        
        Args:
            audio_tensor: The current audio tensor being processed
        """
        if not self.auto_calibration:
            return
            
        # Add current audio to history
        self.audio_history.append(audio_tensor.detach().clone())
        self.audio_history_timestamps.append(time.time())
        
        # Erken RMS hesaplama - noise detection için
        rms = torch.sqrt(torch.mean(audio_tensor ** 2)).item()
        peak = torch.max(torch.abs(audio_tensor)).item()
        
        # Check for continuous noise using WebRTC VAD for additional verification
        if self.webrtc_vad and audio_tensor.shape[0] >= 320:  # WebRTC needs minimum 10ms audio
            # Convert to 16-bit PCM bytes for WebRTC VAD
            audio_bytes = (audio_tensor * 32767).to(torch.int16).numpy().tobytes()
            
            # WebRTC VAD works with specific frame sizes (10, 20, or 30 ms)
            frame_size = 320  # 20ms at 16kHz
            num_frames = min(len(audio_bytes) // (2 * frame_size), 3)  # Check up to 3 frames
            
            noise_frames = 0
            for i in range(num_frames):
                frame = audio_bytes[i*2*frame_size:(i+1)*2*frame_size]
                try:
                    if not self.webrtc_vad.is_speech(frame, self.sample_rate):
                        noise_frames += 1
                except Exception as e:
                    logging.warning(f"WebRTC VAD error in noise detection: {e}")
            
            # Detect continuous noise - minimum 2 frames must be noise
            is_noise = noise_frames >= 2
            
            # Only log noise events if RMS is above a minimum threshold to avoid false positives
            if is_noise != self.last_detected_noise:
                self.last_detected_noise = is_noise
                if is_noise and rms > 0.012:  # RMS eşiği ekledik
                    self.noise_events_count += 1
                    logging.info(f"Noise detected by WebRTC VAD! ({self.noise_events_count} events so far)")
            
            # Her 30 saniyede bir gürültü olaylarını logla ve sıfırla
            current_time = time.time()
            if current_time - self.noise_tracking_start_time > 30:
                logging.info(f"Last 30 seconds noise summary: {self.noise_events_count} noise events detected")
                self.noise_tracking_start_time = current_time
                self.noise_events_count = 0
        
        # Maintain only recent audio within calibration window
        current_time = time.time()
        window_duration = self.calibration_window_ms / 1000  # Convert ms to seconds
        
        # Remove old audio from history
        while self.audio_history and (current_time - self.audio_history_timestamps[0]) > window_duration:
            self.audio_history.pop(0)
            self.audio_history_timestamps.pop(0)
            
        # Only recalibrate every 3 seconds (değiştirildi: 5 saniyeden 3 saniyeye indirildi)
        if current_time - self.last_calibration_time < 2:  # Daha sık kalibrasyon (3 -> 2 saniye)
            return
            
        # Only calibrate if we have enough audio history
        if not self.audio_history or sum(t.shape[0] for t in self.audio_history) < self.calibration_window_samples // 2:
            return
            
        # Concatenate audio history for analysis
        concat_audio = torch.cat(self.audio_history, dim=0)
        
        # Analyze audio characteristics - rms ve peak zaten hesaplandı, concat_audio için yeniden hesaplayalım
        rms_concat = torch.sqrt(torch.mean(concat_audio ** 2))
        peak_concat = torch.max(torch.abs(concat_audio))
        
        # Calculate noise floor - use lower percentiles as estimate
        sorted_amplitudes = torch.sort(torch.abs(concat_audio))[0]
        
        # Boş ses verisi kontrolü
        if torch.all(sorted_amplitudes < 1e-10):
            logging.info(f"Empty or nearly silent audio detected. Skipping calibration.")
            return
            
        noise_floor = sorted_amplitudes[int(len(sorted_amplitudes) * 0.1)]  # 10th percentile
        
        # Güvenli SNR hesaplama - sıfıra bölme ve -inf sonucunu önleme
        if noise_floor < 1e-10:  # Gerçekten sessiz
            noise_floor = 1e-10  # Minimum değer
            snr = torch.tensor(0.0)  # Sessiz ortam için SNR sıfır - torch.tensor olarak oluştur
        else:
            snr = 20 * torch.log10(rms_concat / noise_floor)
            
        # -inf değeri kontrolü
        if isinstance(snr, torch.Tensor):
            if torch.isinf(snr) or torch.isnan(snr):
                snr = torch.tensor(0.0)
            # SNR değerinin mantıklı bir aralıkta olduğundan emin ol
            elif snr < 0:
                snr = torch.tensor(0.0)  # Negatif SNR'yi sıfır olarak kabul et
            elif snr > 60:
                snr = torch.tensor(60.0)  # Çok yüksek SNR değerlerini sınırla (60dB oldukça yüksek)
        else:
            # int veya float gibi Python tipi ise tensor'a dönüştür
            if float(snr) < 0:
                snr = torch.tensor(0.0)
            elif float(snr) > 60:
                snr = torch.tensor(60.0)
            else:
                snr = torch.tensor(float(snr))
            
        # Calculate dynamic range - güvenli hesaplama
        if noise_floor < 1e-10:
            dynamic_range = torch.tensor(1.0)  # Çok düşük gürültü için varsayılan değer
        else:
            dynamic_range = peak_concat / noise_floor
            
        # Dinamik aralık kontrolü
        if isinstance(dynamic_range, torch.Tensor):
            if torch.isinf(dynamic_range) or torch.isnan(dynamic_range):
                dynamic_range = torch.tensor(1.0)
            # Çok büyük değerleri makul bir değerle sınırla (100 makul bir dinamik aralık üst sınırıdır)
            elif dynamic_range > 100:
                dynamic_range = torch.tensor(100.0)
        else:
            # Python tipi için de sınırlama uygula
            if dynamic_range > 100:
                dynamic_range = 100.0
            dynamic_range = torch.tensor(float(dynamic_range))
        
        # Her 3 saniyede bir ses analiz değerlerini loglayalım
        logging.info(f"AUDIO ANALYSIS - rms: {rms_concat:.4f}, peak: {peak_concat:.4f}, noise_floor: {noise_floor:.4f}, snr: {snr:.2f}, dynamic_range: {dynamic_range:.2f}")
        
        # Adjust threshold based on audio characteristics
        new_threshold = self.threshold
        
        # Gürültü seviyesi değişimini hızlandırmak için önceki logları oku
        consecutive_noise_detections = 0
        noise_trend_strength = 1.0  # Başlangıç çarpanı
        
        # Son 3 kalibrasyon noktasını kontrol et
        if len(self.calibration_history) >= 3:
            for i in range(min(3, len(self.calibration_history))):
                idx = len(self.calibration_history) - 1 - i
                if idx >= 0 and 'is_high_noise' in self.calibration_history[idx][2]:
                    if self.calibration_history[idx][2]['is_high_noise']:
                        consecutive_noise_detections += 1
            
            # Eğer son 3 kalibrasyonda sürekli gürültü tespit edildiyse, değişim hızını artır
            if consecutive_noise_detections >= 2:
                noise_trend_strength = 1.5  # Daha hızlı değişim
            if consecutive_noise_detections == 3:
                noise_trend_strength = 2.0  # Çok daha hızlı değişim
        
        # HIGH NOISE ENVIRONMENT DETECTION - İYİLEŞTİRİLMİŞ MANTIK
        # Düşük SNR değerlerinde daha hassas olmak için gürültü tespit kriterleri güncellendi
        is_high_noise = (
            (noise_floor > 0.018) or                     # Gürültü tabanı eşiği
            (snr < 20 and rms_concat > 0.009) or               # SNR < 20 (was 18), RMS > 0.009
            (rms_concat > 0.05 and dynamic_range < 10)         # Yüksek RMS düşük dinamik aralık
        )
        
        # Düşük RMS değerlerinde gürültü tespitini engellemek için bir eşik, ancak biraz daha düşürüyoruz
        if rms_concat < 0.008:  # Çok düşük ses seviyelerinde gürültü olarak değerlendirme (0.010 -> 0.008)
            is_high_noise = False
        
        # Gürültü tespit mantığını logla
        logging.info(f"NOISE DETECTION - conditions: noise_floor > 0.018: {noise_floor > 0.018}, snr < 20 and rms_concat > 0.009: {snr < 20 and rms_concat > 0.009}, rms_concat > 0.05 and dynamic_range < 10: {rms_concat > 0.05 and dynamic_range < 10}")
        logging.info(f"NOISE DETECTION - result: is_high_noise: {is_high_noise}, current threshold: {self.threshold:.2f}")
        
        # Düşük/yüksek gürültü eşikleri
        if is_high_noise:
            # Eşik artışını sınırla: maximum değerin %80'ini geçmesin
            if self.threshold < self.max_threshold * 0.9:  # Sınır yükseltildi (0.8 -> 0.9)
                # Kademeli artış: SNR'ye göre uyarlanmış artış miktarı
                if isinstance(snr, torch.Tensor) and snr.item() < 5:
                    noise_increase = 0.08 * noise_trend_strength  # Çok düşük SNR için daha agresif artış
                else:
                    noise_increase = 0.05 * noise_trend_strength  # Normal artış
                
                new_threshold = min(self.threshold + noise_increase, self.max_threshold)
                logging.info(f"High noise environment detected. Increasing threshold to {new_threshold:.2f} (noise_floor={noise_floor:.4f}, SNR={snr:.2f}, trend_strength={noise_trend_strength:.1f})")
            else:
                # Eşik çok yüksekse, mevcut değerde tut
                logging.info(f"Threshold already high ({self.threshold:.2f}). Maintaining current level.")
                
        # Low noise environment - decrease threshold to improve sensitivity
        elif (noise_floor < 0.01 and snr > 20) or (rms_concat < 0.0025):  # Düşük gürültü eşikleri daha da hassas hale getirildi
            # Daha hızlı azalma: yüksek eşikler için daha büyük azalma adımları
            decrease_step = 0.05
            if self.threshold > 0.5:  # Eşik çok yüksekse daha hızlı düşür
                decrease_step = 0.1
            elif self.threshold > 0.4:  # Orta yüksek eşikler için de hızlı düşür
                decrease_step = 0.08
                
            new_threshold = max(self.threshold - decrease_step, self.min_threshold)
            logging.info(f"Low noise environment detected. Decreasing threshold to {new_threshold:.2f}")
            
        # Very quiet audio overall - decrease threshold slightly
        elif peak_concat < 0.1:
            new_threshold = max(self.threshold - 0.02, self.min_threshold)
            logging.info(f"Very quiet audio detected. Decreasing threshold to {new_threshold:.2f}")
            
        # Very loud audio - increase threshold slightly
        elif peak_concat > 0.8:
            new_threshold = min(self.threshold + 0.05, self.max_threshold)
            logging.info(f"Very loud audio detected. Increasing threshold to {new_threshold:.2f}")
            
        # Update threshold if it changed
        if new_threshold != self.threshold:
            self.threshold = new_threshold
            
            # Geçmişe kaydetmeden önce tüm değerlerin Python tipinde olduğundan emin ol
            try:
                # Tensor tipindeki değerleri Python float'a dönüştür
                rms_value = float(rms_concat) if isinstance(rms_concat, torch.Tensor) else float(rms_concat)
                peak_value = float(peak_concat) if isinstance(peak_concat, torch.Tensor) else float(peak_concat)
                noise_floor_value = float(noise_floor) if isinstance(noise_floor, torch.Tensor) else float(noise_floor)
                snr_value = float(snr) if isinstance(snr, torch.Tensor) else float(snr)
                dynamic_range_value = float(dynamic_range) if isinstance(dynamic_range, torch.Tensor) else float(dynamic_range)
                
                # Geçmişe kaydet - şimdi is_high_noise değerini de kaydet
                self.calibration_history.append((time.time(), new_threshold, {
                    'rms': rms_value, 
                    'peak': peak_value, 
                    'noise_floor': noise_floor_value,
                    'snr': snr_value,
                    'dynamic_range': dynamic_range_value,
                    'is_high_noise': is_high_noise  # Gürültü durumunu kaydet
                }))
            except Exception as e:
                logging.error(f"Error saving calibration history: {e}")
                # Hata olsa bile geçmişi kaydetmemeyi tercih et, ana işlevselliği etkilemesin
            
        # Her 30 saniyede bir eşik değerini varsayılana doğru hafifçe yaklaştır (yeni)
        # Bu, uzun süre sonra normal koşullara geri dönmeyi sağlar
        if len(self.calibration_history) > 0 and (time.time() - self.calibration_history[-1][0]) > 30: # Check last calibration time
            base_threshold = 0.30  # Hedeflenen temel eşik değeri
            
            # Eşik değeri temelden çok farklıysa, yavaşça yaklaştır
            if abs(self.threshold - base_threshold) > 0.05:
                # Normalleştirme adımı eşiğin ne kadar farklı olduğuna bağlı olsun
                norm_step = 0.03  # Temel adım
                if abs(self.threshold - base_threshold) > 0.15:
                    norm_step = 0.05  # Büyük fark varsa daha hızlı normalleştir
                
                if self.threshold > base_threshold:
                    self.threshold = max(self.threshold - norm_step, base_threshold)
                    logging.info(f"Gradual normalization: Decreasing threshold to {self.threshold:.2f} towards {base_threshold}")
                else:
                    self.threshold = min(self.threshold + norm_step, base_threshold)
                    logging.info(f"Gradual normalization: Increasing threshold to {self.threshold:.2f} towards {base_threshold}")
            
        self.last_calibration_time = time.time()

    def is_speech(self, audio_tensor: torch.Tensor) -> bool:
        """
        Enhanced method to determine if the given audio tensor contains speech.
        Includes calibration, adaptation, echo cancellation, and debouncing.

        Args:
            audio_tensor: A PyTorch tensor containing the audio data.

        Returns:
            True if speech is detected in the audio tensor, False otherwise.
        """
        # Skip speech detection during TTS playback or cooldown period
        if self._should_ignore_due_to_echo(audio_tensor):
            logging.debug("Ignoring audio due to active TTS or cooldown period")
            return False
            
        # Calculate current frame metrics immediately for all checks
        rms = torch.sqrt(torch.mean(audio_tensor ** 2)).item()
        peak = torch.max(torch.abs(audio_tensor)).item()
        
        # Çok düşük ses seviyelerinde gürültü tespitini tamamen atla
        if rms < 0.006:
            logging.debug(f"Audio level too low for reliable detection, RMS={rms:.4f}. Skipping VAD.")
            return False
            
        # Update calibration based on current audio
        self._update_calibration(audio_tensor)
        
        # Check if we're in an extreme noise situation - RMS ve peak değerlerini burada kullan
        is_extreme_noise = False
        if len(self.calibration_history) >= 3:
            high_noise_count = 0
            for i in range(min(3, len(self.calibration_history))):
                idx = len(self.calibration_history) - 1 - i
                if idx >= 0 and 'is_high_noise' in self.calibration_history[idx][2]:
                    if self.calibration_history[idx][2]['is_high_noise']:
                        high_noise_count += 1
            
            # Üst üste 3 kez yüksek gürültü tespit edildiyse ve mevcut eşik değeri yüksekse ve RMS değeri belli bir eşiğin üzerindeyse
            is_extreme_noise = high_noise_count == 3 and self.threshold > 0.45 and rms > 0.012
            
            if is_extreme_noise:
                logging.info(f"EXTREME NOISE ENVIRONMENT DETECTED! Threshold: {self.threshold:.2f}, RMS: {rms:.4f}")
        
        # Aşırı gürültülü ortamlarda konuşma tespitini atla - false positive'leri önler
        if is_extreme_noise and rms > 0.012 and peak < 0.7:
            logging.debug(f"Bypassing speech detection in extreme noise environment. RMS={rms:.4f}, Peak={peak:.4f}")
            return False
        
        # Log current frame noise metrics
        logging.debug(f"Current frame: RMS={rms:.4f}, Peak={peak:.4f}, VAD Threshold={self.threshold:.2f}")
        
        # Get raw speech detection from parent class
        raw_speech_detected = super().is_speech(audio_tensor)
        
        # Apply debouncing to prevent rapid on/off switching in noisy environments
        if raw_speech_detected:
            self.consecutive_speech_frames += 1
            self.consecutive_silence_frames = 0
            
            # If we have enough consecutive speech frames, confirm it's speech
            if self.consecutive_speech_frames >= self.speech_debounce_frames:
                if not self.debounced_speech_state:
                    logging.debug(f"Speech confirmed after {self.consecutive_speech_frames} consecutive frames")
                self.debounced_speech_state = True
        else:
            self.consecutive_silence_frames += 1
            self.consecutive_speech_frames = 0
            
            # If we have enough consecutive silence frames, confirm it's silence
            if self.consecutive_silence_frames >= self.silence_debounce_frames:
                if self.debounced_speech_state:
                    logging.debug(f"Silence confirmed after {self.consecutive_silence_frames} consecutive frames")
                self.debounced_speech_state = False
                
        # Yüksek gürültülü ortamlarda (ama ekstrem değil) ekstra doğrulama yap
        if self.debounced_speech_state and self.threshold > 0.4 and not is_extreme_noise:
            # WebRTC VAD ile çift kontrol
            if self.webrtc_vad and audio_tensor.shape[0] >= 320:
                audio_bytes = (audio_tensor * 32767).to(torch.int16).numpy().tobytes()
                frame_size = 320  # 20ms at 16kHz
                
                # Sadece ilk frame'i kontrol et, hızlı karar vermek için
                try:
                    frame = audio_bytes[0:2*frame_size]
                    webrtc_speech = self.webrtc_vad.is_speech(frame, self.sample_rate)
                    
                    # WebRTC speech false ise ve RMS düşükse, bizim de false dönmemizi sağla (gürültüyü filtrele)
                    if not webrtc_speech and rms < 0.04:  # Düşük RMS değerlerinde daha sıkı filtrele
                        logging.debug(f"WebRTC VAD contradicts Silero VAD in high noise environment, filtering out false positive")
                        return False
                except Exception as e:
                    logging.warning(f"WebRTC VAD double-check error: {e}")
                
        return self.debounced_speech_state 