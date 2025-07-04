"""Sentence Flush Aggregator

Aggregates incoming TextFrame tokens into full sentences using match_endofsentence
but also ensures any residual buffer is flushed when a LLMFullResponseEndFrame
is received. This allows sentence-by-sentence delivery to downstream TTS even
when the LLM response does not terminate with punctuation.

Usage:
    from bot.processors.sentence_flush import SentenceFlushAggregator
    ... pipeline components ...
"""

from typing import Optional

from pipecat.frames.frames import (
    Frame,
    TextFrame,
    EndFrame,
    LLMFullResponseEndFrame,
)
from pipecat.processors.frame_processor import FrameDirection
from pipecat.processors.aggregators.sentence import SentenceAggregator


class SentenceFlushAggregator(SentenceAggregator):
    """Extend Pipecat's SentenceAggregator to flush on LLMFullResponseEndFrame."""

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        # Let the parent class handle TextFrame accumulation and EndFrame logic.
        if isinstance(frame, TextFrame):
            await super().process_frame(frame, direction)
            return

        # If the LLM signals its response end, flush any buffered text first.
        if isinstance(frame, LLMFullResponseEndFrame):
            if self._aggregation:
                await self.push_frame(TextFrame(self._aggregation))
                self._aggregation = ""
            await self.push_frame(frame, direction)
            return

        # Delegate EndFrame and other frame types to the parent implementation.
        await super().process_frame(frame, direction) 