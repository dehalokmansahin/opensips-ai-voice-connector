import torch
from silero_vad import load_silero_vad, get_speech_timestamps
import logging
from typing import Any, Optional, List # For torch.classes.silero_vad.SileroVAD

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

    # New private helpers for VAD detection steps
    def _validate_and_squeeze(self, audio_tensor: torch.Tensor) -> Optional[torch.Tensor]:
        """Ensure tensor is 1D or 2D; return 1D tensor or None if invalid."""
        if audio_tensor.ndim == 2:
            return audio_tensor.squeeze(0)
        if audio_tensor.ndim == 1:
            return audio_tensor
        logging.warning(f"{self.__class__.__name__}: Expected 1D or 2D tensor, got {audio_tensor.ndim}D.")
        return None

    def _is_completely_silent(self, audio_tensor: torch.Tensor) -> bool:
        """Check if tensor contains only zeros."""
        if torch.max(torch.abs(audio_tensor)) == 0:
            logging.debug(f"{self.__class__.__name__}: Silent audio segment.")
            return True
        return False

    def _debug_log_tensor_stats(self, audio_tensor: torch.Tensor) -> None:
        """Log min, max and abs max of tensor for debugging."""
        if logging.getLogger().isEnabledFor(logging.DEBUG):
            min_val = torch.min(audio_tensor).item()
            max_val = torch.max(audio_tensor).item()
            abs_max = max(abs(min_val), abs(max_val))
            logging.debug(f"{self.__class__.__name__}: Audio stats - Length: {audio_tensor.numel()}, Min: {min_val:.4f}, Max: {max_val:.4f}, AbsMax: {abs_max:.4f}")

    def _amplify_quiet_audio(self, audio_tensor: torch.Tensor) -> torch.Tensor:
        """Amplify audio with very low amplitude to aid detection."""
        current_abs_max = torch.max(torch.abs(audio_tensor)).item()
        if 0 < current_abs_max < 0.05:
            gain = min(0.3 / (current_abs_max + 1e-9), 7.0)
            audio_tensor = audio_tensor * gain
            logging.debug(f"{self.__class__.__name__}: Amplified audio with gain {gain:.2f}. New AbsMax: {torch.max(torch.abs(audio_tensor)).item():.4f}")
        return audio_tensor

    def _add_batch_dim(self, audio_tensor: torch.Tensor) -> torch.Tensor:
        """Ensure a batch dimension for the VAD model input."""
        return audio_tensor.unsqueeze(0) if audio_tensor.ndim == 1 else audio_tensor

    def _log_vad_parameters(self) -> None:
        """Log parameters used for the VAD call."""
        logging.debug(f"{self.__class__.__name__}: VAD params - threshold={self.threshold}, min_speech_ms={self.min_speech_duration_ms}, min_silence_ms={self.min_silence_duration_ms}, speech_pad_ms=30")

    def _run_silero_vad(self, audio_tensor: torch.Tensor) -> List[Any]:
        """Invoke Silero VAD and return detected speech timestamps (empty list on error)."""
        try:
            return get_speech_timestamps(
                audio_tensor, self.model,
                sampling_rate=self.sample_rate,
                threshold=self.threshold,
                min_speech_duration_ms=self.min_speech_duration_ms,
                min_silence_duration_ms=self.min_silence_duration_ms,
                return_seconds=False,
                speech_pad_ms=30,
                visualize_probs=False
            )
        except Exception as e:
            logging.error(f"{self.__class__.__name__}: Error during Silero VAD: {e}", exc_info=True)
            return []

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
        # 1) Validate and squeeze tensor dimensions
        audio_tensor = self._validate_and_squeeze(audio_tensor)
        if audio_tensor is None:
            return False

        # 2) Silent audio check
        if self._is_completely_silent(audio_tensor):
            return False

        # 3) Debug log tensor stats
        self._debug_log_tensor_stats(audio_tensor)

        # 4) Amplify if too quiet
        audio_tensor = self._amplify_quiet_audio(audio_tensor)

        # 5) Add batch dimension
        audio_tensor = self._add_batch_dim(audio_tensor)

        # 6) Run Silero VAD
        self._log_vad_parameters()
        speech_timestamps = self._run_silero_vad(audio_tensor)

        # 7) Return detection result
        logging.debug(f"{self.__class__.__name__}: Detected speech timestamps: {speech_timestamps}")
        return bool(speech_timestamps)
