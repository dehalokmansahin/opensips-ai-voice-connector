"""
Interruption (Barge-in) Management
Pipecat MinWordsInterruptionStrategy referansı ile implementasyon
"""

import asyncio
import time
from abc import ABC, abstractmethod
from typing import Optional, List
import structlog

logger = structlog.get_logger()

class BaseInterruptionStrategy(ABC):
    """Base class for interruption strategies"""
    
    async def append_audio(self, audio: bytes, sample_rate: int):
        """Appends audio to the strategy. Not all strategies handle audio."""
        pass

    async def append_text(self, text: str):
        """Appends text to the strategy. Not all strategies handle text."""
        pass

    @abstractmethod
    async def should_interrupt(self) -> bool:
        """Decide whether the user should interrupt the bot"""
        pass

    @abstractmethod
    async def reset(self):
        """Reset the current accumulated text and/or audio"""
        pass

class MinWordsInterruptionStrategy(BaseInterruptionStrategy):
    """
    Interruption strategy based on minimum number of words
    Pipecat MinWordsInterruptionStrategy'den esinlenmiştir
    """

    def __init__(self, *, min_words: int = 2):
        super().__init__()
        self._min_words = min_words
        self._text = ""

    async def append_text(self, text: str):
        """Appends text for later analysis"""
        self._text += " " + text.strip()
        self._text = self._text.strip()

    async def should_interrupt(self) -> bool:
        word_count = len(self._text.split())
        interrupt = word_count >= self._min_words
        logger.debug(
            "Interruption strategy check",
            should_interrupt=interrupt,
            num_spoken_words=word_count,
            min_words=self._min_words,
            text=self._text[:50]
        )
        return interrupt

    async def reset(self):
        self._text = ""

class VolumeBasedInterruptionStrategy(BaseInterruptionStrategy):
    """
    Ses seviyesi bazlı interruption strategy
    Yüksek ses seviyesinde hemen kesme
    """
    
    def __init__(self, *, volume_threshold: float = 0.5, min_duration_ms: int = 500):
        super().__init__()
        self._volume_threshold = volume_threshold
        self._min_duration_ms = min_duration_ms
        self._high_volume_start = None
        self._current_volume = 0.0
        self._last_audio_time = None
        
    async def append_audio(self, audio: bytes, sample_rate: int):
        """Audio seviyesini analiz et"""
        try:
            import numpy as np
            # PCM bytes to numpy array
            audio_array = np.frombuffer(audio, dtype=np.int16)
            
            # Boş array kontrolü
            if len(audio_array) == 0:
                return
            
            # RMS hesapla - NaN kontrolü ile
            mean_square = np.mean(audio_array.astype(np.float64)**2)
            if mean_square < 0 or np.isnan(mean_square):
                rms = 0.0
            else:
                rms = np.sqrt(mean_square)
            
            # Normalize (0-1 arası) - güvenli normalizasyon
            if rms > 0:
                self._current_volume = min(rms / 32768.0, 1.0)
            else:
                self._current_volume = 0.0
            
            current_time = time.time() * 1000  # ms
            self._last_audio_time = current_time
            
            if self._current_volume > self._volume_threshold:
                if self._high_volume_start is None:
                    self._high_volume_start = current_time
            else:
                self._high_volume_start = None
                
        except Exception as e:
            logger.warning("Volume analysis error", error=str(e))
            self._current_volume = 0.0
    
    async def should_interrupt(self) -> bool:
        if self._high_volume_start is None:
            return False
            
        current_time = time.time() * 1000
        
        # Eğer son audio'dan beri çok zaman geçmişse, reset et
        if self._last_audio_time and (current_time - self._last_audio_time) > 1000:
            self._high_volume_start = None
            return False
            
        duration = current_time - self._high_volume_start
        interrupt = duration >= self._min_duration_ms
        
        logger.debug(
            "Volume-based interruption check",
            should_interrupt=interrupt,
            current_volume=self._current_volume,
            threshold=self._volume_threshold,
            duration_ms=duration,
            min_duration_ms=self._min_duration_ms
        )
        
        return interrupt
    
    async def reset(self):
        self._high_volume_start = None
        self._current_volume = 0.0
        self._last_audio_time = None

