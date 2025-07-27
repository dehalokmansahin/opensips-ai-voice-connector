"""
Test configuration for ASR service
"""

import pytest
import asyncio
import tempfile
import shutil
from pathlib import Path
from unittest.mock import Mock, AsyncMock, patch, MagicMock
import sys
import numpy as np

# Add service source to path
ASR_SERVICE_PATH = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(ASR_SERVICE_PATH))


@pytest.fixture
def mock_vosk_model():
    """Mock Vosk model for testing."""
    with patch('asr_grpc_server.Model') as mock_model:
        mock_instance = Mock()
        mock_model.return_value = mock_instance
        yield mock_instance


@pytest.fixture
def mock_vosk_recognizer():
    """Mock Vosk recognizer for testing."""
    with patch('asr_grpc_server.KaldiRecognizer') as mock_recognizer:
        mock_instance = Mock()
        
        # Mock methods
        mock_instance.AcceptWaveform = Mock(return_value=True)
        mock_instance.Result = Mock(return_value='{"text": "test result"}')
        mock_instance.PartialResult = Mock(return_value='{"partial": "test partial"}')
        mock_instance.FinalResult = Mock(return_value='{"text": "final result"}')
        mock_instance.SetWords = Mock()
        mock_instance.SetMaxAlternatives = Mock()
        
        mock_recognizer.return_value = mock_instance
        yield mock_instance


@pytest.fixture
def mock_model_path(tmp_path):
    """Create a mock model directory structure."""
    model_dir = tmp_path / "model"
    tr_dir = model_dir / "tr"
    tr_dir.mkdir(parents=True)
    
    # Create required files
    (tr_dir / "final.mdl").touch()
    (tr_dir / "conf").mkdir()
    
    return str(model_dir)


@pytest.fixture
def sample_audio_chunk():
    """Generate sample audio data for testing."""
    # Generate 100ms of 16kHz sine wave
    sample_rate = 16000
    duration = 0.1
    frequency = 440.0
    
    t = np.linspace(0, duration, int(sample_rate * duration), False)
    wave = np.sin(frequency * 2 * np.pi * t)
    audio_data = (wave * 32767).astype(np.int16)
    return audio_data.tobytes()


@pytest.fixture
def asr_config():
    """Sample ASR configuration."""
    return {
        "sample_rate": 16000,
        "model_path": "model",
        "show_words": True,
        "max_alternatives": 0,
        "phrase_list": None
    }


@pytest.fixture
def mock_grpc_context():
    """Mock gRPC context."""
    context = Mock()
    context.set_code = Mock()
    context.set_details = Mock()
    return context


@pytest.fixture
async def asr_service_impl(mock_vosk_model, mock_vosk_recognizer, mock_model_path):
    """Create ASR service implementation with mocked dependencies."""
    with patch.dict('os.environ', {'VOSK_MODEL_PATH': mock_model_path}):
        with patch('os.path.exists', return_value=True):
            with patch('os.listdir', return_value=['final.mdl', 'conf']):
                from asr_grpc_server import ASRServiceImpl
                service = ASRServiceImpl()
                yield service