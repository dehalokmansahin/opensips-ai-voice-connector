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
import audioop

from pipecat.frames.frames import StartFrame, EndFrame, AudioRawFrame, Frame
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.task import PipelineTask
from pipecat.pipeline.runner import PipelineRunner
from pipecat.processors.frame_processor import FrameProcessor, FrameDirection

from transports.pipecat_udp_transport import UDPRTPTransport, create_opensips_rtp_transport
from pipeline.stages import VADProcessor, STTProcessor, LLMProcessor, TTSProcessor
from services.vosk_websocket import VoskWebsocketSTTService
from services.llama_websocket import LlamaWebsocketLLMService
from services.piper_websocket import PiperWebsocketTTSService
from config import get as get_config, get_section

logger = structlog.get_logger()


class ULawDecoder(FrameProcessor):
    """Decodes U-Law encoded audio frames to 16-bit PCM."""

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        if isinstance(frame, AudioRawFrame):
            decoded_audio = audioop.ulaw2lin(frame.audio, 2)
            await self.push_frame(AudioRawFrame(audio=decoded_audio, sample_rate=8000), direction)
        else:
            await self.push_frame(frame, direction)


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
            
            # ===== RTP TEST MODE =====
            # Skip complex pipeline setup, just test RTP reception
            logger.warning("🧪 ENTERING RTP TEST MODE - Pipeline bypassed!")
            
            # Create transport with correct parameters
            from transports.pipecat_udp_transport import UDPRTPTransportParams
            transport_params = UDPRTPTransportParams(
                bind_ip="0.0.0.0",
                bind_port=bind_port,
                audio_in_enabled=True,
                audio_out_enabled=True
            )
            
            # Create transport using the factory function
            self.transport = create_opensips_rtp_transport(
                bind_ip="0.0.0.0",
                bind_port=bind_port
            )
            
            # Override the input transport's RTP handler for test mode
            input_transport = self.transport.input()
            original_handle_rtp = input_transport._handle_rtp_packet
            
            async def test_rtp_handler(data: bytes, addr: tuple):
                """Test RTP packet handler - logs packets and echoes them back"""
                logger.info("🎤 RTP PACKET RECEIVED!", 
                           call_id=self.call_id,
                           packet_size=len(data),
                           from_addr=f"{addr[0]}:{addr[1]}",
                           packet_preview=data[:20].hex() if len(data) >= 20 else data.hex())
                
                # Try to decode RTP packet
                try:
                    from transports.rtp_utils import decode_rtp_packet
                    # Convert bytes to hex string for decode_rtp_packet
                    data_hex = data.hex()
                    rtp_info = decode_rtp_packet(data_hex)
                    logger.info("🎵 RTP decoded", 
                               call_id=self.call_id,
                               payload_type=rtp_info.get('payload_type'),
                               sequence=rtp_info.get('sequence_number'),
                               timestamp=rtp_info.get('timestamp'))
                except Exception as decode_err:
                    logger.warning("⚠️ RTP decode failed", 
                                  call_id=self.call_id, 
                                  error=str(decode_err),
                                  raw_data=data_hex[:40] if len(data_hex) > 40 else data_hex)
                
                # Echo back the packet (simple test)
                try:
                    if hasattr(input_transport, '_socket') and input_transport._socket:
                        input_transport._socket.sendto(data, addr)
                        logger.info("🔊 RTP packet echoed back", 
                                   call_id=self.call_id,
                                   to_addr=f"{addr[0]}:{addr[1]}")
                except Exception as echo_err:
                    logger.error("❌ Failed to echo RTP packet", 
                                call_id=self.call_id, 
                                error=str(echo_err))

            # ===== CRITICAL FIX: Direct asyncio UDP reader for test mode =====
            async def test_udp_reader():
                """Direct UDP reader for test mode (bypasses TaskManager)"""
                logger.info("🔄 Test UDP reader started", call_id=self.call_id)
                
                socket = input_transport._socket
                if not socket:
                    logger.error("❌ No socket available for UDP reader", call_id=self.call_id)
                    return
                
                try:
                    packet_count = 0
                    while True:
                        try:
                            logger.debug("🔍 Waiting for UDP packet...", call_id=self.call_id)
                            data, addr = await asyncio.get_event_loop().sock_recvfrom(socket, 4096)
                            
                            packet_count += 1
                            logger.info("📦 Test UDP packet received!", 
                                       call_id=self.call_id,
                                       packet_num=packet_count,
                                       size=len(data), 
                                       from_addr=f"{addr[0]}:{addr[1]}")
                            
                            await test_rtp_handler(data, addr)
                            
                        except Exception as recv_error:
                            logger.error("Error in test UDP reader", 
                                        call_id=self.call_id, 
                                        error=str(recv_error))
                            await asyncio.sleep(0.01)
                            
                except asyncio.CancelledError:
                    logger.info("Test UDP reader cancelled", call_id=self.call_id)
                except Exception as fatal_error:
                    logger.error("Fatal error in test UDP reader", 
                                call_id=self.call_id, 
                                error=str(fatal_error))
            
            # Start test UDP reader with direct asyncio (no TaskManager needed)
            self._test_udp_task = asyncio.create_task(test_udp_reader())
            logger.info("🎯 Test UDP reader task started via asyncio", call_id=self.call_id)
            
            # Override transport's UDP task startup to prevent TaskManager issues
            input_transport._udp_task = self._test_udp_task
            
            # Start the transport
            logger.info("🎵 Starting RTP transport...", call_id=self.call_id)
            
            # Create minimal pipeline for transport startup
            from pipecat.frames.frames import StartFrame
            from pipecat.pipeline.pipeline import Pipeline
            from pipecat.pipeline.task import PipelineTask
            
            # Create simple pipeline: input -> output (echo mode)
            self.pipeline = Pipeline([
                self.transport.input(),
                self.transport.output()
            ])
            
            # Create pipeline task
            self.pipeline_task = PipelineTask(self.pipeline)
            
            # Start the pipeline in the background
            self._pipeline_running_task = asyncio.create_task(self._run_pipeline())
            
            # Give it a moment to start
            await asyncio.sleep(0.1)
            
            # Generate SDP response
            sdp_response = self._generate_sdp_response(rtp_ip)
            self._sdp_response = sdp_response
            
            self.is_running = True
            logger.info("✅ Native call started successfully (RTP TEST MODE)", call_id=self.call_id)
            logger.info("🎯 Test mode: Packets will be logged and echoed back", call_id=self.call_id)
            
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
            # NOT: U-Law decoder kaldırıldı - Pipecat'in native audio conversion'ını kullanıyoruz
            # # 0. U-Law Decoder
            # ulaw_decoder = ULawDecoder()
            # processors.append(ulaw_decoder)

            # 1. VAD Processor
            vad_config = get_config("vad", {})
            vad_processor = VADProcessor(vad_config)
            processors.append(vad_processor)
            
            # 2. STT Processor  
            if self.services.get("stt"):
                stt_processor = STTProcessor(stt_service=self.services["stt"])
                processors.append(stt_processor)
            
            # 3. LLM Processor
            if self.services.get("llm"):
                llm_processor = LLMProcessor(llm_service=self.services["llm"])
                processors.append(llm_processor)
            
            # 4. TTS Processor
            if self.services.get("tts"):
                tts_processor = TTSProcessor(tts_service=self.services["tts"])
                processors.append(tts_processor)
            
            logger.info("✅ Pipeline processors created", 
                       call_id=self.call_id,
                       count=len(processors))
            
            return processors
            
        except Exception as e:
            logger.error("Failed to create processors", call_id=self.call_id, error=str(e))
            raise
    
    def _get_rtp_ip(self) -> str:
        """Get RTP IP address - dynamic detection"""
        try:
            # Önce config'den al
            rtp_cfg = get_section("rtp") or {}
            configured_ip = rtp_cfg.get("ip")
            
            if configured_ip and configured_ip != "0.0.0.0":
                logger.info("🌐 Using configured RTP IP", rtp_ip=configured_ip)
                return configured_ip
            
            # Client 192.168.88.1'den geliyor, Docker container'ı 172.18.0.6
            # Bu durumda Docker host'un client network'ündeki IP'sini kullanmalıyız
            
            # Docker Desktop Windows'ta client'ın erişebileceği IP:
            # Genellikle Docker Desktop host'un Wi-Fi IP'si
            
            # Ana makine Wi-Fi IP'si (client'ın network'ünden erişilebilir)
            # Bu IP client'ın 192.168.88.1 network'ünden erişilebilir olmalı
            host_wifi_ip = "192.168.1.120"  # Ana makine Wi-Fi IP'si
            
            logger.info("🌐 Using host Wi-Fi IP for RTP", 
                       host_ip=host_wifi_ip,
                       note="Client should be able to reach this IP")
            
            return host_wifi_ip
            
        except Exception as e:
            logger.error("Error getting RTP IP", error=str(e))
            # Fallback to localhost if everything fails
            return "127.0.0.1"
    
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
            
            # Check if call already exists (SIP retransmission deduplication)
            existing_call = self.calls.get(call_id)
            if existing_call:
                logger.info("📞 Call already exists, returning existing call", call_id=call_id)
                return existing_call
            
            # Create call with timeout
            call = NativeCall(call_id, sdp_info, self.services)
            
            # Start call with timeout (this will create transport, pipeline, etc.)
            try:
                sdp_response = await asyncio.wait_for(call.start(), timeout=5.0)
                logger.info("✅ Call started within timeout", call_id=call_id)
            except asyncio.TimeoutError:
                logger.error("❌ Call start timeout", call_id=call_id)
                await call.stop()
                raise Exception(f"Call start timeout for {call_id}")
            
            # Store SDP response for OpenSIPS
            call._sdp_response = sdp_response
            
            # Store call
            self.calls[call_id] = call
            
            logger.info("✅ Native call created successfully", call_id=call_id)
            return call
            
        except Exception as e:
            logger.error("❌ Failed to create native call", call_id=call_id, error=str(e), exc_info=True)
            # Cleanup on failure
            if call_id in self.calls:
                del self.calls[call_id]
            raise
    
    async def terminate_call(self, call_id: str):
        """Terminate a call"""
        call = self.calls.get(call_id)
        if call:
            await call.stop()
            del self.calls[call_id]
            logger.info("✅ Call terminated", call_id=call_id)

    def get_call(self, call_id: str) -> Optional[NativeCall]:
        """Get a call by its ID"""
        return self.calls.get(call_id)

    def set_engine(self, engine):
        """Sets the OpenSIPS engine for callbacks."""
        # This might not be needed in the native transport model
        pass

    async def shutdown(self):
        """Shutdown the call manager and terminate all calls."""
        logger.info("Shutting down NativeCallManager...")
        for call_id in list(self.calls.keys()):
            await self.terminate_call(call_id)
        logger.info("All native calls terminated.") 