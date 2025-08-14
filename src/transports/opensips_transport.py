#!/usr/bin/env python3
"""
OpenSIPS Transport - Following Twilio/Telnyx Pattern with VAD Observer
Simplified implementation using serializer, event handlers and VAD observer
"""

import asyncio
import socket
from typing import Optional, Dict, Any, Callable
import structlog
import random
import numpy as np
from transports.rtp_utils import generate_rtp_packet

# Updated to use voice-ai-core instead of full Pipecat
import sys
import os

# Add parent directory to path so voice_ai_core can be imported
parent_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..'))
if parent_path not in sys.path:
    sys.path.insert(0, parent_path)

# Add parent src directory to Python path for local imports
src_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if src_dir not in sys.path:
    sys.path.insert(0, src_dir)

from voice_ai_core.frames import (
    Frame, InputAudioRawFrame, OutputAudioRawFrame, StartFrame, EndFrame,
    CancelFrame, UserStartedSpeakingFrame, UserStoppedSpeakingFrame,
    VADUserStartedSpeakingFrame, VADUserStoppedSpeakingFrame
)
from voice_ai_core.transports import BaseInputTransport, BaseOutputTransport, BaseTransport, TransportParams
from voice_ai_core.pipeline import FrameDirection

# Use voice-ai-core VAD components  
from voice_ai_core.audio import SileroVADAnalyzer, VADState

# Import our new serializer
from serializers.opensips import OpenSIPSFrameSerializer

logger = structlog.get_logger()


class VADObserver:
    """
    VAD Observer - Following Twilio/Telnyx Pattern
    Observes VAD events and logs state transitions for debugging
    """
    
    def __init__(self, call_id: str):
        self._call_id = call_id
        self._vad_state = VADState.QUIET
        self._speech_start_time = None
        self._speech_frames_count = 0
        
    async def on_vad_event(self, frame: Frame) -> None:
        """Handle VAD events - following Twilio/Telnyx logging pattern"""
        
        if isinstance(frame, VADUserStartedSpeakingFrame):
            self._vad_state = VADState.SPEAKING
            self._speech_start_time = asyncio.get_event_loop().time()
            self._speech_frames_count = 0
            logger.info("🎤 VAD DETECTED: User started speaking",
                       call_id=self._call_id,
                       state_transition="QUIET → SPEAKING",
                       pattern="twilio_telnyx_compliant")
                       
        elif isinstance(frame, VADUserStoppedSpeakingFrame):
            self._vad_state = VADState.QUIET
            if self._speech_start_time:
                duration = asyncio.get_event_loop().time() - self._speech_start_time
                logger.info("🔇 VAD DETECTED: User stopped speaking",
                           call_id=self._call_id,
                           state_transition="SPEAKING → QUIET",
                           speech_duration_secs=round(duration, 2),
                           speech_frames_processed=self._speech_frames_count,
                           pattern="twilio_telnyx_compliant")
            self._speech_start_time = None
            
        elif isinstance(frame, UserStartedSpeakingFrame):
            logger.info("👤 USER SPEECH EVENT: Started speaking",
                       call_id=self._call_id,
                       vad_state=self._vad_state.value if hasattr(self._vad_state, 'value') else str(self._vad_state),
                       pattern="twilio_telnyx_compliant")
                       
        elif isinstance(frame, UserStoppedSpeakingFrame):
            logger.info("👤 USER SPEECH EVENT: Stopped speaking",
                       call_id=self._call_id,
                       vad_state=self._vad_state.value if hasattr(self._vad_state, 'value') else str(self._vad_state),
                       pattern="twilio_telnyx_compliant")
        
        # Track speech frames during speaking
        if self._vad_state == VADState.SPEAKING and isinstance(frame, InputAudioRawFrame):
            self._speech_frames_count += 1


