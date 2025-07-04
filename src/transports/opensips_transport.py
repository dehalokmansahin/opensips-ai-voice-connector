#!/usr/bin/env python3
"""
OpenSIPS Transport - Clean RTP Transport with VAD Integration
Handles RTP audio streaming with voice activity detection for OpenSIPS integration
"""

import asyncio
import socket
from typing import Optional, Dict, Any, Callable
import structlog
import random
from transports.rtp_utils import generate_rtp_packet

from pipecat.frames.frames import (
    Frame, InputAudioRawFrame, OutputAudioRawFrame, StartFrame, EndFrame,
    CancelFrame, UserStartedSpeakingFrame, UserStoppedSpeakingFrame,
    VADUserStartedSpeakingFrame, VADUserStoppedSpeakingFrame
)
from pipecat.transports.base_input import BaseInputTransport
from pipecat.transports.base_output import BaseOutputTransport  
from pipecat.transports.base_transport import BaseTransport, TransportParams
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.audio.vad.vad_analyzer import VADState
from pipecat.processors.frame_processor import FrameDirection

from serializers.opensips import OpenSIPSFrameSerializer

logger = structlog.get_logger()


class VADObserver:
    """VAD Event Observer for monitoring voice activity detection."""
    
    def __init__(self, call_id: str):
        self._call_id = call_id
        self._vad_state = VADState.QUIET
        self._speech_start_time = None
        self._speech_frames_count = 0
        
    async def on_vad_event(self, frame: Frame) -> None:
        """Handle VAD events with structured logging."""
        
        if isinstance(frame, VADUserStartedSpeakingFrame):
            self._vad_state = VADState.SPEAKING
            self._speech_start_time = asyncio.get_event_loop().time()
            self._speech_frames_count = 0
            logger.info("🎤 VAD: User started speaking",
                       call_id=self._call_id,
                       state_transition="QUIET → SPEAKING")
                       
        elif isinstance(frame, VADUserStoppedSpeakingFrame):
            self._vad_state = VADState.QUIET
            if self._speech_start_time:
                duration = asyncio.get_event_loop().time() - self._speech_start_time
                logger.info("🔇 VAD: User stopped speaking",
                           call_id=self._call_id,
                           state_transition="SPEAKING → QUIET",
                           speech_duration_secs=round(duration, 2),
                           speech_frames_processed=self._speech_frames_count)
            self._speech_start_time = None
            
        elif isinstance(frame, UserStartedSpeakingFrame):
            logger.info("👤 User speech started",
                       call_id=self._call_id,
                       vad_state=self._vad_state.value if hasattr(self._vad_state, 'value') else str(self._vad_state))
                       
        elif isinstance(frame, UserStoppedSpeakingFrame):
            logger.info("👤 User speech stopped",
                       call_id=self._call_id,
                       vad_state=self._vad_state.value if hasattr(self._vad_state, 'value') else str(self._vad_state))
        
        # Track speech frames during speaking
        if self._vad_state == VADState.SPEAKING and isinstance(frame, InputAudioRawFrame):
            self._speech_frames_count += 1


class OpenSIPSTransportParams(TransportParams):
    """OpenSIPS Transport Parameters with RTP-specific settings."""
    
    # OpenSIPS specific fields
    bind_ip: str = "0.0.0.0"
    bind_port: int = 0
    call_id: Optional[str] = None
    serializer: Optional[OpenSIPSFrameSerializer] = None
    
    # Audio settings optimized for RTP
    add_wav_header: bool = False
    audio_in_enabled: bool = True
    audio_out_enabled: bool = True
    audio_in_sample_rate: int = 8000   # RTP input rate
    audio_out_sample_rate: int = 8000  # RTP output rate
    audio_in_passthrough: bool = True  # Required for audio processing


