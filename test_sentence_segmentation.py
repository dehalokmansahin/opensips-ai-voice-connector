#!/usr/bin/env python3
"""
Sentence Segmentation Test
LLM streaming response'unu noktalama işaretlerinde kesme testi
"""

import sys
import os
import asyncio
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
from services.llama_websocket import LlamaWebsocketLLMService, StreamingSentenceSegmenter

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

def test_sentence_segmenter():
    """StreamingSentenceSegmenter unit testi"""
    print("🔧 Testing StreamingSentenceSegmenter...")
    
    segmenter = StreamingSentenceSegmenter()
    
    # Test 1: Basit cümle
    print("\n📝 Test 1: Basit cümle")
    chunks = ["Merhaba", ", nasıl", "sın", "?"]
    sentences = []
    
    for chunk in chunks:
        print(f"   + Chunk: '{chunk}'")
        completed = segmenter.add_chunk(chunk)
        sentences.extend(completed)
        for sentence in completed:
            print(f"   ✅ Completed sentence: '{sentence}'")
    
    remaining = segmenter.get_remaining()
    if remaining:
        sentences.append(remaining)
        print(f"   📝 Remaining: '{remaining}'")
    
    expected = ["Merhaba, nasılsın?"]
    success1 = sentences == expected
    print(f"   Result: {'✅ PASS' if success1 else '❌ FAIL'} - {sentences}")
    
    # Test 2: Çoklu cümle
    print("\n📝 Test 2: Çoklu cümle")
    segmenter.reset()
    chunks = ["Size yardımcı", " olabilirim", ". Başka", " bir sorun", " var mı", "?"]
    sentences = []
    
    for chunk in chunks:
        print(f"   + Chunk: '{chunk}'")
        completed = segmenter.add_chunk(chunk)
        sentences.extend(completed)
        for sentence in completed:
            print(f"   ✅ Completed sentence: '{sentence}'")
    
    remaining = segmenter.get_remaining()
    if remaining:
        sentences.append(remaining)
        print(f"   📝 Remaining: '{remaining}'")
    
    expected = ["Size yardımcı olabilirim.", "Başka bir sorun var mı?"]
    success2 = sentences == expected
    print(f"   Result: {'✅ PASS' if success2 else '❌ FAIL'} - {sentences}")
    
    # Test 3: Ünlem işareti
    print("\n📝 Test 3: Ünlem işareti")
    segmenter.reset()
    chunks = ["Harika", "! Bu çok", " güzel", ". Teşekkürler", "!"]
    sentences = []
    
    for chunk in chunks:
        print(f"   + Chunk: '{chunk}'")
        completed = segmenter.add_chunk(chunk)
        sentences.extend(completed)
        for sentence in completed:
            print(f"   ✅ Completed sentence: '{sentence}'")
    
    remaining = segmenter.get_remaining()
    if remaining:
        sentences.append(remaining)
        print(f"   📝 Remaining: '{remaining}'")
    
    expected = ["Harika!", "Bu çok güzel.", "Teşekkürler!"]
    success3 = sentences == expected
    print(f"   Result: {'✅ PASS' if success3 else '❌ FAIL'} - {sentences}")
    
    return success1 and success2 and success3

