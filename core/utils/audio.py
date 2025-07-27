"""
Audio processing utilities for OpenSIPS AI Voice Connector
Enhanced audio processing functions
"""

import logging
import numpy as np
import struct
from typing import Optional, Tuple, List

logger = logging.getLogger(__name__)

class AudioFormat:
    """Audio format constants"""
    PCMU = 0  # G.711 μ-law
    PCMA = 8  # G.711 A-law
    PCM16 = 1  # Linear PCM 16-bit
    
    SAMPLE_RATES = {
        'narrow': 8000,   # Narrow band (telephony)
        'wide': 16000,    # Wide band (speech recognition)
        'music': 22050,   # Music quality (TTS)
        'cd': 44100       # CD quality
    }

def pcmu_to_pcm16(pcmu_data: bytes) -> bytes:
    """Convert PCMU (μ-law) to PCM 16-bit"""
    try:
        # μ-law decode table (simplified)
        pcm_samples = []
        
        for byte in pcmu_data:
            # μ-law decode
            byte = ~byte  # Invert bits
            sign = byte & 0x80
            exponent = (byte & 0x70) >> 4
            mantissa = byte & 0x0F
            
            # Calculate linear value
            linear = (mantissa << 3) + 0x84
            linear <<= exponent
            
            if sign:
                linear = -linear
            
            # Scale to 16-bit range
            pcm_value = max(-32768, min(32767, linear))
            pcm_samples.append(pcm_value)
        
        # Convert to bytes
        return struct.pack(f'<{len(pcm_samples)}h', *pcm_samples)
        
    except Exception as e:
        logger.error(f"Error converting PCMU to PCM16: {e}")
        return b''

def pcm16_to_pcmu(pcm_data: bytes) -> bytes:
    """Convert PCM 16-bit to PCMU (μ-law)"""
    try:
        if len(pcm_data) % 2 != 0:
            logger.warning("PCM data length not even, truncating")
            pcm_data = pcm_data[:-1]
        
        # Unpack PCM samples
        pcm_samples = struct.unpack(f'<{len(pcm_data)//2}h', pcm_data)
        
        pcmu_bytes = []
        for sample in pcm_samples:
            # μ-law encode
            sign = 0x80 if sample < 0 else 0x00
            sample = abs(sample)
            
            # Bias and clip
            sample = min(sample + 33, 32767)
            
            # Find exponent
            exponent = 7
            for i in range(7):
                if sample <= (33 << i):
                    exponent = i
                    break
            
            # Find mantissa
            if exponent == 0:
                mantissa = (sample - 33) >> 1
            else:
                mantissa = (sample >> (exponent + 3)) & 0x0F
            
            # Combine and invert
            byte = ~(sign | (exponent << 4) | mantissa) & 0xFF
            pcmu_bytes.append(byte)
        
        return bytes(pcmu_bytes)
        
    except Exception as e:
        logger.error(f"Error converting PCM16 to PCMU: {e}")
        return b''

# Alias for backward compatibility
def convert_sample_rate(audio_data: bytes, input_rate: int, output_rate: int) -> bytes:
    """Convert audio sample rate (backward compatibility alias)"""
    return resample_audio(audio_data, input_rate, output_rate)

def resample_audio(
    audio_data: bytes,
    input_rate: int,
    output_rate: int,
    input_format: int = AudioFormat.PCM16,
    output_format: int = AudioFormat.PCM16
) -> bytes:
    """Resample audio data"""
    try:
        if input_rate == output_rate and input_format == output_format:
            return audio_data
        
        # Convert input to PCM16 if needed
        pcm_data = audio_data
        if input_format == AudioFormat.PCMU:
            pcm_data = pcmu_to_pcm16(audio_data)
        elif input_format == AudioFormat.PCMA:
            # For now, treat PCMA same as PCMU (simplified)
            pcm_data = pcmu_to_pcm16(audio_data)
        
        # Resample if needed
        if input_rate != output_rate:
            pcm_data = _resample_pcm16(pcm_data, input_rate, output_rate)
        
        # Convert output format if needed
        if output_format == AudioFormat.PCMU:
            return pcm16_to_pcmu(pcm_data)
        elif output_format == AudioFormat.PCMA:
            # For now, treat PCMA same as PCMU (simplified)
            return pcm16_to_pcmu(pcm_data)
        
        return pcm_data
        
    except Exception as e:
        logger.error(f"Error resampling audio: {e}")
        return audio_data

