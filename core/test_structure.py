#!/usr/bin/env python3
"""
Structure Verification Test for OpenSIPS AI Voice Connector
Tests that the clean structure is properly set up
"""

import sys
from pathlib import Path

# Add core to path
sys.path.insert(0, str(Path(__file__).parent))

def test_imports():
    """Test that all core modules can be imported"""
    results = {}
    
    # Test core config
    try:
        from config.settings import Settings, OpenSIPSConfig, ServicesConfig, ServiceConfig
        results['config'] = True
        print("OK Config module imports successful")
    except Exception as e:
        results['config'] = False
        print(f"FAIL Config module import failed: {e}")
    
    # Test utilities
    try:
        from utils.logging import setup_logging
        from utils.audio import convert_sample_rate
        from utils.networking import check_port_available
        results['utils'] = True
        print("OK Utils module imports successful")
    except Exception as e:
        results['utils'] = False
        print(f"FAIL Utils module import failed: {e}")
    
    # Test OpenSIPS integration
    try:
        from opensips.rtp_transport import RTPTransport
        from opensips.integration import OpenSIPSIntegration
        from opensips.event_listener import OpenSIPSEventListener
        from opensips.sip_backend import SIPBackendListener
        results['opensips'] = True
        print("OK OpenSIPS module imports successful")
    except Exception as e:
        results['opensips'] = False
        print(f"FAIL OpenSIPS module import failed: {e}")
    
    # Test pipecat integration
    try:
        from pipecat.frames.frames import Frame, AudioFrame, TextFrame
        from pipecat.pipeline.pipeline import Pipeline, FrameProcessor
        from pipecat.processors.grpc_processors import ASRProcessor, LLMProcessor, TTSProcessor
        from pipecat.transports.rtp_transport import PipecatRTPTransport
        results['pipecat'] = True
        print("OK Pipecat module imports successful")
    except Exception as e:
        results['pipecat'] = False
        print(f"FAIL Pipecat module import failed: {e}")
    
    # Test bot components (these might fail without services)
    try:
        # Try importing without gRPC clients first
        import sys
        sys.path.append('.')
        from bot.session import SessionState
        results['bot'] = True
        print("OK Bot module imports successful (basic)")
    except Exception as e:
        results['bot'] = False
        print(f"FAIL Bot module import failed: {e}")
    
    return results

def test_file_structure():
    """Test that expected files exist"""
    core_path = Path(__file__).parent
    
    expected_files = [
        "main.py",
        "config/__init__.py",
        "config/settings.py",
        "utils/__init__.py", 
        "utils/logging.py",
        "utils/audio.py",
        "utils/networking.py",
        "opensips/__init__.py",
        "opensips/integration.py",
        "opensips/rtp_transport.py",
        "opensips/event_listener.py",
        "opensips/sip_backend.py",
        "pipecat/__init__.py",
        "pipecat/frames/__init__.py",
        "pipecat/frames/frames.py",
        "pipecat/pipeline/__init__.py", 
        "pipecat/pipeline/pipeline.py",
        "pipecat/processors/__init__.py",
        "pipecat/processors/grpc_processors.py",
        "pipecat/transports/__init__.py",
        "pipecat/transports/rtp_transport.py",
        "bot/__init__.py",
        "bot/pipeline_manager.py",
        "bot/session.py"
    ]
    
    missing_files = []
    for file_path in expected_files:
        full_path = core_path / file_path
        if not full_path.exists():
            missing_files.append(file_path)
    
    if missing_files:
        print(f"FAIL Missing files: {missing_files}")
        return False
    else:
        print("OK All expected files exist")
        return True

def test_config_file():
    """Test configuration file exists"""
    config_path = Path(__file__).parent.parent / "config" / "app.ini"
    
    if config_path.exists():
        print("OK Configuration file exists")
        return True
    else:
        print("FAIL Configuration file missing")
        return False

def test_services_structure():
    """Test services directory structure"""
    services_path = Path(__file__).parent.parent / "services"
    
    expected_services = [
        "asr-service",
        "llm-service", 
        "tts-service",
        "common"
    ]
    
    missing_services = []
    for service in expected_services:
        service_path = services_path / service
        if not service_path.exists():
            missing_services.append(service)
    
    if missing_services:
        print(f"FAIL Missing services: {missing_services}")
        return False
    else:
        print("OK All expected services exist")
        return True

def main():
    """Run all structure tests"""
    print("Testing Clean Architecture Structure")
    print("=" * 50)
    
    # Test file structure
    print("\nTesting File Structure...")
    file_structure_ok = test_file_structure()
    
    # Test config
    print("\nTesting Configuration...")
    config_ok = test_config_file()
    
    # Test services
    print("\nTesting Services Structure...")
    services_ok = test_services_structure()
    
    # Test imports
    print("\nTesting Module Imports...")
    import_results = test_imports()
    
    # Summary
    print("\n" + "=" * 50)
    print("Test Summary:")
    
    total_tests = 4 + len(import_results)
    passed_tests = sum([
        file_structure_ok,
        config_ok, 
        services_ok,
        sum(import_results.values())
    ])
    
    print(f"Tests passed: {passed_tests}/{total_tests}")
    
    if file_structure_ok:
        print("  OK File structure")
    else:
        print("  FAIL File structure")
        
    if config_ok:
        print("  OK Configuration")
    else:
        print("  FAIL Configuration")
        
    if services_ok:
        print("  OK Services structure")
    else:
        print("  FAIL Services structure")
    
    for module, success in import_results.items():
        status = "OK" if success else "FAIL"
        print(f"  {status} {module} imports")
    
    if passed_tests == total_tests:
        print("\nAll structure tests passed! Clean architecture is properly set up.")
        return 0
    else:
        print(f"\n{total_tests - passed_tests} tests failed. Please check the issues above.")
        return 1

if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)