class OpenSIPSTransportParams(TransportParams):
    """OpenSIPS Transport Parameters - Following Pydantic BaseModel pattern"""
    
    def __init__(self, bind_ip: str = "0.0.0.0", bind_port: int = 0, 
                 call_id: Optional[str] = None, 
                 serializer: Optional[OpenSIPSFrameSerializer] = None,
                 add_wav_header: bool = False,
                 audio_in_sample_rate: int = 8000,
                 audio_out_sample_rate: int = 8000,
                 audio_in_passthrough: bool = True,
                 **kwargs):
        # Store OpenSIPS specific fields first
        self.bind_ip = bind_ip
        self.bind_port = bind_port
        self.call_id = call_id
        self.serializer = serializer
        self.add_wav_header = add_wav_header
        self.audio_in_sample_rate = audio_in_sample_rate
        self.audio_out_sample_rate = audio_out_sample_rate
        self.audio_in_passthrough = audio_in_passthrough
        
        # Extract parent class parameters from kwargs
        parent_kwargs = {}
        if 'audio_in_enabled' in kwargs:
            parent_kwargs['audio_in_enabled'] = kwargs.pop('audio_in_enabled')
        else:
            parent_kwargs['audio_in_enabled'] = True
            
        if 'audio_out_enabled' in kwargs:
            parent_kwargs['audio_out_enabled'] = kwargs.pop('audio_out_enabled')
        else:
            parent_kwargs['audio_out_enabled'] = True
            
        if 'vad_enabled' in kwargs:
            parent_kwargs['vad_enabled'] = kwargs.pop('vad_enabled')
        else:
            parent_kwargs['vad_enabled'] = True
            
        if 'vad_analyzer' in kwargs:
            parent_kwargs['vad_analyzer'] = kwargs.pop('vad_analyzer')
            
        if 'sample_rate' in kwargs:
            parent_kwargs['sample_rate'] = kwargs.pop('sample_rate')
        else:
            parent_kwargs['sample_rate'] = 16000
            
        if 'channels' in kwargs:
            parent_kwargs['channels'] = kwargs.pop('channels')
        else:
            parent_kwargs['channels'] = 1
        
        # Pass only valid parent parameters
        super().__init__(**parent_kwargs)


