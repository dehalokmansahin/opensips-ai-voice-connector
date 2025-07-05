#!/usr/bin/env python3
"""
OpenSIPS Bot - Clean modular implementation
Uses unified configuration and modular pipeline builder
"""

import sys
import asyncio
from typing import Dict, Any, Optional
import structlog

# Configure logging
from loguru import logger as _root_logger

_root_logger.remove()

def _is_pipecat(record):
    try:
        return "/pipecat/" in record["file"].path.replace("\\", "/")
    except Exception:
        return False

_root_logger.add(sys.stderr, level="DEBUG", filter=_is_pipecat)
_root_logger.add(sys.stderr, level="DEBUG", filter=lambda record: not _is_pipecat(record))

import logging
logging.basicConfig(level=logging.INFO, force=True)

import structlog
structlog.configure(wrapper_class=structlog.make_filtering_bound_logger(logging.INFO))

# Core imports
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.audio.interruptions.min_words_interruption_strategy import MinWordsInterruptionStrategy
from pipecat.processors.aggregators.openai_llm_context import OpenAILLMContext
from pipecat.observers.loggers.llm_log_observer import LLMLogObserver
from pipecat.observers.loggers.transcription_log_observer import TranscriptionLogObserver
from pipecat.observers.loggers.user_bot_latency_log_observer import UserBotLatencyLogObserver
from pipecat.observers.loggers.debug_log_observer import DebugLogObserver
from pipecat.frames.frames import (
    TTSAudioRawFrame,
    TTSStartedFrame,
    TTSStoppedFrame,
    TTSTextFrame,
    BotStartedSpeakingFrame,
    BotStoppedSpeakingFrame,
    UserStartedSpeakingFrame,
    UserStoppedSpeakingFrame,
)

# Our modular components
from bot.config_manager import get_config, ConfigManager
from bot.transport_factory import create_transport
from bot.pipeline_builder import build_pipeline
from services.vosk_websocket import VoskWebsocketSTTService
from services.llama_websocket import LlamaWebsocketLLMService
from services.piper_websocket import PiperWebsocketTTSService

logger = structlog.get_logger()


async def run_opensips_bot(
    call_id: str,
    client_ip: str,
    client_port: int,
    bind_ip: str = "0.0.0.0",
    bind_port: int = 0,
    config: Optional[Dict[str, Any]] = None,
    config_file: Optional[str] = None
):
    """
    Run OpenSIPS bot with unified configuration system
    """
    try:
        logger.info("Starting OpenSIPS bot", 
                   call_id=call_id,
                   client_ip=client_ip,
                   client_port=client_port)
        
        # Load unified configuration
        if config_file:
            # Use specific config file
            config_manager = ConfigManager(config_file)
            unified_config = config_manager.load()
        else:
            # Use default config with optional overrides
            unified_config = get_config()
        
        # Override network settings from parameters
        unified_config.network.bind_ip = bind_ip
        unified_config.network.bind_port = bind_port
        
        # Override service URLs from legacy config if provided
        if config:
            if "stt" in config and "url" in config["stt"]:
                unified_config.stt.url = config["stt"]["url"]
            if "llm" in config and "url" in config["llm"]:
                unified_config.llm.url = config["llm"]["url"]
            if "tts" in config and "url" in config["tts"]:
                unified_config.tts.url = config["tts"]["url"]
        
        logger.info("Configuration loaded", 
                   stt_url=unified_config.stt.url,
                   llm_url=unified_config.llm.url,
                   tts_url=unified_config.tts.url,
                   vad_confidence=unified_config.voice.vad_confidence)
        
        # Create transport
        transport = create_transport(unified_config, call_id)
        transport.update_client_info(client_ip, client_port)
        
        # Create AI services with unified config
        stt = VoskWebsocketSTTService(
            url=unified_config.stt.url,
            sample_rate=unified_config.voice.sample_rate
        )
        
        llm = LlamaWebsocketLLMService(
            url=unified_config.llm.url,
            model=unified_config.llm.model or "llama3.2:3b-instruct-turkish",
            temperature=unified_config.llm.temperature or 0.2,
            max_tokens=unified_config.llm.max_tokens or 80
        )
        
        tts = PiperWebsocketTTSService(
            url=unified_config.tts.url,
            voice=unified_config.tts.voice or "tr_TR-dfki-medium",
            sample_rate=unified_config.tts.sample_rate or 22050,
            aggregate_sentences=True  # Tam cümle bekler
        )
        
        # Create context
        messages = [
            {
                "role": "system",
                "content": "Merhaba! Size nasıl yardımcı olabilirim? Bankacılık işlemleriniz için buradayım. Kısa ve anlaşılır cevaplar veririm."
            }
        ]
        
        context = OpenAILLMContext(messages)
        context_aggregator = llm.create_context_aggregator(context)
        
        # Create observers
        observers = [
            LLMLogObserver(),
            TranscriptionLogObserver(),
            UserBotLatencyLogObserver(),
            DebugLogObserver(
                frame_types=(
                    TTSAudioRawFrame,
                    TTSStartedFrame,
                    TTSStoppedFrame,
                )
            ),
        ]
        
        # Build pipeline
        pipeline = build_pipeline(
            transport=transport,
            stt=stt,
            llm=llm,
            tts=tts,
            context_aggregator=context_aggregator
        )
        
        # Event handlers
        @transport.event_handler("on_client_connected")
        async def on_client_connected(transport, client):
            logger.info("Client connected", call_id=call_id, client=client)
        
        @transport.event_handler("on_client_disconnected")
        async def on_client_disconnected(transport, client):
            logger.info("Client disconnected", call_id=call_id, client=client)
        
        # Run pipeline
        task = PipelineTask(
            pipeline, 
            params=PipelineParams(
                allow_interruptions=unified_config.voice.enable_interruption,
                interruption_strategies=[MinWordsInterruptionStrategy(min_words=2)],
            ),
            observers=observers
        )
        
        runner = PipelineRunner()
        await runner.run(task)
        
        logger.info("Bot session completed", call_id=call_id)
        
    except Exception as e:
        logger.error("Bot session failed", call_id=call_id, error=str(e))
        raise


def get_bot_sdp_info(
    call_id: str,
    bind_ip: str = "0.0.0.0",
    bind_port: int = 0,
    config_file: Optional[str] = None
) -> Dict[str, Any]:
    """Get SDP info for bot transport using unified config."""
    
    # Load unified configuration
    if config_file:
        config_manager = ConfigManager(config_file)
        unified_config = config_manager.load()
    else:
        unified_config = get_config()
    
    # Override network settings
    unified_config.network.bind_ip = bind_ip
    unified_config.network.bind_port = bind_port
    
    transport = create_transport(unified_config, call_id)
    return transport.get_sdp_info() 