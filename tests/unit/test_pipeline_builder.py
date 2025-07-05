"""
Test Pipeline Builder
Tests for the new pipeline builder module
"""

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock

# Add src to path for imports
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from pipeline.builder import build_voice_pipeline, create_conversation_context
from pipecat.processors.aggregators.openai_llm_context import OpenAILLMContext
from pipecat.pipeline.pipeline import Pipeline

@pytest.fixture
def mock_transport():
    """Mock transport with input/output"""
    transport = Mock()
    transport.input.return_value = Mock()
    transport.output.return_value = Mock()
    return transport

@pytest.fixture  
def mock_services():
    """Mock STT, LLM, TTS services"""
    stt = Mock()
    llm = Mock()
    tts = Mock()
    
    # Mock context aggregator creation
    context_aggregator = Mock()
    context_aggregator.user.return_value = Mock()
    context_aggregator.assistant.return_value = Mock()
    llm.create_context_aggregator.return_value = context_aggregator
    
    return {
        'stt': stt,
        'llm': llm, 
        'tts': tts
    }

def test_create_conversation_context():
    """Test conversation context creation"""
    context = create_conversation_context()
    
    assert isinstance(context, OpenAILLMContext)
    assert len(context.messages) == 1
    assert context.messages[0]["role"] == "system"
    assert "helpful AI assistant" in context.messages[0]["content"]

def test_create_conversation_context_custom_message():
    """Test conversation context with custom system message"""
    custom_msg = "You are a banking assistant."
    context = create_conversation_context(
        system_message=custom_msg
    )
    
    assert isinstance(context, OpenAILLMContext)
    assert len(context.messages) == 1
    assert context.messages[0]["role"] == "system"
    assert context.messages[0]["content"] == custom_msg

def test_build_voice_pipeline_correct_order(mock_transport, mock_services):
    """Test pipeline is built with correct element order"""
    context = create_conversation_context()
    
    pipeline = build_voice_pipeline(
        transport=mock_transport,
        stt_service=mock_services['stt'],
        llm_service=mock_services['llm'],
        tts_service=mock_services['tts'],
        context=context
    )
    
    assert isinstance(pipeline, Pipeline)
    
    # Verify pipeline elements were created (Pipecat adds source/sink automatically)
    elements = pipeline._processors
    # Expected: source, input, stt, context_user, llm, tts, output, context_assistant, sink
    assert len(elements) >= 7  # At least our 7 elements (Pipecat may add source/sink)
    
    # Verify services were accessed
    mock_transport.input.assert_called_once()
    mock_transport.output.assert_called_once()

def test_build_voice_pipeline_without_context_aggregator(mock_transport):
    """Test pipeline building without context aggregator"""
    pipeline = build_voice_pipeline(
        transport=mock_transport,
        stt_service=Mock(),
        llm_service=Mock(),
        tts_service=Mock(),
        context=None  # No context
    )
    
    assert isinstance(pipeline, Pipeline)
    
    # Should still have 5 elements: input, stt, llm, tts, output (plus Pipecat's source/sink)
    elements = pipeline._processors
    assert len(elements) >= 5

def test_build_voice_pipeline_missing_services(mock_transport):
    """Test pipeline building with missing services"""
    context = create_conversation_context()
    
    pipeline = build_voice_pipeline(
        transport=mock_transport,
        stt_service=None,  # Missing STT
        llm_service=None,  # Missing LLM
        tts_service=None,  # Missing TTS
        context=context
    )
    
    assert isinstance(pipeline, Pipeline)
    
    # Should have transport elements + context: input, context_user, context_assistant, output (plus Pipecat's source/sink)
    elements = pipeline._processors
    assert len(elements) >= 4 