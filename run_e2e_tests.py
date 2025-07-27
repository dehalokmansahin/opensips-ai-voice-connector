#!/usr/bin/env python3
"""
Quick Test Execution Script for OpenSIPS AI Voice Connector
Provides easy commands to run different types of tests
"""

import asyncio
import argparse
import logging
import sys
from pathlib import Path

# Add tests to path
sys.path.insert(0, str(Path(__file__).parent / "tests"))

from tests.e2e_test_runner import test_runner_context
from tests.test_scenarios import (
    BankingTestScenarios, 
    TestType, 
    get_scenarios_by_type,
    get_mvp_scenarios
)
from tests.audio_generator import TestAudioGenerator

def setup_logging(verbose: bool = False):
    """Setup logging configuration"""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

async def run_mvp_tests(core_port: int = 10000):
    """Run only MVP core tests"""
    print("Running MVP Core Tests")
    print("=" * 50)
    
    async with test_runner_context(core_port) as runner:
        # Get MVP scenarios
        mvp_scenarios = get_mvp_scenarios()
        
        if not mvp_scenarios:
            print("[ERROR] No MVP scenarios found!")
            return False
        
        print(f"[INFO] Found {len(mvp_scenarios)} MVP scenarios")
        
        # Run each MVP scenario
        all_passed = True
        for i, scenario in enumerate(mvp_scenarios, 1):
            print(f"\n[TEST] MVP Test {i}/{len(mvp_scenarios)}: {scenario.name}")
            result = await runner.run_single_test(scenario)
            
            if result.success:
                print(f"[PASS] {scenario.name} ({result.duration_seconds:.2f}s)")
            else:
                print(f"[FAIL] {scenario.name} - {result.error_message}")
                all_passed = False
        
        return all_passed

async def run_quick_tests(core_port: int = 10000):
    """Run quick test suite (MVP + basic conversation)"""
    print("Running Quick Test Suite")
    print("=" * 50)
    
    async with test_runner_context(core_port) as runner:
        # Get high priority scenarios
        scenarios = []
        scenarios.extend(get_scenarios_by_type(TestType.MVP_CORE))
        scenarios.extend([s for s in get_scenarios_by_type(TestType.CONVERSATION_FLOW) if s.priority <= 2])
        
        print(f"[INFO] Found {len(scenarios)} quick test scenarios")
        
        # Run scenarios
        all_passed = True
        for i, scenario in enumerate(scenarios, 1):
            print(f"\n[TEST] Quick Test {i}/{len(scenarios)}: {scenario.name}")
            result = await runner.run_single_test(scenario)
            
            if result.success:
                print(f"[PASS] {scenario.name} ({result.duration_seconds:.2f}s)")
            else:
                print(f"[FAIL] {scenario.name} - {result.error_message}")
                all_passed = False
        
        return all_passed

async def run_full_tests(core_port: int = 10000):
    """Run complete test suite"""
    print("Running Full Test Suite")
    print("=" * 50)
    
    async with test_runner_context(core_port) as runner:
        report = await runner.run_all_tests()
        
        success = report['test_summary']['failed_tests'] == 0
        return success

async def generate_test_audio():
    """Generate test audio files"""
    print("Generating Test Audio Files")
    print("=" * 50)
    
    try:
        generator = TestAudioGenerator("tests/test_audio")
        generator.generate_banking_test_files()
        readme_path = generator.generate_test_audio_info()
        
        print(f"[OK] Test audio files generated in: tests/test_audio/")
        print(f"[INFO] Documentation created: {readme_path}")
        return True
        
    except Exception as e:
        print(f"[ERROR] Failed to generate test audio: {e}")
        return False

async def check_services(core_port: int = 10000):
    """Check service health only"""
    print("Checking Service Health")
    print("=" * 50)
    
    async with test_runner_context(core_port) as runner:
        health_checks = await runner.check_service_health()
        
        print("\n[INFO] Service Health Report:")
        all_healthy = True
        
        for health in health_checks:
            status_icon = "[OK]" if health.available else "[FAIL]"
            print(f"{status_icon} {health.service_name}")
            print(f"   Status: {'Available' if health.available else 'Unavailable'}")
            print(f"   Response Time: {health.response_time_ms:.1f}ms")
            if health.error_message:
                print(f"   Error: {health.error_message}")
            print()
            
            if not health.available:
                all_healthy = False
        
        if all_healthy:
            print("[INFO] All services are healthy!")
        else:
            print("[WARN] Some services have issues - check Docker containers")
        
        return all_healthy

def main():
    """Main CLI interface"""
    parser = argparse.ArgumentParser(
        description="OpenSIPS AI Voice Connector - E2E Testing Suite",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python run_e2e_tests.py mvp                    # Run MVP tests only
  python run_e2e_tests.py quick                  # Run quick test suite
  python run_e2e_tests.py full                   # Run complete test suite
  python run_e2e_tests.py generate-audio         # Generate test audio files
  python run_e2e_tests.py check-services         # Check service health only
  python run_e2e_tests.py mvp --port 10001       # Use custom RTP port
        """
    )
    
    parser.add_argument(
        'command',
        choices=['mvp', 'quick', 'full', 'generate-audio', 'check-services'],
        help='Test command to execute'
    )
    
    parser.add_argument(
        '--port',
        type=int,
        default=10000,
        help='Core application RTP port (default: 10000)'
    )
    
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Enable verbose logging'
    )
    
    args = parser.parse_args()
    
    # Setup logging
    setup_logging(args.verbose)
    
    # Execute command
    try:
        if args.command == 'mvp':
            success = asyncio.run(run_mvp_tests(args.port))
        elif args.command == 'quick':
            success = asyncio.run(run_quick_tests(args.port))
        elif args.command == 'full':
            success = asyncio.run(run_full_tests(args.port))
        elif args.command == 'generate-audio':
            success = asyncio.run(generate_test_audio())
        elif args.command == 'check-services':
            success = asyncio.run(check_services(args.port))
        else:
            print(f"[ERROR] Unknown command: {args.command}")
            return 1
        
        if success:
            print("\n[INFO] All tests completed successfully!")
            return 0
        else:
            print("\n[ERROR] Some tests failed or services unavailable")
            return 1
            
    except KeyboardInterrupt:
        print("\n[WARN] Tests interrupted by user")
        return 130
    except Exception as e:
        print(f"\n[ERROR] Test execution failed: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(main())