"""
RTVI-enabled OpenSIPS Transport
Combines UDP/RTP with RTVI protocol layer
"""

from typing import Optional, Dict, Any
import structlog
from pipecat.processors.frameworks.rtvi import (
    RTVIProcessor, RTVIConfig, RTVIService,
    RTVIServiceConfig, RTVIServiceOptionConfig
)
from pipecat.transports.base_transport import BaseTransport
from src.transports.opensips_transport import create_opensips_transport, OpenSIPSTransportParams
from src.monitoring.opensips_rtvi_observer import OpenSIPSRTVIObserver
import structlog

logger = structlog.get_logger()


class RTVIOpenSIPSTransportParams(OpenSIPSTransportParams):
    """RTVI + OpenSIPS Transport Parameters"""

    def __init__(self, **kwargs):
        kwargs.setdefault('rtvi_config', None)
        kwargs.setdefault('enable_rtvi_observer', True)
        kwargs.setdefault('enable_rtvi_metrics', True)
        super().__init__(**kwargs)


class RTVIOpenSIPSTransport(BaseTransport):
    """RTVI-enabled OpenSIPS Transport"""

    def __init__(self, params: RTVIOpenSIPSTransportParams, **kwargs):
        super().__init__(params, **kwargs)

        # Create underlying OpenSIPS transport
        self._rtp_transport = create_opensips_transport(
            bind_ip=params.bind_ip,
            bind_port=params.bind_port,
            call_id=params.call_id,
            vad_analyzer=params.vad_analyzer,
            **kwargs
        )

        # Initialize RTVI components
        self._rtvi_config = self._create_default_rtvi_config()
        self._rtvi_processor = RTVIProcessor(
            config=self._rtvi_config,
            transport=self._rtp_transport
        )

        # RTVI observer for monitoring
        self._rtvi_observer = None
        if params.enable_rtvi_observer:
            self._rtvi_observer = OpenSIPSRTVIObserver(self._rtvi_processor, call_id=params.call_id)

        logger.info("🎵 RTVI OpenSIPS Transport initialized")

    def _create_default_rtvi_config(self) -> RTVIConfig:
        """Create default RTVI configuration"""
        return RTVIConfig(config=[
            RTVIServiceConfig(
                service="vosk_stt",
                options=[
                    RTVIServiceOptionConfig(name="language", value="tr"),
                    RTVIServiceOptionConfig(name="confidence", value=0.8)
                ]
            ),
            RTVIServiceConfig(
                service="llama_llm",
                options=[
                    RTVIServiceOptionConfig(name="temperature", value=0.7),
                    RTVIServiceOptionConfig(name="max_tokens", value=150)
                ]
            ),
            RTVIServiceConfig(
                service="piper_tts",
                options=[
                    RTVIServiceOptionConfig(name="voice", value="tr"),
                    RTVIServiceOptionConfig(name="speed", value=1.0)
                ]
            )
        ])

    def input(self):
        return self._rtp_transport.input()

    def output(self):
        return self._rtp_transport.output()

    @property
    def rtvi_processor(self) -> RTVIProcessor:
        return self._rtvi_processor

    @property
    def rtvi_observer(self) -> Optional[RTVIObserver]:
        return self._rtvi_observer

    @property
    def local_port(self) -> int:
        return self._rtp_transport.local_port
