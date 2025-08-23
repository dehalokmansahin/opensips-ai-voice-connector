"""
Dynamic Pipeline Configuration via RTVI
"""

import time
import structlog
from typing import Dict, Any
from pipecat.processors.frameworks.rtvi import RTVIConfig, RTVIServiceConfig

logger = structlog.get_logger()

class RTVIConfigManager:
    """Manages dynamic pipeline configuration changes via RTVI"""

    def __init__(self, call_manager):
        # NOTE: This class depends on a call_manager to get active call objects.
        # This does not exist in the current architecture and will need to be
        # implemented or this class will need to be refactored.
        self.call_manager = call_manager
        self.config_history = {}

    async def handle_config_update(self, call_id: str, config_update):
        """Handle RTVI configuration updates"""
        call = self.call_manager.get_call(call_id)
        if not call:
            logger.warning("Config update for unknown call", call_id=call_id)
            return False

        logger.info("🔧 Processing RTVI config update",
                   call_id=call_id,
                   services=len(config_update.config))

        # Store config history
        if call_id not in self.config_history:
            self.config_history[call_id] = []

        self.config_history[call_id].append({
            "timestamp": time.time(),
            "config": config_update.config,
            "interrupt": config_update.interrupt
        })

        # Apply configuration changes
        success = True
        for service_config in config_update.config:
            try:
                await self._update_service_config(call, service_config)
            except Exception as e:
                logger.error("Failed to update service config",
                           service=service_config.service,
                           error=str(e))
                success = False

        return success

    async def _update_service_config(self, call, service_config: RTVIServiceConfig):
        """Update specific service configuration"""
        service_name = service_config.service

        logger.info("🔧 Updating service config",
                   service=service_name,
                   options=len(service_config.options))

        if service_name == "vosk_stt":
            await self._update_stt_config(call, service_config)
        elif service_name == "llama_llm":
            await self._update_llm_config(call, service_config)
        elif service_name == "piper_tts":
            await self._update_tts_config(call, service_config)
        elif service_name == "opensips_call":
            await self._update_call_config(call, service_config)
        else:
            logger.warning("Unknown service for config update", service=service_name)

    async def _update_stt_config(self, call, config: RTVIServiceConfig):
        """Update STT service configuration"""
        stt_service = call.services.get("stt")
        if not stt_service:
            return

        for option in config.options:
            if option.name == "language":
                logger.info("🗣️ Updating STT language", language=option.value)
                # Update STT language if service supports it
                if hasattr(stt_service, 'set_language'):
                    await stt_service.set_language(option.value)

            elif option.name == "confidence_threshold":
                logger.info("🎯 Updating STT confidence", confidence=option.value)
                # Update confidence threshold if supported
                if hasattr(stt_service, 'set_confidence_threshold'):
                    await stt_service.set_confidence_threshold(option.value)

    async def _update_llm_config(self, call, config: RTVIServiceConfig):
        """Update LLM service configuration"""
        llm_service = call.services.get("llm")
        if not llm_service:
            return

        for option in config.options:
            if option.name == "temperature":
                logger.info("🌡️ Updating LLM temperature", temperature=option.value)
                # Update temperature if service supports it
                if hasattr(llm_service, 'set_temperature'):
                    await llm_service.set_temperature(option.value)

            elif option.name == "max_tokens":
                logger.info("📝 Updating LLM max tokens", max_tokens=option.value)
                if hasattr(llm_service, 'set_max_tokens'):
                    await llm_service.set_max_tokens(option.value)

    async def _update_tts_config(self, call, config: RTVIServiceConfig):
        """Update TTS service configuration"""
        tts_service = call.services.get("tts")
        if not tts_service:
            return

        for option in config.options:
            if option.name == "voice":
                logger.info("🗣️ Updating TTS voice", voice=option.value)
                if hasattr(tts_service, 'set_voice'):
                    await tts_service.set_voice(option.value)

            elif option.name == "speed":
                logger.info("⚡ Updating TTS speed", speed=option.value)
                if hasattr(tts_service, 'set_speed'):
                    await tts_service.set_speed(option.value)

    async def _update_call_config(self, call, config: RTVIServiceConfig):
        """Update call-level configuration"""
        for option in config.options:
            if option.name == "volume":
                logger.info("🔊 Updating call volume", volume=option.value)
                # Call volume control implementation

            elif option.name == "mute_enabled":
                logger.info("🔇 Updating mute status", muted=option.value)
                # Call mute control implementation

    def get_config_history(self, call_id: str) -> list:
        """Get configuration change history for a call"""
        return self.config_history.get(call_id, [])
