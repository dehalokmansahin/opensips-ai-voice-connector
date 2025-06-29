"""
Audio format conversion utilities - Düzeltilmiş versiyon
"""

from __future__ import annotations

import logging
from typing import Tuple, Union

import numpy as np
import struct

# Simple μ-law codec implementation 
# Constants for μ-law conversion
BIAS = 0x84
CLIP = 32635
SIGN_BIT = 0x80
QUANT_MASK = 0xf
NSEGS = 8
SEG_SHIFT = 4
SEG_MASK = 0x70

logger = logging.getLogger(__name__)

# Constants
ULAW_SAMPLE_RATE = 8000  # Hz
PCM_TARGET_SAMPLE_RATE = 16000  # Hz expected by pipeline

# G.711 μ-law decode tablosu
ULAW_DECODE_TABLE = np.array([
    -32124, -31100, -30076, -29052, -28028, -27004, -25980, -24956,
    -23932, -22908, -21884, -20860, -19836, -18812, -17788, -16764,
    -15996, -15484, -14972, -14460, -13948, -13436, -12924, -12412,
    -11900, -11388, -10876, -10364, -9852, -9340, -8828, -8316,
    -7932, -7676, -7420, -7164, -6908, -6652, -6396, -6140,
    -5884, -5628, -5372, -5116, -4860, -4604, -4348, -4092,
    -3900, -3772, -3644, -3516, -3388, -3260, -3132, -3004,
    -2876, -2748, -2620, -2492, -2364, -2236, -2108, -1980,
    -1884, -1820, -1756, -1692, -1628, -1564, -1500, -1436,
    -1372, -1308, -1244, -1180, -1116, -1052, -988, -924,
    -876, -844, -812, -780, -748, -716, -684, -652,
    -620, -588, -556, -524, -492, -460, -428, -396,
    -372, -356, -340, -324, -308, -292, -276, -260,
    -244, -228, -212, -196, -180, -164, -148, -132,
    -120, -112, -104, -96, -88, -80, -72, -64,
    -56, -48, -40, -32, -24, -16, -8, 0,
    32124, 31100, 30076, 29052, 28028, 27004, 25980, 24956,
    23932, 22908, 21884, 20860, 19836, 18812, 17788, 16764,
    15996, 15484, 14972, 14460, 13948, 13436, 12924, 12412,
    11900, 11388, 10876, 10364, 9852, 9340, 8828, 8316,
    7932, 7676, 7420, 7164, 6908, 6652, 6396, 6140,
    5884, 5628, 5372, 5116, 4860, 4604, 4348, 4092,
    3900, 3772, 3644, 3516, 3388, 3260, 3132, 3004,
    2876, 2748, 2620, 2492, 2364, 2236, 2108, 1980,
    1884, 1820, 1756, 1692, 1628, 1564, 1500, 1436,
    1372, 1308, 1244, 1180, 1116, 1052, 988, 924,
    876, 844, 812, 780, 748, 716, 684, 652,
    620, 588, 556, 524, 492, 460, 428, 396,
    372, 356, 340, 324, 308, 292, 276, 260,
    244, 228, 212, 196, 180, 164, 148, 132,
    120, 112, 104, 96, 88, 80, 72, 64,
    56, 48, 40, 32, 24, 16, 8, 0
], dtype=np.int16)

def pcmu_to_pcm16(pcmu_bytes: bytes) -> bytes:
    """
    PCMU (μ-law) formatını PCM 16-bit'e çevir
    
    Args:
        pcmu_bytes: PCMU encoded bytes (8-bit μ-law)
        
    Returns:
        PCM 16-bit signed bytes
    """
    if not pcmu_bytes:
        return b''
    
    try:
        # PCMU bytes'ı numpy array'e çevir
        pcmu_array = np.frombuffer(pcmu_bytes, dtype=np.uint8)
        
        # μ-law decode tablosunu kullanarak decode et
        pcm_array = ULAW_DECODE_TABLE[pcmu_array]
        
        # 16-bit signed PCM bytes'a çevir
        return pcm_array.astype(np.int16).tobytes()
        
    except Exception as e:
        logger.error(f"PCMU to PCM16 conversion error: {e}")
        return b''

def resample_pcm(pcm_bytes: bytes, input_rate: int, output_rate: int) -> bytes:
    """
    PCM ses verisini yeniden örnekle
    
    Args:
        pcm_bytes: PCM 16-bit bytes
        input_rate: Giriş sample rate (Hz)
        output_rate: Çıkış sample rate (Hz)
        
    Returns:
        Resampled PCM bytes
    """
    if not pcm_bytes or input_rate == output_rate:
        return pcm_bytes
    
    try:
        # Bytes'ı 16-bit signed array'e çevir
        pcm_array = np.frombuffer(pcm_bytes, dtype=np.int16)
        
        if len(pcm_array) == 0:
            return b''
        
        # Resampling ratio hesapla
        ratio = output_rate / input_rate
        output_length = int(len(pcm_array) * ratio)
        
        if output_length == 0:
            return b''
        
        # Linear interpolation ile resample
        input_indices = np.arange(len(pcm_array))
        output_indices = np.linspace(0, len(pcm_array) - 1, output_length)
        
        resampled = np.interp(output_indices, input_indices, pcm_array.astype(np.float32))
        
        # 16-bit signed'a geri çevir
        return resampled.astype(np.int16).tobytes()
        
    except Exception as e:
        logger.error(f"PCM resampling error: {e}")
        return pcm_bytes

