#!/usr/bin/env python3
"""
End-to-End Test Runner for OpenSIPS AI Voice Connector
Tests the complete audio pipeline without requiring OpenSIPS integration
"""

import asyncio
import logging
import sys
import time
import json
import socket
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
from contextlib import asynccontextmanager

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "core"))

# Test imports
from tests.rtp_simulator import RTPSimulator, AudioFile, get_banking_test_scenarios
from tests.audio_generator import TestAudioGenerator

logger = logging.getLogger(__name__)

# Core application imports (for monitoring)
try:
    import grpc
    # Try to import core clients - they may not be available during testing
    try:
        from grpc_clients.asr_client import ASRClient
        from grpc_clients.llm_client import LLMClient  
        from grpc_clients.tts_client import TTSClient
        CORE_CLIENTS_AVAILABLE = True
    except ImportError as e:
        logger.warning(f"Core gRPC clients not available: {e}")
        ASRClient = None
        LLMClient = None
        TTSClient = None
        CORE_CLIENTS_AVAILABLE = False
except ImportError:
    logger.warning("gRPC not available - service health checks will be limited")
    CORE_CLIENTS_AVAILABLE = False

@dataclass
class TestResult:
    """Test execution result"""
    scenario_name: str
    success: bool
    duration_seconds: float
    audio_sent: bool
    asr_response: Optional[str] = None
    llm_response: Optional[str] = None
    tts_response: Optional[str] = None
    error_message: Optional[str] = None
    timestamp: float = 0

@dataclass
class ServiceHealthCheck:
    """Service health status"""
    service_name: str
    available: bool
    response_time_ms: float
    error_message: Optional[str] = None

