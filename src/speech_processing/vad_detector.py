import torch
from silero_vad import load_silero_vad, get_speech_timestamps
import logging
from typing import Any # For torch.classes.silero_vad.SileroVAD

class VADDetector:
    """
    Voice Activity Detector (VAD) using the Silero VAD model.

    This class loads the Silero VAD model (once, cached statically) and provides
    a method `is_speech` to determine if a given audio tensor contains speech.
    It includes logic for handling audio tensor shapes, normalizing very quiet audio,
    and calling the Silero VAD `get_speech_timestamps` function.
    """
    _model: Any = None  # Static model cache for SileroVAD

    def __init__(self, 
                 sample_rate: int = 16000, 
                 threshold: float = 0.3, 
                 min_speech_duration_ms: int = 300, 
                 min_silence_duration_ms: int = 500):
        """
        Initializes the VADDetector.

        Args:
            sample_rate: The sample rate of the audio to be processed (e.g., 16000 Hz).
                         This must match the sample rate expected by the Silero VAD model.
            threshold: VAD sensitivity threshold. Lower values are more sensitive.
                       Typical values are between 0.1 and 0.9.
            min_speech_duration_ms: Minimum duration (in ms) of a speech segment to be considered speech.
            min_silence_duration_ms: Minimum duration (in ms) of silence after a speech segment
                                     to determine the end of that segment.
        """
        self.sample_rate: int = sample_rate
        self.threshold: float = threshold  # VAD sensitivity
        self.min_speech_duration_ms: int = min_speech_duration_ms
        self.min_silence_duration_ms: int = min_silence_duration_ms
        
        logging.info(
            f"Initializing VADDetector with: "
            f"sample_rate={self.sample_rate}, threshold={self.threshold}, "
            f"min_speech_duration_ms={self.min_speech_duration_ms}, "
            f"min_silence_duration_ms={self.min_silence_duration_ms}"
        )

        # Load the Silero VAD model if it hasn't been loaded yet (static caching)
        if not VADDetector._model:
            try:
                # Assuming silero_vad is installed and accessible
                VADDetector._model = load_silero_vad()
                logging.info("Successfully loaded Silero VAD model.")
            except Exception as e:
                logging.error(f"Failed to load Silero VAD model: {e}", exc_info=True)
                # Propagate error or handle appropriately if model loading is critical
                raise

        self.model: Any = VADDetector._model

    def is_speech(self, audio_tensor: torch.Tensor) -> bool:
        """
        Determines if the given audio tensor contains speech.

        Args:
            audio_tensor: A PyTorch tensor containing the audio data. 
                          Expected to be a 1D tensor of float32 samples,
                          or a 2D tensor of shape (1, samples).
                          The audio should be in the range [-1.0, 1.0].

        Returns:
            True if speech is detected in the audio tensor, False otherwise.
        """
        # Ensure audio_tensor is 1D
        if audio_tensor.ndim == 2:
            audio_tensor = audio_tensor.squeeze(0)
        elif audio_tensor.ndim != 1:
            logging.warning(f"Expected 1D or 2D audio tensor, got {audio_tensor.ndim}D. Skipping VAD.")
            return False

        # Handle completely silent audio to prevent VAD errors or misbehavior
        if torch.max(torch.abs(audio_tensor)) == 0:
            logging.debug("VAD: Silent audio segment received (all zeros). Returning False.")
            return False

        # Log basic audio properties for debugging
        if logging.getLogger().isEnabledFor(logging.DEBUG):
            min_val = torch.min(audio_tensor).item()
            max_val = torch.max(audio_tensor).item()
            abs_max = max(abs(min_val), abs(max_val))
            logging.debug(
                f"VAD: Audio tensor details - Length: {len(audio_tensor)}, "
                f"Min: {min_val:.4f}, Max: {max_val:.4f}, AbsMax: {abs_max:.4f}"
            )

        # Amplify very quiet audio. This helps VAD detect speech in low-volume recordings.
        # This complements normalization in AudioProcessor, targeting a specific quiet range.
        # Effective abs_max range for this block is [0.005, 0.05) due to AudioProcessor's earlier normalization.
        current_abs_max = torch.max(torch.abs(audio_tensor)).item() # Re-evaluate abs_max for safety
        if 0 < current_abs_max < 0.05:  # Only non-silent audio that is still very quiet
            # Gain calculation aims to bring quiet audio to a more detectable level (e.g., peak around 0.3)
            # Capped at 7.0 to prevent excessive amplification of noise.
            gain = min(0.3 / (current_abs_max + 1e-9), 7.0) # Added epsilon for stability with extremely small abs_max
            audio_tensor = audio_tensor * gain
            logging.debug(f"VAD: Amplified quiet audio with gain: {gain:.2f}. New AbsMax: {torch.max(torch.abs(audio_tensor)).item():.4f}")

        # Silero VAD expects a batch dimension, so add it if the tensor is 1D.
        # This was already done by audio_tensor = audio_tensor.unsqueeze(0) if it was 1D,
        # but if it was already (1,N) it's fine. Re-affirming for clarity.
        if audio_tensor.ndim == 1:
            audio_tensor = audio_tensor.unsqueeze(0) 
        
        # Log the parameters being used for the VAD call
        logging.debug(
            f"VAD parameters for get_speech_timestamps: "
            f"threshold={self.threshold}, min_speech_ms={self.min_speech_duration_ms}, "
            f"min_silence_ms={self.min_silence_duration_ms}, speech_pad_ms=30"
        )
        
        try:
            # Perform VAD using Silero's get_speech_timestamps
            speech_timestamps = get_speech_timestamps(
                audio_tensor, 
                self.model, 
                sampling_rate=self.sample_rate,
                threshold=self.threshold,  # VAD sensitivity
                min_speech_duration_ms=self.min_speech_duration_ms, # Min duration for a speech segment
                min_silence_duration_ms=self.min_silence_duration_ms, # Min silence to split segments
                return_seconds=False,  # Get timestamps in samples, not seconds
                speech_pad_ms=30,  # Optional padding at start/end of detected speech
                visualize_probs=False # Set to True to get speech probabilities (for debugging)
            )
            
            logging.debug(f"VAD: Detected speech timestamps: {speech_timestamps}")
            
            # If timestamps list is not empty, speech is considered present.
            return bool(speech_timestamps)
            
        except Exception as e:
            logging.error(f"VAD: Error during Silero VAD processing: {e}", exc_info=True)
            # In case of an error during VAD processing, assume no speech detected as a fallback.
            return False
