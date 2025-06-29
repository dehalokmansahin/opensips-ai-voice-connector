#!/usr/bin/env python3
"""
LLM Streaming Performance Test
"""

import sys
import os
import time
import asyncio

# Python path ekle
current_dir = os.path.dirname(os.path.abspath(__file__))
src_path = os.path.join(current_dir, "src")
pipecat_src_path = os.path.join(current_dir, "pipecat", "src")

if src_path not in sys.path:
    sys.path.insert(0, src_path)
if pipecat_src_path not in sys.path:
    sys.path.insert(0, pipecat_src_path)

# soxr stub
import numpy as np
if not hasattr(sys.modules, 'soxr'):
    class SoxrStub:
        def resample(self, *args, **kwargs):
            return np.array([])
    sys.modules['soxr'] = SoxrStub()

from services.ollama_llm import OllamaLLMService

async def test_streaming_vs_regular():
    """Streaming vs Regular LLM yanıt süresi karşılaştırması"""
    
    print("🚀 LLM Streaming Performance Test")
    print("=" * 50)
    
    service = OllamaLLMService()
    await service.start()
    
    test_messages = [
        "Merhaba, nasılsınız?",
        "Kredi kartı başvurusu yapmak istiyorum",
        "Hesap bakiyemi öğrenebilir miyim?",
        "Bu günün tarihi nedir?",
        "Teşekkürler, iyi günler"
    ]
    
    for i, message in enumerate(test_messages, 1):
        print(f"\n📝 Test {i}: {message}")
        
        # 1. Regular (non-streaming) test
        print("🔄 Regular LLM:")
        start_time = time.time()
        
        try:
            response = await service.generate_response(message)
            end_time = time.time()
            regular_duration = (end_time - start_time) * 1000
            
            print(f"  ⏱️ Total: {regular_duration:.0f}ms")
            print(f"  📝 Response: {response[:80]}...")
            
        except Exception as e:
            print(f"  ❌ Error: {e}")
            regular_duration = 0
        
        # 2. Streaming test
        print("⚡ Streaming LLM:")
        start_time = time.time()
        first_token_time = None
        token_count = 0
        full_response = ""
        
        try:
            async for token in service.generate_response_streaming(message):
                if first_token_time is None:
                    first_token_time = time.time()
                    first_token_latency = (first_token_time - start_time) * 1000
                    print(f"  🎯 First token: {first_token_latency:.0f}ms")
                
                token_count += 1
                full_response += token
            
            end_time = time.time()
            total_duration = (end_time - start_time) * 1000
            
            print(f"  ⏱️ Total: {total_duration:.0f}ms")
            print(f"  🔢 Tokens: {token_count}")
            print(f"  📝 Response: {full_response[:80]}...")
            
            # Performance comparison
            if regular_duration > 0:
                improvement = ((regular_duration - (first_token_time - start_time) * 1000) / regular_duration) * 100
                print(f"  📊 First token improvement: {improvement:.1f}%")
                
        except Exception as e:
            print(f"  ❌ Error: {e}")
    
    await service.stop()

async def test_streaming_pipeline():
    """Pipeline streaming test"""
    
    print("\n🔗 Pipeline Streaming Test")
    print("=" * 30)
    
    from pipeline.stages import LLMProcessor
    from pipecat.frames.frames import TranscriptionFrame, StartFrame, EndFrame
    
    # Mock pipeline için basit frame collector
    class FrameCollector:
        def __init__(self):
            self.frames = []
            self.first_llm_frame_time = None
            self.start_time = None
        
        async def process_frame(self, frame, direction=None):
            if self.start_time is None:
                self.start_time = time.time()
            
            self.frames.append(frame)
            
            # İlk LLM text frame timing
            if hasattr(frame, 'text') and frame.text and self.first_llm_frame_time is None:
                self.first_llm_frame_time = time.time()
                latency = (self.first_llm_frame_time - self.start_time) * 1000
                print(f"  🎯 First LLM token: {latency:.0f}ms")
                print(f"  📝 Token: '{frame.text}'")
    
    # LLM processor test
    llm_processor = LLMProcessor()
    frame_collector = FrameCollector()
    llm_processor._next_processor = frame_collector
    
    # Start the processor
    await llm_processor.process_frame(StartFrame())
    
    # Test transcription
    test_text = "Merhaba, kredi kartı başvurusu yapmak istiyorum"
    print(f"📝 Input: {test_text}")
    
    transcription_frame = TranscriptionFrame(text=test_text, user_id="test", timestamp=time.time())
    
    start_time = time.time()
    await llm_processor.process_frame(transcription_frame)
    end_time = time.time()
    
    total_duration = (end_time - start_time) * 1000
    print(f"⏱️ Total pipeline: {total_duration:.0f}ms")
    print(f"🔢 Total frames: {len(frame_collector.frames)}")
    
    # Stop the processor
    await llm_processor.process_frame(EndFrame())

async def test_real_time_simulation():
    """Gerçek zamanlı konuşma simülasyonu"""
    
    print("\n🎙️ Real-time Conversation Simulation")
    print("=" * 40)
    
    service = OllamaLLMService()
    await service.start()
    
    conversation = [
        "Merhaba",
        "Kredi kartı başvurusu yapmak istiyorum",
        "Aylık gelirim 15 bin lira",
        "Evet, çalışma belgem var",
        "Teşekkürler"
    ]
    
    total_conversation_time = 0
    
    for i, user_input in enumerate(conversation, 1):
        print(f"\n👤 Kullanıcı: {user_input}")
        
        start_time = time.time()
        first_token_received = False
        response_text = ""
        
        print("🤖 Asistan: ", end="", flush=True)
        
        async for token in service.generate_response_streaming(user_input):
            if not first_token_received:
                first_token_time = time.time()
                first_token_latency = (first_token_time - start_time) * 1000
                print(f"[{first_token_latency:.0f}ms] ", end="", flush=True)
                first_token_received = True
            
            print(token, end="", flush=True)
            response_text += token
            
            # Simulate real-time typing (optional)
            await asyncio.sleep(0.01)  # 10ms per token
        
        end_time = time.time()
        total_time = (end_time - start_time) * 1000
        total_conversation_time += total_time
        
        print(f" [{total_time:.0f}ms total]")
    
    print(f"\n📊 Conversation Summary:")
    print(f"  Total time: {total_conversation_time:.0f}ms")
    print(f"  Average per exchange: {total_conversation_time/len(conversation):.0f}ms")
    
    await service.stop()

if __name__ == "__main__":
    print("🧪 LLM Streaming Performance Test Suite")
    print("=" * 50)
    
    asyncio.run(test_streaming_vs_regular())
    asyncio.run(test_streaming_pipeline())
    asyncio.run(test_real_time_simulation())
    
    print("\n🎉 Streaming tests completed!")
    print("\n📈 Expected improvements:")
    print("  • First token latency: 400-800ms (vs 2000+ms)")
    print("  • User experience: Immediate response start")
    print("  • Pipeline throughput: Higher concurrent capacity") 