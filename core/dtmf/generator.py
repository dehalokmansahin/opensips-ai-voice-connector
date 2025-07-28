"""
DTMF Tone Generator for IVR Test Automation
Generates and injects DTMF tones into RTP streams
"""

import asyncio
import logging
import numpy as np
from typing import Dict, Tuple, Optional, List, Any
from dataclasses import dataclass

from .timing import DTMFTiming, DTMFSequence, DTMFPresets

logger = logging.getLogger(__name__)

@dataclass
class DTMFTone:
    """Represents a single DTMF tone with frequency components"""
    digit: str
    low_freq: int
    high_freq: int
    
    def __str__(self):
        return f"DTMF({self.digit}): {self.low_freq}Hz + {self.high_freq}Hz"

class DTMFGenerator:
    """Generates DTMF tones for IVR navigation"""
    
    # DTMF frequency mapping (ITU-T Q.23)
    DTMF_FREQUENCIES = {
        '1': (697, 1209), '2': (697, 1336), '3': (697, 1477), 'A': (697, 1633),
        '4': (770, 1209), '5': (770, 1336), '6': (770, 1477), 'B': (770, 1633),
        '7': (852, 1209), '8': (852, 1336), '9': (852, 1477), 'C': (852, 1633),
        '*': (941, 1209), '0': (941, 1336), '#': (941, 1477), 'D': (941, 1633),
    }
    
    def __init__(self, sample_rate: int = 8000):
        """
        Initialize DTMF generator
        
        Args:
            sample_rate: Audio sample rate (8000 Hz for telephony)
        """
        self.sample_rate = sample_rate
        self.amplitude = 0.5  # Amplitude for generated tones (0-1)
        self._tone_cache: Dict[str, np.ndarray] = {}
        
        # Pre-generate common tones for performance
        self._pregenerate_tones()
    
    def _pregenerate_tones(self):
        """Pre-generate commonly used DTMF tones"""
        common_tones = "0123456789*#"
        standard_timing = DTMFPresets.STANDARD
        
        for tone in common_tones:
            self._generate_tone_audio(tone, standard_timing.tone_duration_ms)
    
    def _generate_tone_audio(self, digit: str, duration_ms: int) -> np.ndarray:
        """
        Generate audio samples for a single DTMF tone
        
        Args:
            digit: DTMF digit (0-9, *, #, A-D)
            duration_ms: Duration in milliseconds
            
        Returns:
            Audio samples as numpy array
        """
        # Check cache first
        cache_key = f"{digit}_{duration_ms}"
        if cache_key in self._tone_cache:
            return self._tone_cache[cache_key]
        
        # Get frequencies for the digit
        if digit not in self.DTMF_FREQUENCIES:
            raise ValueError(f"Invalid DTMF digit: {digit}")
        
        low_freq, high_freq = self.DTMF_FREQUENCIES[digit]
        
        # Calculate number of samples
        num_samples = int(self.sample_rate * duration_ms / 1000)
        
        # Generate time array
        t = np.arange(num_samples) / self.sample_rate
        
        # Generate dual-tone signal
        low_tone = np.sin(2 * np.pi * low_freq * t)
        high_tone = np.sin(2 * np.pi * high_freq * t)
        
        # Combine tones with equal amplitude
        signal = self.amplitude * (low_tone + high_tone) / 2
        
        # Apply fade-in and fade-out to reduce clicking
        fade_samples = min(int(self.sample_rate * 0.005), num_samples // 4)  # 5ms fade
        if fade_samples > 0:
            fade_in = np.linspace(0, 1, fade_samples)
            fade_out = np.linspace(1, 0, fade_samples)
            signal[:fade_samples] *= fade_in
            signal[-fade_samples:] *= fade_out
        
        # Convert to 16-bit PCM
        pcm_signal = np.int16(signal * 32767)
        
        # Cache the generated tone
        self._tone_cache[cache_key] = pcm_signal
        
        return pcm_signal
    
    def _generate_silence(self, duration_ms: int) -> np.ndarray:
        """Generate silence (zeros) for specified duration"""
        num_samples = int(self.sample_rate * duration_ms / 1000)
        return np.zeros(num_samples, dtype=np.int16)
    
    async def generate_sequence(self, sequence: DTMFSequence) -> np.ndarray:
        """
        Generate audio for a complete DTMF sequence
        
        Args:
            sequence: DTMF sequence configuration
            
        Returns:
            Complete audio signal as numpy array
        """
        if not sequence.timing.validate():
            raise ValueError("Invalid DTMF timing parameters")
        
        logger.info(f"Generating DTMF sequence: {sequence.tones} "
                   f"(label: {sequence.label or 'none'})")
        
        audio_segments = []
        
        # Pre-sequence delay
        if sequence.timing.pre_sequence_delay_ms > 0:
            audio_segments.append(
                self._generate_silence(sequence.timing.pre_sequence_delay_ms)
            )
        
        # Generate each tone
        tones = sequence.get_tone_list()
        for i, tone in enumerate(tones):
            # Generate tone
            tone_audio = self._generate_tone_audio(
                tone, 
                sequence.timing.tone_duration_ms
            )
            audio_segments.append(tone_audio)
            
            # Add pause between tones (except after last tone)
            if i < len(tones) - 1 and sequence.timing.pause_duration_ms > 0:
                audio_segments.append(
                    self._generate_silence(sequence.timing.pause_duration_ms)
                )
        
        # Post-sequence delay
        if sequence.timing.post_sequence_delay_ms > 0:
            audio_segments.append(
                self._generate_silence(sequence.timing.post_sequence_delay_ms)
            )
        
        # Concatenate all segments
        complete_audio = np.concatenate(audio_segments)
        
        logger.debug(f"Generated {len(complete_audio)} samples "
                    f"({len(complete_audio) / self.sample_rate:.2f}s) "
                    f"for sequence: {sequence.tones}")
        
        return complete_audio
    
    async def send_dtmf_sequence(self, 
                               call_id: str, 
                               sequence: DTMFSequence,
                               rtp_transport: Optional[Any] = None) -> bool:
        """
        Send DTMF sequence through RTP transport
        
        Args:
            call_id: Call identifier
            sequence: DTMF sequence to send
            rtp_transport: RTP transport instance (optional)
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Generate audio for the sequence
            audio = await self.generate_sequence(sequence)
            
            # TODO: Integrate with actual RTP transport
            # For now, simulate sending
            logger.info(f"Sending DTMF sequence '{sequence.tones}' for call {call_id}")
            
            # Simulate transmission delay
            duration_s = len(audio) / self.sample_rate
            await asyncio.sleep(duration_s)
            
            logger.info(f"DTMF sequence '{sequence.tones}' sent successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to send DTMF sequence: {e}")
            return False
    
    async def send_single_tone(self, 
                             call_id: str, 
                             tone: str, 
                             duration_ms: int = 100) -> bool:
        """
        Send a single DTMF tone
        
        Args:
            call_id: Call identifier
            tone: Single DTMF digit
            duration_ms: Tone duration in milliseconds
            
        Returns:
            True if successful, False otherwise
        """
        timing = DTMFTiming(
            tone_duration_ms=duration_ms,
            pause_duration_ms=0,
            pre_sequence_delay_ms=0,
            post_sequence_delay_ms=0
        )
        
        sequence = DTMFSequence(tones=tone, timing=timing)
        return await self.send_dtmf_sequence(call_id, sequence)
    
    def get_tone_info(self, digit: str) -> DTMFTone:
        """Get frequency information for a DTMF digit"""
        if digit not in self.DTMF_FREQUENCIES:
            raise ValueError(f"Invalid DTMF digit: {digit}")
        
        low_freq, high_freq = self.DTMF_FREQUENCIES[digit]
        return DTMFTone(digit=digit, low_freq=low_freq, high_freq=high_freq)
    
    def validate_sequence(self, sequence: str) -> Tuple[bool, Optional[str]]:
        """
        Validate a DTMF sequence string
        
        Args:
            sequence: String of DTMF digits
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        if not sequence:
            return False, "Empty sequence"
        
        valid_digits = set(self.DTMF_FREQUENCIES.keys())
        invalid_digits = []
        
        for digit in sequence.upper():
            if digit not in valid_digits:
                invalid_digits.append(digit)
        
        if invalid_digits:
            return False, f"Invalid DTMF digits: {', '.join(invalid_digits)}"
        
        return True, None
    
    async def inject_dtmf_rfc2833(self, 
                                call_id: str,
                                digit: str,
                                duration_ms: int = 100) -> bool:
        """
        Inject DTMF using RFC 2833 (RTP events)
        
        This is an alternative method that sends DTMF as RTP events
        rather than in-band audio tones.
        
        Args:
            call_id: Call identifier
            digit: DTMF digit to send
            duration_ms: Duration of the tone
            
        Returns:
            True if successful, False otherwise
        """
        # TODO: Implement RFC 2833 DTMF injection
        logger.info(f"RFC 2833 DTMF injection not yet implemented")
        return False