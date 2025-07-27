"""
OpenSIPS AI Voice Connector - Core Module
Clean microservices architecture with minimal dependencies

Version: 2.0.0 (New Architecture)
"""

from .main import OpenSIPSAIVoiceConnector

# Core components
from .config import Settings, OpenSIPSConfig, ServiceConfig, ServicesConfig, AudioConfig, LoggingConfig
from .opensips import OpenSIPSIntegration, CallInfo, OpenSIPSEventListener, SIPBackendListener, RTPTransport
from .grpc_clients import ServiceRegistry, ASRClient, LLMClient, TTSClient
from .bot import PipelineManager, ConversationSession, SessionState, SessionConfig
from .utils import setup_logging, get_logger, AudioFormat, find_free_port, get_local_ip

# Version info
__version__ = "2.0.0"
__architecture__ = "microservices"
__description__ = "OpenSIPS AI Voice Connector - Clean Architecture"

__all__ = [
    # Main application
    "OpenSIPSAIVoiceConnector",
    
    # Configuration
    "Settings",
    "OpenSIPSConfig", 
    "ServiceConfig",
    "ServicesConfig",
    "AudioConfig",
    "LoggingConfig",
    
    # OpenSIPS integration
    "OpenSIPSIntegration",
    "CallInfo",
    "OpenSIPSEventListener",
    "SIPBackendListener", 
    "RTPTransport",
    
    # gRPC clients
    "ServiceRegistry",
    "ASRClient",
    "LLMClient",
    "TTSClient",
    
    # Bot pipeline
    "PipelineManager",
    "ConversationSession",
    "SessionState",
    "SessionConfig",
    
    # Utilities
    "setup_logging",
    "get_logger",
    "AudioFormat",
    "find_free_port",
    "get_local_ip",
    
    # Metadata
    "__version__",
    "__architecture__",
    "__description__",
]