class OpenSIPSInputTransport(BaseInputTransport):
    """OpenSIPS Input Transport with RTP handling and VAD integration."""
    
    def __init__(self, transport: "OpenSIPSTransport", params: OpenSIPSTransportParams):
        super().__init__(params)
        self._transport = transport
        self._params = params
        self._receiver_task: Optional[asyncio.Task] = None
        self._socket: Optional[socket.socket] = None
        self._vad_observer = VADObserver(params.call_id or "unknown_call")
    
    @property
    def vad_analyzer(self) -> Optional[SileroVADAnalyzer]:
        """VAD analyzer property for BaseInputTransport compatibility."""
        return self._params.vad_analyzer
    
    async def _vad_analyze(self, audio_frame: InputAudioRawFrame) -> VADState:
        """Analyze audio frame for voice activity with error handling."""
        from pipecat.audio.vad.vad_analyzer import VADState
        
        state = VADState.QUIET
        if self.vad_analyzer:
            try:
                logger.debug("🔍 VAD analysis", 
                           call_id=self._params.call_id,
                           audio_length=len(audio_frame.audio),
                           sample_rate=audio_frame.sample_rate)
                
                state = await self.get_event_loop().run_in_executor(
                    self._executor, self.vad_analyzer.analyze_audio, audio_frame.audio
                )
                
            except Exception as e:
                logger.error("❌ VAD analysis failed", 
                           call_id=self._params.call_id,
                           error=str(e))
        else:
            logger.warning("⚠️ No VAD analyzer available", call_id=self._params.call_id)
            
        return state
        
    async def start(self, frame: StartFrame):
        """Start RTP receiver with VAD configuration."""
        
        # Initialize parent transport first
        await super().start(frame)
        
        logger.info("🎤 VAD configuration initialized",
                   call_id=self._params.call_id,
                   vad_available=self.vad_analyzer is not None,
                   confidence=self.vad_analyzer.params.confidence if self.vad_analyzer else None)
        
        if not self._receiver_task:
            self._receiver_task = asyncio.create_task(self._receive_rtp_packets())
            logger.debug("RTP receiver task started")
        
        # Initialize audio processing
        await self.set_transport_ready(frame)
        logger.info("🎵 Audio processing initialized", 
                   call_id=self._params.call_id,
                   audio_passthrough=self._params.audio_in_passthrough)
        
        # Trigger connection event
        await self._transport._trigger_event("on_client_connected", self._transport, None)
        await self.push_frame(frame)
    
    async def process_frame(self, frame: Frame, direction: FrameDirection):
        """Process frames with VAD observer - following Twilio/Telnyx pattern"""
        
        # 🔧 VAD OBSERVER: Handle VAD events before processing
        if isinstance(frame, (VADUserStartedSpeakingFrame, VADUserStoppedSpeakingFrame,
                             UserStartedSpeakingFrame, UserStoppedSpeakingFrame)):
            await self._vad_observer.on_vad_event(frame)
        
        # 🔧 Also observe audio frames for speech tracking
        elif isinstance(frame, InputAudioRawFrame) and self._vad_observer:
            await self._vad_observer.on_vad_event(frame)
        
        # Continue with normal processing
        await super().process_frame(frame, direction)
    
    async def stop(self, frame: EndFrame):
        """Stop RTP receiver"""
        await super().stop(frame)
        
        if self._receiver_task:
            self._receiver_task.cancel()
            try:
                await self._receiver_task
            except asyncio.CancelledError:
                pass
            self._receiver_task = None
        
        if self._socket:
            self._socket.close()
            self._socket = None
        
        # Trigger on_client_disconnected event
        await self._transport._trigger_event("on_client_disconnected", self._transport, None)
    
    async def cancel(self, frame: CancelFrame):
        """Cancel RTP receiver"""
        await super().cancel(frame)
        
        if self._receiver_task:
            self._receiver_task.cancel()
            self._receiver_task = None
        
        if self._socket:
            self._socket.close()
            self._socket = None
    
    async def _receive_rtp_packets(self):
        """RTP packet receiver - simplified following Twilio pattern"""
        try:
            # Create and bind socket
            self._socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self._socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self._socket.bind((self._params.bind_ip, self._params.bind_port))
            self._socket.setblocking(False)
            
            # Get actual bound address
            actual_addr = self._socket.getsockname()
            self._params.bind_port = actual_addr[1]  # Update with actual port
            
            logger.info("RTP receiver bound", 
                       bind_address=f"{self._params.bind_ip}:{self._params.bind_port}")
            
            loop = asyncio.get_running_loop()
            packet_count = 0
            
            while True:
                try:
                    data, addr = await loop.sock_recvfrom(self._socket, 2048)
                    packet_count += 1
                    
                    logger.debug("RTP packet received", 
                                packet_num=packet_count,
                                size=len(data), 
                                from_addr=f"{addr[0]}:{addr[1]}")
                    
                    # Use serializer to deserialize RTP packet - following Twilio/Telnyx pattern
                    if self._params.serializer:
                        frame = await self._params.serializer.deserialize(data)
                        if frame:
                            if isinstance(frame, InputAudioRawFrame):
                                logger.debug("📤 Pushing audio frame to VAD pipeline", 
                                           call_id=self._params.call_id,
                                           audio_size=len(frame.audio),
                                           sample_rate=frame.sample_rate,
                                           audio_task_running=self._audio_task is not None,
                                           vad_analyzer_available=self.vad_analyzer is not None)
                                
                                # 🔧 DEBUG: Check audio queue before pushing
                                queue_size_before = self._audio_in_queue.qsize() if hasattr(self, '_audio_in_queue') else "no_queue"
                                await self.push_audio_frame(frame)  # Audio frames go to audio channel
                                queue_size_after = self._audio_in_queue.qsize() if hasattr(self, '_audio_in_queue') else "no_queue"
                                
                                logger.debug("🎯 Audio frame pushed to VAD queue", 
                                           call_id=self._params.call_id,
                                           queue_before=queue_size_before,
                                           queue_after=queue_size_after,
                                           note="Frame should now be processed by BaseInputTransport._audio_task_handler()")
                            else:
                                await self.push_frame(frame)        # Other frames go to normal channel
                        else:
                            logger.warning("❌ Serializer returned None frame", 
                                         call_id=self._params.call_id,
                                         packet_size=len(data))
                    
                except ConnectionResetError:
                    continue
                except OSError as e:
                    if e.errno == 10054:  # Windows connection reset
                        continue
                    else:
                        logger.error("Socket error in RTP receiver", error=str(e))
                        await asyncio.sleep(0.01)
                except Exception as e:
                    logger.error("RTP receive error", error=str(e))
                    await asyncio.sleep(0.01)
                    
        except Exception as e:
            logger.error("Fatal error in RTP receiver", error=str(e))
            raise


