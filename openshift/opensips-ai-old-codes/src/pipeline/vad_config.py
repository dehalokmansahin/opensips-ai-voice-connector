"""
VAD Configuration for Turkish Speech
Pipecat SileroVADAnalyzer inspired configuration
"""

from dataclasses import dataclass
from typing import Optional
import structlog

logger = structlog.get_logger()

@dataclass
class VADConfig:
    """VAD configuration parameters optimized for Turkish speech"""
    
    # Silero VAD inspired parameters
    min_speech_duration_ms: int = 250  # Minimum speech duration
    min_silence_duration_ms: int = 500  # Minimum silence for end detection
    speech_pad_start_ms: int = 100     # Padding before speech
    speech_pad_end_ms: int = 200       # Padding after speech
    
    # Audio analysis parameters
    frame_size_ms: int = 20            # 20ms frames
    sample_rate: int = 16000           # 16kHz
    volume_threshold: float = 0.01     # Volume threshold for activity
    
    # Turkish language optimizations
    turkish_optimized: bool = True
    long_pause_threshold_ms: int = 800  # Longer pauses for Turkish speech patterns
    
    def __post_init__(self):
        """Validate configuration"""
        if self.min_speech_duration_ms < 100:
            logger.warning("min_speech_duration_ms too low, setting to 100ms")
            self.min_speech_duration_ms = 100
            
        if self.min_silence_duration_ms < 200:
            logger.warning("min_silence_duration_ms too low, setting to 200ms") 
            self.min_silence_duration_ms = 200
            
        logger.info("VAD config initialized", 
                   min_speech_ms=self.min_speech_duration_ms,
                   min_silence_ms=self.min_silence_duration_ms,
                   turkish_optimized=self.turkish_optimized)

# Default config instance
DEFAULT_VAD_CONFIG = VADConfig() 