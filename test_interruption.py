#!/usr/bin/env python3
"""
Interruption (Barge-in) Test Suite
MinWordsInterruptionStrategy ve VolumeBasedInterruptionStrategy testleri
"""

import sys
import os
import asyncio
import numpy as np
from pathlib import Path
import time

# Python path setup
current_dir = Path(__file__).parent
src_path = current_dir / "src"
pipecat_src_path = current_dir / "pipecat" / "src"

if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))
if str(pipecat_src_path) not in sys.path:
    sys.path.insert(0, str(pipecat_src_path))

# soxr compatibility stub
if not hasattr(sys.modules, 'soxr'):
    class SoxrStub:
        def resample(self, *args, **kwargs):
            return np.array([])
    sys.modules['soxr'] = SoxrStub()

import structlog
from pipeline.interruption import (
    MinWordsInterruptionStrategy, 
    VolumeBasedInterruptionStrategy, 
    InterruptionManager
)

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

async def test_min_words_strategy():
    """MinWordsInterruptionStrategy testi"""
    print("🔧 Testing MinWordsInterruptionStrategy...")
    
    # Test 1: 2 kelime threshold
    print("\n📝 Test 1: 2 kelime threshold")
    strategy = MinWordsInterruptionStrategy(min_words=2)
    
    # İlk kelime
    await strategy.append_text("Merhaba")
    should_interrupt = await strategy.should_interrupt()
    print(f"   1 kelime: {should_interrupt} (beklenen: False)")
    success1 = should_interrupt == False
    
    # İkinci kelime
    await strategy.append_text("nasılsın")
    should_interrupt = await strategy.should_interrupt()
    print(f"   2 kelime: {should_interrupt} (beklenen: True)")
    success2 = should_interrupt == True
    
    # Reset test
    await strategy.reset()
    should_interrupt = await strategy.should_interrupt()
    print(f"   Reset sonrası: {should_interrupt} (beklenen: False)")
    success3 = should_interrupt == False
    
    # Test 2: Türkçe cümle testi
    print("\n📝 Test 2: Türkçe cümle testi")
    await strategy.append_text("Dur")  # 1 kelime
    should_interrupt_1 = await strategy.should_interrupt()
    
    await strategy.append_text("artık")  # 2 kelime
    should_interrupt_2 = await strategy.should_interrupt()
    
    await strategy.append_text("konuşmayı")  # 3 kelime
    should_interrupt_3 = await strategy.should_interrupt()
    
    print(f"   'Dur': {should_interrupt_1} (False)")
    print(f"   'Dur artık': {should_interrupt_2} (True)")
    print(f"   'Dur artık konuşmayı': {should_interrupt_3} (True)")
    
    success4 = not should_interrupt_1 and should_interrupt_2 and should_interrupt_3
    
    return success1 and success2 and success3 and success4