def _resample_pcm16(pcm_data: bytes, input_rate: int, output_rate: int) -> bytes:
    """Resample PCM16 data using linear interpolation"""
    try:
        if len(pcm_data) % 2 != 0:
            pcm_data = pcm_data[:-1]
        
        # Unpack samples
        input_samples = np.frombuffer(pcm_data, dtype=np.int16)
        
        # Calculate resampling ratio
        ratio = output_rate / input_rate
        output_length = int(len(input_samples) * ratio)
        
        # Generate output sample indices
        output_indices = np.linspace(0, len(input_samples) - 1, output_length)
        
        # Linear interpolation
        output_samples = np.interp(output_indices, np.arange(len(input_samples)), input_samples.astype(np.float32))
        
        # Convert back to int16
        output_samples = np.clip(output_samples, -32768, 32767).astype(np.int16)
        
        return output_samples.tobytes()
        
    except Exception as e:
        logger.error(f"Error in PCM16 resampling: {e}")
        return pcm_data

def calculate_audio_level(audio_data: bytes, format: int = AudioFormat.PCM16) -> float:
    """Calculate audio level (RMS)"""
    try:
        # Convert to PCM16 if needed
        pcm_data = audio_data
        if format == AudioFormat.PCMU:
            pcm_data = pcmu_to_pcm16(audio_data)
        
        if len(pcm_data) % 2 != 0:
            pcm_data = pcm_data[:-1]
        
        if len(pcm_data) == 0:
            return 0.0
        
        # Calculate RMS
        samples = np.frombuffer(pcm_data, dtype=np.int16)
        rms = np.sqrt(np.mean(samples.astype(np.float32) ** 2))
        
        # Normalize to 0-1 range
        return min(rms / 32768.0, 1.0)
        
    except Exception as e:
        logger.error(f"Error calculating audio level: {e}")
        return 0.0

def detect_silence(
    audio_data: bytes,
    threshold: float = 0.01,
    format: int = AudioFormat.PCM16
) -> bool:
    """Detect if audio is silent"""
    try:
        level = calculate_audio_level(audio_data, format)
        return level < threshold
        
    except Exception as e:
        logger.error(f"Error detecting silence: {e}")
        return False

def mix_audio(audio_streams: List[bytes], format: int = AudioFormat.PCM16) -> bytes:
    """Mix multiple audio streams"""
    try:
        if not audio_streams:
            return b''
        
        if len(audio_streams) == 1:
            return audio_streams[0]
        
        # Convert all to PCM16
        pcm_streams = []
        for audio in audio_streams:
            if format == AudioFormat.PCMU:
                pcm_data = pcmu_to_pcm16(audio)
            else:
                pcm_data = audio
            
            if len(pcm_data) % 2 != 0:
                pcm_data = pcm_data[:-1]
            
            if pcm_data:
                pcm_streams.append(np.frombuffer(pcm_data, dtype=np.int16))
        
        if not pcm_streams:
            return b''
        
        # Find minimum length
        min_length = min(len(stream) for stream in pcm_streams)
        
        # Mix streams
        mixed = np.zeros(min_length, dtype=np.float32)
        for stream in pcm_streams:
            mixed += stream[:min_length].astype(np.float32)
        
        # Average and clip
        mixed = mixed / len(pcm_streams)
        mixed = np.clip(mixed, -32768, 32767).astype(np.int16)
        
        # Convert back to original format if needed
        result = mixed.tobytes()
        if format == AudioFormat.PCMU:
            result = pcm16_to_pcmu(result)
        
        return result
        
    except Exception as e:
        logger.error(f"Error mixing audio: {e}")
        return audio_streams[0] if audio_streams else b''