class OpenSIPSOutputTransport(BaseOutputTransport):
    """OpenSIPS Output Transport with RTP sending"""
    
    def __init__(self, transport: "OpenSIPSTransport", params: OpenSIPSTransportParams):
        super().__init__(params)
        self._transport = transport
        self._params = params
        self._socket: Optional[socket.socket] = None
        # RTP header state for outgoing packets
        self._sequence_number = random.randint(0, 0xFFFF)
        self._timestamp = random.randint(0, 0xFFFFFFFF)
        self._ssrc = random.randint(0, 0xFFFFFFFF)
        
    async def start(self, frame: StartFrame):
        """Start output transport"""
        await super().start(frame)
        
        # Create UDP socket for sending
        self._socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        logger.debug("RTP sender socket created")
        
        # Packet pacing variables (20 ms per 160-byte PCMU chunk)
        self._send_interval = 0.02  # seconds
        self._next_send_time = 0.0
        
        # Register default audio destination so frames with destination=None are accepted
        await self.set_transport_ready(frame)
        
        await self.push_frame(frame)
    
    async def write_audio_frame(self, frame: OutputAudioRawFrame):
        """Encode PCM (16 kHz) to μ-law (8 kHz) and send as 20 ms RTP packets.

        This is the method expected by ``BaseOutputTransport.MediaSender``. It
        replaces the previous (incorrect) ``send_frame`` override so that audio
        actually reaches the subscriber over the network, mirroring Pipecat's
        FastAPI/Twilio reference implementation.
        """
        try:
            if not self._params.serializer:
                return

            pcmu_data: bytes | None = await self._params.serializer.serialize(frame)
            client_ip: str | None = self._params.serializer.media_ip
            client_port: int | None = self._params.serializer.media_port

            if not (pcmu_data and self._socket and client_ip and client_port):
                # Destination not yet known or nothing to send.
                return

            loop = asyncio.get_running_loop()
            chunk_size = 160  # 20 ms of 8 kHz PCMU

            for i in range(0, len(pcmu_data), chunk_size):
                chunk = pcmu_data[i : i + chunk_size]
                if len(chunk) < chunk_size:
                    chunk += b"\xff" * (chunk_size - len(chunk))

                packet_vars = {
                    "version": 2,
                    "padding": 0,
                    "extension": 0,
                    "csi_count": 0,
                    "marker": 1 if self._sequence_number == 0 else 0,  # Marker on first packet
                    "payload_type": 0,  # PCMU
                    "sequence_number": self._sequence_number,
                    "timestamp": self._timestamp,
                    "ssrc": self._ssrc,
                    "payload": chunk,
                }

                packet_bytes = generate_rtp_packet(packet_vars)
                await loop.sock_sendto(self._socket, packet_bytes, (client_ip, client_port))

                logger.debug(
                    "📡 RTP packet sent",
                    size=len(packet_bytes),
                    to_addr=f"{client_ip}:{client_port}",
                    seq=self._sequence_number,
                    call_id=self._params.call_id,
                )

                # Update RTP sequence and timestamp for next packet
                self._sequence_number = (self._sequence_number + 1) & 0xFFFF
                self._timestamp = (self._timestamp + chunk_size) & 0xFFFFFFFF

                # Pace packets in real-time so the subscriber's jitter buffer isn't starved
                current_time = asyncio.get_running_loop().time()
                if self._next_send_time == 0:
                    # First packet → send immediately, schedule next
                    self._next_send_time = current_time + self._send_interval
                else:
                    sleep_for = self._next_send_time - current_time
                    if sleep_for > 0:
                        await asyncio.sleep(sleep_for)
                    self._next_send_time += self._send_interval

        except Exception as e:  # pragma: no cover – network errors are non-fatal
            logger.error("Error sending RTP packet", error=str(e))