class OpenSIPSInputTransport(BaseInputTransport):
    """OpenSIPS Input Transport with UDP/RTP handling and VAD Observer"""
    
    def __init__(self, transport: "OpenSIPSTransport", params: OpenSIPSTransportParams):
        super().__init__(params)
        self._transport = transport
        self._params = params
        self._receiver_task: Optional[asyncio.Task] = None
        self._socket: Optional[socket.socket] = None
        
        # 🔧 VAD Observer - Following Twilio/Telnyx Pattern
        self._vad_observer = VADObserver(params.call_id or "unknown_call")
    
    @property
    def vad_analyzer(self) -> Optional[SileroVADAnalyzer]:
        """🔧 CRITICAL FIX: VAD analyzer property for BaseInputTransport compatibility"""
        return self._params.vad_analyzer
    
    async def _vad_analyze(self, audio_frame: InputAudioRawFrame) -> VADState:
        """🔧 OVERRIDE: Add debug logging to VAD analysis"""
        
        state = VADState.QUIET
        if self.vad_analyzer:
            try:
                # 🔧 DEBUG: Log before VAD analysis
                logger.debug("🔍 VAD Analysis Starting", 
                           call_id=self._params.call_id,
                           audio_length=len(audio_frame.audio),
                           sample_rate=audio_frame.sample_rate,
                           vad_sample_rate=getattr(self.vad_analyzer, 'sample_rate', 'not_set'))
                
                # Debug audio data before VAD
                import numpy as np
                audio_array = np.frombuffer(audio_frame.audio, dtype=np.int16)
                audio_rms = np.sqrt(np.mean(audio_array.astype(np.float32) ** 2))
                audio_max = np.max(np.abs(audio_array))
                audio_min = np.min(audio_array)
                
                logger.debug("�� Audio data for VAD", 
                           call_id=self._params.call_id,
                           samples=len(audio_array),
                           rms=f"{audio_rms:.2f}",
                           max_amplitude=audio_max,
                           min_amplitude=audio_min,
                           audio_hex=audio_frame.audio[:20].hex())
                
                state = await self.get_event_loop().run_in_executor(
                    self._executor, self.vad_analyzer.analyze_audio, audio_frame.audio
                )
                
                
            except Exception as e:
                logger.error("❌ VAD Analysis Failed", 
                           call_id=self._params.call_id,
                           error=str(e))
                           
        else:
            logger.warning("⚠️ No VAD analyzer available", call_id=self._params.call_id)
            
        return state
        
    async def read_frames(self):
        """Read frames from the transport - required abstract method"""
        # This is an async generator that should yield frames
        # For RTP transport, we handle frame reading in _receive_rtp_packets
        # This method is required by BaseInputTransport but not used in our implementation
        while self._running:
            await asyncio.sleep(0.1)
            # No frames to yield - our RTP receiver pushes frames directly
            if False:  # This will never execute but makes it an async generator
                yield None
    
    async def start(self):
        """Start RTP receiver following Twilio/Telnyx pattern with VAD observer"""
        
        # 🔧 CRITICAL FIX: Call parent start FIRST (like Twilio/Telnyx examples)
        # This ensures VAD analyzer is properly configured before we use it
        await super().start()
        
        logger.info("🎤 VAD Configuration verified after start()",
                   call_id=self._params.call_id,
                   vad_available=self.vad_analyzer is not None,
                   vad_sample_rate=getattr(self.vad_analyzer, 'sample_rate', 'not_set') if self.vad_analyzer else None,
                   confidence=self.vad_analyzer.params.confidence if self.vad_analyzer else None,
                   pattern="twilio_telnyx_compliant")
        
        # Ensure UDP socket is created *before* other pipeline stages (e.g. output
        # transport) attempt to reuse it. Creating it here synchronously avoids
        # a race-condition where OpenSIPSOutputTransport starts first and finds
        # `None`, resulting in the fallback socket and one-way audio.

        if self._socket is None:
            import socket as _socket_mod

            self._socket = _socket_mod.socket(_socket_mod.AF_INET, _socket_mod.SOCK_DGRAM)
            self._socket.setsockopt(_socket_mod.SOL_SOCKET, _socket_mod.SO_REUSEADDR, 1)
            
            try:
                self._socket.bind((self._params.bind_ip, self._params.bind_port))
                self._socket.setblocking(False)

                # Update params with the dynamically-assigned port (bind_port may be 0)
                actual_addr = self._socket.getsockname()
                self._params.bind_port = actual_addr[1]

                logger.info(
                    "🎯 RTP UDP SOCKET BOUND SUCCESSFULLY!",
                    bind_address=f"{self._params.bind_ip}:{self._params.bind_port}",
                    socket_family=self._socket.family,
                    socket_type=self._socket.type
                )
                
                # Test socket by trying to receive (non-blocking)
                logger.info("🔍 UDP Socket ready to receive RTP packets",
                           call_id=self._params.call_id,
                           bind_port=self._params.bind_port)
                
            except Exception as e:
                logger.error("❌ FAILED TO BIND UDP SOCKET!", 
                           bind_ip=self._params.bind_ip,
                           bind_port=self._params.bind_port,
                           error=str(e))
                raise

        # Now start async receiving loop which will reuse the existing socket.
        if not self._receiver_task:
            self._receiver_task = asyncio.create_task(self._receive_rtp_packets())
            logger.debug("RTP receiver task started")
        
        # 🔧 CRITICAL FIX: Initialize audio queue for push_audio_frame
        logger.debug("Audio queue initialization completed")
        logger.info("🎵 Audio task and queue initialized", 
                   call_id=self._params.call_id,
                   audio_passthrough=self._params.audio_in_passthrough,
                   audio_queue_created=hasattr(self, '_audio_in_queue'))
        
        # Trigger on_client_connected event
        await self._transport._trigger_event("on_client_connected", self._transport, None)
    
    async def process_frame(self, frame: Frame, direction: FrameDirection):
        """Process frames with VAD observer - following Twilio/Telnyx pattern"""
        
        # 🔧 VAD OBSERVER: Handle VAD events before processing
        if isinstance(frame, (VADUserStartedSpeakingFrame, VADUserStoppedSpeakingFrame,
                             UserStartedSpeakingFrame, UserStoppedSpeakingFrame)):
            await self._vad_observer.on_vad_event(frame)
        
        # 🔧 Also observe audio frames for speech tracking
        elif isinstance(frame, InputAudioRawFrame) and self._vad_observer:
            await self._vad_observer.on_vad_event(frame)
        
        # Continue with normal processing - yield from parent async generator
        async for processed_frame in super().process_frame(frame, direction):
            yield processed_frame
    
    async def stop(self):
        """Stop RTP receiver"""
        await super().stop()
        
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
    
    async def cancel(self):
        """Cancel RTP receiver"""
        await super().cancel() if hasattr(super(), 'cancel') else None
        
        if self._receiver_task:
            self._receiver_task.cancel()
            self._receiver_task = None
        
        if self._socket:
            self._socket.close()
            self._socket = None
    
    async def _receive_rtp_packets(self):
        """RTP packet receiver - simplified following Twilio pattern"""
        try:

            # Socket may already be created eagerly in `start()`. Only create it
            # here if that step was skipped for some reason (e.g. unit tests).
            if self._socket is None:
                self._socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                self._socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                self._socket.bind((self._params.bind_ip, self._params.bind_port))
                self._socket.setblocking(False)

                # Get actual bound address
                actual_addr = self._socket.getsockname()
                self._params.bind_port = actual_addr[1]  # Update with actual port

                logger.info(
                    "RTP receiver bound (lazy)",
                    bind_address=f"{self._params.bind_ip}:{self._params.bind_port}"
                )

            loop = asyncio.get_running_loop()
            packet_count = 0
            
            while True:
                try:
                    data, addr = await loop.sock_recvfrom(self._socket, 2048)
                    packet_count += 1
                    
                    logger.info("🎯 RTP PACKET RECEIVED!", 
                                packet_num=packet_count,
                                size=len(data), 
                                from_addr=f"{addr[0]}:{addr[1]}",
                                data_hex=data[:20].hex())
                    
                    # Use serializer to deserialize RTP packet - following Twilio/Telnyx pattern
                    if self._params.serializer:
                        frame = await self._params.serializer.deserialize(data)
                        if frame:
                            if isinstance(frame, InputAudioRawFrame):
                                logger.info("📤 PUSHING AUDIO FRAME TO VAD PIPELINE!", 
                                           call_id=self._params.call_id,
                                           audio_size=len(frame.audio),
                                           sample_rate=frame.sample_rate,
                                           vad_analyzer_available=self.vad_analyzer is not None)
                                
                                # 🔧 CRITICAL FIX: Manual VAD processing since voice-ai-core BaseInputTransport is simplified
                                # We need to manually run VAD and generate VAD events
                                if self.vad_analyzer:
                                    try:
                                        vad_state = await self._vad_analyze(frame)
                                        logger.info("🎯 VAD ANALYSIS RESULT", 
                                                   call_id=self._params.call_id,
                                                   vad_state=vad_state.value if hasattr(vad_state, 'value') else str(vad_state),
                                                   audio_rms=f"{np.sqrt(np.mean(np.frombuffer(frame.audio, dtype=np.int16).astype(np.float32) ** 2)):.2f}")
                                        
                                        # Generate VAD events based on state transitions
                                        if not hasattr(self, '_last_vad_state'):
                                            self._last_vad_state = VADState.QUIET
                                        
                                        if vad_state == VADState.SPEAKING and self._last_vad_state == VADState.QUIET:
                                            logger.info("🎤 VAD TRANSITION: QUIET → SPEAKING")
                                            await self.push_frame(VADUserStartedSpeakingFrame())
                                            await self.push_frame(UserStartedSpeakingFrame())
                                        elif vad_state == VADState.QUIET and self._last_vad_state == VADState.SPEAKING:
                                            logger.info("🔇 VAD TRANSITION: SPEAKING → QUIET")
                                            await self.push_frame(VADUserStoppedSpeakingFrame())
                                            await self.push_frame(UserStoppedSpeakingFrame())
                                        
                                        self._last_vad_state = vad_state
                                        
                                        # Always push the audio frame to the pipeline
                                        await self.push_frame(frame)
                                        logger.info("🎯 Audio frame pushed to pipeline", 
                                                   call_id=self._params.call_id,
                                                   vad_state=vad_state.value if hasattr(vad_state, 'value') else str(vad_state))
                                        
                                    except Exception as e:
                                        logger.error("❌ Manual VAD processing failed", 
                                                   call_id=self._params.call_id, error=str(e))
                                        # Still push the frame even if VAD fails
                                        await self.push_frame(frame)
                                else:
                                    logger.warning("⚠️ No VAD analyzer - pushing frame without VAD", call_id=self._params.call_id)
                                    await self.push_frame(frame)
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
    
    async def write_frame(self, frame: Frame):
        """Write frame to the transport - required abstract method"""
        await self.send_frame(frame)
        
    async def start(self):
        """Start output transport"""
        await super().start()
        
        # Re-use the same UDP socket that the input transport bound to.
        # Böylece RTP sesi, SDP’de ilan edilen porttan (bind_port) gönderilir;
        # NAT / SBC tarafında paketler beklenen porttan geldiği için ses ulaşır.
        self._socket = self._transport._input_transport._socket
        if self._socket is None:
            # Fallback – shouldn’t normally happen, but keep previous behaviour.
            self._socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            logger.warning("Input socket unavailable – created separate RTP sender socket (may cause audio one-way)")
        else:
            logger.debug("RTP sender reusing input socket (port staying the same)")
        
        # Register default audio destination so frames with destination=None are accepted
        logger.debug("OpenSIPS Output Transport started successfully")
    
    async def send_frame(self, frame: Frame):
        """Send frame using serializer - following Twilio/Telnyx pattern"""
        try:
            if isinstance(frame, OutputAudioRawFrame) and self._params.serializer:
                # Get raw μ-law payload (no header)
                pcmu_data = await self._params.serializer.serialize(frame)
                client_ip = self._params.serializer.media_ip
                client_port = self._params.serializer.media_port
                if pcmu_data and self._socket and client_ip and client_port:
                    loop = asyncio.get_running_loop()
                    # Chunk size: 20ms = 160 bytes at 8kHz μ-law
                    chunk_size = 160
                    for i in range(0, len(pcmu_data), chunk_size):
                        chunk = pcmu_data[i : i + chunk_size]
                        if len(chunk) < chunk_size:
                            chunk = chunk + b"\xff" * (chunk_size - len(chunk))
                        # Build RTP header + payload
                        packet_vars = {
                            'version': 2,
                            'padding': 0,
                            'extension': 0,
                            'csi_count': 0,
                            'marker': 0,
                            'payload_type': 0,  # PCMU
                            'sequence_number': self._sequence_number,
                            'timestamp': self._timestamp,
                            'ssrc': self._ssrc,
                            'payload': chunk
                        }
                        packet_bytes = generate_rtp_packet(packet_vars)
                        await loop.sock_sendto(self._socket, packet_bytes, (client_ip, client_port))
                        logger.debug(
                            "RTP packet sent",
                            size=len(packet_bytes),
                            seq=self._sequence_number,
                            ts=self._timestamp,
                            to_addr=f"{client_ip}:{client_port}"
                        )
                        # Update sequence and timestamp
                        self._sequence_number = (self._sequence_number + 1) & 0xFFFF
                        self._timestamp = (self._timestamp + chunk_size) & 0xFFFFFFFF

                        # Pace the transmission so that packets are sent in real-time
                        # 160 samples @ 8 kHz = 20 ms of audio.
                        await asyncio.sleep(0.02)
            
            # No parent send_frame implementation exists in BaseOutputTransport.
            # Additional pipeline propagation is handled by MediaSender upstream.

        except Exception as e:
            logger.error("Error sending RTP packet", error=str(e))
            # We intentionally do not call a parent implementation as none exists.

    async def write_audio_frame(self, frame: OutputAudioRawFrame):
        """Encode and send raw PCM audio to the client as μ-law RTP.

        This method is called by BaseOutputTransport's media sender. We simply
        delegate to ``send_frame`` which already implements the μ-law
        conversion, RTP header creation and UDP transmission logic. By adding
        this override we ensure that TTSAudioRawFrame / OutputAudioRawFrame
        chunks generated by the TTS service are actually transmitted to the
        customer.
        """
        await self.send_frame(frame)
    
    async def stop(self, frame: EndFrame = None):
        """Stop output transport - required abstract method"""
        await super().stop(frame) if frame else await super().stop()
        logger.info("OpenSIPS Output Transport stopped")
    
    async def cancel(self, frame: CancelFrame = None):
        """Cancel output transport"""
        await super().cancel(frame) if frame else None
        logger.info("OpenSIPS Output Transport cancelled")


class OpenSIPSTransport(BaseTransport):
    """
    OpenSIPS Transport - Following Twilio/Telnyx Pattern with VAD Observer
    Using serializer, event handlers and VAD state monitoring
    """
    
    def __init__(self, params: OpenSIPSTransportParams):
        super().__init__(params)
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
        
    async def start(self):
        """Start the transport"""
        await super().start()
        await self._input_transport.start()
        await self._output_transport.start()
        logger.info("OpenSIPS Transport started", call_id=self._params.call_id)
    
    async def stop(self):
        """Stop the transport"""
        await self._input_transport.stop()
        await self._output_transport.stop()
        await super().stop()
        logger.info("OpenSIPS Transport stopped", call_id=self._params.call_id)
        
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