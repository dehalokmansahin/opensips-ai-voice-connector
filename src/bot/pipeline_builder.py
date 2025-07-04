"""Helper that wires the Pipecat pipeline together."""
from __future__ import annotations

from pipecat.pipeline.pipeline import Pipeline
from bot.processors.sentence_flush import SentenceFlushAggregator
from pipecat.frames.frames import TextFrame
from bot.processors.tts_flush import TTSFlushProcessor


def build_pipeline(
    transport,
    stt,
    llm,
    tts,
    context_aggregator,
) -> Pipeline:
    """Return a ready-to-run Pipecat Pipeline; observers will be passed to PipelineTask."""

    pipeline = Pipeline(
        [
            transport.input(),
            stt,
            context_aggregator.user(),
            llm,
            SentenceFlushAggregator(),
            tts,
            TTSFlushProcessor(),
            transport.output(),
            context_aggregator.assistant(),
        ]
    )

    return pipeline 