"""
Test configuration for Intent Recognition Service
"""

import pytest
import grpc
from grpc import aio as aio_grpc
import asyncio
import sys
from pathlib import Path

# Add src directory to path
src_path = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_path))

@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()

@pytest.fixture
def intent_service():
    """Create Intent Recognition service for testing"""
    from intent_grpc_server import IntentRecognitionServiceImpl
    return IntentRecognitionServiceImpl()

@pytest.fixture
async def grpc_server(intent_service):
    """Create gRPC server for testing"""
    import intent_service_pb2_grpc
    
    server = aio_grpc.server()
    intent_service_pb2_grpc.add_IntentRecognitionServicer_to_server(intent_service, server)
    
    # Use a test port
    listen_addr = '[::]:50055'  # Different from production port
    server.add_insecure_port(listen_addr)
    
    await server.start()
    yield server, listen_addr
    await server.stop(grace=1)

@pytest.fixture
async def grpc_channel(grpc_server):
    """Create gRPC channel for testing"""
    server, listen_addr = grpc_server
    channel = aio_grpc.insecure_channel(listen_addr)
    yield channel
    await channel.close()

@pytest.fixture
async def intent_stub(grpc_channel):
    """Create Intent Recognition stub for testing"""
    import intent_service_pb2_grpc
    return intent_service_pb2_grpc.IntentRecognitionStub(grpc_channel)