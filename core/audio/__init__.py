"""
Audio processing module for OpenSIPS AI Voice Connector
Handles RTP audio stream processing, codec conversion, and buffering
"""

from .streaming import RTPAudioStreamer, RTPSessionConfig
from .codecs import PCMUCodec
from .buffering import JitterBuffer, EventReplayBuffer, BufferedAudioPacket
from .event_bus import AudioEventBus, AudioEventType, AudioEvent
from .rtp_basic import RTPPacket, parse_rtp_packet, serialize_rtp_packet
from .threading import (
    MultiThreadedRTPProcessor, AudioThreadPool, LockFreeQueue, 
    ThreadMetrics, ThreadPriority
)

__all__ = [
    'RTPAudioStreamer',
    'RTPSessionConfig',
    'PCMUCodec', 
    'JitterBuffer',
    'EventReplayBuffer',
    'BufferedAudioPacket',
    'AudioEventBus',
    'AudioEventType',
    'AudioEvent',
    'RTPPacket',
    'parse_rtp_packet',
    'serialize_rtp_packet',
    'MultiThreadedRTPProcessor',
    'AudioThreadPool',
    'LockFreeQueue',
    'ThreadMetrics',
    'ThreadPriority'
]