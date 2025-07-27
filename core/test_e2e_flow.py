#!/usr/bin/env python3
"""
End-to-End Flow Test for OpenSIPS AI Voice Connector
Tests the complete audio processing pipeline with pipecat integration
"""

import asyncio
import logging
import sys
from pathlib import Path

# Add core to path
sys.path.insert(0, str(Path(__file__).parent))

try:
    from config.settings import Settings
    from grpc_clients.service_registry import ServiceRegistry
    from bot.pipeline_manager import PipelineManager
    from bot.session import ConversationSession, SessionConfig
    from utils.logging import setup_logging
except ImportError as e:
    print(f"Import error: {e}")
    print("This test requires the services to be configured and running.")
    print("Please ensure Docker services are started first.")
    sys.exit(1)

logger = logging.getLogger(__name__)

class E2EFlowTest:
    """End-to-end flow test"""
    
    def __init__(self):
        self.settings = None
        self.service_registry = None
        self.pipeline_manager = None
        
    async def setup(self):
        """Setup test environment"""
        try:
            logger.info("Setting up E2E test environment")
            
            # Load settings
            self.settings = Settings("config/app.ini")
            await self.settings.load()
            
            # Initialize service registry
            self.service_registry = ServiceRegistry(self.settings.services)
            await self.service_registry.initialize()
            
            # Initialize pipeline manager
            self.pipeline_manager = PipelineManager(
                service_registry=self.service_registry,
                settings=self.settings
            )
            await self.pipeline_manager.initialize()
            
            logger.info("E2E test environment setup completed")
            
        except Exception as e:
            logger.error(f"Failed to setup test environment: {e}")
            raise
    
    async def test_service_connectivity(self):
        """Test connectivity to all gRPC services"""
        try:
            logger.info("Testing service connectivity...")
            
            # Check service health
            health_status = await self.pipeline_manager.health_check()
            
            logger.info(f"Health check results: {health_status}")
            
            services_healthy = health_status.get('services', {})
            total_services = len(services_healthy)
            healthy_services = sum(1 for status in services_healthy.values() if status)
            
            logger.info(f"Services healthy: {healthy_services}/{total_services}")
            
            if healthy_services == 0:
                raise Exception("No services are healthy")
            
            return healthy_services >= 2  # At least 2 services should be healthy
            
        except Exception as e:
            logger.error(f"Service connectivity test failed: {e}")
            return False
    
    async def test_session_creation(self):
        """Test conversation session creation"""
        try:
            logger.info("Testing session creation...")
            
            # Create test session
            session = await self.pipeline_manager.create_test_session("test_e2e_session")
            
            if not session:
                raise Exception("Failed to create test session")
            
            # Check session state
            stats = session.get_stats()
            logger.info(f"Session stats: {stats}")
            
            # Verify session components
            if session.use_pipecat and session.pipecat_transport:
                transport_stats = session.pipecat_transport.get_stats()
                logger.info(f"Pipecat transport stats: {transport_stats}")
                
                if not transport_stats.get('running'):
                    raise Exception("Pipecat transport not running")
            
            # Cleanup session
            await session.cleanup()
            
            logger.info("Session creation test completed successfully")
            return True
            
        except Exception as e:
            logger.error(f"Session creation test failed: {e}")
            return False
    
    async def test_individual_services(self):
        """Test individual service functionality"""
        try:
            logger.info("Testing individual services...")
            
            results = {}
            
            # Test ASR service
            try:
                asr_client = self.pipeline_manager.asr_client
                if asr_client:
                    asr_health = await asr_client.health_check()
                    results['asr'] = asr_health
                    logger.info(f"ASR service health: {asr_health}")
                else:
                    results['asr'] = False
                    logger.warning("ASR client not available")
            except Exception as e:
                logger.error(f"ASR test failed: {e}")
                results['asr'] = False
            
            # Test LLM service  
            try:
                llm_client = self.pipeline_manager.llm_client
                if llm_client:
                    llm_health = await llm_client.health_check()
                    results['llm'] = llm_health
                    logger.info(f"LLM service health: {llm_health}")
                else:
                    results['llm'] = False
                    logger.warning("LLM client not available")
            except Exception as e:
                logger.error(f"LLM test failed: {e}")
                results['llm'] = False
            
            # Test TTS service
            try:
                tts_client = self.pipeline_manager.tts_client
                if tts_client:
                    tts_health = await tts_client.health_check()
                    results['tts'] = tts_health
                    logger.info(f"TTS service health: {tts_health}")
                else:
                    results['tts'] = False
                    logger.warning("TTS client not available")
            except Exception as e:
                logger.error(f"TTS test failed: {e}")
                results['tts'] = False
            
            healthy_count = sum(1 for status in results.values() if status)
            logger.info(f"Individual service test results: {results}")
            logger.info(f"Healthy services: {healthy_count}/{len(results)}")
            
            return healthy_count > 0
            
        except Exception as e:
            logger.error(f"Individual services test failed: {e}")
            return False
    
    async def test_pipeline_integration(self):
        """Test pipecat pipeline integration"""
        try:
            logger.info("Testing pipecat pipeline integration...")
            
            # Import pipecat components
            from pipecat.pipeline.pipeline import Pipeline
            from pipecat.processors.grpc_processors import (
                ASRProcessor, LLMProcessor, TTSProcessor
            )
            
            # Create test processors
            processors = []
            
            if self.pipeline_manager.asr_client:
                asr_proc = ASRProcessor(
                    asr_client=self.pipeline_manager.asr_client,
                    name="TestASRProcessor"
                )
                processors.append(asr_proc)
            
            if self.pipeline_manager.llm_client:
                llm_proc = LLMProcessor(
                    llm_client=self.pipeline_manager.llm_client,
                    conversation_id="test_conversation",
                    system_prompt="You are a test assistant.",
                    name="TestLLMProcessor"
                )
                processors.append(llm_proc)
            
            if self.pipeline_manager.tts_client:
                tts_proc = TTSProcessor(
                    tts_client=self.pipeline_manager.tts_client,
                    name="TestTTSProcessor"
                )
                processors.append(tts_proc)
            
            if not processors:
                logger.warning("No processors available for pipeline test")
                return False
            
            # Create pipeline
            pipeline = Pipeline(processors)
            
            # Test pipeline creation
            logger.info(f"Pipeline created with {len(processors)} processors")
            
            # Test pipeline start/stop
            await pipeline.start()
            await asyncio.sleep(0.1)  # Let it initialize
            await pipeline.stop()
            
            logger.info("Pipeline integration test completed successfully")
            return True
            
        except Exception as e:
            logger.error(f"Pipeline integration test failed: {e}")
            return False
    
    async def cleanup(self):
        """Cleanup test environment"""
        try:
            logger.info("Cleaning up test environment")
            
            if self.pipeline_manager:
                await self.pipeline_manager.stop()
            
            if self.service_registry:
                await self.service_registry.stop()
            
            logger.info("Test environment cleanup completed")
            
        except Exception as e:
            logger.error(f"Error cleaning up test environment: {e}")
    
    async def run_all_tests(self):
        """Run all E2E tests"""
        try:
            logger.info("🚀 Starting E2E Flow Test")
            
            # Setup
            await self.setup()
            
            # Run tests
            tests = [
                ("Service Connectivity", self.test_service_connectivity),
                ("Individual Services", self.test_individual_services),
                ("Pipeline Integration", self.test_pipeline_integration),
                ("Session Creation", self.test_session_creation),
            ]
            
            results = {}
            for test_name, test_func in tests:
                logger.info(f"\n📋 Running test: {test_name}")
                try:
                    result = await test_func()
                    results[test_name] = result
                    status = "✅ PASSED" if result else "❌ FAILED"
                    logger.info(f"{test_name}: {status}")
                except Exception as e:
                    results[test_name] = False
                    logger.error(f"{test_name}: ❌ FAILED - {e}")
            
            # Summary
            passed = sum(1 for result in results.values() if result)
            total = len(results)
            
            logger.info(f"\n📊 Test Summary:")
            logger.info(f"Tests passed: {passed}/{total}")
            
            for test_name, result in results.items():
                status = "✅" if result else "❌"
                logger.info(f"  {status} {test_name}")
            
            if passed == total:
                logger.info("🎉 All tests passed! E2E flow is working correctly.")
                return True
            elif passed > 0:
                logger.warning(f"⚠️  Partial success: {passed}/{total} tests passed.")
                return False
            else:
                logger.error("💥 All tests failed! Check service configurations.")
                return False
                
        except Exception as e:
            logger.error(f"E2E test execution failed: {e}")
            return False
        finally:
            await self.cleanup()

async def main():
    """Main test entry point"""
    # Setup logging
    setup_logging()
    
    try:
        # Run E2E tests
        test = E2EFlowTest()
        success = await test.run_all_tests()
        
        return 0 if success else 1
        
    except Exception as e:
        logger.error(f"Test execution error: {e}")
        return 1

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)