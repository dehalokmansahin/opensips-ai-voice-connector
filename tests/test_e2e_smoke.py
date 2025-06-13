#!/usr/bin/env python3
"""
End-to-End Smoke Tests for OpenSIPS AI Voice Connector

Tests the complete call flow: INVITE → 200 OK → media → BYE
Designed to run in GitHub CI within 15 seconds.
"""

import asyncio
import pytest
import logging
import time
import socket
import json
from unittest.mock import Mock, AsyncMock, patch
from typing import Dict, Any, Optional

# Import OAVC components
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from engine import mi_reply, handle_call, calls
from call import Call
from config import Config
from opensips.mi import OpenSIPSMI
from aiortc.sdp import SessionDescription

# Test configuration
TEST_TIMEOUT = 15.0  # Maximum test duration for CI
TEST_SDP = """v=0
o=- 123456 654321 IN IP4 192.168.1.100
s=-
c=IN IP4 192.168.1.100
t=0 0
m=audio 5004 RTP/AVP 0
a=rtpmap:0 PCMU/8000
a=sendrecv
"""

class MockOpenSIPSMI:
    """Mock OpenSIPS MI interface for testing"""
    
    def __init__(self):
        self.commands = []
        self.responses = {}
    
    def execute(self, command: str, params: Dict[str, Any] = None):
        """Mock MI command execution"""
        self.commands.append((command, params))
        if command in self.responses:
            return self.responses[command]
        return {"status": "OK"}
    
    def set_response(self, command: str, response: Any):
        """Set mock response for a command"""
        self.responses[command] = response

class MockAIEngine:
    """Mock AI engine for testing"""
    
    def __init__(self):
        self.started = False
        self.closed = False
        self.audio_chunks = []
    
    async def start(self):
        self.started = True
        return True
    
    async def close(self):
        self.closed = True
    
    async def send(self, audio_chunk: bytes):
        self.audio_chunks.append(audio_chunk)
    
    def get_codec(self):
        from codec import PCMU
        from aiortc.codecs import PCMU as RTCCodec
        return PCMU(RTCCodec())

@pytest.fixture
def mock_config():
    """Mock configuration for testing"""
    config = {
        'opensips': {
            'ip': '127.0.0.1',
            'port': '8088'
        },
        'engine': {
            'event_ip': '127.0.0.1',
            'event_port': '8089'
        },
        'rtp': {
            'min_port': '35000',
            'max_port': '35010',
            'bind_ip': '127.0.0.1',
            'ip': '127.0.0.1'
        },
        'SmartSpeech': {
            'url': 'ws://localhost:2700',
            'host': 'localhost',
            'port': '8000',
            'TTS_VOICE': 'test-voice',
            'match': '^test.*$'
        }
    }
    
    with patch.object(Config, 'get') as mock_get:
        mock_get.side_effect = lambda section, default=None: config.get(section, default or {})
        with patch.object(Config, 'engine') as mock_engine:
            mock_engine.side_effect = lambda key, env_key=None, default=None: config['engine'].get(key, default)
            yield config

@pytest.fixture
def mock_mi_conn():
    """Mock MI connection"""
    return MockOpenSIPSMI()

@pytest.fixture
def test_call_params():
    """Standard test call parameters"""
    return {
        'key': 'TEST123',
        'method': 'INVITE',
        'body': TEST_SDP,
        'from': 'sip:test@example.com',
        'to': 'sip:vosk@ai.example.com',
        'callid': 'test-call-123'
    }

