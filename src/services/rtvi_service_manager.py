"""
RTVI Service Registration and Management for OpenSIPS
"""

from typing import Dict, Any
import structlog
from pipecat.processors.frameworks.rtvi import (
    RTVIService, RTVIServiceOption, RTVIAction, RTVIActionArgument
)

logger = structlog.get_logger()

class RTVIServiceManager:
    """Manages RTVI service registration and actions for OpenSIPS"""

    def __init__(self, rtvi_processor, call_manager):
        self.rtvi = rtvi_processor
        self.call_manager = call_manager
        self._register_opensips_services()
        self._register_opensips_actions()

    def _register_opensips_services(self):
        """Register OpenSIPS-specific RTVI services"""

        # 1. Call Control Service
        call_service = RTVIService(
            name="opensips_call",
            options=[
                RTVIServiceOption(
                    name="volume",
                    type="number",
                    handler=self._handle_volume_change
                ),
                RTVIServiceOption(
                    name="mute_enabled",
                    type="bool",
                    handler=self._handle_mute_toggle
                )
            ]
        )

        # 2. STT Configuration Service
        stt_service = RTVIService(
            name="vosk_stt",
            options=[
                RTVIServiceOption(
                    name="language",
                    type="string",
                    handler=self._handle_stt_language_change
                ),
                RTVIServiceOption(
                    name="confidence_threshold",
                    type="number",
                    handler=self._handle_stt_confidence_change
                )
            ]
        )

        # 3. LLM Configuration Service
        llm_service = RTVIService(
            name="llama_llm",
            options=[
                RTVIServiceOption(
                    name="temperature",
                    type="number",
                    handler=self._handle_llm_temperature_change
                ),
                RTVIServiceOption(
                    name="max_tokens",
                    type="number",
                    handler=self._handle_llm_max_tokens_change
                )
            ]
        )

        # Services'leri register et
        self.rtvi.register_service(call_service)
        self.rtvi.register_service(stt_service)
        self.rtvi.register_service(llm_service)

        logger.info("✅ RTVI services registered",
                   services=["opensips_call", "vosk_stt", "llama_llm"])

    def _register_opensips_actions(self):
        """Register call control actions"""

        # Transfer action
        transfer_action = RTVIAction(
            service="opensips_call",
            action="transfer",
            arguments=[
                RTVIActionArgument(name="destination", type="string")
            ],
            result="object",
            handler=self._handle_call_transfer
        )

        # Hangup action
        hangup_action = RTVIAction(
            service="opensips_call",
            action="hangup",
            arguments=[],
            result="bool",
            handler=self._handle_call_hangup
        )

        # Mute action
        mute_action = RTVIAction(
            service="opensips_call",
            action="mute",
            arguments=[
                RTVIActionArgument(name="enabled", type="bool")
            ],
            result="bool",
            handler=self._handle_mute_action
        )

        self.rtvi.register_action(transfer_action)
        self.rtvi.register_action(hangup_action)
        self.rtvi.register_action(mute_action)

        logger.info("✅ RTVI actions registered",
                   actions=["transfer", "hangup", "mute"])

    # Event Handlers
    async def _handle_volume_change(self, rtvi, service, config):
        """Handle volume change via RTVI"""
        volume = config.value
        logger.info("🔊 RTVI volume change", volume=volume)
        # Volume control implementation here

    async def _handle_mute_toggle(self, rtvi, service, config):
        """Handle mute toggle via RTVI"""
        mute_enabled = config.value
        logger.info("🔇 RTVI mute toggle", mute_enabled=mute_enabled)
        # Mute control implementation here

    async def _handle_stt_language_change(self, rtvi, service, config):
        """Handle STT language change"""
        language = config.value
        logger.info("🗣️ RTVI STT language change", language=language)
        # STT language change implementation here

    async def _handle_llm_temperature_change(self, rtvi, service, config):
        """Handle LLM temperature change"""
        temperature = config.value
        logger.info("🌡️ RTVI LLM temperature change", temperature=temperature)
        # LLM temperature change implementation here

    async def _handle_llm_max_tokens_change(self, rtvi, service, config):
        """Handle LLM max tokens change"""
        max_tokens = config.value
        logger.info("📝 RTVI LLM max tokens change", max_tokens=max_tokens)
        # LLM max tokens change implementation here

    # Action Handlers
    async def _handle_call_transfer(self, rtvi, action_id, args):
        """Handle call transfer action"""
        destination = args.get("destination")
        logger.info("📞 RTVI call transfer", destination=destination)

        # OpenSIPS transfer implementation
        return {
            "success": True,
            "destination": destination,
            "transferred_at": "2024-01-01T12:00:00Z"
        }

    async def _handle_call_hangup(self, rtvi, action_id, args):
        """Handle call hangup action"""
        logger.info("📴 RTVI call hangup")

        # OpenSIPS hangup implementation
        return True

    async def _handle_mute_action(self, rtvi, action_id, args):
        """Handle mute action"""
        enabled = args.get("enabled", True)
        logger.info("🔇 RTVI mute action", enabled=enabled)

        # Mute implementation
        return enabled
