"""
Global test configuration and fixtures for OpenSIPS AI Voice Connector
"""

import pytest
import asyncio
import sys
import tempfile
import shutil
from pathlib import Path
from unittest.mock import Mock, AsyncMock, MagicMock
from typing import Generator, AsyncGenerator, Dict, Any
import grpc
from grpc import aio as grpc_aio

# Add core module to path for testing
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "core"))
sys.path.insert(0, str(PROJECT_ROOT / "services" / "asr-service" / "src"))
sys.path.insert(0, str(PROJECT_ROOT / "services" / "llm-service" / "src"))
sys.path.insert(0, str(PROJECT_ROOT / "services" / "tts-service" / "src"))
sys.path.insert(0, str(PROJECT_ROOT / "shared" / "proto_generated"))


@pytest.fixture(scope="session")
def event_loop():
    """Create an event loop for the test session."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def temp_dir() -> Generator[Path, None, None]:
    """Create a temporary directory for test files."""
    temp_path = Path(tempfile.mkdtemp())
    yield temp_path
    shutil.rmtree(temp_path, ignore_errors=True)


@pytest.fixture
def mock_config() -> Dict[str, Any]:
    """Mock configuration for testing."""
    return {
        "grpc": {
            "asr_service": {
                "host": "localhost",
                "port": 50051
            },
            "llm_service": {
                "host": "localhost", 
                "port": 50052
            },
            "tts_service": {
                "host": "localhost",
                "port": 50053
            }
        },
        "audio": {
            "sample_rate": 16000,
            "chunk_size": 1024,
            "format": "LINEAR16"
        },
        "opensips": {
            "mi_host": "localhost",
            "mi_port": 8888,
            "event_socket": "udp:127.0.0.1:25060"
        }
    }


@pytest.fixture
def mock_logger():
    """Mock logger for testing."""
    logger = Mock()
    logger.info = Mock()
    logger.error = Mock()
    logger.warning = Mock()
    logger.debug = Mock()
    return logger


@pytest.fixture
def sample_audio_data() -> bytes:
    """Generate sample audio data for testing."""
    import numpy as np
    
    # Generate 1 second of 16kHz sine wave at 440Hz
    sample_rate = 16000
    duration = 1.0
    frequency = 440.0
    
    t = np.linspace(0, duration, int(sample_rate * duration), False)
    wave = np.sin(frequency * 2 * np.pi * t)
    
    # Convert to 16-bit integers
    audio_data = (wave * 32767).astype(np.int16)
    return audio_data.tobytes()


@pytest.fixture
def sample_text() -> str:
    """Sample text for testing."""
    return "Hello, this is a test message for the AI voice connector."


@pytest.fixture
def grpc_channel():
    """Mock gRPC channel for testing."""
    channel = Mock(spec=grpc_aio.Channel)
    channel.__aenter__ = AsyncMock(return_value=channel)
    channel.__aexit__ = AsyncMock(return_value=None)
    return channel


@pytest.fixture
def mock_asr_stub():
    """Mock ASR service stub."""
    stub = Mock()
    stub.HealthCheck = AsyncMock()
    stub.TranscribeAudio = AsyncMock()
    stub.StartRealtimeTranscription = AsyncMock()
    stub.StopRealtimeTranscription = AsyncMock()
    return stub


@pytest.fixture
def mock_llm_stub():
    """Mock LLM service stub."""
    stub = Mock()
    stub.HealthCheck = AsyncMock()
    stub.ProcessText = AsyncMock()
    stub.ProcessConversation = AsyncMock()
    return stub


@pytest.fixture
def mock_tts_stub():
    """Mock TTS service stub."""
    stub = Mock()
    stub.HealthCheck = AsyncMock()
    stub.SynthesizeText = AsyncMock()
    stub.GetVoices = AsyncMock()
    return stub


class MockGrpcServer:
    """Mock gRPC server for testing."""
    
    def __init__(self, port: int):
        self.port = port
        self._server = None
        self.is_running = False
    
    async def start(self):
        """Start the mock server."""
        self.is_running = True
    
    async def stop(self):
        """Stop the mock server."""
        self.is_running = False
    
    async def wait_for_termination(self):
        """Wait for server termination."""
        pass


@pytest.fixture
async def mock_grpc_server() -> AsyncGenerator[MockGrpcServer, None]:
    """Create a mock gRPC server for testing."""
    server = MockGrpcServer(port=0)  # Use random port
    await server.start()
    yield server
    await server.stop()


class AsyncContextManagerMock:
    """Mock async context manager."""
    
    def __init__(self, return_value=None):
        self._return_value = return_value
    
    async def __aenter__(self):
        return self._return_value
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        return None


@pytest.fixture
def mock_session_state():
    """Mock session state for testing."""
    session = Mock()
    session.session_id = "test-session-123"
    session.user_id = "test-user"
    session.context = {}
    session.conversation_history = []
    session.is_active = True
    session.created_at = "2024-01-01T00:00:00Z"
    return session


@pytest.fixture  
def mock_audio_frame():
    """Mock audio frame for testing."""
    frame = Mock()
    frame.audio = b"test_audio_data"
    frame.sample_rate = 16000
    frame.num_channels = 1
    frame.timestamp = 0.0
    return frame


@pytest.fixture
def mock_text_frame():
    """Mock text frame for testing."""
    frame = Mock()
    frame.text = "Test text content"
    frame.timestamp = 0.0
    return frame


# Test environment setup
def pytest_configure(config):
    """Configure pytest environment."""
    # Set test environment variables
    import os
    os.environ["TESTING"] = "1"
    os.environ["LOG_LEVEL"] = "DEBUG"


def pytest_collection_modifyitems(config, items):
    """Modify test collection to add markers automatically."""
    for item in items:
        # Add 'unit' marker to all tests in unit test directories
        if "unit" in str(item.fspath):
            item.add_marker(pytest.mark.unit)
        # Add 'integration' marker to integration tests
        elif "integration" in str(item.fspath):
            item.add_marker(pytest.mark.integration)
        # Add 'e2e' marker to end-to-end tests
        elif "e2e" in str(item.fspath):
            item.add_marker(pytest.mark.e2e)
        
        # Add markers based on test names
        if "grpc" in item.name.lower():
            item.add_marker(pytest.mark.grpc)
        if "audio" in item.name.lower():
            item.add_marker(pytest.mark.audio)
        if "network" in item.name.lower():
            item.add_marker(pytest.mark.network)


# Cleanup after tests
@pytest.fixture(autouse=True)
async def cleanup_after_test():
    """Cleanup resources after each test."""
    yield
    # Cleanup any remaining async tasks
    tasks = [task for task in asyncio.all_tasks() if not task.done()]
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)