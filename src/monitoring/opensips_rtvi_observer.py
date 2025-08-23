"""
Enhanced RTVI Observer for OpenSIPS Integration
"""

import time
from typing import Dict, Any
import structlog
from pipecat.processors.frameworks.rtvi import RTVIObserver, RTVIObserverParams
from pipecat.frames.frames import (
    UserStartedSpeakingFrame, UserStoppedSpeakingFrame,
    BotStartedSpeakingFrame, BotStoppedSpeakingFrame,
    BotInterruptionFrame, TranscriptionFrame
)

logger = structlog.get_logger()

class OpenSIPSRTVIObserver(RTVIObserver):
    """OpenSIPS-specific RTVI Observer with enhanced monitoring"""

    def __init__(self, rtvi, call_id: str, **kwargs):
        # Enable comprehensive monitoring
        params = RTVIObserverParams(
            bot_llm_enabled=True,
            bot_tts_enabled=True,
            bot_speaking_enabled=True,
            user_llm_enabled=True,
            user_speaking_enabled=True,
            user_transcription_enabled=True,
            metrics_enabled=True,
            errors_enabled=True
        )

        super().__init__(rtvi, params=params, **kwargs)
        self.call_id = call_id
        self.start_time = time.time()

        # Custom metrics tracking
        self.metrics = {
            "total_user_utterances": 0,
            "total_bot_responses": 0,
            "interruption_count": 0,
            "conversation_turns": 0,
            "avg_response_time": 0.0
        }

        self.last_user_speech_start = None
        self.last_bot_response_start = None

        logger.info("📊 OpenSIPS RTVI Observer initialized", call_id=call_id)

    async def on_push_frame(self, data):
        """Enhanced frame processing with OpenSIPS-specific metrics"""
        await super().on_push_frame(data)

        frame = data.frame

        # Track OpenSIPS-specific events
        if isinstance(frame, UserStartedSpeakingFrame):
            await self._track_user_speech_start()
        elif isinstance(frame, UserStoppedSpeakingFrame):
            await self._track_user_speech_end()
        elif isinstance(frame, BotStartedSpeakingFrame):
            await self._track_bot_response_start()
        elif isinstance(frame, BotStoppedSpeakingFrame):
            await self._track_bot_response_end()
        elif isinstance(frame, BotInterruptionFrame):
            await self._track_interruption()
        elif isinstance(frame, TranscriptionFrame):
            await self._track_transcription(frame)

    async def _track_user_speech_start(self):
        """Track when user starts speaking"""
        self.last_user_speech_start = time.time()

        message = {
            "type": "opensips-user-speech-start",
            "call_id": self.call_id,
            "timestamp": time.time(),
            "call_duration": time.time() - self.start_time
        }

        await self.push_transport_message_urgent({
            "label": "rtvi-ai",
            "type": "server-message",
            "data": message
        })

        logger.info("🎤 User started speaking", call_id=self.call_id)

    async def _track_user_speech_end(self):
        """Track when user stops speaking"""
        if self.last_user_speech_start:
            speech_duration = time.time() - self.last_user_speech_start
            self.metrics["total_user_utterances"] += 1

            message = {
                "type": "opensips-user-speech-end",
                "call_id": self.call_id,
                "speech_duration": speech_duration,
                "total_utterances": self.metrics["total_user_utterances"]
            }

            await self.push_transport_message_urgent({
                "label": "rtvi-ai",
                "type": "server-message",
                "data": message
            })

        logger.info("🎤 User stopped speaking", call_id=self.call_id)

    async def _track_bot_response_start(self):
        """Track bot response start with timing"""
        current_time = time.time()
        self.last_bot_response_start = current_time

        # Calculate response time if we have user speech timing
        response_time = None
        if self.last_user_speech_start:
            response_time = current_time - self.last_user_speech_start

            # Update average response time
            total_responses = self.metrics["total_bot_responses"]
            current_avg = self.metrics["avg_response_time"]
            self.metrics["avg_response_time"] = (
                (current_avg * total_responses + response_time) / (total_responses + 1)
            )

        self.metrics["total_bot_responses"] += 1
        self.metrics["conversation_turns"] += 1

        message = {
            "type": "opensips-bot-response-start",
            "call_id": self.call_id,
            "response_time": response_time,
            "avg_response_time": self.metrics["avg_response_time"],
            "conversation_turns": self.metrics["conversation_turns"]
        }

        await self.push_transport_message_urgent({
            "label": "rtvi-ai",
            "type": "server-message",
            "data": message
        })

        logger.info("🤖 Bot response started",
                   call_id=self.call_id,
                   response_time=response_time)

    async def _track_bot_response_end(self):
        """Track bot response end"""
        if self.last_bot_response_start:
            response_duration = time.time() - self.last_bot_response_start

            message = {
                "type": "opensips-bot-response-end",
                "call_id": self.call_id,
                "response_duration": response_duration
            }

            await self.push_transport_message_urgent({
                "label": "rtvi-ai",
                "type": "server-message",
                "data": message
            })

        logger.info("🤖 Bot response ended", call_id=self.call_id)

    async def _track_interruption(self):
        """Track bot interruptions"""
        self.metrics["interruption_count"] += 1

        message = {
            "type": "opensips-bot-interrupted",
            "call_id": self.call_id,
            "interruption_count": self.metrics["interruption_count"],
            "timestamp": time.time()
        }

        await self.push_transport_message_urgent({
            "label": "rtvi-ai",
            "type": "server-message",
            "data": message
        })

        logger.info("⚡ Bot interrupted",
                   call_id=self.call_id,
                   count=self.metrics["interruption_count"])

    async def _track_transcription(self, frame):
        """Track transcription events"""
        message = {
            "type": "opensips-transcription",
            "call_id": self.call_id,
            "text": frame.text,
            "confidence": getattr(frame, 'confidence', None),
            "timestamp": time.time()
        }

        await self.push_transport_message_urgent({
            "label": "rtvi-ai",
            "type": "server-message",
            "data": message
        })

    def get_call_summary(self) -> Dict[str, Any]:
        """Get comprehensive call summary"""
        duration = time.time() - self.start_time

        return {
            "call_id": self.call_id,
            "duration": duration,
            "metrics": self.metrics.copy(),
            "rtvi_enabled": True,
            "features": [
                "real_time_monitoring",
                "dynamic_configuration",
                "action_system",
                "structured_messaging",
                "advanced_observability"
            ]
        }
