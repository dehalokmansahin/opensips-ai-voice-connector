"""gRPC clients module for microservices communication"""

from .service_registry import ServiceRegistry
from .asr_client import ASRClient, StreamingSession
from .tts_client import TTSClient, TTSQueue, SentenceFlushAggregator
from .intent_rest_client import IntentClient, IntentRESTClient, IntentRecognitionManager

__all__ = [
    "ServiceRegistry",
    "ASRClient",
    "StreamingSession", 
    "TTSClient",
    "TTSQueue",
    "SentenceFlushAggregator",
    "IntentClient",
    "IntentRESTClient",
    "IntentRecognitionManager",
]