class OpenSIPSTransport(BaseTransport):
    """
    OpenSIPS Transport - Following Twilio/Telnyx Pattern with VAD Observer
    Using serializer, event handlers and VAD state monitoring
    """
    
    def __init__(self, params: OpenSIPSTransportParams):
        super().__init__()
        self._params = params
        self._input_transport = OpenSIPSInputTransport(self, params)
        self._output_transport = OpenSIPSOutputTransport(self, params)
        
        # Event handlers - following Twilio/Telnyx pattern
        self._event_handlers: Dict[str, Callable] = {}
        
        logger.info("OpenSIPS Transport initialized", 
                   call_id=params.call_id,
                   bind_ip=params.bind_ip,
                   bind_port=params.bind_port,
                   vad_observer_enabled=True,
                   pattern="twilio_telnyx_compliant")
    
    def input(self) -> OpenSIPSInputTransport:
        """Return input transport"""
        return self._input_transport
    
    def output(self) -> OpenSIPSOutputTransport:
        """Return output transport"""
        return self._output_transport
    
    def event_handler(self, event_name: str):
        """Event handler decorator - following Twilio/Telnyx pattern"""
        def decorator(func):
            self._event_handlers[event_name] = func
            logger.debug("Event handler registered", event_name=event_name)
            return func
        return decorator
    
    async def _trigger_event(self, event_name: str, *args, **kwargs):
        """Trigger event handler"""
        if event_name in self._event_handlers:
            try:
                await self._event_handlers[event_name](*args, **kwargs)
                logger.debug("Event handler executed", event_name=event_name)
            except Exception as e:
                logger.error("Error in event handler", event_name=event_name, error=str(e))
    
    def update_client_info(self, client_ip: str, client_port: int):
        """Update client RTP information"""
        if self._params.serializer:
            self._params.serializer.update_sdp_info(media_ip=client_ip, media_port=client_port)
        
        logger.info("Client RTP info updated", 
                   call_id=self._params.call_id,
                   client_ip=client_ip, 
                   client_port=client_port)
    
    def get_bind_info(self) -> Dict[str, Any]:
        """Get transport bind information"""
        return {
            'bind_ip': self._params.bind_ip,
            'bind_port': self._params.bind_port,
            'call_id': self._params.call_id
        }
    
    def get_sdp_info(self) -> Dict[str, Any]:
        """Get SDP information for 200 OK response"""
        if self._params.serializer:
            return self._params.serializer.get_sdp_info()
        
        # Fallback SDP info
        media_ip = self._params.bind_ip
        if media_ip == "0.0.0.0":
            try:
                # Try to detect local IP
                import socket
                with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                    s.connect(("8.8.8.8", 80))
                    media_ip = s.getsockname()[0]
            except Exception:
                media_ip = "127.0.0.1"
        
        return {
            'media_ip': media_ip,
            'media_port': self._params.bind_port,
            'audio_format': 'PCMU',
            'call_id': self._params.call_id
        }


