#!/usr/bin/env python3
"""
Pipeline Düzeltme Testi
Bu script pipeline lifecycle sorunlarını test eder
"""

import asyncio
import sys
import os
sys.path.append('src')

from pipeline.manager import EnhancedPipelineManager
from transports.oavc_adapter import OAVCAdapter
from services.ollama_llm import OllamaLLMService
from services.vosk_websocket import VoskWebSocketService  
from services.piper_websocket import PiperWebSocketService
import structlog

# Setup logging
logging_config = {
    "format": "%(asctime)s [%(levelname)s] %(message)s",
    "datefmt": "%Y-%m-%d %H:%M:%S",
    "level": "INFO"
}

structlog.configure(
    processors=[
        structlog.dev.ConsoleRenderer()
    ],
    wrapper_class=structlog.make_filtering_bound_logger(logging_config["level"]),
    logger_factory=structlog.WriteLoggerFactory(),
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger()

async def test_pipeline_lifecycle():
    """Test pipeline lifecycle fixes"""
    
    logger.info("🧪 Testing Pipeline Lifecycle Fixes...")
    
    try:
        # 1. Create mock services (you can replace with real ones)
        class MockService:
            async def start(self): pass
            async def stop(self): pass
        
        llm_service = MockService()
        stt_service = MockService() 
        tts_service = MockService()
        
        # 2. Create Pipeline Manager
        logger.info("Creating Pipeline Manager...")
        pipeline_manager = EnhancedPipelineManager(
            llm_service=llm_service,
            stt_service=stt_service, 
            tts_service=tts_service,
            enable_interruption=True,
            audio_in_enabled=True,
            audio_out_enabled=True
        )
        
        # 3. Test lifecycle
        test_call_key = "test_call_123"
        
        logger.info("Starting pipeline...")
        await pipeline_manager.start(test_call_key)
        
        logger.info("Checking pipeline status...")
        assert pipeline_manager.is_running, "Pipeline should be running"
        logger.info("✅ Pipeline is running!")
        
        logger.info("Sending start stream...")
        await pipeline_manager.start_stream()
        logger.info("✅ Start stream sent!")
        
        logger.info("Testing audio push...")
        # Test with dummy PCM data (160 bytes = 20ms at 8kHz)
        dummy_pcm = b'\x00' * 320  # 16-bit, 16kHz, 20ms
        await pipeline_manager.push_audio(dummy_pcm)
        logger.info("✅ Audio push test completed!")
        
        # 4. Test OAVC adapter
        logger.info("Testing OAVC Adapter...")
        oavc_adapter = OAVCAdapter(pipeline_manager)
        await oavc_adapter.start()
        
        # Test PCMU feed
        dummy_pcmu = b'\xff' * 160  # PCMU data (160 bytes = 20ms at 8kHz)
        await oavc_adapter.feed_pcmu(dummy_pcmu)
        logger.info("✅ OAVC Adapter test completed!")
        
        await oavc_adapter.stop()
        
        # 5. Cleanup
        logger.info("Stopping pipeline...")
        await pipeline_manager.stop()
        logger.info("✅ Pipeline stopped!")
        
        logger.info("🎉 ALL TESTS PASSED! Pipeline lifecycle is working correctly.")
        return True
        
    except Exception as e:
        logger.error(f"❌ TEST FAILED: {e}", exc_info=True)
        return False

async def main():
    """Main test function"""
    
    logger.info("🚀 Starting Pipeline Lifecycle Tests...")
    
    success = await test_pipeline_lifecycle()
    
    if success:
        logger.info("✅ All tests completed successfully!")
        return 0
    else:
        logger.error("❌ Some tests failed!")
        return 1

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code) 