def apply_gain(audio_data: bytes, gain_db: float, format: int = AudioFormat.PCM16) -> bytes:
    """Apply gain to audio data"""
    try:
        if gain_db == 0.0:
            return audio_data
        
        # Convert to PCM16
        pcm_data = audio_data
        if format == AudioFormat.PCMU:
            pcm_data = pcmu_to_pcm16(audio_data)
        
        if len(pcm_data) % 2 != 0:
            pcm_data = pcm_data[:-1]
        
        if len(pcm_data) == 0:
            return audio_data
        
        # Apply gain
        samples = np.frombuffer(pcm_data, dtype=np.int16)
        gain_linear = 10.0 ** (gain_db / 20.0)
        
        gained_samples = samples.astype(np.float32) * gain_linear
        gained_samples = np.clip(gained_samples, -32768, 32767).astype(np.int16)
        
        # Convert back to original format
        result = gained_samples.tobytes()
        if format == AudioFormat.PCMU:
            result = pcm16_to_pcmu(result)
        
        return result
        
    except Exception as e:
        logger.error(f"Error applying gain: {e}")
        return audio_data

def generate_tone(
    frequency: float,
    duration_ms: int,
    sample_rate: int = 8000,
    amplitude: float = 0.5,
    format: int = AudioFormat.PCM16
) -> bytes:
    """Generate audio tone"""
    try:
        num_samples = int(sample_rate * duration_ms / 1000.0)
        t = np.linspace(0, duration_ms / 1000.0, num_samples, False)
        
        # Generate sine wave
        wave = amplitude * np.sin(2 * np.pi * frequency * t)
        
        # Convert to int16
        samples = (wave * 32767).astype(np.int16)
        
        # Convert to desired format
        result = samples.tobytes()
        if format == AudioFormat.PCMU:
            result = pcm16_to_pcmu(result)
        
        return result
        
    except Exception as e:
        logger.error(f"Error generating tone: {e}")
        return b''

def validate_audio_data(
    audio_data: bytes,
    expected_format: int = AudioFormat.PCM16,
    expected_rate: int = 8000,
    min_duration_ms: int = 10
) -> dict:
    """Validate audio data"""
    try:
        result = {
            'valid': True,
            'format': expected_format,
            'size_bytes': len(audio_data),
            'errors': []
        }
        
        if len(audio_data) == 0:
            result['valid'] = False
            result['errors'].append('Empty audio data')
            return result
        
        # Format-specific validation
        if expected_format == AudioFormat.PCM16:
            if len(audio_data) % 2 != 0:
                result['errors'].append('PCM16 data length not even')
            
            samples = len(audio_data) // 2
            duration_ms = (samples / expected_rate) * 1000
            
        else:  # PCMU/PCMA
            samples = len(audio_data)
            duration_ms = (samples / expected_rate) * 1000
        
        result['samples'] = samples
        result['duration_ms'] = duration_ms
        
        # Check minimum duration
        if duration_ms < min_duration_ms:
            result['errors'].append(f'Duration {duration_ms:.1f}ms below minimum {min_duration_ms}ms')
        
        # Calculate audio level
        level = calculate_audio_level(audio_data, expected_format)
        result['audio_level'] = level
        
        if level == 0.0:
            result['errors'].append('Audio appears to be silent')
        
        # Set validity
        result['valid'] = len(result['errors']) == 0
        
        return result
        
    except Exception as e:
        return {
            'valid': False,
            'error': str(e),
            'size_bytes': len(audio_data)
        }