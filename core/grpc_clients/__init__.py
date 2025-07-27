"""gRPC clients module for microservices communication"""

from .service_registry import ServiceRegistry
from .asr_client import ASRClient, StreamingSession
from .tts_client import TTSClient, TTSQueue, SentenceFlushAggregator

__all__ = [
    "ServiceRegistry",
    "ASRClient",
    "StreamingSession", 
    "TTSClient",
    "TTSQueue",
    "SentenceFlushAggregator",
]