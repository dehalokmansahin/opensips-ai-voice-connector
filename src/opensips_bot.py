#!/usr/bin/env python3
"""
OpenSIPS Bot - Following Twilio/Telnyx Pattern with VAD Observer
Simplified bot implementation with inline pipeline setup and VAD monitoring
"""

import os
import sys
import asyncio
from typing import Dict, Any
import structlog

# Configure global logging once – reduce verbosity to INFO
from loguru import logger as _root_logger

_root_logger.remove()  # Remove default sink

# Helper filter to detect Pipecat files by path fragment
def _is_pipecat(record):
    try:
        return "/pipecat/" in record["file"].path.replace("\\", "/")
    except Exception:
        return False

# 1) Pipecat-only sink at DEBUG
_root_logger.add(
    sys.stderr,
    level="DEBUG",
    filter=_is_pipecat,
)

# 2) Everything-else sink at INFO (excluding Pipecat to avoid duplicates)
_root_logger.add(
    sys.stderr,
    level="DEBUG",
    filter=lambda record: not _is_pipecat(record),
)

# Std-lib logging + structlog bridge at INFO for non-Pipecat modules
import logging

logging.basicConfig(level=logging.INFO, force=True)

import structlog

structlog.configure(wrapper_class=structlog.make_filtering_bound_logger(logging.INFO))

from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.audio.vad.vad_analyzer import VADParams
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.processors.aggregators.openai_llm_context import OpenAILLMContext
from pipecat.frames.frames import TextFrame
from pipecat.observers.loggers.debug_log_observer import DebugLogObserver
from pipecat.frames.frames import TTSStartedFrame, TTSStoppedFrame

# Custom rate-limited wrapper to avoid log floods
from rate_limited_observer import RateLimitedObserver

# Import our services
from services.vosk_websocket import VoskWebsocketSTTService
from services.piper_websocket import PiperWebsocketTTSService
from pipecat.services.openai.llm import OpenAILLMService
from pipecat.services.openai.base_llm import BaseOpenAILLMService

# Import our transport
from transports.opensips_transport import create_opensips_transport

# Pipecat observers for higher-level insights (no low-level RTP spam)
from pipecat.observers.loggers.llm_log_observer import LLMLogObserver
from pipecat.observers.loggers.transcription_log_observer import TranscriptionLogObserver
from pipecat.observers.loggers.user_bot_latency_log_observer import UserBotLatencyLogObserver

from pipecat.processors.aggregators.sentence import SentenceAggregator

logger = structlog.get_logger()


