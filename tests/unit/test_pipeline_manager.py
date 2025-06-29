import pytest

from pipeline.manager import PipelineManager
from pipeline.stages import VADProcessor, STTProcessor, LLMProcessor, TTSProcessor


@pytest.mark.asyncio
async def test_pipeline_manager_requires_processors():
    """Pipeline should raise if started without any processor."""
    pm = PipelineManager([])
    with pytest.raises(RuntimeError):
        await pm.start()


@pytest.mark.asyncio
async def test_pipeline_manager_start_stop():
    """Pipeline should start, accept audio and stop without errors."""
    processors = [VADProcessor(), STTProcessor(), LLMProcessor(), TTSProcessor()]
    pm = PipelineManager(processors)

    await pm.start()

    # Push a dummy 20 ms μ-law frame (160 bytes)
    await pm.push_audio(b"\xff" * 160, sample_rate=8000, channels=1)

    await pm.stop()

    # After stop the internal pipeline reference is cleared.
    assert pm._pipeline is None 