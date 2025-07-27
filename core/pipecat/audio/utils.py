"""
Minimal Audio Utilities for OpenSIPS AI Voice Connector
Essential audio processing functions extracted from pipecat
"""

import logging
import numpy as np
from typing import Optional

logger = logging.getLogger(__name__)

def audio_resample(
    audio_data: bytes,
    input_sample_rate: int,
    output_sample_rate: int,
    input_channels: int = 1,
    output_channels: int = 1
) -> bytes:
    """
    Simple audio resampling using numpy
    For production use, consider librosa or other audio libraries
    """
    if input_sample_rate == output_sample_rate and input_channels == output_channels:
        return audio_data
    
    try:
        # Convert bytes to numpy array (assuming 16-bit PCM)
        audio_array = np.frombuffer(audio_data, dtype=np.int16)
        
        # Handle multi-channel to mono conversion
        if input_channels > 1 and output_channels == 1:
            audio_array = audio_array.reshape(-1, input_channels)
            audio_array = np.mean(audio_array, axis=1).astype(np.int16)
        
        # Simple resampling (nearest neighbor - not ideal for production)
        if input_sample_rate != output_sample_rate:
            ratio = output_sample_rate / input_sample_rate
            new_length = int(len(audio_array) * ratio)
            indices = np.linspace(0, len(audio_array) - 1, new_length).astype(int)
            audio_array = audio_array[indices]
        
        # Handle mono to multi-channel conversion
        if input_channels == 1 and output_channels > 1:
            audio_array = np.repeat(audio_array[:, np.newaxis], output_channels, axis=1)
            audio_array = audio_array.flatten()
        
        return audio_array.tobytes()
        
    except Exception as e:
        logger.error(f"Audio resampling error: {e}")
        return audio_data

def calculate_audio_volume(audio_data: bytes) -> float:
    """Calculate RMS volume of audio data"""
    try:
        audio_array = np.frombuffer(audio_data, dtype=np.int16)
        if len(audio_array) == 0:
            return 0.0
        
        # Calculate RMS
        rms = np.sqrt(np.mean(audio_array.astype(np.float32) ** 2))
        
        # Normalize to 0-1 range (assuming 16-bit audio)
        return min(rms / 32768.0, 1.0)
        
    except Exception as e:
        logger.error(f"Volume calculation error: {e}")
        return 0.0

def is_audio_silent(
    audio_data: bytes, 
    silence_threshold: float = 0.01,
    min_duration_ms: int = 100,
    sample_rate: int = 16000
) -> bool:
    """Check if audio data is considered silent"""
    try:
        volume = calculate_audio_volume(audio_data)
        
        # Check volume threshold
        if volume > silence_threshold:
            return False
        
        # Check minimum duration
        audio_array = np.frombuffer(audio_data, dtype=np.int16)
        duration_ms = (len(audio_array) / sample_rate) * 1000
        
        return duration_ms >= min_duration_ms
        
    except Exception as e:
        logger.error(f"Silence detection error: {e}")
        return False

def merge_audio_chunks(chunks: list, sample_rate: int = 16000) -> bytes:
    """Merge multiple audio chunks into single audio data"""
    try:
        if not chunks:
            return b''
        
        # Convert all chunks to numpy arrays
        arrays = []
        for chunk in chunks:
            if isinstance(chunk, bytes) and len(chunk) > 0:
                array = np.frombuffer(chunk, dtype=np.int16)
                arrays.append(array)
        
        if not arrays:
            return b''
        
        # Concatenate arrays
        merged = np.concatenate(arrays)
        return merged.tobytes()
        
    except Exception as e:
        logger.error(f"Audio merge error: {e}")
        return b''

def generate_silence(duration_ms: int, sample_rate: int = 16000) -> bytes:
    """Generate silence audio data"""
    try:
        num_samples = int((duration_ms / 1000.0) * sample_rate)
        silence_array = np.zeros(num_samples, dtype=np.int16)
        return silence_array.tobytes()
        
    except Exception as e:
        logger.error(f"Silence generation error: {e}")
        return b''

def validate_audio_format(
    audio_data: bytes,
    expected_sample_rate: int = 16000,
    expected_channels: int = 1,
    expected_bit_depth: int = 16
) -> dict:
    """Validate audio format and return information"""
    try:
        # Basic validation for PCM 16-bit
        if len(audio_data) % 2 != 0:
            return {
                "valid": False,
                "error": "Audio data length not compatible with 16-bit format"
            }
        
        audio_array = np.frombuffer(audio_data, dtype=np.int16)
        
        # Calculate duration
        duration_ms = (len(audio_array) / expected_sample_rate) * 1000
        
        # Calculate basic stats
        volume = calculate_audio_volume(audio_data)
        max_amplitude = np.max(np.abs(audio_array)) if len(audio_array) > 0 else 0
        
        return {
            "valid": True,
            "samples": len(audio_array),
            "duration_ms": duration_ms,
            "volume": volume,
            "max_amplitude": int(max_amplitude),
            "estimated_sample_rate": expected_sample_rate,
            "estimated_channels": expected_channels
        }
        
    except Exception as e:
        return {
            "valid": False,
            "error": str(e)
        }