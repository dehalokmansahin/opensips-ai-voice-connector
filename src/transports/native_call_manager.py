"""
Native Pipecat Call Manager
Pipecat native transport'ları kullanarak OpenSIPS entegrasyonu
"""

import asyncio
import logging
from typing import Optional, Dict, Any
import structlog
import random
import socket

from pipecat.frames.frames import StartFrame, EndFrame
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.task import PipelineTask
from pipecat.pipeline.runner import PipelineRunner

from transports.pipecat_udp_transport import UDPRTPTransport, create_opensips_rtp_transport
from pipeline.stages import VADProcessor, STTProcessor, LLMProcessor, TTSProcessor
from config import get as get_config, get_section

logger = structlog.get_logger()


class NativeCall:
    """
    Native Pipecat Call using UDP/RTP Transport
    Simpler and cleaner than the legacy Call class
    """
    
    def __init__(self, call_id: str, sdp_info: dict, services: dict):
        """
        Args:
            call_id: Unique call identifier
            sdp_info: SDP information from OpenSIPS
            services: Dict containing LLM, STT, TTS services
        """
        self.call_id = call_id
        self.sdp_info = sdp_info
        self.services = services
        
        # Native transport
        self.transport: Optional[UDPRTPTransport] = None
        self.pipeline: Optional[Pipeline] = None
        self.pipeline_task: Optional[PipelineTask] = None
        self.pipeline_runner: Optional[PipelineRunner] = None
        
        # State
        self.is_running = False
        self.client_connected = False
        
        logger.info("🎵 NativeCall created", call_id=call_id)
    
    async def start(self) -> str:
        """
        Start the native call with Pipecat transport
        Returns: SDP response for OpenSIPS
        """
        try:
            logger.info("🚀 Starting native call...", call_id=self.call_id)
            
            # Select bind_port from configured RTP range
            rtp_cfg = get_section("rtp") or {}
            min_port = int(rtp_cfg.get("min_port", 35000))
            max_port = int(rtp_cfg.get("max_port", 35100))
            bind_port = random.randint(min_port, max_port)
            logger.info("🎲 Selected RTP bind port", call_id=self.call_id, bind_port=bind_port)
            # Create transport bound to chosen port
            rtp_ip = self._get_rtp_ip()
            # Bind to all interfaces but advertise external IP in SDP
            bind_ip = "0.0.0.0"  # Bind to all interfaces in container
            self.transport = create_opensips_rtp_transport(
                bind_ip=bind_ip,
                bind_port=bind_port
            )
            
            logger.info("🌐 UDP socket bound", 
                       bind_ip=bind_ip, 
                       bind_port=bind_port,
                       advertise_ip=rtp_ip)
            
            # 2. Register event handlers
            @self.transport.event_handler("on_client_connected")
            async def on_client_connected(client_ip: str, client_port: int):
                logger.info("🎯 RTP client connected", 
                           call_id=self.call_id,
                           client_ip=client_ip, 
                           client_port=client_port)
                self.client_connected = True
            
            @self.transport.event_handler("on_rtp_ready")
            async def on_rtp_ready():
                logger.info("🎵 RTP transport ready", call_id=self.call_id)
            
            # 3. Create processors
            processors = await self._create_processors()
            
            # 4. Create pipeline: Input → Processors → Output
            self.pipeline = Pipeline([
                self.transport.input(),
                *processors,
                self.transport.output()
            ])
            
            # 5. Create and start pipeline task
            self.pipeline_task = PipelineTask(self.pipeline)
            
            # 6. Start the pipeline runner (disable signal handling for Windows compatibility)
            self.pipeline_runner = PipelineRunner(handle_sigint=False)
            
            # Start pipeline in background
            asyncio.create_task(self._run_pipeline())
            
            # 7. Generate SDP response (socket is already bound with actual port)
            sdp_response = self._generate_sdp_response(rtp_ip)
            
            self.is_running = True
            logger.info("✅ Native call started successfully", call_id=self.call_id)
            
            return sdp_response
            
        except Exception as e:
            logger.error("❌ Failed to start native call", call_id=self.call_id, error=str(e), exc_info=True)
            await self.stop()
            raise
    
    async def _run_pipeline(self):
        """Run the pipeline"""
        try:
            await self.pipeline_runner.run(self.pipeline_task)
        except Exception as e:
            logger.error("Pipeline error", call_id=self.call_id, error=str(e))
    
    async def _create_processors(self) -> list:
        """Create pipeline processors"""
        processors = []
        
        try:
            # VAD Processor
            vad_config = get_config("vad", {})
            vad_processor = VADProcessor(vad_config)
            processors.append(vad_processor)
            
            # STT Processor  
            if self.services.get("stt"):
                stt_processor = STTProcessor(self.services["stt"])
                processors.append(stt_processor)
            
            # LLM Processor
            if self.services.get("llm"):
                llm_processor = LLMProcessor(self.services["llm"])
                processors.append(llm_processor)
            
            # TTS Processor
            if self.services.get("tts"):
                tts_processor = TTSProcessor(self.services["tts"])
                processors.append(tts_processor)
            
            logger.info("✅ Pipeline processors created", 
                       call_id=self.call_id,
                       count=len(processors))
            
            return processors
            
        except Exception as e:
            logger.error("Failed to create processors", call_id=self.call_id, error=str(e))
            raise
    
    def _get_rtp_ip(self) -> str:
        """Get RTP IP address"""
        # Hardcoded external IP for testing - REMOVE IN PRODUCTION
        # Bu IP Docker host'un IP'si olmalı ve client'ın erişebileceği bir IP olmalı
        rtp_ip = "192.168.88.120"  # Docker host IP
        logger.info("🌐 Using hardcoded IP for testing", rtp_ip=rtp_ip)
        return rtp_ip
    
    def _generate_sdp_response(self, rtp_ip: str) -> str:
        """Generate SDP response"""
        if not self.transport:
            raise ValueError("Transport not initialized")
        
        local_port = self.transport.local_port
        
        logger.info("🎵 Generating SDP response", 
                   call_id=self.call_id,
                   rtp_ip=rtp_ip, 
                   local_port=local_port)
        
        # Basic SDP template - PCMU/8000 codec
        sdp_lines = [
            "v=0",
            f"o=- {random.randint(1000000000, 9999999999)} {random.randint(1000000000, 9999999999)} IN IP4 {rtp_ip}",
            "s=OpenSIPS AI Voice Connector (Native Pipecat)",
            f"c=IN IP4 {rtp_ip}",
            "t=0 0",
            f"m=audio {local_port} RTP/AVP 0",
            "a=rtpmap:0 PCMU/8000",
            "a=sendrecv"
        ]
        
        sdp_response = "\n".join(sdp_lines)
        logger.info("🎵 Native SDP response generated", 
                   call_id=self.call_id,
                   sdp_preview=sdp_response[:100] + "...")
        
        return sdp_response
    
    async def stop(self):
        """Stop the native call"""
        if not self.is_running:
            return
        
        logger.info("🛑 Stopping native call...", call_id=self.call_id)
        
        try:
            # Stop pipeline
            if self.pipeline_task:
                await self.pipeline_task.queue_frame(EndFrame())
                
            if self.pipeline_runner:
                # PipelineRunner will handle cleanup
                pass
            
            self.is_running = False
            logger.info("✅ Native call stopped", call_id=self.call_id)
            
        except Exception as e:
            logger.error("Error stopping native call", call_id=self.call_id, error=str(e))
    
    def get_sdp_body(self) -> str:
        """Get SDP body for OpenSIPS response"""
        if hasattr(self, '_sdp_response'):
            return self._sdp_response
        return ""


