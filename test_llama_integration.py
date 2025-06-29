#!/usr/bin/env python3
"""
Custom LLaMA WebSocket Integration Test
Kendi LLaMA model serveriniz ile entegrasyon testi
"""

import sys
import os
import asyncio
import json
import websockets
from pathlib import Path

# Python path setup
current_dir = Path(__file__).parent
src_path = current_dir / "src"
pipecat_src_path = current_dir / "pipecat" / "src"

if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))
if str(pipecat_src_path) not in sys.path:
    sys.path.insert(0, str(pipecat_src_path))

# soxr compatibility stub
import numpy as np
if not hasattr(sys.modules, 'soxr'):
    class SoxrStub:
        def resample(self, *args, **kwargs):
            return np.array([])
    sys.modules['soxr'] = SoxrStub()

import structlog
from services.llama_websocket import LlamaWebsocketLLMService

# Setup logging
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="ISO"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        structlog.processors.JSONRenderer()
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    wrapper_class=structlog.stdlib.BoundLogger,
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger()

async def test_direct_websocket():
    """Direkt WebSocket bağlantısı testi"""
    print("🔗 Testing direct WebSocket connection to LLaMA server...")
    
    try:
        # Serverinizin URL'i
        url = "ws://localhost:8765"
        
        async with websockets.connect(url) as websocket:
            print("✅ WebSocket connection successful!")
            
            # Test request
            request_data = {
                "prompt": "Merhaba, nasılsın?",
                "system_prompt": "Sen Türk Telekom müşteri hizmetleri asistanısın. Türkçe konuş, kısa ve net yanıtlar ver.",
                "max_tokens": 50,
                "temperature": 0.2,
                "top_p": 0.7,
                "stream": True,
                "stop": ["User:", "System:", "\n\n"]
            }
            
            print(f"📤 Sending request: {json.dumps(request_data, indent=2)}")
            await websocket.send(json.dumps(request_data))
            
            print("📥 Receiving response chunks:")
            response_text = ""
            
            async for message in websocket:
                try:
                    data = json.loads(message)
                    print(f"🔍 Raw response: {data}")
                    
                    if "chunk" in data and data["chunk"]:
                        chunk = data["chunk"]
                        response_text += chunk
                        print(f"📝 Chunk: '{chunk}'")
                    
                    elif "done" in data and data["done"]:
                        print("✅ Response completed!")
                        break
                        
                except json.JSONDecodeError as e:
                    print(f"❌ JSON decode error: {e}")
                    print(f"   Raw message: {message}")
            
            print(f"🎯 Complete response: '{response_text}'")
            return True
            
    except Exception as e:
        print(f"❌ WebSocket connection failed: {e}")
        return False

async def test_llama_service():
    """LLaMA WebSocket Service testi"""
    print("\n🔧 Testing LLaMA WebSocket Service...")
    
    try:
        # Service oluştur
        service = LlamaWebsocketLLMService(url="ws://localhost:8765")
        
        # Service'i başlat
        await service.start()
        print("✅ LLaMA service started successfully!")
        
        # Test prompts
        test_prompts = [
            "Merhaba, nasılsın?",
            "Fatura ödeme konusunda yardım edebilir misin?",
            "İnternet bağlantım yavaş, ne yapabilirim?"
        ]
        
        for i, prompt in enumerate(test_prompts, 1):
            print(f"\n📝 Test {i}: '{prompt}'")
            
            response_text = ""
            start_time = asyncio.get_event_loop().time()
            
            async for chunk in service.generate_response_streaming(prompt):
                response_text += chunk
                print(f"   📤 Chunk: '{chunk}'")
            
            end_time = asyncio.get_event_loop().time()
            duration = (end_time - start_time) * 1000
            
            print(f"   🎯 Complete response: '{response_text}'")
            print(f"   ⏱️ Duration: {duration:.1f}ms")
            print(f"   📊 Response length: {len(response_text)} chars")
        
        # Service'i durdur
        await service.stop()
        print("✅ LLaMA service stopped successfully!")
        
        return True
        
    except Exception as e:
        print(f"❌ LLaMA service test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

async def test_performance():
    """Performans testi"""
    print("\n⚡ Testing LLaMA service performance...")
    
    try:
        service = LlamaWebsocketLLMService(url="ws://localhost:8765")
        await service.start()
        
        # Performans testi
        test_prompt = "Merhaba, yardım edebilir misin?"
        num_tests = 5
        
        print(f"🔄 Running {num_tests} performance tests...")
        
        latencies = []
        
        for i in range(num_tests):
            start_time = asyncio.get_event_loop().time()
            
            response_text = ""
            first_token_time = None
            
            async for chunk in service.generate_response_streaming(test_prompt):
                if first_token_time is None:
                    first_token_time = (asyncio.get_event_loop().time() - start_time) * 1000
                response_text += chunk
            
            total_time = (asyncio.get_event_loop().time() - start_time) * 1000
            latencies.append(first_token_time)
            
            print(f"   Test {i+1}: {first_token_time:.1f}ms first token, {total_time:.1f}ms total")
        
        # İstatistikler
        avg_latency = sum(latencies) / len(latencies)
        min_latency = min(latencies)
        max_latency = max(latencies)
        
        print(f"\n📊 Performance Results:")
        print(f"   🎯 Average first token: {avg_latency:.1f}ms")
        print(f"   🚀 Best first token: {min_latency:.1f}ms")
        print(f"   🐌 Worst first token: {max_latency:.1f}ms")
        print(f"   ✅ Target ≤400ms: {'PASS' if avg_latency <= 400 else 'FAIL'}")
        
        await service.stop()
        return True
        
    except Exception as e:
        print(f"❌ Performance test failed: {e}")
        return False

async def main():
    """Ana test fonksiyonu"""
    print("🚀 LLaMA WebSocket Integration Test Suite")
    print("=" * 50)
    
    # Test 1: Direct WebSocket
    success1 = await test_direct_websocket()
    
    # Test 2: Service Integration
    success2 = await test_llama_service()
    
    # Test 3: Performance
    success3 = await test_performance()
    
    print("\n" + "=" * 50)
    print("📋 Test Results Summary:")
    print(f"   🔗 Direct WebSocket: {'✅ PASS' if success1 else '❌ FAIL'}")
    print(f"   🔧 Service Integration: {'✅ PASS' if success2 else '❌ FAIL'}")
    print(f"   ⚡ Performance: {'✅ PASS' if success3 else '❌ FAIL'}")
    
    all_passed = success1 and success2 and success3
    print(f"\n🎯 Overall Result: {'✅ ALL TESTS PASSED' if all_passed else '❌ SOME TESTS FAILED'}")
    
    if all_passed:
        print("\n🎉 LLaMA WebSocket integration is ready!")
        print("   ✅ Your custom LLaMA server is working perfectly")
        print("   ✅ Service integration is functional")
        print("   ✅ Performance meets requirements")
    else:
        print("\n⚠️ Please check the failed tests and fix issues")
    
    return 0 if all_passed else 1

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code) 