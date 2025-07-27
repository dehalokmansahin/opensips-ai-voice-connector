#!/usr/bin/env python3
"""
Test script for gRPC services
"""

import asyncio
import grpc
import sys
import os

# Add service paths for imports
sys.path.append('services/asr-service/src')
sys.path.append('services/tts-service/src')
sys.path.append('services/llm-service/src')

# Import generated protobuf files
import asr_service_pb2
import asr_service_pb2_grpc
import tts_service_pb2
import tts_service_pb2_grpc
import llm_service_simple_pb2
import llm_service_simple_pb2_grpc

from google.protobuf import empty_pb2

async def test_asr_health():
    """Test ASR service health check"""
    try:
        async with grpc.aio.insecure_channel('localhost:50051') as channel:
            stub = asr_service_pb2_grpc.ASRServiceStub(channel)
            response = await stub.HealthCheck(empty_pb2.Empty())
            status_name = asr_service_pb2.HealthResponse.Status.Name(response.status)
            print(f"ASR Health: {status_name} - {response.message}")
            print(f"   Model: {response.model_loaded}")
            return True
    except Exception as e:
        print(f"ASR Health Check Failed: {e}")
        return False

async def test_tts_health():
    """Test TTS service health check"""
    try:
        async with grpc.aio.insecure_channel('localhost:50053') as channel:
            stub = tts_service_pb2_grpc.TTSServiceStub(channel)
            response = await stub.HealthCheck(empty_pb2.Empty())
            status_name = tts_service_pb2.HealthResponse.Status.Name(response.status)
            print(f"TTS Health: {status_name} - {response.message}")
            print(f"   Model: {response.voice_model}")
            return True
    except Exception as e:
        print(f"TTS Health Check Failed: {e}")
        return False

async def test_llm_health():
    """Test LLM service health check"""
    try:
        async with grpc.aio.insecure_channel('localhost:50052') as channel:
            stub = llm_service_simple_pb2_grpc.LLMServiceStub(channel)
            response = await stub.HealthCheck(empty_pb2.Empty())
            status_name = llm_service_simple_pb2.HealthResponse.Status.Name(response.status)
            print(f"LLM Health: {status_name} - {response.message}")
            print(f"   Model: {response.model_loaded}")
            return True
    except Exception as e:
        print(f"LLM Health Check Failed: {e}")
        return False

async def test_tts_synthesis():
    """Test TTS synthesis"""
    try:
        async with grpc.aio.insecure_channel('localhost:50053') as channel:
            stub = tts_service_pb2_grpc.TTSServiceStub(channel)
            
            request = tts_service_pb2.SynthesizeRequest(
                text="Merhaba, bu bir test mesajıdır.",
                voice="tr_TR-fahrettin-medium",
                sample_rate=22050
            )
            
            print("Testing TTS synthesis...")
            chunk_count = 0
            async for response in stub.SynthesizeText(request):
                if response.HasField('started'):
                    print(f"   Started: {response.started.message}")
                elif response.HasField('audio_chunk'):
                    chunk_count += 1
                elif response.HasField('completed'):
                    print(f"   Completed: {response.completed.message}")
                    print(f"   Audio chunks: {chunk_count}")
                    print(f"   Stats: {response.completed.stats.processing_time_ms:.2f}ms")
                    
            return True
    except Exception as e:
        print(f"TTS Synthesis Test Failed: {e}")
        return False

async def test_llm_processing():
    """Test LLM text processing"""
    try:
        async with grpc.aio.insecure_channel('localhost:50052') as channel:
            stub = llm_service_simple_pb2_grpc.LLMServiceStub(channel)
            
            request = llm_service_simple_pb2.TextProcessingRequest(
                text="Merhaba, nasılsın?",
                temperature=0.2,
                max_tokens=50
            )
            
            print("Testing LLM processing...")
            response_text = ""
            async for response in stub.ProcessText(request):
                if not response.done:
                    response_text += response.chunk
                else:
                    print(f"   Response: {response_text.strip()}")
                    
            return True
    except Exception as e:
        print(f"LLM Processing Test Failed: {e}")
        return False

async def main():
    """Run all tests"""
    print("Testing OpenSIPS AI Voice Connector gRPC Services")
    print("=" * 60)
    
    tests = [
        ("ASR Health Check", test_asr_health),
        ("TTS Health Check", test_tts_health),
        ("LLM Health Check", test_llm_health),
        ("TTS Synthesis", test_tts_synthesis),
        ("LLM Processing", test_llm_processing),
    ]
    
    results = []
    for test_name, test_func in tests:
        print(f"\n[{test_name}]")
        result = await test_func()
        results.append((test_name, result))
    
    print("\n" + "=" * 60)
    print("Test Results:")
    
    passed = 0
    for test_name, result in results:
        status = "PASS" if result else "FAIL"
        print(f"   {status}: {test_name}")
        if result:
            passed += 1
    
    print(f"\nSummary: {passed}/{len(tests)} tests passed")
    
    if passed == len(tests):
        print("All gRPC services are working correctly!")
        return True
    else:
        print("Some tests failed. Check the logs above.")
        return False

if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)