"""
DTMF Timing Configuration and Sequence Management
Controls timing parameters for DTMF tone generation
"""

from dataclasses import dataclass
from typing import List, Optional

@dataclass
class DTMFTiming:
    """DTMF timing configuration parameters"""
    tone_duration_ms: int = 100      # Duration of each DTMF tone
    pause_duration_ms: int = 100     # Pause between tones
    pre_sequence_delay_ms: int = 500 # Delay before starting sequence
    post_sequence_delay_ms: int = 200 # Delay after completing sequence
    
    def validate(self) -> bool:
        """Validate timing parameters"""
        # Minimum tone duration for reliable detection
        if self.tone_duration_ms < 40:
            return False
        
        # Maximum tone duration to avoid timeout
        if self.tone_duration_ms > 1000:
            return False
        
        # Minimum pause for tone separation
        if self.pause_duration_ms < 40:
            return False
        
        return True
    
    def get_sequence_duration(self, num_tones: int) -> int:
        """Calculate total duration for a sequence of tones"""
        if num_tones <= 0:
            return 0
        
        tone_time = num_tones * self.tone_duration_ms
        pause_time = (num_tones - 1) * self.pause_duration_ms
        
        return (self.pre_sequence_delay_ms + 
                tone_time + 
                pause_time + 
                self.post_sequence_delay_ms)

@dataclass
class DTMFSequence:
    """Represents a sequence of DTMF tones to be sent"""
    tones: str                      # String of tones (0-9, *, #, A-D)
    timing: DTMFTiming              # Timing configuration
    label: Optional[str] = None     # Optional label for logging
    
    def __post_init__(self):
        """Validate the DTMF sequence"""
        # Validate tones
        valid_tones = "0123456789*#ABCD"
        self.tones = self.tones.upper()
        
        for tone in self.tones:
            if tone not in valid_tones:
                raise ValueError(f"Invalid DTMF tone: {tone}")
    
    def get_tone_list(self) -> List[str]:
        """Get list of individual tones"""
        return list(self.tones)
    
    def get_duration_ms(self) -> int:
        """Get total duration of the sequence"""
        return self.timing.get_sequence_duration(len(self.tones))
    
    def split_sequence(self, max_length: int = 10) -> List['DTMFSequence']:
        """Split long sequences into smaller chunks"""
        if len(self.tones) <= max_length:
            return [self]
        
        sequences = []
        for i in range(0, len(self.tones), max_length):
            chunk = self.tones[i:i + max_length]
            sequences.append(DTMFSequence(
                tones=chunk,
                timing=self.timing,
                label=f"{self.label}_part{i//max_length + 1}" if self.label else None
            ))
        
        return sequences

# Standard timing presets
class DTMFPresets:
    """Common DTMF timing presets for different IVR systems"""
    
    # Fast timing for modern IVR systems
    FAST = DTMFTiming(
        tone_duration_ms=60,
        pause_duration_ms=60,
        pre_sequence_delay_ms=200,
        post_sequence_delay_ms=100
    )
    
    # Standard timing for most IVR systems
    STANDARD = DTMFTiming(
        tone_duration_ms=100,
        pause_duration_ms=100,
        pre_sequence_delay_ms=500,
        post_sequence_delay_ms=200
    )
    
    # Slow timing for older or sensitive IVR systems
    SLOW = DTMFTiming(
        tone_duration_ms=150,
        pause_duration_ms=150,
        pre_sequence_delay_ms=800,
        post_sequence_delay_ms=300
    )
    
    # Extra slow timing for very old systems
    LEGACY = DTMFTiming(
        tone_duration_ms=200,
        pause_duration_ms=200,
        pre_sequence_delay_ms=1000,
        post_sequence_delay_ms=500
    )