class TestE2ESmokeFlow:
    """End-to-end smoke tests for complete call flow"""
    
    @pytest.mark.asyncio
    async def test_complete_call_flow(self, mock_config, mock_mi_conn, test_call_params):
        """Test complete INVITE → 200 OK → media → BYE flow"""
        start_time = time.time()
        
        # Clear any existing calls
        calls.clear()
        
        # Mock AI engine creation
        mock_ai_engine = MockAIEngine()
        
        with patch('utils.get_ai', return_value=mock_ai_engine):
            with patch('engine.mi_conn', mock_mi_conn):
                # Step 1: Handle INVITE
                logging.info("Step 1: Processing INVITE")
                handle_call(None, test_call_params['key'], 'INVITE', test_call_params)
                
                # Verify call was created
                assert test_call_params['key'] in calls
                call_obj = calls[test_call_params['key']]
                assert isinstance(call_obj, Call)
                
                # Verify MI reply was sent
                mi_commands = [cmd for cmd, params in mock_mi_conn.commands if cmd == 'ua_session_reply']
                assert len(mi_commands) >= 1
                
                # Step 2: Simulate media exchange
                logging.info("Step 2: Simulating media exchange")
                test_audio = b'\x00\x01' * 160  # Mock RTP payload
                
                # Send audio to AI engine
                await call_obj.ai_engine_instance.send(test_audio)
                assert len(mock_ai_engine.audio_chunks) > 0
                
                # Step 3: Handle BYE
                logging.info("Step 3: Processing BYE")
                handle_call(call_obj, test_call_params['key'], 'BYE', {})
                
                # Verify BYE response was sent
                bye_commands = [cmd for cmd, params in mock_mi_conn.commands 
                              if cmd == 'ua_session_reply' and params and params.get('method') == 'BYE']
                assert len(bye_commands) >= 1
                
                # Step 4: Verify cleanup
                logging.info("Step 4: Verifying cleanup")
                # Give some time for async cleanup
                await asyncio.sleep(0.1)
                
                # Call should be removed from active calls
                assert test_call_params['key'] not in calls
                
        elapsed = time.time() - start_time
        logging.info(f"Complete call flow test completed in {elapsed:.2f}s")
        assert elapsed < TEST_TIMEOUT, f"Test took too long: {elapsed:.2f}s > {TEST_TIMEOUT}s"
    
    @pytest.mark.asyncio
    async def test_invite_sdp_parsing(self, mock_config, mock_mi_conn, test_call_params):
        """Test SDP parsing in INVITE handling"""
        calls.clear()
        mock_ai_engine = MockAIEngine()
        
        with patch('utils.get_ai', return_value=mock_ai_engine):
            with patch('engine.mi_conn', mock_mi_conn):
                # Test with valid SDP
                handle_call(None, test_call_params['key'], 'INVITE', test_call_params)
                
                assert test_call_params['key'] in calls
                call_obj = calls[test_call_params['key']]
                
                # Verify SDP was parsed correctly
                assert call_obj.sdp is not None
                assert len(call_obj.sdp.media) > 0
                assert call_obj.sdp.media[0].fmt == ['0']  # PCMU
    
    @pytest.mark.asyncio
    async def test_invite_without_body(self, mock_config, mock_mi_conn):
        """Test INVITE handling without SDP body"""
        calls.clear()
        
        with patch('engine.mi_conn', mock_mi_conn):
            params = {'key': 'TEST456', 'method': 'INVITE'}  # No body
            handle_call(None, 'TEST456', 'INVITE', params)
            
            # Should send 415 Unsupported Media Type
            error_commands = [cmd for cmd, params in mock_mi_conn.commands 
                            if cmd == 'ua_session_reply' and params and params.get('code') == 415]
            assert len(error_commands) >= 1
            
            # No call should be created
            assert 'TEST456' not in calls
    
    @pytest.mark.asyncio
    async def test_bye_nonexistent_call(self, mock_config, mock_mi_conn):
        """Test BYE handling for non-existent call"""
        calls.clear()
        
        with patch('engine.mi_conn', mock_mi_conn):
            # Try to send BYE for non-existent call
            handle_call(None, 'NONEXISTENT', 'BYE', {})
            
            # Should still send 200 OK (per our new BYE handling)
            bye_commands = [cmd for cmd, params in mock_mi_conn.commands 
                          if cmd == 'ua_session_reply' and params and params.get('method') == 'BYE']
            assert len(bye_commands) >= 1
    
    @pytest.mark.asyncio
    async def test_rtp_port_allocation(self, mock_config, mock_mi_conn, test_call_params):
        """Test RTP port allocation and cleanup"""
        calls.clear()
        mock_ai_engine = MockAIEngine()
        
        with patch('utils.get_ai', return_value=mock_ai_engine):
            with patch('engine.mi_conn', mock_mi_conn):
                # Create multiple calls to test port allocation
                call_keys = ['CALL1', 'CALL2', 'CALL3']
                
                for key in call_keys:
                    params = test_call_params.copy()
                    params['key'] = key
                    handle_call(None, key, 'INVITE', params)
                    assert key in calls
                
                # All calls should have different RTP ports
                ports = set()
                for key in call_keys:
                    call_obj = calls[key]
                    port = call_obj.serversock.getsockname()[1]
                    ports.add(port)
                
                assert len(ports) == len(call_keys), "Calls should have unique RTP ports"
                
                # Clean up calls
                for key in call_keys:
                    if key in calls:
                        handle_call(calls[key], key, 'BYE', {})
                
                await asyncio.sleep(0.1)  # Allow cleanup
    
    @pytest.mark.asyncio
    async def test_concurrent_calls(self, mock_config, mock_mi_conn, test_call_params):
        """Test handling multiple concurrent calls"""
        calls.clear()
        mock_ai_engine = MockAIEngine()
        
        with patch('utils.get_ai', return_value=mock_ai_engine):
            with patch('engine.mi_conn', mock_mi_conn):
                # Create multiple concurrent calls
                call_tasks = []
                call_keys = [f'CONCURRENT_{i}' for i in range(5)]
                
                async def create_call(key):
                    params = test_call_params.copy()
                    params['key'] = key
                    handle_call(None, key, 'INVITE', params)
                    
                    # Simulate some media
                    if key in calls:
                        await calls[key].ai_engine_instance.send(b'\x00\x01' * 80)
                    
                    # Clean up
                    if key in calls:
                        handle_call(calls[key], key, 'BYE', {})
                
                # Run calls concurrently
                call_tasks = [create_call(key) for key in call_keys]
                await asyncio.gather(*call_tasks)
                
                await asyncio.sleep(0.2)  # Allow cleanup
                
                # All calls should be cleaned up
                for key in call_keys:
                    assert key not in calls