async def run_opensips_bot(
    call_id: str,
    client_ip: str,
    client_port: int,
    bind_ip: str = "0.0.0.0", 
    bind_port: int = 0,
    config: Dict[str, Any] = None
):
    """
    Run OpenSIPS bot following Twilio/Telnyx pattern with VAD Observer
    Single function handles everything - simple and clean
    """
    try:
        logger.info("Starting OpenSIPS bot with VAD observer", 
                   call_id=call_id,
                   client_ip=client_ip,
                   client_port=client_port,
                   pattern="twilio_telnyx_compliant")
        
        # 🔧 CRITICAL FIX: Sample rate consistency - RTP is 8kHz but pipeline needs conversion
        # OpenSIPS/RTP uses 8kHz but Pipecat pipeline processes at 16kHz internally
        rtp_sample_rate = 8000      # RTP audio from OpenSIPS
        pipeline_sample_rate = 16000  # Internal pipeline processing rate
        
        # 🔧 FOLLOW TWILIO/TELNYX PATTERN: Create VAD analyzer like examples
        # But optimized for Turkish speech and configured for 8kHz RTP input
        vad_config = config.get('vad', {}) if config else {}
        
        # 🔧 TEST: Use more sensitive VAD params for better Turkish speech detection
        # Default Twilio params might be too conservative
        from pipecat.audio.vad.vad_analyzer import VADParams
        
        vad_analyzer = SileroVADAnalyzer(
            params=VADParams(
                confidence=0.15,    # Very sensitive
                start_secs=0.1,     # 100ms
                stop_secs=0.25,
                min_volume=0.0      # Disable volume gating
            )
        )
        logger.info("🔧 VAD created with optimized params for Turkish speech",
                   confidence=0.15, start_secs=0.1, stop_secs=0.25, min_volume=0.0)
        
        # 🔧 DEBUG: VAD Configuration Applied
        logger.info("🎤 VAD Configuration Applied", 
                   confidence_threshold=vad_analyzer.params.confidence,
                   start_delay_secs=vad_analyzer.params.start_secs,
                   stop_delay_secs=vad_analyzer.params.stop_secs,
                   min_volume_threshold=vad_analyzer.params.min_volume,
                   vad_sample_rate=rtp_sample_rate,
                   pipeline_sample_rate=pipeline_sample_rate,
                   note="VAD processes 8kHz RTP, pipeline upsamples to 16kHz")
        
        # 🔧 FOLLOW TWILIO/TELNYX PATTERN: Create transport like examples
        # Create transport with serializer and VAD analyzer in params
        transport = create_opensips_transport(
            bind_ip=bind_ip,
            bind_port=bind_port,
            call_id=call_id,
            vad_analyzer=vad_analyzer  # VAD analyzer passed to transport params
        )
        
        # 🔧 DEBUG: Verify VAD analyzer is properly configured (following examples)
        if hasattr(transport._params, 'vad_analyzer') and transport._params.vad_analyzer:
            logger.info("✅ VAD analyzer properly configured in transport", 
                       call_id=call_id,
                       vad_class=type(transport._params.vad_analyzer).__name__,
                       vad_sample_rate=getattr(transport._params.vad_analyzer, 'sample_rate', 'not_set'),
                       confidence=transport._params.vad_analyzer.params.confidence,
                       vad_observer_enabled=True,
                       note="Following Twilio/Telnyx pattern with VAD observer - VAD should work!")
        else:
            logger.error("❌ VAD analyzer NOT configured in transport!", 
                        call_id=call_id,
                        note="Pattern not followed correctly - VAD will not work")
        
        # Update transport with client RTP info
        transport.update_client_info(client_ip, client_port)
        
        # 🔧 FOLLOW TWILIO/TELNYX PATTERN: Create AI services like examples
        stt_config = config.get('stt', {}) if config else {}
        stt = VoskWebsocketSTTService(
            url=stt_config.get('url', 'ws://vosk-server:2700'),
            sample_rate=pipeline_sample_rate  # 🔧 CRITICAL FIX: Always 16kHz for STT (not from config)
        )
        
        logger.info("🎤 STT Service Configuration", 
                   url=stt_config.get('url', 'ws://vosk-server:2700'),
                   sample_rate=pipeline_sample_rate,
                   note="Vosk STT always uses 16kHz regardless of RTP input rate")
        
        openai_config = config.get('openai', {}) if config else {}
        openai_model = openai_config.get('model', 'gpt-4o')
        openai_temperature = float(openai_config.get('temperature', '0.2'))
        openai_top_p = float(openai_config.get('top_p', '0.7'))
        openai_max_tokens = int(openai_config.get('max_tokens', '80'))

        llm = OpenAILLMService(
            api_key=os.getenv('OPENAI_API_KEY'),
            model=openai_model,
            params=BaseOpenAILLMService.InputParams(
                temperature=openai_temperature,
                top_p=openai_top_p,
                max_completion_tokens=openai_max_tokens,
            ),
        )
        
        tts_config = config.get('tts', {}) if config else {}
        tts = PiperWebsocketTTSService(
            url=tts_config.get('url', 'ws://piper-tts-server:8000/tts'),
            voice=tts_config.get('voice', 'tr_TR-dfki-medium'),
            sample_rate=int(tts_config.get('sample_rate', '22050')),
            aggregate_sentences=False  # Sentence aggregation handled upstream
        )
        
        # 🔧 FOLLOW TWILIO/TELNYX PATTERN: Create conversation context like examples
        # System prompt should set assistant persona but not contain words to be spoken directly.
        messages = [
            {
                "role": "system",
                "content": (
                    "Sen bir banka müşteri hizmetleri sanal asistanısın. Kullanıcıya para transferi, fatura ödeme, yatırım işlemleri gibi "
                    "bankacılık konularında yardımcı olursun. Cevapların kısa, net ve anlaşılır olmalıdır. "
                    "Her zaman kesinlikle Türkçe yanıt ver."
                ),
            }
        ]
        
        context = OpenAILLMContext(messages)
        context_aggregator = llm.create_context_aggregator(context)
        
        # 🔧 FOLLOW TWILIO/TELNYX PATTERN: Create pipeline like examples
        pipeline = Pipeline([
            transport.input(),              # OpenSIPS input
            stt,                            # Speech-To-Text (Vosk)
            context_aggregator.user(),      # User context
            llm,                            # LLM (OpenAI) – streams tokens
            SentenceAggregator(),      # Buffer until sentence or LLM end
            tts,                            # Text-To-Speech (Piper) – receives sentence text
            transport.output(),             # RTP output to OpenSIPS
            context_aggregator.assistant()  # Assistant context
        ])
        
        # 🔧 FOLLOW TWILIO/TELNYX PATTERN: Create pipeline task like examples
        # 🔧 CRITICAL FIX: Sample rate configuration for RTP/OpenSIPS
        task = PipelineTask(
            pipeline,
            params=PipelineParams(
                # 🔧 RTP comes in at 8kHz, but pipeline processes at 16kHz
                audio_in_sample_rate=pipeline_sample_rate,     # 🔥 16 kHz
                audio_out_sample_rate=rtp_sample_rate,    # 8kHz RTP output 
                enable_metrics=False,                     # Disable metrics initially
                enable_usage_metrics=False,               # Disable usage metrics initially
                allow_interruptions=True
            )
        )
        
        # 🔧 FOLLOW TWILIO/TELNYX PATTERN: Attach observers for concise logging
        task.add_observer(TranscriptionLogObserver())
        task.add_observer(LLMLogObserver())
        task.add_observer(UserBotLatencyLogObserver())
        # Attach rate-limited debug observer to monitor TTS start/stop (no audio frames)
        debug_observer = DebugLogObserver(
            frame_types=(TTSStartedFrame, TTSStoppedFrame),
        )
        task.add_observer(debug_observer)
        # 🔧 FOLLOW TWILIO/TELNYX PATTERN: Event handlers like examples
        # Send greeting only once even if transport fires the event multiple times
        greeting_sent = False

        @transport.event_handler("on_client_connected")
        async def on_client_connected(transport, client):
            nonlocal greeting_sent
            if greeting_sent:
                return  # Prevent duplicate greetings

            greeting_sent = True
            logger.info("Client connected with VAD observer", call_id=call_id)

            # Give pipeline a moment to fully initialize before pushing frames
            await asyncio.sleep(0.1)

            # Start conversation with a welcome message using proper frame
            welcome_text = "Merhaba size nasıl yardımcı olabilirim"
            await tts.say(welcome_text)
        
        @transport.event_handler("on_client_disconnected") 
        async def on_client_disconnected(transport, client):
            logger.info("Client disconnected", call_id=call_id)
            await task.cancel()
        
        # 🔧 FOLLOW TWILIO/TELNYX PATTERN: Create and run pipeline like examples
        runner = PipelineRunner(handle_sigint=False, force_gc=True)
        
        logger.info("Pipeline starting with VAD observer", 
                   call_id=call_id, 
                   pattern="twilio_telnyx_compliant",
                   rtp_sample_rate=f"{rtp_sample_rate}Hz",
                   pipeline_sample_rate=f"{pipeline_sample_rate}Hz",
                   vad_observer_enabled=True)
        await runner.run(task)
        
    except Exception as e:
        logger.error("Error in OpenSIPS bot", call_id=call_id, error=str(e))
        raise


def get_bot_sdp_info(
    call_id: str,
    bind_ip: str = "0.0.0.0",
    bind_port: int = 0
) -> Dict[str, Any]:
    """
    Get SDP info for bot without starting it
    Used for SIP 200 OK responses
    """
    # Create temporary transport to get SDP info
    transport = create_opensips_transport(
        bind_ip=bind_ip,
        bind_port=bind_port,
        call_id=call_id
    )
    
    return transport.get_sdp_info() 