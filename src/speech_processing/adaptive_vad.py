import torch
import numpy as np
import webrtcvad
import logging
import time
import asyncio
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
    
    Heavy computations are offloaded to thread pool to maintain async event loop responsiveness.
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

    def _should_ignore_due_to_echo_sync(self, audio_tensor: torch.Tensor) -> bool:
        """
        Synchronous version of echo detection for thread execution.
        
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

    async def _should_ignore_due_to_echo(self, audio_tensor: torch.Tensor) -> bool:
        """
        Async wrapper for echo detection that offloads computation to thread pool.
        
        Args:
            audio_tensor: The current audio tensor being processed
            
        Returns:
            True if the audio should be ignored as an echo
        """
        return await asyncio.to_thread(self._should_ignore_due_to_echo_sync, audio_tensor)

    def _compute_audio_metrics_sync(self, audio_tensor: torch.Tensor) -> Dict[str, float]:
        """
        Synchronous computation of audio metrics for thread execution.
        
        Args:
            audio_tensor: Audio tensor to analyze
            
        Returns:
            Dictionary containing computed metrics
        """
        # Basic metrics
        rms = torch.sqrt(torch.mean(audio_tensor ** 2)).item()
        peak = torch.max(torch.abs(audio_tensor)).item()
        
        # Advanced metrics for calibration
        sorted_amplitudes = torch.sort(torch.abs(audio_tensor))[0]
        
        if torch.all(sorted_amplitudes < 1e-10):
            return {
                'rms': rms,
                'peak': peak,
                'noise_floor': 1e-10,
                'snr': 0.0,
                'dynamic_range': 0.0
            }
            
        noise_floor = sorted_amplitudes[int(len(sorted_amplitudes) * 0.1)]  # 10th percentile
        
        # Safe SNR calculation
        if noise_floor < 1e-10:
            noise_floor = 1e-10
            snr = 0.0
        else:
            snr_tensor = 20 * torch.log10(peak / noise_floor)
            snr = snr_tensor.item() if not torch.isinf(snr_tensor) and not torch.isnan(snr_tensor) else 0.0
        
        # Dynamic range calculation
        p90 = sorted_amplitudes[int(len(sorted_amplitudes) * 0.9)]  # 90th percentile
        p10 = sorted_amplitudes[int(len(sorted_amplitudes) * 0.1)]  # 10th percentile
        
        if p10 > 1e-10:
            dynamic_range_tensor = 20 * torch.log10(p90 / p10)
            dynamic_range = dynamic_range_tensor.item() if not torch.isinf(dynamic_range_tensor) and not torch.isnan(dynamic_range_tensor) else 0.0
        else:
            dynamic_range = 0.0
            
        return {
            'rms': rms,
            'peak': peak,
            'noise_floor': noise_floor.item() if isinstance(noise_floor, torch.Tensor) else noise_floor,
            'snr': snr,
            'dynamic_range': dynamic_range
        }

    async def _compute_audio_metrics(self, audio_tensor: torch.Tensor) -> Dict[str, float]:
        """
        Async wrapper for audio metrics computation that offloads to thread pool.
        
        Args:
            audio_tensor: Audio tensor to analyze
            
        Returns:
            Dictionary containing computed metrics
        """
        return await asyncio.to_thread(self._compute_audio_metrics_sync, audio_tensor)

    def _webrtc_vad_check_sync(self, audio_tensor: torch.Tensor) -> Tuple[bool, int, int]:
        """
        Synchronous WebRTC VAD check for thread execution.
        
        Args:
            audio_tensor: Audio tensor to check
            
        Returns:
            Tuple of (is_noise, noise_frames, total_frames)
        """
        if not self.webrtc_vad or audio_tensor.shape[0] < 320:
            return False, 0, 0
            
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
        return is_noise, noise_frames, num_frames

    async def _webrtc_vad_check(self, audio_tensor: torch.Tensor) -> Tuple[bool, int, int]:
        """
        Async wrapper for WebRTC VAD check that offloads to thread pool.
        
        Args:
            audio_tensor: Audio tensor to check
            
        Returns:
            Tuple of (is_noise, noise_frames, total_frames)
        """
        return await asyncio.to_thread(self._webrtc_vad_check_sync, audio_tensor)

    async def _update_calibration(self, audio_tensor: torch.Tensor) -> None:
        """
        Update VAD calibration based on recent audio using async thread execution.
        
        Args:
            audio_tensor: The current audio tensor being processed
        """
        if not self.auto_calibration:
            return
            
        # Add current audio to history
        self.audio_history.append(audio_tensor.detach().clone())
        self.audio_history_timestamps.append(time.time())
        
        # Compute metrics asynchronously
        metrics = await self._compute_audio_metrics(audio_tensor)
        rms = metrics['rms']
        peak = metrics['peak']
        
        # Check for continuous noise using WebRTC VAD
        is_noise, noise_frames, total_frames = await self._webrtc_vad_check(audio_tensor)
        
        # Only log noise events if RMS is above a minimum threshold to avoid false positives
        if is_noise != self.last_detected_noise:
            self.last_detected_noise = is_noise
            if is_noise and rms > 0.012:  # RMS eşiği ekledik
                self.noise_events_count += 1
                logging.info(f"Noise detected by WebRTC VAD! ({self.noise_events_count} events so far)")
        
        # Every 30 seconds, log noise events and reset
        current_time = time.time()
        if current_time - self.noise_tracking_start_time > 30:
            logging.info(f"Last 30 seconds noise summary: {self.noise_events_count} noise events detected")
            self.noise_tracking_start_time = current_time
            self.noise_events_count = 0
        
        # Maintain only recent audio within calibration window
        window_duration = self.calibration_window_ms / 1000  # Convert ms to seconds
        
        # Remove old audio from history
        while self.audio_history and (current_time - self.audio_history_timestamps[0]) > window_duration:
            self.audio_history.pop(0)
            self.audio_history_timestamps.pop(0)
            
        # Only recalibrate every 2 seconds
        if current_time - self.last_calibration_time < 2:
            return
            
        # Only calibrate if we have enough audio history
        if not self.audio_history or sum(t.shape[0] for t in self.audio_history) < self.calibration_window_samples // 2:
            return
            
        # Concatenate audio history for analysis and compute metrics asynchronously
        concat_audio = torch.cat(self.audio_history, dim=0)
        concat_metrics = await self._compute_audio_metrics(concat_audio)
        
        rms_concat = concat_metrics['rms']
        peak_concat = concat_metrics['peak']
        noise_floor = concat_metrics['noise_floor']
        snr = concat_metrics['snr']
        dynamic_range = concat_metrics['dynamic_range']
        
        # Rest of calibration logic remains the same but uses computed metrics
        new_threshold = self.threshold
        
        # Noise trend analysis
        consecutive_noise_detections = 0
        if len(self.calibration_history) >= 3:
            for i in range(min(3, len(self.calibration_history))):
                idx = len(self.calibration_history) - 1 - i
                if idx >= 0 and 'is_high_noise' in self.calibration_history[idx][2]:
                    if self.calibration_history[idx][2]['is_high_noise']:
                        consecutive_noise_detections += 1
                    else:
                        break
        
        noise_trend_strength = 1.0
        if consecutive_noise_detections >= 1:
            noise_trend_strength = 1.5
        if consecutive_noise_detections == 3:
            noise_trend_strength = 2.0
        
        # HIGH NOISE ENVIRONMENT DETECTION
        is_high_noise = (
            (noise_floor > 0.018) or
            (snr < 20 and rms_concat > 0.009) or
            (rms_concat > 0.05 and dynamic_range < 10)
        )
        
        if rms_concat < 0.008:
            is_high_noise = False
        
        logging.info(f"NOISE DETECTION - conditions: noise_floor > 0.018: {noise_floor > 0.018}, snr < 20 and rms_concat > 0.009: {snr < 20 and rms_concat > 0.009}, rms_concat > 0.05 and dynamic_range < 10: {rms_concat > 0.05 and dynamic_range < 10}")
        logging.info(f"NOISE DETECTION - result: is_high_noise: {is_high_noise}, current threshold: {self.threshold:.2f}")
        
        # Threshold adjustment logic
        if is_high_noise:
            if self.threshold < self.max_threshold * 0.9:
                if snr < 5:
                    noise_increase = 0.08 * noise_trend_strength
                else:
                    noise_increase = 0.05 * noise_trend_strength
                
                new_threshold = min(self.threshold + noise_increase, self.max_threshold)
                logging.info(f"High noise environment detected. Increasing threshold to {new_threshold:.2f} (noise_floor={noise_floor:.4f}, SNR={snr:.2f}, trend_strength={noise_trend_strength:.1f})")
            else:
                logging.info(f"Threshold already high ({self.threshold:.2f}). Maintaining current level.")
                
        elif (noise_floor < 0.01 and snr > 20) or (rms_concat < 0.0025):
            decrease_step = 0.05
            if self.threshold > 0.5:
                decrease_step = 0.1
            elif self.threshold > 0.4:
                decrease_step = 0.08
                
            new_threshold = max(self.threshold - decrease_step, self.min_threshold)
            logging.info(f"Low noise environment detected. Decreasing threshold to {new_threshold:.2f}")
            
        elif peak_concat < 0.1:
            new_threshold = max(self.threshold - 0.02, self.min_threshold)
            logging.info(f"Very quiet audio detected. Decreasing threshold to {new_threshold:.2f}")
            
        elif peak_concat > 0.8:
            new_threshold = min(self.threshold + 0.05, self.max_threshold)
            logging.info(f"Very loud audio detected. Increasing threshold to {new_threshold:.2f}")
            
        # Update threshold if it changed
        if new_threshold != self.threshold:
            self.threshold = new_threshold
            
            try:
                self.calibration_history.append((time.time(), new_threshold, {
                    'rms': rms_concat, 
                    'peak': peak_concat, 
                    'noise_floor': noise_floor,
                    'snr': snr,
                    'dynamic_range': dynamic_range,
                    'is_high_noise': is_high_noise
                }))
            except Exception as e:
                logging.error(f"Error saving calibration history: {e}")
            
        # Gradual normalization every 30 seconds
        if len(self.calibration_history) > 0 and (time.time() - self.calibration_history[-1][0]) > 30:
            base_threshold = 0.30
            
            if abs(self.threshold - base_threshold) > 0.05:
                norm_step = 0.03
                if abs(self.threshold - base_threshold) > 0.15:
                    norm_step = 0.05
                
                if self.threshold > base_threshold:
                    self.threshold = max(self.threshold - norm_step, base_threshold)
                    logging.info(f"Gradual normalization: Decreasing threshold to {self.threshold:.2f} towards {base_threshold}")
                else:
                    self.threshold = min(self.threshold + norm_step, base_threshold)
                    logging.info(f"Gradual normalization: Increasing threshold to {self.threshold:.2f} towards {base_threshold}")
            
        self.last_calibration_time = time.time()

    async def is_speech(self, audio_tensor: torch.Tensor) -> bool:
        """
        Enhanced async method to determine if the given audio tensor contains speech.
        Includes calibration, adaptation, echo cancellation, and debouncing.
        Heavy computations are offloaded to thread pool for better async performance.

        Args:
            audio_tensor: A PyTorch tensor containing the audio data.

        Returns:
            True if speech is detected in the audio tensor, False otherwise.
        """
        # Skip speech detection during TTS playback or cooldown period
        if await self._should_ignore_due_to_echo(audio_tensor):
            logging.debug("Ignoring audio due to active TTS or cooldown period")
            return False
            
        # Calculate current frame metrics asynchronously
        metrics = await self._compute_audio_metrics(audio_tensor)
        rms = metrics['rms']
        peak = metrics['peak']
        
        # Very low audio levels - skip VAD
        if rms < 0.006:
            logging.debug(f"Audio level too low for reliable detection, RMS={rms:.4f}. Skipping VAD.")
            return False
            
        # Update calibration based on current audio (async)
        await self._update_calibration(audio_tensor)
        
        # Check if we're in an extreme noise situation
        is_extreme_noise = False
        if len(self.calibration_history) >= 3:
            high_noise_count = 0
            for i in range(min(3, len(self.calibration_history))):
                idx = len(self.calibration_history) - 1 - i
                if idx >= 0 and 'is_high_noise' in self.calibration_history[idx][2]:
                    if self.calibration_history[idx][2]['is_high_noise']:
                        high_noise_count += 1
            
            is_extreme_noise = high_noise_count == 3 and self.threshold > 0.45 and rms > 0.012
            
            if is_extreme_noise:
                logging.info(f"EXTREME NOISE ENVIRONMENT DETECTED! Threshold: {self.threshold:.2f}, RMS: {rms:.4f}")
        
        # Skip speech detection in extreme noise
        if is_extreme_noise and rms > 0.012 and peak < 0.7:
            logging.debug(f"Bypassing speech detection in extreme noise environment. RMS={rms:.4f}, Peak={peak:.4f}")
            return False
        
        logging.debug(f"Current frame: RMS={rms:.4f}, Peak={peak:.4f}, VAD Threshold={self.threshold:.2f}")
        
        # Get raw speech detection from parent class (this is still sync but fast)
        raw_speech_detected = super().is_speech(audio_tensor)
        
        # Apply debouncing
        if raw_speech_detected:
            self.consecutive_speech_frames += 1
            self.consecutive_silence_frames = 0
            
            if self.consecutive_speech_frames >= self.speech_debounce_frames:
                if not self.debounced_speech_state:
                    logging.debug(f"Speech confirmed after {self.consecutive_speech_frames} consecutive frames")
                self.debounced_speech_state = True
        else:
            self.consecutive_silence_frames += 1
            self.consecutive_speech_frames = 0
            
            if self.consecutive_silence_frames >= self.silence_debounce_frames:
                if self.debounced_speech_state:
                    logging.debug(f"Silence confirmed after {self.consecutive_silence_frames} consecutive frames")
                self.debounced_speech_state = False
                
        # High noise environment extra validation with WebRTC VAD (async)
        if self.debounced_speech_state and self.threshold > 0.4 and not is_extreme_noise:
            is_noise, noise_frames, total_frames = await self._webrtc_vad_check(audio_tensor)
            
            # WebRTC contradicts our detection in high noise - filter false positive
            if total_frames > 0:
                webrtc_speech_ratio = (total_frames - noise_frames) / total_frames
                if webrtc_speech_ratio < 0.5 and rms < 0.04:
                    logging.debug(f"WebRTC VAD contradicts Silero VAD in high noise environment, filtering out false positive")
                    return False
                
        return self.debounced_speech_state 