class TestPerformanceBenchmarks:
    """Performance benchmarks for CI monitoring"""
    
    @pytest.mark.asyncio
    async def test_call_setup_performance(self, mock_config, mock_mi_conn, test_call_params):
        """Benchmark call setup time"""
        calls.clear()
        mock_ai_engine = MockAIEngine()
        
        with patch('utils.get_ai', return_value=mock_ai_engine):
            with patch('engine.mi_conn', mock_mi_conn):
                # Measure call setup time
                start_time = time.time()
                
                handle_call(None, test_call_params['key'], 'INVITE', test_call_params)
                
                setup_time = time.time() - start_time
                
                assert test_call_params['key'] in calls
                logging.info(f"Call setup time: {setup_time:.3f}s")
                
                # Should be very fast (< 100ms for mock setup)
                assert setup_time < 0.1, f"Call setup too slow: {setup_time:.3f}s"
                
                # Cleanup
                handle_call(calls[test_call_params['key']], test_call_params['key'], 'BYE', {})
    
    @pytest.mark.asyncio
    async def test_media_processing_performance(self, mock_config, mock_mi_conn, test_call_params):
        """Benchmark media processing performance"""
        calls.clear()
        mock_ai_engine = MockAIEngine()
        
        with patch('utils.get_ai', return_value=mock_ai_engine):
            with patch('engine.mi_conn', mock_mi_conn):
                handle_call(None, test_call_params['key'], 'INVITE', test_call_params)
                call_obj = calls[test_call_params['key']]
                
                # Benchmark audio processing
                test_audio = b'\x00\x01' * 160
                num_chunks = 100
                
                start_time = time.time()
                
                for _ in range(num_chunks):
                    await call_obj.ai_engine_instance.send(test_audio)
                
                processing_time = time.time() - start_time
                avg_time_per_chunk = processing_time / num_chunks
                
                logging.info(f"Processed {num_chunks} audio chunks in {processing_time:.3f}s")
                logging.info(f"Average time per chunk: {avg_time_per_chunk:.6f}s")
                
                # Should process audio chunks quickly
                assert avg_time_per_chunk < 0.001, f"Audio processing too slow: {avg_time_per_chunk:.6f}s per chunk"
                
                # Cleanup
                handle_call(call_obj, test_call_params['key'], 'BYE', {})

if __name__ == "__main__":
    # Configure logging for test runs
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Run tests
    pytest.main([__file__, "-v", "--tb=short"]) 