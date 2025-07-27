"""
Test configuration for TTS service
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
TTS_SERVICE_PATH = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(TTS_SERVICE_PATH))


@pytest.fixture
def mock_piper_voice():
    """Mock Piper voice for testing."""
    with patch('tts_grpc_server.PiperVoice') as mock_piper:
        mock_instance = Mock()
        
        # Mock voice configuration
        mock_config = Mock()
        mock_config.sample_rate = 22050
        mock_instance.config = mock_config
        
        # Mock synthesis method
        def mock_synthesize_stream_raw(text):
            # Generate mock audio data (22050 Hz, 16-bit, 1 second)
            sample_rate = 22050
            duration = 1.0
            frequency = 440.0
            
            t = np.linspace(0, duration, int(sample_rate * duration), False)
            wave = np.sin(frequency * 2 * np.pi * t)
            audio_data = (wave * 32767).astype(np.int16)
            
            # Split into chunks and yield
            chunk_size = 1024
            audio_bytes = audio_data.tobytes()
            for i in range(0, len(audio_bytes), chunk_size):
                yield audio_bytes[i:i+chunk_size]
        
        mock_instance.synthesize_stream_raw = mock_synthesize_stream_raw
        
        # Mock the load class method
        mock_piper.load.return_value = mock_instance
        
        yield mock_instance


@pytest.fixture
def mock_model_files(tmp_path):
    """Create mock TTS model files."""
    model_dir = tmp_path / "model"
    model_dir.mkdir()
    
    # Create mock model files
    model_file = model_dir / "tr_TR-fahrettin-medium.onnx"
    config_file = model_dir / "tr_TR-fahrettin-medium.onnx.json"
    
    model_file.write_bytes(b"mock model data")
    config_file.write_text('{"sample_rate": 22050, "channels": 1}')
    
    return str(model_dir)


@pytest.fixture
def sample_tts_request():
    """Sample TTS request data."""
    return {
        "text": "Merhaba, bu bir test mesajıdır.",
        "voice": "tr_TR-fahrettin-medium",
        "sample_rate": 22050
    }


@pytest.fixture
def turkish_text_samples():
    """Sample Turkish texts for testing."""
    return [
        "Merhaba, nasılsınız?",
        "Hesap bakiyeniz 1.250 TL'dir.",
        "İşleminiz başarıyla tamamlanmıştır.",
        "Lütfen bekleyiniz, size yardımcı olalım.",
        "Garanti BBVA'ya hoş geldiniz."
    ]


@pytest.fixture
def mock_grpc_context():
    """Mock gRPC context."""
    context = Mock()
    context.set_code = Mock()
    context.set_details = Mock()
    return context


@pytest.fixture
def sample_audio_chunks():
    """Generate sample audio chunks for testing."""
    chunks = []
    
    # Generate 5 chunks of audio data
    for i in range(5):
        # Each chunk is 20ms of 22050Hz, 16-bit mono audio
        samples_per_chunk = int(22050 * 0.02)  # 441 samples
        audio_data = np.random.randint(-32768, 32767, samples_per_chunk, dtype=np.int16)
        chunks.append(audio_data.tobytes())
    
    return chunks


@pytest.fixture
async def tts_service_impl(mock_piper_voice, mock_model_files):
    """Create TTS service implementation with mocked dependencies."""
    with patch.dict('os.environ', {
        'PIPER_MODEL_DIR': mock_model_files,
        'PIPER_MODEL_NAME': 'tr_TR-fahrettin-medium'
    }):
        from tts_grpc_server import TTSServiceImpl
        service = TTSServiceImpl()
        yield service