def pcmu_to_pcm16k(pcmu_bytes: bytes) -> bytes:
    """
    PCMU (8kHz, 8-bit μ-law) → PCM (16kHz, 16-bit signed)
    
    Args:
        pcmu_bytes: PCMU encoded bytes
        
    Returns:
        PCM 16kHz 16-bit bytes
    """
    if not pcmu_bytes:
        return b''
    
    try:
        # PCMU → PCM 16-bit (8kHz)
        pcm_8k = pcmu_to_pcm16(pcmu_bytes)
        
        if not pcm_8k:
            return b''
        
        # 8kHz → 16kHz resample
        pcm_16k = resample_pcm(pcm_8k, 8000, 16000)
        
        return pcm_16k
        
    except Exception as e:
        logger.error("PCMU to PCM16k conversion error", error=str(e))
        return b''

# μ-law encoding function - direct implementation for better performance
def linear_to_ulaw(sample: int) -> int:
    """
    Convert linear PCM sample to μ-law
    
    Args:
        sample: 16-bit signed PCM sample
        
    Returns:
        8-bit μ-law sample
    """
    # Get the sign and absolute value
    sign = 0
    if sample < 0:
        sign = 0x80
        sample = -sample
    
    # Clip to avoid overflow
    if sample > CLIP:
        sample = CLIP
    
    # Add bias
    sample = sample + BIAS
    
    # Find segment
    seg = 8
    for i in range(8):
        if sample <= (0xFF << i):
            seg = i
            break
    
    if seg >= 8:
        return sign | 0x7F
    
    # Quantization
    result = sign | ((seg << 4) | ((sample >> (seg + 3)) & 0x0F))
    
    # Invert bits for μ-law
    return ~result & 0xFF

def pcm16_to_pcmu(pcm_bytes: bytes) -> bytes:
    """
    PCM 16-bit signed formatını PCMU (μ-law) formatına çevir
    
    Args:
        pcm_bytes: PCM 16-bit signed bytes
        
    Returns:
        PCMU encoded bytes (8-bit μ-law)
    """
    if not pcm_bytes:
        return b''
    
    try:
        # Bytes'ı 16-bit signed array'e çevir
        pcm_array = np.frombuffer(pcm_bytes, dtype=np.int16)
        
        if len(pcm_array) == 0:
            return b''
        
        # Convert each sample to μ-law
        ulaw_array = np.zeros(len(pcm_array), dtype=np.uint8)
        for i in range(len(pcm_array)):
            ulaw_array[i] = linear_to_ulaw(int(pcm_array[i]))
        
        return ulaw_array.tobytes()
        
    except Exception as e:
        logger.error(f"PCM16 to PCMU conversion error: {e}")
        return b''

def pcm16k_to_pcmu(pcm_bytes: bytes) -> bytes:
    """
    PCM (16kHz, 16-bit signed) → PCMU (8kHz, 8-bit μ-law)
    
    Args:
        pcm_bytes: PCM 16kHz 16-bit bytes
        
    Returns:
        PCMU encoded bytes (8-bit μ-law)
    """
    if not pcm_bytes:
        return b''
    
    try:
        # 16kHz → 8kHz resample
        pcm_8k = resample_pcm(pcm_bytes, 16000, 8000)
        
        if not pcm_8k:
            return b''
        
        # PCM 16-bit → PCMU
        pcmu = pcm16_to_pcmu(pcm_8k)
        
        return pcmu
        
    except Exception as e:
        logger.error("PCM16k to PCMU conversion error", error=str(e))
        return b''

def validate_pcm_format(pcm_bytes: bytes, expected_sample_rate: int = 16000) -> bool:
    """
    Validate PCM audio format
    
    Args:
        pcm_bytes: PCM bytes
        expected_sample_rate: Expected sample rate
        
    Returns:
        True if valid, False otherwise
    """
    if not pcm_bytes:
        return False
    
    # Check length is multiple of 2 (16-bit samples)
    if len(pcm_bytes) % 2 != 0:
        return False
    
    # Check minimum size (at least 10ms of audio)
    min_samples = expected_sample_rate // 100
    if len(pcm_bytes) < min_samples * 2:
        return False
    
    # Check for extreme values that might indicate format issues
    pcm_array = np.frombuffer(pcm_bytes, dtype=np.int16)
    if np.max(np.abs(pcm_array)) == 0:
        return False  # Silent audio
    
    return True 