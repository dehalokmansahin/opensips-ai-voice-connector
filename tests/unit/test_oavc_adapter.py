import asyncio

import numpy as np
import pytest

from pipeline.manager import PipelineManager
from pipeline.stages import VADProcessor, STTProcessor, LLMProcessor, TTSProcessor
from transports.oavc_adapter import OAVCAdapter


@pytest.mark.asyncio
async def test_oavc_adapter_conversion():
    # Prepare pipeline manager (no processing needed for this test)
    pm = PipelineManager([VADProcessor(), STTProcessor(), LLMProcessor(), TTSProcessor()])
    await pm.start()

    adapter = OAVCAdapter(pm)

    pcmu_packet = b"\xff" * 160  # 20 ms silence in μ-law

    await adapter.feed_pcmu(pcmu_packet)

    # Since internal operations are async, we give the loop a tick to process.
    await asyncio.sleep(0.01)

    await pm.stop()

    # Validate conversion: 160 μ-law bytes -> 320 int16 samples -> 640 bytes
    from transports.audio_utils import pcmu_to_pcm16k

    pcm_bytes, sr = pcmu_to_pcm16k(pcmu_packet)
    assert len(pcm_bytes) == 640
    assert sr == 16000
    # Ensure PCM is int16 zeros (silence) after scaling (0xFF µ-law is near silence)
    samples = np.frombuffer(pcm_bytes, dtype=np.int16)
    assert np.all(np.abs(samples) < 50) 