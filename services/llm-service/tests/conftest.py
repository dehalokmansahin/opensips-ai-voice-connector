"""
Test configuration for LLM service
"""

import pytest
import asyncio
import tempfile
import shutil
from pathlib import Path
from unittest.mock import Mock, AsyncMock, patch, MagicMock
import sys

# Add service source to path
LLM_SERVICE_PATH = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(LLM_SERVICE_PATH))


@pytest.fixture
def mock_llama_model():
    """Mock Llama model for testing."""
    with patch('llm_grpc_server.Llama') as mock_llama:
        mock_instance = Mock()
        
        # Mock the streaming generator
        def mock_stream(*args, **kwargs):
            responses = [
                {'choices': [{'text': 'Hello '}]},
                {'choices': [{'text': 'world '}]},
                {'choices': [{'text': '!'}]}
            ]
            for response in responses:
                yield response
        
        mock_instance.side_effect = mock_stream
        mock_llama.return_value = mock_instance
        yield mock_instance


@pytest.fixture
def mock_model_file(tmp_path):
    """Create a mock model file for testing."""
    model_dir = tmp_path / "model"
    model_dir.mkdir()
    model_file = model_dir / "test_model.gguf"
    model_file.write_text("mock model content")
    return str(model_dir)


@pytest.fixture
def sample_llm_request():
    """Sample LLM request data."""
    return {
        "text": "Hello, how can I help you today?",
        "system_prompt": "You are a helpful banking assistant.",
        "temperature": 0.2,
        "max_tokens": 50
    }


@pytest.fixture
def banking_context():
    """Sample banking conversation context."""
    return {
        "customer_id": "12345",
        "account_type": "checking",
        "recent_transactions": [
            {"amount": 100.0, "type": "deposit"},
            {"amount": -50.0, "type": "withdrawal"}
        ],
        "conversation_history": [
            {"role": "user", "content": "What's my balance?"},
            {"role": "assistant", "content": "Your balance is $1,250."}
        ]
    }


@pytest.fixture
def mock_grpc_context():
    """Mock gRPC context."""
    context = Mock()
    context.set_code = Mock()
    context.set_details = Mock()
    return context


@pytest.fixture
async def llm_service_impl(mock_llama_model, mock_model_file):
    """Create LLM service implementation with mocked dependencies."""
    with patch.dict('os.environ', {'MODEL_DIR': mock_model_file}):
        with patch('os.listdir', return_value=['test_model.gguf']):
            with patch('llm_grpc_server.LLAMA_AVAILABLE', True):
                from llm_grpc_server import LLMServiceImpl
                service = LLMServiceImpl()
                yield service


@pytest.fixture
async def llm_service_mock_mode():
    """Create LLM service implementation in mock mode (no llama-cpp)."""
    with patch('llm_grpc_server.LLAMA_AVAILABLE', False):
        from llm_grpc_server import LLMServiceImpl
        service = LLMServiceImpl()
        yield service