def create_opensips_transport(
    bind_ip: str = "0.0.0.0",
    bind_port: int = 0,
    call_id: str = None,
    vad_analyzer: Optional[SileroVADAnalyzer] = None,
    **kwargs
) -> OpenSIPSTransport:
    """
    Create OpenSIPS transport following Twilio/Telnyx pattern with VAD Observer
    
    This function follows the exact same pattern as Twilio/Telnyx examples:
    - VAD analyzer is passed to transport params (like in examples)
    - Serializer is created and passed to transport params
    - Transport handles VAD processing internally via BaseInputTransport
    - VAD Observer monitors and logs VAD state transitions
    """
    # Create serializer (equivalent to TwilioFrameSerializer/TelnyxFrameSerializer)
    serializer = OpenSIPSFrameSerializer(
        call_id=call_id or "default_call",
        media_ip=bind_ip,
        media_port=bind_port
    )
    
    # 🔧 TWILIO EXACT PATTERN: Copy exact FastAPIWebsocketParams configuration
    # From Twilio bot.py lines 65-71
    params = OpenSIPSTransportParams(
        bind_ip=bind_ip,
        bind_port=bind_port,
        call_id=call_id,
        serializer=serializer,
        
        # 🔧 TWILIO EXACT PATTERN: Same params as FastAPIWebsocketParams
        audio_in_enabled=True,
        audio_out_enabled=True,
        add_wav_header=False,        # 🔧 From Twilio example
        vad_analyzer=vad_analyzer,   # 🔧 From Twilio example
        
        # OpenSIPS specific - keep minimal config
        # 🔧 CRITICAL FIX: Use pipeline sample rate (16kHz) for VAD compatibility
        # RTP comes in at 8kHz but serializer upsamples to 16kHz before VAD
        audio_in_sample_rate=16000,  # Pipeline processes at 16kHz (after serializer upsampling)
        audio_out_sample_rate=8000,  # RTP output is 8kHz  
        audio_in_passthrough=True,   # Must be True for audio to reach pipeline
        **kwargs
    )
    
    transport = OpenSIPSTransport(params)
    
    logger.info("OpenSIPS transport created with VAD observer", 
               call_id=call_id,
               bind_ip=bind_ip,
               bind_port=bind_port,
               vad_configured=vad_analyzer is not None,
               vad_observer_enabled=True,
               pattern="twilio_telnyx_compliant")
    
    return transport 