import torch
import torchaudio
import logging
from pcmu_decoder import PCMUDecoder # Assuming pcmu_decoder.py is in PYTHONPATH or src
from typing import Optional, Tuple

class AudioProcessor:
    """
    Handles audio processing for speech recognition.

    This class takes raw audio bytes (expected in PCMU format, 8kHz),
    decodes them, performs cleaning (NaN/Inf removal), normalization,
    resampling to a target sample rate (e.g., 16kHz for STT), and
    converts the audio to both a PyTorch tensor and 16-bit PCM byte format.
    """

    def __init__(self, target_sample_rate: int = 16000, debug: bool = False, session_id: str = ""):
        """
        Initializes the AudioProcessor.

        Args:
            target_sample_rate: The desired sample rate for the output audio, typically 16000 Hz for STT.
            debug: If True, enables detailed debug logging for audio processing steps.
            session_id: An identifier for the current session, used for contextual logging.
        """
        self.target_sample_rate: int = target_sample_rate
        self.debug: bool = debug
        self.session_id: str = session_id

        self.pcmu_decoder: PCMUDecoder = PCMUDecoder()
        # Ensure torchaudio.transforms is available. It might require separate installation
        # or might be part of a larger PyTorch audio package.
        self.resampler: torchaudio.transforms.Resample = torchaudio.transforms.Resample(
            orig_freq=8000,  # PCMU is typically 8kHz
            new_freq=self.target_sample_rate
        )
        logging.info(f"{self.session_id}AudioProcessor initialized for target sample rate {self.target_sample_rate}Hz.")

    def tensor_to_bytes(self, tensor: torch.Tensor) -> bytes:
        """
        Converts a float32 audio tensor to 16-bit PCM bytes (little-endian).

        The input tensor is expected to contain audio samples in the range [-1.0, 1.0].
        Values outside this range will be clamped. The tensor is then scaled to the
        int16 range [-32768, 32767] and converted to raw bytes.

        Args:
            tensor: A PyTorch float32 audio tensor (1D).

        Returns:
            Audio data as a byte string in 16-bit PCM format.
        """
        # Ensure tensor values are within the expected float range [-1.0, 1.0]
        clamped_tensor = torch.clamp(tensor, -1.0, 1.0)
        # Scale to int16 range, convert type, then to bytes
        # Note: .numpy().tobytes() uses the system's native endianness, usually little-endian.
        return (clamped_tensor * 32767.0).to(torch.int16).numpy().tobytes() # Max int16 is 32767

    def process_bytes_audio(self, audio: bytes) -> Tuple[Optional[torch.Tensor], Optional[bytes]]:
        """
        Processes raw PCMU audio bytes into a resampled float32 tensor and 16-bit PCM bytes.

        The pipeline includes:
        1. Decoding PCMU bytes to float32 PCM NumPy array.
        2. Converting NumPy array to a PyTorch tensor.
        3. Cleaning the tensor (removing NaN/Inf values).
        4. Normalizing audio levels if too quiet.
        5. Resampling the audio to the target sample rate.
        6. Converting the final resampled tensor to 16-bit PCM bytes.

        Args:
            audio: Raw audio bytes, expected in PCMU (G.711 mu-law) format.

        Returns:
            tuple: A tuple containing:
                - resampled_tensor (torch.Tensor | None): The processed and resampled audio
                  as a float32 PyTorch tensor, or None if processing failed.
                - audio_bytes (bytes | None): The processed audio converted to 16-bit PCM bytes,
                  suitable for STT engines, or None if processing failed.
        """
        if len(audio) == 0:
            logging.warning(f"{self.session_id}Received empty audio bytes. Skipping processing.")
            return None, None

        if self.debug:
            logging.debug(f"{self.session_id}Raw input audio: {len(audio)} bytes")

        try:
            # Decode and convert to tensor
            pcm32_samples_np = self._decode_pcmu(audio)
            if pcm32_samples_np is None:
                return None, None
            audio_tensor = self._to_tensor(pcm32_samples_np)

            # Step 3: Clean tensor by removing NaN or Inf values
            audio_tensor = self._clean_tensor(audio_tensor)

            # Step 4: Normalize audio levels, especially for very quiet audio
            audio_tensor = self._normalize_audio(audio_tensor)

            # Resample and validate
            resampled_tensor = self._resample_tensor(audio_tensor)
            if resampled_tensor.shape[0] == 0:
                logging.warning(f"{self.session_id}Resampling resulted in an empty tensor. Skipping.")
                return None, None

            # Convert to bytes and return
            audio_bytes_out = self.tensor_to_bytes(resampled_tensor)

            if self.debug:
                logging.debug(f"{self.session_id}Final processed audio bytes length: {len(audio_bytes_out)}")

            return resampled_tensor, audio_bytes_out

        except Exception as e:
            logging.error(f"{self.session_id}Error processing audio bytes: {e}", exc_info=True)
            return None, None

    def _decode_pcmu(self, audio: bytes):
        """Decode PCMU bytes to float32 NumPy array (8kHz)."""
        pcm32_samples_np = self.pcmu_decoder.decode(audio)
        if pcm32_samples_np is None or pcm32_samples_np.size == 0:
            logging.warning(f"{self.session_id}PCMU decoder returned empty result. Skipping processing.")
            return None
        if self.debug:
            logging.debug(f"{self.session_id}Decoded PCMU to float32 PCM samples: count={len(pcm32_samples_np)}")
        return pcm32_samples_np

    def _to_tensor(self, pcm32_samples_np) -> torch.Tensor:
        """Convert float32 NumPy array to float32 PyTorch tensor."""
        audio_tensor = torch.from_numpy(pcm32_samples_np)
        if self.debug:
            logging.debug(f"{self.session_id}Converted NumPy to 8kHz PyTorch tensor: shape={audio_tensor.shape}, dtype={audio_tensor.dtype}, min={audio_tensor.min():.4f}, max={audio_tensor.max():.4f}")
        return audio_tensor

    def _resample_tensor(self, audio_tensor: torch.Tensor) -> torch.Tensor:
        """Resample 8kHz tensor to target sample rate."""
        resampled_tensor = self.resampler(audio_tensor.unsqueeze(0)).squeeze(0)
        if self.debug:
            logging.debug(f"{self.session_id}Resampled tensor to {self.target_sample_rate}Hz: shape={resampled_tensor.shape}, dtype={resampled_tensor.dtype}, min={resampled_tensor.min():.4f}, max={resampled_tensor.max():.4f}")
        return resampled_tensor

    def _clean_tensor(self, tensor: torch.Tensor) -> torch.Tensor:
        """
        Cleans an audio tensor by replacing NaN or Inf values.

        NaN values are replaced with 0.0.
        Positive infinity values are replaced with 0.99.
        Negative infinity values are replaced with -0.99.

        Args:
            tensor: The input PyTorch audio tensor.

        Returns:
            torch.Tensor: The cleaned audio tensor.
        """
        if torch.isnan(tensor).any() or torch.isinf(tensor).any():
            if self.debug:
                logging.debug(f"{self.session_id}Audio tensor contains NaN or Inf values. Cleaning tensor.")
            return torch.nan_to_num(tensor, nan=0.0, posinf=0.99, neginf=-0.99)
        return tensor

    def _normalize_audio(self, tensor: torch.Tensor) -> torch.Tensor:
        """
        Normalizes audio levels, particularly for very quiet audio.

        If the maximum absolute amplitude of the tensor is below a threshold (0.005),
        a gain is applied to boost the audio level. The gain is capped to avoid
        excessive amplification.

        Args:
            tensor: The input PyTorch audio tensor.

        Returns:
            torch.Tensor: The (potentially) normalized audio tensor.
        """
        audio_max = torch.max(torch.abs(tensor))
        
        # Hızlı gürültü analizi
        rms = torch.sqrt(torch.mean(tensor ** 2))
        sorted_amplitudes = torch.sort(torch.abs(tensor))[0]
        if len(sorted_amplitudes) > 10:  # Dizinin en az 10 eleman içerdiğinden emin ol
            noise_floor = sorted_amplitudes[int(len(sorted_amplitudes) * 0.1)]  # 10th percentile
            snr = 20 * torch.log10(rms / (noise_floor + 1e-10))
            
            # Her ses parçası için gürültü seviyesini logla
            logging.debug(f"{self.session_id}Audio processor noise analysis - rms: {rms:.4f}, max: {audio_max:.4f}, noise_floor: {noise_floor:.4f}, SNR: {snr:.2f}")

        # Sessiz ses için normalizasyon
        if audio_max < 0.005:
            gain = min(0.2 / (audio_max + 1e-10), 5.0)
            tensor = tensor * gain
            logging.debug(f"{self.session_id}Applied normalization with gain: {gain:.2f}")
        
        # Gürültülü ortam belirtisi - zaten normalize edilmiş ses için yumuşatma
        # Gürültülü ses genellikle yüksek RMS ama düşük dinamik aralığa sahiptir
        if rms > 0.05 and audio_max < 0.3:
            # Soft gürültü azaltma için hafif bir yumuşatma uygula
            tensor = tensor * 0.8
            logging.info(f"{self.session_id}Applied soft noise reduction (high RMS but low peak)")

        return tensor