async def test_volume_strategy():
    """VolumeBasedInterruptionStrategy testi"""
    print("\n🔊 Testing VolumeBasedInterruptionStrategy...")
    
    strategy = VolumeBasedInterruptionStrategy(
        volume_threshold=0.5, 
        min_duration_ms=200
    )
    
    # Test 1: Düşük ses seviyesi
    print("\n📝 Test 1: Düşük ses seviyesi")
    low_volume_audio = (np.random.randint(-1000, 1000, 1600, dtype=np.int16)).tobytes()
    await strategy.append_audio(low_volume_audio, 16000)
    should_interrupt = await strategy.should_interrupt()
    print(f"   Düşük ses: {should_interrupt} (beklenen: False)")
    print(f"   Current volume: {strategy._current_volume}")
    success1 = should_interrupt == False
    
    # Test 2: Yüksek ses seviyesi - sürekli gönder
    print("\n📝 Test 2: Yüksek ses seviyesi (sürekli)")
    await strategy.reset()
    
    # Çok yüksek ses oluştur
    high_volume_audio = (np.full(1600, 30000, dtype=np.int16)).tobytes()
    
    # İlk chunk - yüksek ses başlat
    await strategy.append_audio(high_volume_audio, 16000)
    should_interrupt_1 = await strategy.should_interrupt()
    print(f"   Yüksek ses (0ms): {should_interrupt_1} (beklenen: False)")
    print(f"   Current volume: {strategy._current_volume}, threshold: {strategy._volume_threshold}")
    print(f"   High volume start: {strategy._high_volume_start}")
    
    # 100ms bekle ve devam et
    await asyncio.sleep(0.1)
    await strategy.append_audio(high_volume_audio, 16000)
    should_interrupt_2 = await strategy.should_interrupt()
    print(f"   Yüksek ses (100ms): {should_interrupt_2} (beklenen: False)")
    print(f"   Current volume: {strategy._current_volume}")
    print(f"   High volume start: {strategy._high_volume_start}")
    
    # 150ms daha bekle (toplam 250ms)
    await asyncio.sleep(0.15)
    await strategy.append_audio(high_volume_audio, 16000)
    should_interrupt_3 = await strategy.should_interrupt()
    print(f"   Yüksek ses (250ms): {should_interrupt_3} (beklenen: True)")
    print(f"   Current volume: {strategy._current_volume}")
    print(f"   High volume start: {strategy._high_volume_start}")
    
    # Debug: Duration hesaplama
    if strategy._high_volume_start:
        current_time = time.time() * 1000
        duration = current_time - strategy._high_volume_start
        print(f"   Duration: {duration}ms, min required: {strategy._min_duration_ms}ms")
    
    success2 = not should_interrupt_1 and not should_interrupt_2 and should_interrupt_3
    
    # Test 3: Reset sonrası
    print("\n📝 Test 3: Reset sonrası")
    await strategy.reset()
    should_interrupt_reset = await strategy.should_interrupt()
    print(f"   Reset sonrası: {should_interrupt_reset} (beklenen: False)")
    print(f"   Current volume after reset: {strategy._current_volume}")
    success3 = should_interrupt_reset == False
    
    return success1 and success2 and success3

async def test_interruption_manager():
    """InterruptionManager testi"""
    print("\n🎛️ Testing InterruptionManager...")
    
    # Multiple strategies ile manager oluştur
    strategies = [
        MinWordsInterruptionStrategy(min_words=2),
        VolumeBasedInterruptionStrategy(volume_threshold=0.4, min_duration_ms=300)
    ]
    
    manager = InterruptionManager(strategies=strategies)
    
    # Test 1: Initial state
    print("\n📝 Test 1: Initial state")
    status = manager.get_status()
    print(f"   Initial status: {status}")
    success1 = not status["bot_speaking"] and not status["user_speaking"]
    
    # Test 2: Bot speaking, user not speaking
    print("\n📝 Test 2: Bot speaking, user not speaking")
    await manager.set_bot_speaking(True)
    await manager.set_user_speaking(False)
    allowed = manager.is_interruption_allowed()
    print(f"   Interruption allowed: {allowed} (beklenen: False)")
    success2 = allowed == False
    
    # Test 3: Both speaking - interruption allowed
    print("\n📝 Test 3: Both speaking")
    await manager.set_user_speaking(True)
    allowed = manager.is_interruption_allowed()
    print(f"   Interruption allowed: {allowed} (beklenen: True)")
    success3 = allowed == True
    
    # Test 4: Text-based interruption
    print("\n📝 Test 4: Text-based interruption")
    await manager.append_user_text("Dur")  # 1 kelime
    interrupted_1 = await manager.check_interruption()
    
    await manager.append_user_text("artık")  # 2 kelime
    interrupted_2 = await manager.check_interruption()
    
    print(f"   1 kelime sonrası: {interrupted_1} (False)")
    print(f"   2 kelime sonrası: {interrupted_2} (True)")
    success4 = not interrupted_1 and interrupted_2
    
    # Test 5: Reset after interruption - manager'ın trigger_interruption çağrısı bot_speaking'i False yapar
    print("\n📝 Test 5: Reset after interruption")
    status_after = manager.get_status()
    print(f"   Status after interruption: {status_after}")
    # trigger_interruption çağrıldığında bot_speaking False olur ve interruption_active sıfırlanır
    success5 = not status_after["bot_speaking"]  # Bot artık konuşmuyor
    
    return success1 and success2 and success3 and success4 and success5

