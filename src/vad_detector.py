import torch
from silero_vad import load_silero_vad, get_speech_timestamps
import logging
import numpy as np

class VADDetector:
    _model = None  # static model cache

    def __init__(self, sample_rate=16000, threshold=0.3, min_speech_duration_ms=300, min_silence_duration_ms=500):
        self.sample_rate = sample_rate
        self.threshold = threshold  # VAD sensitivity
        self.min_speech_duration_ms = min_speech_duration_ms
        self.min_silence_duration_ms = min_silence_duration_ms
        logging.info(f"Initializing VADDetector with sample rate: {self.sample_rate}, threshold: {self.threshold}")

        if not VADDetector._model:
            VADDetector._model = load_silero_vad()
            logging.info("Loaded Silero VAD model")

        self.model = VADDetector._model

    def is_speech(self, audio_tensor: torch.Tensor) -> bool:
        if len(audio_tensor.shape) == 2:
            audio_tensor = audio_tensor.squeeze(0)

        # Ensure valid values
        if torch.max(torch.abs(audio_tensor)) == 0:
            logging.warning("Silent audio segment received (all zeros)")
            return False

        # Log min/max values and shape
        min_val = torch.min(audio_tensor).item()
        max_val = torch.max(audio_tensor).item()
        abs_max = max(abs(min_val), abs(max_val))
        logging.debug(f"Audio tensor min: {min_val}, max: {max_val}, length: {len(audio_tensor)}")

        # Optimize: Check if amplitude is too low using max abs value
        # Only amplify extremely quiet audio (below 0.05 instead of 0.1)
        if abs_max < 0.05 and abs_max > 0:  # Only quiet but non-silent audio
            # Use fixed gain of 0.3/abs_max with max limit of 7
            gain = min(0.3 / abs_max, 7.0)
            audio_tensor = audio_tensor * gain
            logging.debug(f"Amplified quiet audio with gain: {gain:.2f}")

        audio_tensor = audio_tensor.unsqueeze(0)  # (1, samples)
        
        # Loglama için detaylı parametreleri göster
        logging.debug(f"VAD parameters: threshold={self.threshold}, min_speech_ms={self.min_speech_duration_ms}, min_silence_ms={self.min_silence_duration_ms}")
        
        # Get speech timestamps with explicit parameters
        try:
            timestamps = get_speech_timestamps(
                audio_tensor, 
                self.model, 
                sampling_rate=self.sample_rate,
                threshold=self.threshold,
                min_speech_duration_ms=self.min_speech_duration_ms,
                min_silence_duration_ms=self.min_silence_duration_ms,
                # Ek VAD parametreleri - daha hassas hale getirmek için
                return_seconds=False,
                speech_pad_ms=30,  # Konuşmanın başlangıç ve bitişini hafifçe genişlet
                visualize_probs=False
            )
            
            logging.debug(f"Detected timestamps: {timestamps}")
            
            # Alternatif VAD kontrolü - artık RMS yerine abs_max kullanıyoruz
            if not timestamps and abs_max > 0.1:
                logging.info(f"No speech detected by VAD, but high amplitude ({abs_max:.4f}). Treating as speech.")
                return True
                
            return bool(timestamps)
            
        except Exception as e:
            logging.error(f"Error in VAD processing: {e}")
            # Hata durumunda False döndür
            return False