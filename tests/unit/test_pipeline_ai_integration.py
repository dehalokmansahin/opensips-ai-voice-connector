import asyncio

import pytest

from pipeline.ai_engine import PipelineAI


class DummyCall:
    b2b_key = "test-call"


@pytest.mark.asyncio
async def test_pipeline_ai_lifecycle():
    ai = PipelineAI(call=DummyCall(), cfg={})

    await ai.start()
    await ai.send(b"\xff" * 160)
    await asyncio.sleep(0.01)
    await ai.close() 