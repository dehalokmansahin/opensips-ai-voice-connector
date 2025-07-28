"""
Test configuration and fixtures for Test Controller Service
"""

import pytest
import asyncio
import sys
import os
from unittest.mock import Mock, AsyncMock

# Add paths for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()

@pytest.fixture
def mock_settings():
    """Mock settings object"""
    settings = Mock()
    settings.opensips = Mock()
    settings.opensips.host = "127.0.0.1"
    settings.opensips.port = 5060
    settings.opensips.mi_port = 8080
    return settings

@pytest.fixture
def mock_test_execution_manager():
    """Mock test execution manager"""
    manager = Mock()
    manager.active_sessions = {}
    manager.start_test_execution = AsyncMock()
    manager.get_execution_state = AsyncMock()
    manager.stop_test_execution = AsyncMock()
    manager.shutdown = AsyncMock()
    return manager

@pytest.fixture
def mock_opensips_integration():
    """Mock OpenSIPS integration"""
    integration = Mock()
    integration.initialize = AsyncMock()
    integration.start = AsyncMock()
    integration.stop = AsyncMock()
    integration.health_check = AsyncMock(return_value={"status": "healthy"})
    integration.initiate_outbound_call = AsyncMock(return_value="call_123")
    integration.terminate_outbound_call = AsyncMock(return_value=True)
    integration.get_active_outbound_calls = AsyncMock(return_value={})
    return integration