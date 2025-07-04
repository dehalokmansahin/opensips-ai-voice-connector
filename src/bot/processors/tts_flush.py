"""Custom processor that converts Piper TTSAudioRawFrame (22 kHz) to 16 kHz OutputAudioRawFrame
before transport.  Keeps the operation non-blocking by only awaiting the resampler asynchronously.
"""
from __future__ import annotations

import asyncio
import structlog

from pipecat.processors.frame_processor import FrameProcessor
from pipecat.frames.frames import (
    TTSAudioRawFrame,
    TTSStoppedFrame,
    OutputAudioRawFrame,
)
from pipecat.audio.utils import create_default_resampler

logger = structlog.get_logger()


class TTSFlushProcessor(FrameProcessor):
    """Ensures TTS sesleri transport katmanına *tek seferde* ve doğru örnekleme
    oranıyla (16 kHz) ulaşır.

    • Piper WebSocket 22 050 Hz/mono PCM gönderir → 16 kHz'e yeniden örnekler.
    • Çerçeveyi `OutputAudioRawFrame` olarak downstream'e iter.
    • System / Control frame'leri doğrudan üst sınıfa paslar.
    """

    def __init__(self, target_sample_rate: int = 16_000):
        super().__init__()
        self._target_rate = target_sample_rate
        self._resampler = create_default_resampler()

    async def process_frame(self, frame, direction):  # noqa: D401
        # Sistem & kontrol frame'leri için: Önce kendi durumumuzu güncelle,
        # ardından çerçeveyi pipeline'da downstream yönünde iletmeye devam et.
        # Bu özellikle StartFrame'in output transport'a ulaşmasını sağlar.
        if not isinstance(frame, TTSAudioRawFrame):
            # Üst sınıf, StartFrame gibi kontrol çerçevelerini dahili olarak işler
            # ancak varsayılan olarak bunları downstream'e iletmez. Bu nedenle
            # çerçeveyi biz manuel olarak push ederiz.
            await super().process_frame(frame, direction)
            await self.push_frame(frame, direction)
            return

        # 1) TTSAudioRawFrame → 16 kHz'e yeniden örnekle
        try:
            resampled_audio = await self._resampler.resample(
                frame.audio, frame.sample_rate, self._target_rate
            )
            out_frame = OutputAudioRawFrame(
                audio=resampled_audio,
                num_channels=frame.num_channels,
                sample_rate=self._target_rate,
            )
            await self.push_frame(out_frame, direction)
            logger.debug(
                "TTS frame resampled",
                in_rate=frame.sample_rate,
                out_rate=self._target_rate,
                in_size=len(frame.audio),
                out_size=len(resampled_audio),
            )
        except Exception as exc:
            logger.error("Resampling failed, forwarding original audio", error=str(exc))
            await self.push_frame(frame, direction)

        # Not: TTSAudioRawFrame'ler tamamlandıktan sonra Piper zaten bir
        # `TTSStoppedFrame` gönderecektir. Burada ekstra sinyal üreterek
        # frame patlamasına neden olmamak adına ek sinyal göndermiyoruz. 