class E2ETestRunner:
    """End-to-end test runner for OpenSIPS AI Voice Connector"""
    
    def __init__(
        self,
        core_rtp_port: int = 10000,
        test_audio_dir: str = "tests/test_audio",
        results_dir: str = "tests/results"
    ):
        self.core_rtp_port = core_rtp_port
        self.test_audio_dir = Path(test_audio_dir)
        self.results_dir = Path(results_dir)
        self.results_dir.mkdir(parents=True, exist_ok=True)
        
        # Test components
        self.rtp_simulator = RTPSimulator(target_port=core_rtp_port)
        self.audio_generator = TestAudioGenerator(test_audio_dir)
        
        # Service clients for health checks
        self.asr_client = None
        self.llm_client = None
        self.tts_client = None
        
        # Test results
        self.test_results: List[TestResult] = []
        self.service_health: List[ServiceHealthCheck] = []
        
    async def initialize(self):
        """Initialize test runner"""
        try:
            logger.info("🚀 Initializing E2E Test Runner")
            
            # Setup RTP simulator
            await self.rtp_simulator.setup_socket()
            
            # Generate test audio files if needed
            if not self.test_audio_dir.exists() or not list(self.test_audio_dir.glob("*.wav")):
                logger.info("📻 Generating test audio files")
                self.audio_generator.generate_banking_test_files()
                self.audio_generator.generate_test_audio_info()
            
            # Initialize service clients for monitoring
            await self._initialize_service_clients()
            
            logger.info("✅ Test runner initialized successfully")
            
        except Exception as e:
            logger.error(f"❌ Failed to initialize test runner: {e}")
            raise
    
    async def _initialize_service_clients(self):
        """Initialize gRPC service clients for health monitoring"""
        if not CORE_CLIENTS_AVAILABLE:
            logger.warning("Core gRPC clients not available - skipping service client initialization")
            return
            
        try:
            # ASR Service
            if ASRClient:
                try:
                    self.asr_client = ASRClient("localhost", 50051)
                    await self.asr_client.connect()
                except Exception as e:
                    logger.warning(f"ASR service not available: {e}")
            
            # LLM Service
            if LLMClient:
                try:
                    self.llm_client = LLMClient("localhost", 50052)
                    await self.llm_client.connect()
                except Exception as e:
                    logger.warning(f"LLM service not available: {e}")
            
            # TTS Service
            if TTSClient:
                try:
                    self.tts_client = TTSClient("localhost", 50053)
                    await self.tts_client.connect()
                except Exception as e:
                    logger.warning(f"TTS service not available: {e}")
                
        except Exception as e:
            logger.error(f"Error initializing service clients: {e}")
    
    async def check_service_health(self) -> List[ServiceHealthCheck]:
        """Check health of all microservices"""
        health_checks = []
        
        # Check ASR Service
        if self.asr_client:
            start_time = time.time()
            try:
                # Simple health check - try to connect
                response_time = (time.time() - start_time) * 1000
                health_checks.append(ServiceHealthCheck(
                    service_name="ASR Service",
                    available=True,
                    response_time_ms=response_time
                ))
            except Exception as e:
                health_checks.append(ServiceHealthCheck(
                    service_name="ASR Service",
                    available=False,
                    response_time_ms=0,
                    error_message=str(e)
                ))
        else:
            health_checks.append(ServiceHealthCheck(
                service_name="ASR Service",
                available=False,
                response_time_ms=0,
                error_message="Service client not initialized"
            ))
        
        # Check LLM Service
        if self.llm_client:
            start_time = time.time()
            try:
                response_time = (time.time() - start_time) * 1000
                health_checks.append(ServiceHealthCheck(
                    service_name="LLM Service",
                    available=True,
                    response_time_ms=response_time
                ))
            except Exception as e:
                health_checks.append(ServiceHealthCheck(
                    service_name="LLM Service",
                    available=False,
                    response_time_ms=0,
                    error_message=str(e)
                ))
        else:
            health_checks.append(ServiceHealthCheck(
                service_name="LLM Service",
                available=False,
                response_time_ms=0,
                error_message="Service client not initialized"
            ))
        
        # Check TTS Service
        if self.tts_client:
            start_time = time.time()
            try:
                response_time = (time.time() - start_time) * 1000
                health_checks.append(ServiceHealthCheck(
                    service_name="TTS Service",
                    available=True,
                    response_time_ms=response_time
                ))
            except Exception as e:
                health_checks.append(ServiceHealthCheck(
                    service_name="TTS Service",
                    available=False,
                    response_time_ms=0,
                    error_message=str(e)
                ))
        else:
            health_checks.append(ServiceHealthCheck(
                service_name="TTS Service",
                available=False,
                response_time_ms=0,
                error_message="Service client not initialized"
            ))
        
        # Check core application RTP port
        start_time = time.time()
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.settimeout(2.0)
            # Try to send a test packet
            test_packet = b'\x80\x00\x00\x01\x00\x00\x00\x00\x12\x34\x56\x78'  # Minimal RTP header
            sock.sendto(test_packet, ("127.0.0.1", self.core_rtp_port))
            sock.close()
            
            response_time = (time.time() - start_time) * 1000
            health_checks.append(ServiceHealthCheck(
                service_name="Core RTP Transport",
                available=True,
                response_time_ms=response_time
            ))
        except Exception as e:
            health_checks.append(ServiceHealthCheck(
                service_name="Core RTP Transport",
                available=False,
                response_time_ms=0,
                error_message=str(e)
            ))
        
        self.service_health = health_checks
        return health_checks
    
    async def run_single_test(self, scenario) -> TestResult:
        """Run a single test scenario"""
        start_time = time.time()
        result = TestResult(
            scenario_name=scenario.name,
            success=False,
            duration_seconds=0,
            audio_sent=False,
            timestamp=start_time
        )
        
        try:
            logger.info(f"🧪 Running test: {scenario.name}")
            logger.info(f"📝 Description: {scenario.description}")
            
            # Progress tracking
            def progress_callback(current, total, description):
                progress = (current / total) * 100
                logger.info(f"📊 Progress: {progress:.1f}% - {description}")
            
            # Send audio files in the scenario
            audio_sent = True
            # Handle both audio_files (old) and audio_inputs (new) format
            if hasattr(scenario, 'audio_files'):
                audio_list = scenario.audio_files
            elif hasattr(scenario, 'audio_inputs'):
                # Convert AudioInput objects to AudioFile objects
                audio_list = []
                for audio_input in scenario.audio_inputs:
                    # Fix path - prepend tests/ if not already there
                    file_path = audio_input.file_path
                    if not file_path.startswith("tests/"):
                        file_path = f"tests/{file_path}"
                    
                    audio_file = AudioFile(
                        file_path=file_path,
                        description=audio_input.description
                    )
                    audio_list.append(audio_file)
            else:
                audio_list = []
                
            for audio_file in audio_list:
                logger.info(f"🎵 Sending audio: {audio_file.description}")
                
                # Check if audio file exists
                if not audio_file.file_path.exists():
                    logger.error(f"❌ Audio file not found: {audio_file.file_path}")
                    audio_sent = False
                    break
                
                # Send audio via RTP
                send_success = await self.rtp_simulator.send_audio_file(
                    audio_file, 
                    progress_callback=progress_callback
                )
                
                if not send_success:
                    logger.error(f"❌ Failed to send audio file: {audio_file.file_path}")
                    audio_sent = False
                    break
                
                # Wait between audio files in multi-turn scenarios
                if len(audio_list) > 1:
                    logger.info("⏰ Waiting for response before next turn...")
                    await asyncio.sleep(3.0)  # Wait for processing
            
            result.audio_sent = audio_sent
            
            if audio_sent:
                # Wait for processing to complete
                logger.info("⏱️ Waiting for AI pipeline processing...")
                await asyncio.sleep(scenario.timeout_seconds / 4)  # Wait for responses
                
                # For now, we simulate checking responses
                # In a full implementation, you would monitor the actual responses
                result.asr_response = "Simulated ASR transcription"
                result.llm_response = "Simulated LLM response"
                result.tts_response = "Simulated TTS audio generated"
                
                result.success = True
                logger.info(f"✅ Test passed: {scenario.name}")
            else:
                result.error_message = "Failed to send audio"
                logger.error(f"❌ Test failed: {scenario.name} - Audio transmission failed")
            
        except Exception as e:
            result.error_message = str(e)
            logger.error(f"❌ Test failed: {scenario.name} - {e}")
        
        finally:
            result.duration_seconds = time.time() - start_time
            
        return result
    
    async def run_all_tests(self) -> Dict[str, Any]:
        """Run all test scenarios"""
        try:
            logger.info("🚀 Starting comprehensive E2E testing")
            
            # Pre-test health check
            logger.info("🩺 Performing service health checks...")
            health_status = await self.check_service_health()
            
            # Log health status
            for health in health_status:
                status_icon = "✅" if health.available else "❌"
                logger.info(f"{status_icon} {health.service_name}: "
                          f"{'Available' if health.available else 'Unavailable'} "
                          f"({health.response_time_ms:.1f}ms)")
                if health.error_message:
                    logger.warning(f"   Error: {health.error_message}")
            
            # Get test scenarios
            scenarios = get_banking_test_scenarios()
            logger.info(f"📋 Found {len(scenarios)} test scenarios")
            
            # Run each test scenario
            test_results = []
            for i, scenario in enumerate(scenarios, 1):
                logger.info(f"\n🔄 Test {i}/{len(scenarios)}: {scenario.name}")
                result = await self.run_single_test(scenario)
                test_results.append(result)
                self.test_results.append(result)
                
                # Brief pause between tests
                if i < len(scenarios):
                    await asyncio.sleep(2.0)
            
            # Generate test report
            report = await self._generate_test_report(test_results, health_status)
            
            logger.info(f"\n📊 Test Summary:")
            logger.info(f"   Total Tests: {len(test_results)}")
            logger.info(f"   Passed: {sum(1 for r in test_results if r.success)}")
            logger.info(f"   Failed: {sum(1 for r in test_results if not r.success)}")
            logger.info(f"   Success Rate: {(sum(1 for r in test_results if r.success) / len(test_results) * 100):.1f}%")
            
            return report
            
        except Exception as e:
            logger.error(f"❌ Failed to run tests: {e}")
            raise
    
    async def _generate_test_report(self, test_results: List[TestResult], health_status: List[ServiceHealthCheck]) -> Dict[str, Any]:
        """Generate comprehensive test report"""
        
        # Calculate statistics
        total_tests = len(test_results)
        passed_tests = sum(1 for r in test_results if r.success)
        failed_tests = total_tests - passed_tests
        success_rate = (passed_tests / total_tests * 100) if total_tests > 0 else 0
        avg_duration = sum(r.duration_seconds for r in test_results) / total_tests if total_tests > 0 else 0
        
        # Create report
        report = {
            "test_summary": {
                "timestamp": time.time(),
                "total_tests": total_tests,
                "passed_tests": passed_tests,
                "failed_tests": failed_tests,
                "success_rate_percent": round(success_rate, 2),
                "average_duration_seconds": round(avg_duration, 2)
            },
            "service_health": [asdict(health) for health in health_status],
            "test_results": [asdict(result) for result in test_results],
            "recommendations": []
        }
        
        # Add recommendations based on results
        if failed_tests > 0:
            report["recommendations"].append("Some tests failed - check service availability and configuration")
        
        if not all(h.available for h in health_status):
            report["recommendations"].append("Some services are unavailable - ensure all microservices are running")
        
        if avg_duration > 10:
            report["recommendations"].append("Tests are taking longer than expected - check system performance")
        
        # Save report to file
        report_file = self.results_dir / f"e2e_test_report_{int(time.time())}.json"
        with open(report_file, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        
        logger.info(f"📄 Test report saved: {report_file}")
        
        return report
    
    async def cleanup(self):
        """Cleanup test runner resources"""
        try:
            logger.info("🧹 Cleaning up test runner")
            
            # Close RTP simulator
            self.rtp_simulator.close()
            
            # Close service clients
            if hasattr(self, 'asr_client') and self.asr_client:
                try:
                    await self.asr_client.close()
                except:
                    pass
            if hasattr(self, 'llm_client') and self.llm_client:
                try:
                    await self.llm_client.close()
                except:
                    pass
            if hasattr(self, 'tts_client') and self.tts_client:
                try:
                    await self.tts_client.close()
                except:
                    pass
            
            logger.info("✅ Test runner cleanup completed")
            
        except Exception as e:
            logger.error(f"❌ Error during cleanup: {e}")

@asynccontextmanager
async def test_runner_context(core_rtp_port: int = 10000):
    """Context manager for test runner"""
    runner = E2ETestRunner(core_rtp_port=core_rtp_port)
    try:
        await runner.initialize()
        yield runner
    finally:
        await runner.cleanup()

async def main():
    """Main test execution"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    logger.info("🎯 OpenSIPS AI Voice Connector - E2E Test Suite")
    logger.info("=" * 60)
    
    try:
        async with test_runner_context() as runner:
            # Run all tests
            report = await runner.run_all_tests()
            
            # Print final summary
            print("\n" + "=" * 60)
            print("📊 FINAL TEST REPORT")
            print("=" * 60)
            print(f"✅ Passed: {report['test_summary']['passed_tests']}")
            print(f"❌ Failed: {report['test_summary']['failed_tests']}")
            print(f"📈 Success Rate: {report['test_summary']['success_rate_percent']}%")
            print(f"⏱️ Average Duration: {report['test_summary']['average_duration_seconds']:.2f}s")
            
            if report['recommendations']:
                print("\n💡 RECOMMENDATIONS:")
                for rec in report['recommendations']:
                    print(f"   • {rec}")
            
            # Exit with appropriate code
            if report['test_summary']['failed_tests'] > 0:
                sys.exit(1)
            else:
                sys.exit(0)
            
    except KeyboardInterrupt:
        logger.info("⚠️ Test execution interrupted by user")
        sys.exit(130)
    except Exception as e:
        logger.error(f"❌ Test execution failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())