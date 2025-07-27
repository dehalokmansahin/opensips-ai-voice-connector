"""
Test utilities and helper functions for OpenSIPS AI Voice Connector
"""

import asyncio
import json
from typing import Dict, Any, List, AsyncGenerator, Optional
from unittest.mock import Mock, AsyncMock
import tempfile
from pathlib import Path
import numpy as np


class TestDataFactory:
    """Factory for creating test data."""
    
    @staticmethod
    def create_audio_data(
        sample_rate: int = 16000,
        duration: float = 1.0,
        frequency: float = 440.0
    ) -> bytes:
        """Create sample audio data."""
        t = np.linspace(0, duration, int(sample_rate * duration), False)
        wave = np.sin(frequency * 2 * np.pi * t)
        audio_data = (wave * 32767).astype(np.int16)
        return audio_data.tobytes()
    
    @staticmethod
    def create_conversation_history() -> List[Dict[str, Any]]:
        """Create sample conversation history."""
        return [
            {
                "role": "user",
                "content": "Hello, how are you?",
                "timestamp": "2024-01-01T00:00:00Z"
            },
            {
                "role": "assistant", 
                "content": "I'm doing well, thank you! How can I help you today?",
                "timestamp": "2024-01-01T00:00:01Z"
            }
        ]
    
    @staticmethod
    def create_session_context() -> Dict[str, Any]:
        """Create sample session context."""
        return {
            "user_preferences": {
                "language": "en",
                "voice": "default"
            },
            "session_metadata": {
                "start_time": "2024-01-01T00:00:00Z",
                "call_id": "test-call-123"
            }
        }


class AsyncMockHelper:
    """Helper for creating async mocks."""
    
    @staticmethod
    def create_async_iterator(items: List[Any]) -> AsyncGenerator:
        """Create an async iterator from a list of items."""
        async def async_gen():
            for item in items:
                yield item
        return async_gen()
    
    @staticmethod
    def create_grpc_stream_response(responses: List[Any]):
        """Create a mock gRPC streaming response."""
        async def stream():
            for response in responses:
                yield response
        return stream()


class GrpcTestHelper:
    """Helper for gRPC testing."""
    
    @staticmethod
    def create_health_response(status: str = "SERVING", message: str = "OK"):
        """Create a mock health response."""
        response = Mock()
        response.status = Mock()
        response.status.Name = Mock(return_value=status)
        response.message = message
        response.model_loaded = True
        return response
    
    @staticmethod
    def create_transcription_response(text: str, confidence: float = 0.95, is_final: bool = True):
        """Create a mock transcription response."""
        response = Mock()
        response.text = text
        response.confidence = confidence
        response.is_final = is_final
        response.language = "en-US"
        return response
    
    @staticmethod
    def create_synthesis_response(audio_data: bytes, is_final: bool = True):
        """Create a mock synthesis response."""
        response = Mock()
        if is_final:
            response.HasField = lambda field: field == "completed"
            response.completed = Mock()
            response.completed.message = "Synthesis completed"
            response.completed.stats = Mock()
            response.completed.stats.processing_time_ms = 100.0
        else:
            response.HasField = lambda field: field == "audio_chunk"
            response.audio_chunk = Mock()
            response.audio_chunk.data = audio_data
            response.audio_chunk.format = "LINEAR16"
        return response
    
    @staticmethod
    def create_llm_response(text: str, done: bool = False):
        """Create a mock LLM response."""
        response = Mock()
        response.chunk = text
        response.done = done
        return response


class FileTestHelper:
    """Helper for file operations in tests."""
    
    @staticmethod
    def create_temp_config_file(config_data: Dict[str, Any]) -> Path:
        """Create a temporary configuration file."""
        temp_file = tempfile.NamedTemporaryFile(
            mode='w', 
            suffix='.ini', 
            delete=False
        )
        
        # Convert dict to INI format
        for section, values in config_data.items():
            temp_file.write(f"[{section}]\n")
            for key, value in values.items():
                temp_file.write(f"{key} = {value}\n")
            temp_file.write("\n")
        
        temp_file.close()
        return Path(temp_file.name)
    
    @staticmethod
    def create_temp_audio_file(audio_data: bytes, suffix: str = ".wav") -> Path:
        """Create a temporary audio file."""
        temp_file = tempfile.NamedTemporaryFile(
            mode='wb',
            suffix=suffix,
            delete=False
        )
        temp_file.write(audio_data)
        temp_file.close()
        return Path(temp_file.name)


class AsyncTestCase:
    """Base class for async test cases."""
    
    @staticmethod
    async def run_with_timeout(coro, timeout: float = 5.0):
        """Run a coroutine with timeout."""
        try:
            return await asyncio.wait_for(coro, timeout=timeout)
        except asyncio.TimeoutError:
            raise AssertionError(f"Test timed out after {timeout} seconds")
    
    @staticmethod
    async def assert_no_pending_tasks():
        """Assert that there are no pending asyncio tasks."""
        tasks = [task for task in asyncio.all_tasks() if not task.done()]
        if tasks:
            # Cancel remaining tasks
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            raise AssertionError(f"Found {len(tasks)} pending tasks after test")


class PerformanceTestHelper:
    """Helper for performance testing."""
    
    @staticmethod
    async def measure_execution_time(coro):
        """Measure execution time of a coroutine."""
        import time
        start_time = time.perf_counter()
        result = await coro
        end_time = time.perf_counter()
        execution_time = end_time - start_time
        return result, execution_time
    
    @staticmethod
    def assert_execution_time(execution_time: float, max_time: float):
        """Assert that execution time is within limits."""
        if execution_time > max_time:
            raise AssertionError(
                f"Execution took {execution_time:.3f}s, expected < {max_time:.3f}s"
            )


class MockServiceRegistry:
    """Mock service registry for testing."""
    
    def __init__(self):
        self.services = {}
        self.health_status = {}
    
    def register_service(self, name: str, host: str, port: int):
        """Register a mock service."""
        self.services[name] = {"host": host, "port": port}
        self.health_status[name] = "SERVING"
    
    def get_service(self, name: str) -> Optional[Dict[str, Any]]:
        """Get service information."""
        return self.services.get(name)
    
    def set_health_status(self, name: str, status: str):
        """Set health status for a service."""
        self.health_status[name] = status
    
    def is_healthy(self, name: str) -> bool:
        """Check if service is healthy."""
        return self.health_status.get(name) == "SERVING"


# Pytest markers for categorizing tests
def unit_test(func):
    """Mark a test as a unit test."""
    import pytest
    return pytest.mark.unit(func)


def integration_test(func):
    """Mark a test as an integration test."""
    import pytest
    return pytest.mark.integration(func)


def grpc_test(func):
    """Mark a test as requiring gRPC services."""
    import pytest
    return pytest.mark.grpc(func)


def audio_test(func):
    """Mark a test as involving audio processing."""
    import pytest
    return pytest.mark.audio(func)


def slow_test(func):
    """Mark a test as slow (may take more than 10 seconds)."""
    import pytest
    return pytest.mark.slow(func)