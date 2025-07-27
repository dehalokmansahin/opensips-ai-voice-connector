"""
Audio codec implementations for RTP stream processing
PCMU/PCM conversion for telephony audio compatibility
"""

import logging
import numpy as np
from typing import Optional, Tuple
import struct

logger = logging.getLogger(__name__)

class PCMUCodec:
    """
    PCMU (G.711 μ-law) codec implementation
    Handles conversion between PCMU and PCM formats
    """
    
    # μ-law compression constants
    BIAS = 0x84
    CLIP = 32635
    
    # Pre-computed μ-law encode table for faster conversion
    _encode_table = None
    _decode_table = None
    
    def __init__(self):
        self._initialize_tables()
        logger.info("PCMUCodec initialized with μ-law tables")
    
    @classmethod
    def _initialize_tables(cls):
        """Initialize μ-law encoding/decoding tables"""
        if cls._encode_table is not None:
            return
        
        # Create encode table (PCM to μ-law)
        cls._encode_table = np.zeros(65536, dtype=np.uint8)
        
        for i in range(65536):
            # Convert 16-bit index to signed PCM sample
            pcm_sample = i - 32768 if i >= 32768 else i
            cls._encode_table[i] = cls._linear_to_ulaw(pcm_sample)
        
        # Create decode table (μ-law to PCM)
        cls._decode_table = np.zeros(256, dtype=np.int16)
        
        for i in range(256):
            cls._decode_table[i] = cls._ulaw_to_linear(i)
    
    @staticmethod
    def _linear_to_ulaw(pcm_sample: int) -> int:
        """Convert linear PCM sample to μ-law"""
        # Get sign and magnitude
        sign = 0x80 if pcm_sample < 0 else 0
        magnitude = abs(pcm_sample)
        
        # Apply bias and clipping
        magnitude = min(magnitude + PCMUCodec.BIAS, PCMUCodec.CLIP)
        
        # Find the segment (exponent)
        if magnitude >= 256:
            exponent = 7
            while exponent > 0:
                if magnitude >= (256 << (exponent - 1)):
                    break
                exponent -= 1
        else:
            exponent = 0
        
        # Calculate mantissa
        if exponent == 0:
            mantissa = (magnitude >> 4) & 0x0F
        else:
            mantissa = ((magnitude >> (exponent + 3)) & 0x0F)
        
        # Combine sign, exponent, and mantissa
        ulaw_byte = sign | (exponent << 4) | mantissa
        
        # Apply μ-law inversion
        return ulaw_byte ^ 0xFF
    
    @staticmethod
    def _ulaw_to_linear(ulaw_byte: int) -> int:
        """Convert μ-law byte to linear PCM sample"""
        # Remove μ-law inversion
        ulaw_byte ^= 0xFF
        
        # Extract components
        sign = ulaw_byte & 0x80
        exponent = (ulaw_byte >> 4) & 0x07
        mantissa = ulaw_byte & 0x0F
        
        # Calculate linear value
        if exponent == 0:
            linear = (mantissa << 4) + 8
        else:
            linear = ((mantissa << 4) + 0x108) << (exponent - 1)
        
        # Remove bias
        linear -= PCMUCodec.BIAS
        
        # Apply sign
        return -linear if sign else linear
    
    def encode_pcm_to_pcmu(self, pcm_data: bytes) -> bytes:
        """
        Convert PCM audio data to PCMU format
        
        Args:
            pcm_data: 16-bit PCM audio data
            
        Returns:
            PCMU encoded audio data (8-bit μ-law)
        """
        try:
            if len(pcm_data) == 0:
                return b''
            
            # Ensure even number of bytes for 16-bit samples
            if len(pcm_data) % 2 != 0:
                logger.warning("PCM data length not even, truncating last byte")
                pcm_data = pcm_data[:-1]
            
            # Convert to numpy array of 16-bit samples
            pcm_samples = np.frombuffer(pcm_data, dtype=np.int16)
            
            # Use lookup table for fast conversion
            # Convert signed int16 to unsigned uint16 indices
            indices = pcm_samples.astype(np.int32) + 32768
            indices = np.clip(indices, 0, 65535).astype(np.uint16)
            
            # Perform lookup
            ulaw_bytes = self._encode_table[indices]
            
            return ulaw_bytes.tobytes()
            
        except Exception as e:
            logger.error(f"PCM to PCMU encoding error: {e}")
            return b''
    
    def decode_pcmu_to_pcm(self, pcmu_data: bytes) -> bytes:
        """
        Convert PCMU audio data to PCM format
        
        Args:
            pcmu_data: PCMU encoded audio data (8-bit μ-law)
            
        Returns:
            16-bit PCM audio data
        """
        try:
            if len(pcmu_data) == 0:
                return b''
            
            # Convert to numpy array of μ-law bytes
            ulaw_bytes = np.frombuffer(pcmu_data, dtype=np.uint8)
            
            # Use lookup table for fast conversion
            pcm_samples = self._decode_table[ulaw_bytes]
            
            return pcm_samples.tobytes()
            
        except Exception as e:
            logger.error(f"PCMU to PCM decoding error: {e}")
            return b''
    
    def validate_pcmu_format(self, pcmu_data: bytes, expected_frame_size: int = 160) -> dict:
        """
        Validate PCMU audio format
        
        Args:
            pcmu_data: PCMU data to validate
            expected_frame_size: Expected frame size in bytes
            
        Returns:
            Validation result dictionary
        """
        try:
            if not pcmu_data:
                return {
                    'valid': False,
                    'error': 'Empty PCMU data'
                }
            
            frame_size = len(pcmu_data)
            
            # Check frame size
            if frame_size != expected_frame_size:
                return {
                    'valid': False,
                    'error': f'Invalid frame size: {frame_size}, expected: {expected_frame_size}'
                }
            
            # Basic μ-law validation - check for reasonable distribution
            ulaw_bytes = np.frombuffer(pcmu_data, dtype=np.uint8)
            
            # μ-law should have good distribution across values
            unique_values = len(np.unique(ulaw_bytes))
            if unique_values < 2:
                return {
                    'valid': False,
                    'error': 'PCMU data appears to be constant (likely silence or invalid)'
                }
            
            # Calculate basic statistics
            mean_value = np.mean(ulaw_bytes)
            std_value = np.std(ulaw_bytes)
            
            return {
                'valid': True,
                'frame_size': frame_size,
                'unique_values': unique_values,
                'mean': float(mean_value),
                'std': float(std_value),
                'format': 'PCMU'
            }
            
        except Exception as e:
            return {
                'valid': False,
                'error': f'Validation error: {str(e)}'
            }
    
    def validate_pcm_format(self, pcm_data: bytes, expected_sample_rate: int = 8000) -> dict:
        """
        Validate PCM audio format
        
        Args:
            pcm_data: PCM data to validate
            expected_sample_rate: Expected sample rate
            
        Returns:
            Validation result dictionary
        """
        try:
            if not pcm_data:
                return {
                    'valid': False,
                    'error': 'Empty PCM data'
                }
            
            # Check for 16-bit alignment
            if len(pcm_data) % 2 != 0:
                return {
                    'valid': False,
                    'error': 'PCM data length not aligned to 16-bit samples'
                }
            
            # Convert to samples
            pcm_samples = np.frombuffer(pcm_data, dtype=np.int16)
            
            if len(pcm_samples) == 0:
                return {
                    'valid': False,
                    'error': 'No PCM samples found'
                }
            
            # Calculate duration
            duration_ms = (len(pcm_samples) / expected_sample_rate) * 1000
            
            # Calculate audio statistics
            max_amplitude = np.max(np.abs(pcm_samples))
            rms = np.sqrt(np.mean(pcm_samples.astype(np.float32) ** 2))
            
            return {
                'valid': True,
                'sample_count': len(pcm_samples),
                'duration_ms': float(duration_ms),
                'max_amplitude': int(max_amplitude),
                'rms': float(rms),
                'sample_rate': expected_sample_rate,
                'format': 'PCM16'
            }
            
        except Exception as e:
            return {
                'valid': False,
                'error': f'Validation error: {str(e)}'
            }
    
    def resample_pcm(
        self, 
        pcm_data: bytes, 
        input_rate: int, 
        output_rate: int
    ) -> bytes:
        """
        Simple PCM resampling (basic linear interpolation)
        For production use, consider using librosa or similar
        
        Args:
            pcm_data: Input PCM data
            input_rate: Input sample rate
            output_rate: Output sample rate
            
        Returns:
            Resampled PCM data
        """
        try:
            if input_rate == output_rate:
                return pcm_data
            
            if len(pcm_data) % 2 != 0:
                pcm_data = pcm_data[:-1]
            
            # Convert to samples
            input_samples = np.frombuffer(pcm_data, dtype=np.int16)
            
            if len(input_samples) == 0:
                return b''
            
            # Calculate resampling ratio
            ratio = output_rate / input_rate
            output_length = int(len(input_samples) * ratio)
            
            # Create output indices
            output_indices = np.linspace(0, len(input_samples) - 1, output_length)
            
            # Linear interpolation
            output_samples = np.interp(output_indices, np.arange(len(input_samples)), input_samples)
            
            # Convert back to int16
            output_samples = np.round(output_samples).astype(np.int16)
            
            return output_samples.tobytes()
            
        except Exception as e:
            logger.error(f"PCM resampling error: {e}")
            return pcm_data
    
    def generate_pcmu_silence(self, frame_count: int = 1, frame_size: int = 160) -> bytes:
        """
        Generate PCMU silence frames
        
        Args:
            frame_count: Number of silence frames
            frame_size: Size of each frame in bytes
            
        Returns:
            PCMU silence data
        """
        # PCMU silence value (μ-law encoded zero)
        silence_byte = 0x7F
        total_size = frame_count * frame_size
        
        return bytes([silence_byte] * total_size)
    
    def analyze_audio_quality(self, pcm_data: bytes, sample_rate: int = 8000) -> dict:
        """
        Analyze PCM audio quality metrics
        
        Args:
            pcm_data: PCM audio data
            sample_rate: Sample rate
            
        Returns:
            Quality analysis results
        """
        try:
            if len(pcm_data) % 2 != 0:
                pcm_data = pcm_data[:-1]
            
            pcm_samples = np.frombuffer(pcm_data, dtype=np.int16)
            
            if len(pcm_samples) == 0:
                return {'valid': False, 'error': 'No samples'}
            
            # Basic quality metrics
            max_amplitude = np.max(np.abs(pcm_samples))
            rms = np.sqrt(np.mean(pcm_samples.astype(np.float32) ** 2))
            snr_estimate = 20 * np.log10(rms / 1.0) if rms > 1.0 else -60  # Rough SNR estimate
            
            # Dynamic range
            dynamic_range = 20 * np.log10(max_amplitude / (rms + 1e-10))
            
            # Zero crossing rate (rough speech activity indicator)
            zero_crossings = np.sum(np.diff(np.sign(pcm_samples)) != 0)
            zcr = zero_crossings / len(pcm_samples)
            
            return {
                'valid': True,
                'max_amplitude': int(max_amplitude),
                'rms': float(rms),
                'snr_estimate_db': float(snr_estimate),
                'dynamic_range_db': float(dynamic_range),
                'zero_crossing_rate': float(zcr),
                'sample_count': len(pcm_samples),
                'duration_ms': (len(pcm_samples) / sample_rate) * 1000
            }
            
        except Exception as e:
            return {
                'valid': False,
                'error': f'Analysis error: {str(e)}'
            }