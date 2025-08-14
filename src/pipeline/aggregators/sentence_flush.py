"""Sentence Flush Aggregator

Aggregates incoming TextFrame tokens into full sentences using match_endofsentence
but also ensures any residual buffer is flushed when a LLMFullResponseEndFrame
is received. This allows sentence-by-sentence delivery to downstream TTS even
when the LLM response does not terminate with punctuation.

Usage:
    from pipeline.aggregators.sentence_flush import SentenceFlushAggregator
    ... pipeline components ...
"""

from typing import Optional

from voice_ai_core.frames import (
    Frame,
    TextFrame,
    EndFrame,
    LLMFullResponseEndFrame,
)
from voice_ai_core.processors import FrameDirection
from voice_ai_core.processors import SentenceAggregator


class SentenceFlushAggregator(SentenceAggregator):
    """Extend Pipecat's SentenceAggregator to flush on LLMFullResponseEndFrame."""

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        # Let the parent class handle TextFrame accumulation and EndFrame logic.
        if isinstance(frame, TextFrame):
            async for processed_frame in super().process_frame(frame, direction):
                yield processed_frame
            return

        # If the LLM signals its response end, flush any buffered text first.
        if isinstance(frame, LLMFullResponseEndFrame):
            if self._aggregation:
                yield TextFrame(self._aggregation)
                self._aggregation = ""
            yield frame
            return

        # Delegate EndFrame and other frame types to the parent implementation.
        async for processed_frame in super().process_frame(frame, direction):
            yield processed_frame 