class InterruptionManager:
    """Barge-in interruption yöneticisi"""
    
    def __init__(self, strategies: List[BaseInterruptionStrategy] = None):
        self.strategies = strategies or [MinWordsInterruptionStrategy(min_words=2)]
        self.bot_speaking = False
        self.user_speaking = False
        self.interruption_active = False
        self._reset_lock = asyncio.Lock()
        
        logger.info("InterruptionManager initialized", 
                   num_strategies=len(self.strategies),
                   strategy_types=[type(s).__name__ for s in self.strategies])
    
    async def set_bot_speaking(self, speaking: bool):
        """Bot konuşma durumunu güncelle"""
        self.bot_speaking = speaking
        logger.debug("Bot speaking state changed", speaking=speaking)
        
        if not speaking and self.interruption_active:
            # Bot durduysa interruption'ı sıfırla
            await self.reset_interruption()
    
    async def set_user_speaking(self, speaking: bool):
        """Kullanıcı konuşma durumunu güncelle"""
        self.user_speaking = speaking
        logger.debug("User speaking state changed", speaking=speaking)
        
        if not speaking:
            # Kullanıcı durduğunda interruption kontrolü yap
            await self.check_interruption()
    
    async def append_user_audio(self, audio: bytes, sample_rate: int):
        """Kullanıcı ses verisini strategies'e ekle"""
        if self.user_speaking:
            for strategy in self.strategies:
                await strategy.append_audio(audio, sample_rate)
    
    async def append_user_text(self, text: str):
        """Kullanıcı metni strategies'e ekle"""
        if self.user_speaking and text.strip():
            for strategy in self.strategies:
                await strategy.append_text(text)
            
            logger.debug("User text appended to strategies", text=text[:30])
    
    async def check_interruption(self) -> bool:
        """Interruption kontrolü yap"""
        if not self.bot_speaking:
            return False
        
        # Tüm strategies'i kontrol et
        should_interrupt = False
        for strategy in self.strategies:
            if await strategy.should_interrupt():
                should_interrupt = True
                logger.info("Interruption triggered", 
                           strategy=type(strategy).__name__)
                break
        
        if should_interrupt:
            await self.trigger_interruption()
            return True
        
        return False
    
    async def trigger_interruption(self):
        """Interruption'ı tetikle"""
        if self.interruption_active:
            return
        
        self.interruption_active = True
        logger.info("🛑 Barge-in interruption triggered!")
        
        # Bot'u durdur (bu pipeline'a gönderilecek)
        await self.set_bot_speaking(False)
        
        # Strategies'i sıfırla
        await self.reset_strategies()
    
    async def reset_interruption(self):
        """Interruption'ı sıfırla"""
        async with self._reset_lock:
            if self.interruption_active:
                self.interruption_active = False
                await self.reset_strategies()
                logger.debug("Interruption reset completed")
    
    async def reset_strategies(self):
        """Tüm strategies'i sıfırla"""
        for strategy in self.strategies:
            await strategy.reset()
        logger.debug("All interruption strategies reset")
    
    def is_interruption_allowed(self) -> bool:
        """Interruption'a izin var mı?"""
        return self.bot_speaking and self.user_speaking
    
    def get_status(self) -> dict:
        """Interruption manager durumunu döndür"""
        return {
            "bot_speaking": self.bot_speaking,
            "user_speaking": self.user_speaking,
            "interruption_active": self.interruption_active,
            "interruption_allowed": self.is_interruption_allowed(),
            "num_strategies": len(self.strategies),
            "strategy_types": [type(s).__name__ for s in self.strategies]
        } 