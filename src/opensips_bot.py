#!/usr/bin/env python3
"""
OpenSIPS Bot - Following Twilio/Telnyx Pattern
Simplified bot implementation with inline pipeline setup
"""

import os
import sys
import asyncio
from typing import Dict, Any
import structlog

from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.processors.aggregators.openai_llm_context import OpenAILLMContext
from pipecat.frames.frames import TextFrame

# Import our services
from services.vosk_websocket import VoskWebsocketSTTService
from services.llama_websocket import LlamaWebsocketLLMService  
from services.piper_websocket import PiperWebsocketTTSService

# Import our transport
from transports.opensips_transport import create_opensips_transport

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
    Run OpenSIPS bot following Twilio/Telnyx pattern
    Single function handles everything - simple and clean
    """
    try:
        logger.info("Starting OpenSIPS bot", 
                   call_id=call_id,
                   client_ip=client_ip,
                   client_port=client_port,
                   pattern="twilio_telnyx_compliant")
        
        # Create VAD analyzer
        vad_analyzer = SileroVADAnalyzer()
        
        # Create transport with serializer and event handlers
        transport = create_opensips_transport(
            bind_ip=bind_ip,
            bind_port=bind_port,
            call_id=call_id,
            vad_analyzer=vad_analyzer
        )
        
        # Update transport with client RTP info
        transport.update_client_info(client_ip, client_port)
        
        # Create AI services
        stt_config = config.get('stt', {}) if config else {}
        stt = VoskWebsocketSTTService(
            url=stt_config.get('url', 'ws://vosk-server:2700'),
            sample_rate=int(stt_config.get('sample_rate', '16000'))
        )
        
        llm_config = config.get('llm', {}) if config else {}
        llm = LlamaWebsocketLLMService(
            url=llm_config.get('url', 'ws://llm-turkish-server:8765'),
            model=llm_config.get('model', 'llama3.2:3b-instruct-turkish'),
            temperature=float(llm_config.get('temperature', '0.2')),
            max_tokens=int(llm_config.get('max_tokens', '80'))
        )
        
        tts_config = config.get('tts', {}) if config else {}
        tts = PiperWebsocketTTSService(
            url=tts_config.get('url', 'ws://piper-tts-server:8000/tts'),
            voice=tts_config.get('voice', 'tr_TR-dfki-medium'),
            sample_rate=int(tts_config.get('sample_rate', '22050'))
        )
        
        # Create conversation context
        messages = [
            {
                "role": "system",
                "content": "Merhaba! Size nasıl yardımcı olabilirim? Bankacılık işlemleriniz için buradayım. Kısa ve anlaşılır cevaplar veririm."
            }
        ]
        
        context = OpenAILLMContext(messages)
        context_aggregator = llm.create_context_aggregator(context)
        
        # Create pipeline - following Twilio/Telnyx inline pattern
        pipeline = Pipeline([
            transport.input(),              # RTP input from OpenSIPS
            stt,                           # Speech-To-Text (Vosk)
            context_aggregator.user(),     # User context
            llm,                           # LLM (Llama)
            tts,                           # Text-To-Speech (Piper)
            transport.output(),            # RTP output to OpenSIPS  
            context_aggregator.assistant() # Assistant context
        ])
        
        # Create pipeline task
        task = PipelineTask(
            pipeline,
            params=PipelineParams(
                audio_in_sample_rate=8000,   # RTP input is 8kHz
                audio_out_sample_rate=8000,  # RTP output is 8kHz  
                enable_metrics=False,        # Disable metrics to avoid StartFrame race condition
                enable_usage_metrics=False,  # Disable usage metrics initially
                allow_interruptions=True
            )
        )
        
        # Event handlers - following Twilio/Telnyx pattern
        @transport.event_handler("on_client_connected")
        async def on_client_connected(transport, client):
            logger.info("Client connected", call_id=call_id)
            # Give pipeline a moment to fully initialize before pushing frames
            await asyncio.sleep(0.1)
            
            # Start conversation with a welcome message using proper frame
            welcome_text = "Merhaba! Size nasıl yardımcı olabilirim?"
            await task.queue_frames([TextFrame(welcome_text)])
        
        @transport.event_handler("on_client_disconnected") 
        async def on_client_disconnected(transport, client):
            logger.info("Client disconnected", call_id=call_id)
            await task.cancel()
        
        # Create and run pipeline - following Twilio/Telnyx pattern
        runner = PipelineRunner(handle_sigint=False, force_gc=True)
        
        logger.info("Pipeline starting", call_id=call_id, pattern="twilio_telnyx_compliant")
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