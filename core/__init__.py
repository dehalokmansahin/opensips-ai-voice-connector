
"""
OpenSIPS AI Voice Connector - Core Module
Clean microservices architecture with minimal dependencies

Version: 2.0.0 (New Architecture)
"""

# Core components (avoid importing main.py to prevent circular imports)
from .config import Settings, OpenSIPSConfig, ServiceConfig, ServicesConfig, AudioConfig, LoggingConfig
from .opensips import OpenSIPSIntegration, CallInfo, OpenSIPSEventListener, SIPBackendListener, RTPTransport
from .grpc_clients import ServiceRegistry, ASRClient, TTSClient
from .grpc_clients.intent_rest_client import IntentClient, IntentRecognitionManager
from .bot import PipelineManager, ConversationSession, SessionState, SessionConfig
from .test_controller import TestExecutionManager, TestExecutionSession, TestStateManager, TestState, StepState
from .dtmf import DTMFGenerator, DTMFTone, DTMFTiming, DTMFSequence
from .utils import setup_logging, get_logger, AudioFormat, find_free_port, get_local_ip

# Version info
__version__ = "2.0.0"
__architecture__ = "microservices"
__description__ = "OpenSIPS AI Voice Connector - Clean Architecture"

__all__ = [
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
    "TTSClient",
    "IntentClient",
    "IntentRecognitionManager",
    
    # Bot pipeline (legacy - to be removed)
    "PipelineManager",
    "ConversationSession",
    "SessionState",
    "SessionConfig",
    
    # Test Controller (new)
    "TestExecutionManager",
    "TestExecutionSession",
    "TestStateManager",
    "TestState",
    "StepState",
    
    # DTMF Generation
    "DTMFGenerator",
    "DTMFTone",
    "DTMFTiming",
    "DTMFSequence",
    
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