"""Factory for creating an OpenSIPS transport with sane defaults.
Keeps bot code clean and testable.
"""
from __future__ import annotations

from typing import Optional

from bot.config_manager import UnifiedConfig
from transports.opensips_transport import create_opensips_transport, OpenSIPSTransport
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.audio.vad.vad_analyzer import VADParams


def create_transport(config: UnifiedConfig, call_id: str) -> OpenSIPSTransport:
    """Create an RTP transport with optimized VAD configuration."""
    
    # Create VAD analyzer with config-driven parameters
    vad = SileroVADAnalyzer(
        params=VADParams(
            confidence=config.voice.vad_confidence,
            start_secs=config.voice.vad_start_secs,
            stop_secs=config.voice.vad_stop_secs,
            min_volume=0.0  # Disable volume gating for better Turkish speech detection
        )
    )
    
    return create_opensips_transport(
        bind_ip=config.network.bind_ip,
        bind_port=config.network.bind_port,
        call_id=call_id,
        vad_analyzer=vad,
    ) 