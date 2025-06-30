#!/usr/bin/env python3
"""
Pipecat Transport Test
Tests the native UDP/RTP transport integration
"""

import asyncio
import sys
import os
from pathlib import Path

# Add project paths
current_dir = Path(__file__).parent
src_path = current_dir / "src"
pipecat_src_path = current_dir / "pipecat" / "src"

if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))
if str(pipecat_src_path) not in sys.path:
    sys.path.insert(0, str(pipecat_src_path))

import structlog

# Setup logging
import logging
structlog.configure(
    processors=[
        structlog.dev.ConsoleRenderer()
    ],
    wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
    logger_factory=structlog.WriteLoggerFactory(),
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger()

# Mock services for testing
class MockSTTService:
    async def start(self):
        logger.info("Mock STT service started")
    
    async def stop(self):
        logger.info("Mock STT service stopped")

class MockLLMService:
    async def start(self):
        logger.info("Mock LLM service started")
    
    async def stop(self):
        logger.info("Mock LLM service stopped")

class MockTTSService:
    async def start(self):
        logger.info("Mock TTS service started")
    
    async def stop(self):
        logger.info("Mock TTS service stopped")


async def test_native_transport():
    """Test native UDP/RTP transport"""
    logger.info("🧪 Testing Native Pipecat UDP/RTP Transport")
    
    try:
        # Import components
        from transports.pipecat_udp_transport import create_opensips_rtp_transport
        from transports.native_call_manager import NativeCallManager as CallManager
        
        logger.info("✅ Native transport imports successful")
        
        # Create mock services
        services = {
            "stt": MockSTTService(),
            "llm": MockLLMService(), 
            "tts": MockTTSService()
        }
        
        # Create call manager
        call_manager = CallManager(services)
        logger.info("✅ Native call manager created")
        
        # Test call creation
        call_id = "test-call-123"
        sdp_info = {
            "media_ip": "192.168.1.100",
            "media_port": 4080,
            "audio_format": "PCMU"
        }
        
        logger.info("🚀 Creating test call...")
        call = await call_manager.create_call(call_id, sdp_info)
        
        if call and call.transport:
            logger.info("✅ Native call created successfully", 
                       call_id=call_id,
                       local_port=call.transport.local_port)
            
            # Wait a bit
            await asyncio.sleep(2)
            
            # Stop call
            await call_manager.terminate_call(call_id)
            logger.info("✅ Native call terminated successfully")
            
        else:
            logger.error("❌ Failed to create native call")
            
    except ImportError as e:
        logger.error("❌ Import error - check if all dependencies are available", error=str(e))
    except Exception as e:
        logger.error("❌ Test failed", error=str(e), exc_info=True)
        raise
    
    logger.info("🧪 Native transport test completed")


async def test_transport_directly():
    """Test UDP/RTP transport directly"""
    logger.info("🧪 Testing UDP/RTP Transport directly")
    
    try:
        from transports.pipecat_udp_transport import create_opensips_rtp_transport
        
        # Create transport
        transport = create_opensips_rtp_transport(
            bind_ip="0.0.0.0",
            bind_port=0  # Auto-assign
        )
        
        logger.info("✅ Transport created", 
                   local_port=transport.local_port)
        
        # Get SDP info
        sdp_info = transport.get_sdp_info()
        logger.info("✅ SDP info generated", sdp_info=sdp_info)
        
        # Test event handlers
        @transport.event_handler("on_client_connected")
        async def on_client_connected(client_ip, client_port):
            logger.info("🎯 Test client connected event", 
                       client_ip=client_ip, client_port=client_port)
        
        # Simulate basic lifecycle
        from pipecat.frames.frames import StartFrame, EndFrame
        from pipecat.pipeline.pipeline import Pipeline
        from pipecat.pipeline.task import PipelineTask
        
        # Basic pipeline
        pipeline = Pipeline([transport.input(), transport.output()])
        task = PipelineTask(pipeline)
        
        logger.info("✅ Basic pipeline created")
        
        # Start pipeline briefly
        start_task = asyncio.create_task(task.queue_frame(StartFrame()))
        await asyncio.sleep(0.1)
        
        # Stop pipeline
        end_task = asyncio.create_task(task.queue_frame(EndFrame()))
        await asyncio.sleep(0.1)
        
        logger.info("✅ Transport lifecycle test completed")
        
    except Exception as e:
        logger.error("❌ Direct transport test failed", error=str(e))
        raise


async def main():
    """Main test function"""
    logger.info("🎵 Starting Native Pipecat Transport Tests")
    
    try:
        # Test 1: Direct transport test
        await test_transport_directly()
        
        # Test 2: Native call manager test
        await test_native_transport()
        
        logger.info("✅ All tests passed!")
        
    except Exception as e:
        logger.error("❌ Tests failed", error=str(e))
        return 1
    
    return 0


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code) 