class NativeCallManager:
    """
    Native Call Manager using Pipecat transports
    Simpler alternative to the legacy CallManager
    """
    
    def __init__(self, services: dict):
        """
        Args:
            services: Dict containing LLM, STT, TTS services
        """
        self.services = services
        self.calls: Dict[str, NativeCall] = {}
        
        logger.info("🎵 NativeCallManager initialized")
    
    async def create_call(self, call_id: str, sdp_info: dict) -> NativeCall:
        """Create a new native call"""
        try:
            logger.info("🚀 Creating native call", call_id=call_id, sdp_info=sdp_info)
            
            # Create call
            call = NativeCall(call_id, sdp_info, self.services)
            
            # Start call (this will create transport, pipeline, etc.)
            sdp_response = await call.start()
            
            # Store SDP response for OpenSIPS
            call._sdp_response = sdp_response
            
            # Store call
            self.calls[call_id] = call
            
            logger.info("✅ Native call created successfully", call_id=call_id)
            return call
            
        except Exception as e:
            logger.error("❌ Failed to create native call", call_id=call_id, error=str(e), exc_info=True)
            raise
    
    async def terminate_call(self, call_id: str):
        """Terminate a call"""
        call = self.calls.get(call_id)
        if call:
            await call.stop()
            del self.calls[call_id]
            logger.info("🔚 Native call terminated", call_id=call_id)
        else:
            logger.warning("Call not found for termination", call_id=call_id)
    
    def get_call(self, call_id: str) -> Optional[NativeCall]:
        """Get a call by ID"""
        return self.calls.get(call_id)
    
    def set_engine(self, engine):
        """Set OpenSIPS engine (for compatibility with legacy interface)"""
        self.engine = engine
        logger.info("✅ Engine set in Native Call Manager")
    
    async def shutdown(self):
        """Shutdown all calls"""
        logger.info("🛑 Shutting down native call manager...")
        
        # Stop all calls
        stop_tasks = [call.stop() for call in self.calls.values()]
        if stop_tasks:
            await asyncio.gather(*stop_tasks, return_exceptions=True)
        
        self.calls.clear()
        logger.info("✅ Native call manager shutdown complete") 