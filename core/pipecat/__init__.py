"""
Minimal Pipecat Framework for OpenSIPS AI Voice Connector
Essential components extracted from full pipecat framework
"""

# Import core components
from .frames import (
    Frame,
    StartFrame,
    EndFrame,
    ErrorFrame,
    AudioRawFrame,
    TextFrame,
    TranscriptionFrame,
    InterimTranscriptionFrame,
    LLMMessagesFrame,
    LLMTextFrame,
    TTSAudioRawFrame,
)

from .pipeline import (
    FrameProcessor,
    Pipeline,
    AsyncFrameProcessor,
    AudioFrameProcessor,
    TextFrameProcessor,
)

from .audio import (
    audio_resample,
    calculate_audio_volume,
    is_audio_silent,
    merge_audio_chunks,
    generate_silence,
    validate_audio_format,
)

__version__ = "0.1.0"
__all__ = [
    # Frames
    "Frame",
    "StartFrame", 
    "EndFrame",
    "ErrorFrame",
    "AudioRawFrame",
    "TextFrame",
    "TranscriptionFrame",
    "InterimTranscriptionFrame",
    "LLMMessagesFrame",
    "LLMTextFrame",
    "TTSAudioRawFrame",
    
    # Pipeline
    "FrameProcessor",
    "Pipeline",
    "AsyncFrameProcessor", 
    "AudioFrameProcessor",
    "TextFrameProcessor",
    
    # Audio
    "audio_resample",
    "calculate_audio_volume",
    "is_audio_silent", 
    "merge_audio_chunks",
    "generate_silence",
    "validate_audio_format",
]