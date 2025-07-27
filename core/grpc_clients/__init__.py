"""gRPC clients module for microservices communication"""

from .service_registry import ServiceRegistry
from .asr_client import ASRClient, StreamingSession
from .llm_client import LLMClient, ConversationManager
from .tts_client import TTSClient, TTSQueue, SentenceFlushAggregator

__all__ = [
    "ServiceRegistry",
    "ASRClient",
    "StreamingSession", 
    "LLMClient",
    "ConversationManager",
    "TTSClient",
    "TTSQueue",
    "SentenceFlushAggregator",
]