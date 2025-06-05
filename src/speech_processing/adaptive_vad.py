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
        
        # --- Noise Trend Analysis ---
        # If high noise is detected consecutively, we might want to adjust the threshold more aggressively.
        # `noise_trend_strength` acts as a multiplier for threshold adjustments.
        consecutive_noise_detections = 0
        noise_trend_strength = 1.0  # Default: no acceleration
        
        # Check the last 3 calibration results stored in history
        if len(self.calibration_history) >= 3:
            # Iterate over the last (up to) 3 calibration records
            for i in range(min(3, len(self.calibration_history))):
                history_index = len(self.calibration_history) - 1 - i
                if history_index >= 0 and 'is_high_noise' in self.calibration_history[history_index][2]:
                    if self.calibration_history[history_index][2]['is_high_noise']:
                        consecutive_noise_detections += 1
            
            # If high noise is detected in at least 2 of the last 3 calibrations, increase trend strength.
            # This makes the threshold adapt faster to persistently noisy conditions.
            if consecutive_noise_detections >= 2: # If 2 out of 3 recent calibrations detected high noise
                noise_trend_strength = 1.5  # Moderate acceleration
            if consecutive_noise_detections == 3: # If all 3 recent calibrations detected high noise
                noise_trend_strength = 2.0  # Strong acceleration

        # --- High Noise Environment Detection Logic ---
        # The goal is to identify if the current calibration window predominantly contains noise.
        # This is determined by a combination of noise floor, SNR, RMS, and dynamic range.
        # These thresholds are empirically derived and may need tuning for different environments/microphones.
        is_high_noise = (
            (noise_floor > 0.018) or                     # Condition 1: Noise floor itself is high (e.g., constant background hum).
                                                         # 0.018 represents a noticeable continuous noise level.
            (snr < 20 and rms_concat > 0.009) or        # Condition 2: Low Signal-to-Noise Ratio (SNR < 20dB)
                                                         # AND the overall signal energy (RMS) isn't extremely low.
                                                         # This catches situations where noise is relatively loud compared to any potential speech.
                                                         # RMS > 0.009 ensures we don't flag very quiet environments with low SNR as noisy.
            (rms_concat > 0.05 and dynamic_range < 10)   # Condition 3: High overall signal energy (RMS > 0.05)
                                                         # BUT low dynamic range (< 10). This can indicate loud, compressed noise
                                                         # where peak and floor are close.
        )
        
        # Override: If the overall RMS of the calibration window is very low,
        # it's unlikely to be a problematic "high noise" environment, even if SNR or dynamic range is low.
        # This prevents overly aggressive threshold increases in very quiet settings.
        if rms_concat < 0.008:  # Threshold for "very low RMS" (previously 0.010)
            is_high_noise = False
        
        logging.info(f"NOISE DETECTION - conditions: noise_floor > 0.018: {noise_floor > 0.018}, snr < 20 and rms_concat > 0.009: {snr < 20 and rms_concat > 0.009}, rms_concat > 0.05 and dynamic_range < 10: {rms_concat > 0.05 and dynamic_range < 10}")
        logging.info(f"NOISE DETECTION - result: is_high_noise: {is_high_noise}, current threshold: {self.threshold:.2f}")
        
        # --- Threshold Adjustment Based on Noise Level ---
        if is_high_noise:
            # In a high noise environment, increase the VAD threshold to be less sensitive.
            # The increase is capped to prevent the threshold from becoming excessively high.
            if self.threshold < self.max_threshold * 0.9:  # Don't increase if already very high (90% of max_threshold)
                # The amount of increase depends on the SNR and the noise_trend_strength.
                # Very low SNR (<5dB) in a noisy environment triggers a more significant increase.
                if isinstance(snr, torch.Tensor) and snr.item() < 5:
                    noise_increase = 0.08 * noise_trend_strength  # Aggressive increase for very low SNR
                else:
                    noise_increase = 0.05 * noise_trend_strength  # Standard increase
                
                new_threshold = min(self.threshold + noise_increase, self.max_threshold)
                logging.info(f"High noise environment detected. Increasing threshold to {new_threshold:.2f} (noise_floor={noise_floor:.4f}, SNR={snr:.2f}, trend_strength={noise_trend_strength:.1f})")
            else:
                # Threshold is already high, maintain current level.
                logging.info(f"Threshold already high ({self.threshold:.2f}). Maintaining current level in noisy environment.")
                
        # Low noise environment: Decrease threshold to improve sensitivity.
        # Condition: (low noise_floor AND good snr) OR very low overall energy (rms_concat).
        elif (noise_floor < 0.01 and snr > 20) or (rms_concat < 0.0025):
            # Adjust decrease step based on current threshold to allow faster normalization from high values.
            decrease_step = 0.05  # Standard decrease
            if self.threshold > 0.5:  # If threshold is very high
                decrease_step = 0.1   # Larger step to decrease faster
            elif self.threshold > 0.4: # If threshold is moderately high
                decrease_step = 0.08  # Moderate step
                
            new_threshold = max(self.threshold - decrease_step, self.min_threshold)
            logging.info(f"Low noise environment detected. Decreasing threshold to {new_threshold:.2f}")
            
        # Very quiet audio overall (low peak energy): Decrease threshold slightly.
        # This helps catch softer speech if the environment is generally very quiet.
        elif peak_concat < 0.1:
            new_threshold = max(self.threshold - 0.02, self.min_threshold) # Smaller step for minor adjustment
            logging.info(f"Very quiet audio detected (peak < 0.1). Decreasing threshold to {new_threshold:.2f}")
            
        # Very loud audio (high peak energy but not necessarily "high noise" by other metrics): Increase threshold slightly.
        # This might be to make the VAD less sensitive to minor sounds if the dominant sound is very loud speech,
        # or to prevent triggering on loud non-speech sounds if they weren't caught by is_high_noise.
        elif peak_concat > 0.8:
            new_threshold = min(self.threshold + 0.05, self.max_threshold)
            logging.info(f"Very loud audio detected (peak > 0.8). Increasing threshold to {new_threshold:.2f}")
            
        # --- Update Threshold ---
        if new_threshold != self.threshold:
            self.threshold = new_threshold
            
            # Store calibration history if threshold changes.
            # Ensure all stored values are Python native types (float) for easier serialization/logging if needed.
            try:
                # Convert tensor values to Python floats
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
        # --- Gradual Normalization ---
        # If the VAD threshold has been pushed to an extreme (high or low) due to specific conditions
        # and then the audio characteristics remain stable for a while (e.g., 30 seconds since last calibration update),
        # this logic gently nudges the threshold back towards a central baseline (0.30).
        # This helps to prevent the VAD from getting "stuck" in a very insensitive or very sensitive state
        # if the environment changes slowly or after a transient event.
        if len(self.calibration_history) > 0 and (time.time() - self.calibration_history[-1][0]) > 30: # Check time since last *change*
            base_threshold = 0.30  # Target baseline threshold

            # If current threshold is significantly different from baseline
            if abs(self.threshold - base_threshold) > 0.05:
                # Adjust normalization step based on how far the current threshold is from the baseline.
                norm_step = 0.03  # Standard normalization step
                if abs(self.threshold - base_threshold) > 0.15: # If very far
                    norm_step = 0.05  # Use a larger step for faster normalization
                
                if self.threshold > base_threshold:
                    self.threshold = max(self.threshold - norm_step, base_threshold)
                    logging.info(f"Gradual normalization: Decreasing threshold to {self.threshold:.2f} towards {base_threshold}")
                else:
                    self.threshold = min(self.threshold + norm_step, base_threshold)
                    logging.info(f"Gradual normalization: Increasing threshold to {self.threshold:.2f} towards {base_threshold}")
            
        self.last_calibration_time = time.time() # Record time of this calibration attempt

    def is_speech(self, audio_tensor: torch.Tensor) -> bool:
        """
        Enhanced method to determine if the given audio tensor contains speech.
        Includes calibration, adaptation, echo cancellation, and debouncing.

        The decision process is as follows:
        1. Echo Cancellation: If TTS is active or in cooldown, ignore audio unless WebRTC VAD strongly suggests speech.
        2. Low Energy Bypass: If audio RMS is very low, assume silence.
        3. Calibration: Update adaptive VAD threshold based on recent audio history.
        4. Extreme Noise Bypass: If calibrated to detect extreme noise and current audio is not a strong peak, assume silence.
        5. Core VAD Decision: Use the parent VAD (e.g., Silero) with the currently adapted threshold.
        6. Debouncing: Smooth the raw VAD decisions to prevent rapid toggling.
        7. WebRTC Double-Check (High Noise): If debounced state is speech, but environment is noisy (high threshold),
           cross-check with WebRTC VAD. If WebRTC VAD disagrees and RMS is low, revert to silence.

        Args:
            audio_tensor: A PyTorch tensor containing the audio data.

        Returns:
            True if speech is detected in the audio tensor, False otherwise.
        """
        # 1. Echo Cancellation Check
        if self._should_ignore_due_to_echo(audio_tensor):
            logging.debug("Ignoring audio due to active TTS or cooldown period")
            return False
            
        # Calculate current frame metrics for immediate checks
        rms = torch.sqrt(torch.mean(audio_tensor ** 2)).item()
        peak = torch.max(torch.abs(audio_tensor)).item()
        
        # 2. Low Energy Bypass: Quickly discard frames with extremely low energy.
        if rms < 0.006: # Threshold for "too low for reliable detection"
            logging.debug(f"Audio level too low for reliable detection, RMS={rms:.4f}. Skipping VAD.")
            return False
            
        # 3. Update adaptive VAD calibration based on current audio
        self._update_calibration(audio_tensor) # This updates self.threshold
        
        # 4. Extreme Noise Handling
        # Check if the calibration history suggests a persistent extreme noise environment.
        is_extreme_noise = False
        if len(self.calibration_history) >= 3:
            high_noise_count = 0
            # Count recent 'is_high_noise' flags from calibration history
            for i in range(min(3, len(self.calibration_history))):
                idx = len(self.calibration_history) - 1 - i
                if idx >= 0 and 'is_high_noise' in self.calibration_history[idx][2]:
                    if self.calibration_history[idx][2]['is_high_noise']:
                        high_noise_count += 1
            
            # Condition for extreme noise:
            # - Consistently high noise detected in last 3 calibrations.
            # - Current VAD threshold is already high (> 0.45).
            # - Current frame RMS is above a minimum level (not complete silence).
            is_extreme_noise = high_noise_count == 3 and self.threshold > 0.45 and rms > 0.012
            
            if is_extreme_noise:
                logging.info(f"EXTREME NOISE ENVIRONMENT DETECTED! Threshold: {self.threshold:.2f}, RMS: {rms:.4f}")
        
        # If in extreme noise and current audio peak is not high enough, bypass further speech detection.
        # This helps prevent false positives from loud, non-speech noise.
        if is_extreme_noise and rms > 0.012 and peak < 0.7: # Peak threshold (0.7) to allow very loud speech through
            logging.debug(f"Bypassing speech detection in extreme noise environment. RMS={rms:.4f}, Peak={peak:.4f}")
            return False
        
        # Log current frame metrics before core VAD decision
        logging.debug(f"Current frame: RMS={rms:.4f}, Peak={peak:.4f}, VAD Threshold={self.threshold:.2f}")
        
        # 5. Core VAD Decision (using parent class, e.g., SileroVAD, with adapted threshold)
        raw_speech_detected = super().is_speech(audio_tensor) # Uses self.threshold
        
        # 6. Debouncing Logic
        # Smooths the raw VAD output to prevent rapid toggling due to transient noises or speech patterns.
        if raw_speech_detected:
            self.consecutive_speech_frames += 1
            self.consecutive_silence_frames = 0
            if self.consecutive_speech_frames >= self.speech_debounce_frames:
                if not self.debounced_speech_state: # Log only on state change
                    logging.debug(f"Speech confirmed after {self.consecutive_speech_frames} consecutive frames")
                self.debounced_speech_state = True
        else:
            self.consecutive_silence_frames += 1
            self.consecutive_speech_frames = 0
            if self.consecutive_silence_frames >= self.silence_debounce_frames:
                if self.debounced_speech_state: # Log only on state change
                    logging.debug(f"Silence confirmed after {self.consecutive_silence_frames} consecutive frames")
                self.debounced_speech_state = False
                
        # 7. WebRTC Double-Check in High Noise (but not "extreme")
        # If the debounced state is speech AND the adaptive threshold is high (indicating a noisy environment)
        # AND it's not an "extreme noise" situation (which was handled above),
        # then perform an additional check using WebRTC VAD.
        if self.debounced_speech_state and self.threshold > 0.4 and not is_extreme_noise:
            if self.webrtc_vad and audio_tensor.shape[0] >= 320: # WebRTC VAD needs at least 10ms (160 samples * 2 bytes)
                audio_bytes = (audio_tensor * 32767).to(torch.int16).numpy().tobytes()
                frame_size_bytes = 320 * 2 # 20ms at 16kHz, 16-bit PCM (2 bytes per sample)
                
                try:
                    # Check only the first 20ms frame for quick decision
                    frame_to_check = audio_bytes[0:frame_size_bytes]
                    if len(frame_to_check) == frame_size_bytes: # Ensure we have enough bytes
                        webrtc_is_speech = self.webrtc_vad.is_speech(frame_to_check, self.sample_rate)

                        # If WebRTC VAD considers it non-speech AND current frame RMS is relatively low,
                        # override the main VAD's decision to reduce false positives in noisy conditions.
                        if not webrtc_is_speech and rms < 0.04: # RMS threshold for this override
                            logging.debug(f"WebRTC VAD contradicts Silero VAD in high noise environment (WebRTC: no speech, RMS: {rms:.4f}). Filtering out potential false positive.")
                            return False
                except Exception as e: # Catch errors from WebRTC VAD (e.g., invalid frame length)
                    logging.warning(f"WebRTC VAD double-check error: {e}")
                
        return self.debounced_speech_state 