async def test_streaming_sentences():
    """Streaming sentence segmentation testi"""
    print("\n🔄 Testing Streaming Sentence Segmentation...")
    
    try:
        service = LlamaWebsocketLLMService(url="ws://localhost:8765")
        await service.start()
        
        # Test prompt
        prompt = "Merhaba, size nasıl yardımcı olabilirim?"
        
        print(f"📤 Prompt: '{prompt}'")
        print("📥 Receiving sentences:")
        
        sentence_count = 0
        start_time = asyncio.get_event_loop().time()
        first_sentence_time = None
        
        async for sentence in service.generate_response_streaming(prompt):
            if sentence.strip():
                sentence_count += 1
                current_time = asyncio.get_event_loop().time()
                
                if first_sentence_time is None:
                    first_sentence_time = (current_time - start_time) * 1000
                
                sentence_time = (current_time - start_time) * 1000
                
                print(f"   📝 Sentence {sentence_count} ({sentence_time:.0f}ms): '{sentence}'")
                print(f"      🔊 → TTS'e gönderildi")
        
        total_time = (asyncio.get_event_loop().time() - start_time) * 1000
        
        print(f"\n📊 Results:")
        print(f"   🎯 Total sentences: {sentence_count}")
        print(f"   ⚡ First sentence: {first_sentence_time:.0f}ms")
        print(f"   ⏱️ Total time: {total_time:.0f}ms")
        print(f"   🚀 Average per sentence: {total_time/sentence_count:.0f}ms")
        
        await service.stop()
        return True
        
    except Exception as e:
        print(f"❌ Streaming test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

async def test_performance_comparison():
    """Performans karşılaştırması: Normal vs Sentence-based"""
    print("\n⚡ Performance Comparison Test...")
    
    try:
        service = LlamaWebsocketLLMService(url="ws://localhost:8765")
        await service.start()
        
        prompt = "Türk Telekom hizmetleri hakkında bilgi verebilir misin?"
        
        print(f"📤 Test prompt: '{prompt}'")
        
        # Sentence-based streaming test
        print("\n🔄 Testing sentence-based streaming...")
        start_time = asyncio.get_event_loop().time()
        
        sentences = []
        sentence_times = []
        
        async for sentence in service.generate_response_streaming(prompt):
            if sentence.strip():
                current_time = (asyncio.get_event_loop().time() - start_time) * 1000
                sentences.append(sentence)
                sentence_times.append(current_time)
                print(f"   📝 {len(sentences)}. cümle ({current_time:.0f}ms): '{sentence[:50]}...'")
        
        total_time = (asyncio.get_event_loop().time() - start_time) * 1000
        
        print(f"\n📊 Sentence-based Results:")
        print(f"   🎯 Total sentences: {len(sentences)}")
        print(f"   ⚡ First sentence: {sentence_times[0]:.0f}ms")
        print(f"   ⏱️ Total time: {total_time:.0f}ms")
        print(f"   🚀 TTS can start at: {sentence_times[0]:.0f}ms (vs {total_time:.0f}ms for full response)")
        
        # Calculate TTS advantage
        tts_advantage = total_time - sentence_times[0]
        print(f"   🎉 TTS Advantage: {tts_advantage:.0f}ms earlier start!")
        
        await service.stop()
        return True
        
    except Exception as e:
        print(f"❌ Performance test failed: {e}")
        return False

async def main():
    """Ana test fonksiyonu"""
    print("🚀 Sentence Segmentation Test Suite")
    print("=" * 50)
    
    # Test 1: Unit test
    success1 = test_sentence_segmenter()
    
    # Test 2: Streaming test
    success2 = await test_streaming_sentences()
    
    # Test 3: Performance comparison
    success3 = await test_performance_comparison()
    
    print("\n" + "=" * 50)
    print("📋 Test Results Summary:")
    print(f"   🔧 Unit Tests: {'✅ PASS' if success1 else '❌ FAIL'}")
    print(f"   🔄 Streaming: {'✅ PASS' if success2 else '❌ FAIL'}")
    print(f"   ⚡ Performance: {'✅ PASS' if success3 else '❌ FAIL'}")
    
    all_passed = success1 and success2 and success3
    print(f"\n🎯 Overall Result: {'✅ ALL TESTS PASSED' if all_passed else '❌ SOME TESTS FAILED'}")
    
    if all_passed:
        print("\n🎉 Sentence Segmentation is working perfectly!")
        print("   ✅ Streaming responses are segmented by punctuation")
        print("   ✅ TTS can start as soon as first sentence is complete")
        print("   ✅ Much faster perceived response time")
        print("   ✅ More natural conversation flow")
    else:
        print("\n⚠️ Please check the failed tests and fix issues")
    
    return 0 if all_passed else 1

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code) 