"""
Minimal Pipecat Frames - Core frame definitions for OpenSIPS AI Voice Connector
Extracted only essential frames from pipecat framework
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Sequence
import time

def obj_id() -> int:
    """Generate unique object ID"""
    return int(time.time() * 1000000) % 1000000

def obj_count() -> int:
    """Simple object counter"""
    if not hasattr(obj_count, 'counter'):
        obj_count.counter = 0
    obj_count.counter += 1
    return obj_count.counter

@dataclass
class Frame:
    """Base frame class for all frames in the pipeline"""
    id: int = field(init=False)
    name: str = field(init=False)
    pts: Optional[int] = field(default=None, init=False)
    metadata: Dict[str, Any] = field(default_factory=dict, init=False)

    def __post_init__(self):
        self.id = obj_id()
        self.name = f"{self.__class__.__name__}#{obj_count()}"

# ---- SYSTEM FRAMES ----

@dataclass
class StartFrame(Frame):
    """Signals the start of processing"""
    pass

@dataclass
class EndFrame(Frame):
    """Signals the end of processing"""
    pass

@dataclass
class CancelFrame(Frame):
    """Signals cancellation of processing"""
    pass

@dataclass
class ErrorFrame(Frame):
    """Represents an error condition"""
    error: str = ""

# ---- DATA FRAMES ----

@dataclass
class AudioRawFrame(Frame):
    """Raw audio data frame"""
    audio: bytes
    sample_rate: int
    num_channels: int = 1

@dataclass
class TextFrame(Frame):
    """Text data frame"""
    text: str = ""

# ---- STT FRAMES ----

@dataclass
class TranscriptionFrame(Frame):
    """Final transcription result"""
    text: str = ""
    user_id: str = ""
    timestamp: str = ""
    language: str = "tr"

@dataclass
class InterimTranscriptionFrame(Frame):
    """Partial transcription result"""
    text: str = ""
    user_id: str = ""
    timestamp: str = ""
    language: str = "tr"

# ---- VAD FRAMES ----

@dataclass
class UserStartedSpeakingFrame(Frame):
    """User started speaking"""
    pass

@dataclass
class UserStoppedSpeakingFrame(Frame):
    """User stopped speaking"""
    pass

@dataclass
class VADUserStartedSpeakingFrame(Frame):
    """Raw VAD detection: user started speaking"""
    pass

@dataclass
class VADUserStoppedSpeakingFrame(Frame):
    """Raw VAD detection: user stopped speaking"""
    pass

# ---- LLM FRAMES ----

@dataclass
class LLMMessagesFrame(Frame):
    """Messages for LLM processing"""
    messages: List[Dict[str, Any]]

@dataclass
class LLMFullResponseStartFrame(Frame):
    """Start of LLM response"""
    pass

@dataclass
class LLMFullResponseEndFrame(Frame):
    """End of LLM response"""
    pass

@dataclass
class LLMTextFrame(Frame):
    """LLM text token"""
    text: str = ""

# ---- TTS FRAMES ----

@dataclass
class TTSAudioRawFrame(Frame):
    """TTS generated audio"""
    audio: bytes
    sample_rate: int
    num_channels: int = 1

@dataclass
class TTSStartedFrame(Frame):
    """TTS synthesis started"""
    pass

@dataclass
class TTSStoppedFrame(Frame):
    """TTS synthesis stopped"""
    pass

# ---- UTILITY FUNCTIONS ----

def is_control_frame(frame: Frame) -> bool:
    """Check if frame is a control frame"""
    return isinstance(frame, (StartFrame, EndFrame, CancelFrame, ErrorFrame))

def is_audio_frame(frame: Frame) -> bool:
    """Check if frame contains audio data"""
    return isinstance(frame, (AudioRawFrame, TTSAudioRawFrame))

def is_text_frame(frame: Frame) -> bool:
    """Check if frame contains text data"""
    return isinstance(frame, (TextFrame, TranscriptionFrame, InterimTranscriptionFrame, LLMTextFrame))