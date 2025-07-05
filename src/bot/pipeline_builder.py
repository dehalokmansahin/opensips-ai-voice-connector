"""Helper that wires the Pipecat pipeline together."""
from __future__ import annotations

from pipecat.pipeline.pipeline import Pipeline
from pipecat.processors.aggregators.llm_response import (
    LLMAssistantContextAggregator,
)
from pipecat.frames.frames import TextFrame, TTSTextFrame, LLMTextFrame
from pipecat.processors.frame_processor import FrameProcessor, FrameDirection


class TTSForwardingAggregator(FrameProcessor):
    """Custom aggregator that forwards LLMTextFrames as TTSTextFrames for TTS processing."""
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
    
    async def process_frame(self, frame, direction):
        await super().process_frame(frame, direction)
        
        # Forward LLMTextFrames as TTSTextFrames for TTS
        if isinstance(frame, LLMTextFrame):
            tts_frame = TTSTextFrame(frame.text)
            await self.push_frame(tts_frame, direction)
        else:
            # Forward all other frames unchanged
            await self.push_frame(frame, direction)


def build_pipeline(
    transport,
    stt,
    llm,
    tts,
    context_aggregator,
) -> Pipeline:
    """Return a ready-to-run Pipecat Pipeline; observers will be passed to PipelineTask."""

    # Create custom aggregator that forwards to TTS
    tts_forwarding_aggregator = TTSForwardingAggregator()

    pipeline = Pipeline(
        [
            transport.input(),
            stt,
            context_aggregator.user(),
            llm,
            tts_forwarding_aggregator,
            tts,
            transport.output(),
            context_aggregator.assistant(),  # Move context aggregator after TTS
        ]
    )

    return pipeline 