async def test_conversation_scenario():
    """Gerçek konuşma senaryosu testi"""
    print("\n🎭 Testing Real Conversation Scenario...")
    
    manager = InterruptionManager([
        MinWordsInterruptionStrategy(min_words=2)
    ])
    
    # Senaryo: Bot konuşuyor, kullanıcı araya giriyor
    print("\n📝 Scenario: Bot speaking, user interrupts")
    
    # 1. Bot konuşmaya başlar
    await manager.set_bot_speaking(True)
    print("   🤖 Bot started speaking")
    
    # 2. Kullanıcı konuşmaya başlar (araya girer)
    await manager.set_user_speaking(True)
    print("   👤 User started speaking")
    
    # 3. Kullanıcı ilk kelimeyi söyler
    await manager.append_user_text("Dur")
    interrupted_1 = await manager.check_interruption()
    print(f"   👤 'Dur': Interrupted = {interrupted_1}")
    
    # 4. Kullanıcı ikinci kelimeyi söyler
    await manager.append_user_text("lütfen")
    interrupted_2 = await manager.check_interruption()
    print(f"   👤 'Dur lütfen': Interrupted = {interrupted_2}")
    
    # 5. Status kontrolü
    final_status = manager.get_status()
    print(f"   📊 Final status: {final_status}")
    
    # Başarı koşulları:
    # - İlk kelimede kesmesin (False)
    # - İkinci kelimede kessin (True)
    # - Son durumda bot konuşmuyor olmalı (trigger_interruption bot'u durdurur)
    success = (
        not interrupted_1 and  # İlk kelimede kesmesin
        interrupted_2 and      # İkinci kelimede kessin
        not final_status["bot_speaking"]  # Bot artık konuşmuyor
    )
    
    if success:
        print("   ✅ Conversation scenario PASSED!")
        print("      - Bot was speaking")
        print("      - User said 2 words")
        print("      - Interruption triggered correctly")
        print("      - Bot stopped speaking after interruption")
    else:
        print("   ❌ Conversation scenario FAILED!")
        print(f"      - interrupted_1: {interrupted_1} (should be False)")
        print(f"      - interrupted_2: {interrupted_2} (should be True)")
        print(f"      - bot_speaking: {final_status['bot_speaking']} (should be False)")
    
    return success

async def main():
    """Ana test fonksiyonu"""
    print("🚀 Interruption (Barge-in) Test Suite")
    print("=" * 50)
    
    # Test 1: MinWordsInterruptionStrategy
    success1 = await test_min_words_strategy()
    
    # Test 2: VolumeBasedInterruptionStrategy
    success2 = await test_volume_strategy()
    
    # Test 3: InterruptionManager
    success3 = await test_interruption_manager()
    
    # Test 4: Conversation Scenario
    success4 = await test_conversation_scenario()
    
    print("\n" + "=" * 50)
    print("📋 Test Results Summary:")
    print(f"   🔤 MinWords Strategy: {'✅ PASS' if success1 else '❌ FAIL'}")
    print(f"   🔊 Volume Strategy: {'✅ PASS' if success2 else '❌ FAIL'}")
    print(f"   🎛️ Interruption Manager: {'✅ PASS' if success3 else '❌ FAIL'}")
    print(f"   🎭 Conversation Scenario: {'✅ PASS' if success4 else '❌ FAIL'}")
    
    all_passed = success1 and success2 and success3 and success4
    print(f"\n🎯 Overall Result: {'✅ ALL TESTS PASSED' if all_passed else '❌ SOME TESTS FAILED'}")
    
    if all_passed:
        print("\n🎉 Barge-in Interruption System is working perfectly!")
        print("   ✅ MinWords strategy works (2+ words trigger interruption)")
        print("   ✅ Volume strategy works (loud audio triggers interruption)")
        print("   ✅ Manager coordinates multiple strategies")
        print("   ✅ Real conversation scenarios handled correctly")
        print("   ✅ Ready for integration with OpenSIPS Voice Connector")
    else:
        print("\n⚠️ Please check the failed tests and fix issues")
    
    return 0 if all_passed else 1

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code) 