#!/usr/bin/env python3
"""
OpenSIPS Integration Test Script
Tests that all components can be imported and integrated correctly
Run with: PYTHONPATH="pipecat:src:$PYTHONPATH" python test_integration.py
"""

import sys
import os

def test_integration():
    """Test OpenSIPS voice AI integration"""
    print("OpenSIPS Voice-AI Integration Test")
    print("=" * 50)
    
    # Add paths
    current_dir = os.path.dirname(os.path.abspath(__file__))
    pipecat_path = os.path.join(current_dir, 'pipecat')
    src_path = os.path.join(current_dir, 'src')
    
    if pipecat_path not in sys.path:
        sys.path.insert(0, pipecat_path)
    if src_path not in sys.path:
        sys.path.insert(0, src_path)
    
    try:
        print("1. Testing Pipecat core imports...")
        import pipecat
        from pipecat.pipeline.pipeline import Pipeline
        from pipecat.pipeline.runner import PipelineRunner
        from pipecat.pipeline.task import PipelineTask, PipelineParams
        from pipecat.frames.frames import TextFrame, TTSStartedFrame, TTSStoppedFrame
        print("   [OK] Pipecat core imports successful")
        
        print("2. Testing transport imports...")
        from pipecat.transports.base_input import BaseInputTransport
        from pipecat.transports.base_output import BaseOutputTransport
        from pipecat.transports.base_transport import BaseTransport, TransportParams
        from pipecat.processors.frame_processor import FrameDirection
        print("   [OK] Transport imports successful")
        
        print("3. Testing VAD integration...")
        from pipecat.audio.vad.silero import SileroVADAnalyzer
        from pipecat.audio.vad.vad_analyzer import VADParams
        
        vad_analyzer = SileroVADAnalyzer(
            params=VADParams(
                confidence=0.15,
                start_secs=0.1,
                stop_secs=0.25,
                min_volume=0.0
            )
        )
        print("   [OK] VAD analyzer created successfully")
        
        print("4. Testing service imports...")
        from services.vosk_websocket import VoskWebsocketSTTService
        from services.piper_websocket import PiperWebsocketTTSService
        print("   [OK] Service imports successful")
        
        print("5. Testing transport creation...")
        # Import after path setup
        sys.path.insert(0, os.path.join(current_dir, 'src'))
        from transports.opensips_transport import create_opensips_transport
        
        transport = create_opensips_transport(
            bind_ip='127.0.0.1',
            bind_port=0,
            call_id='integration_test',
            vad_analyzer=vad_analyzer
        )
        print("   [OK] OpenSIPS transport created successfully")
        
        print("6. Testing pipeline construction...")
        # Create minimal pipeline to test architecture
        pipeline_processors = []
        if transport.input():
            pipeline_processors.append(transport.input())
        if transport.output():
            pipeline_processors.append(transport.output())
            
        if pipeline_processors:
            pipeline = Pipeline(pipeline_processors)
            print("   [OK] Pipeline created successfully")
        
        print()
        print("INTEGRATION TEST PASSED!")
        print("All components are properly integrated and ready for use.")
        print()
        print("To run the OpenSIPS bot:")
        print("  cd src")
        print("  PYTHONPATH='../pipecat:.:$PYTHONPATH' python -c 'from opensips_bot import run_opensips_bot'")
        
        return True
        
    except Exception as e:
        print(f"[ERROR] Integration test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_integration()
    sys.exit(0 if success else 1)