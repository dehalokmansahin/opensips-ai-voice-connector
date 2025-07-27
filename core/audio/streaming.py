"""
RTP Audio Streaming with UDP + Event Bus pattern
Main RTP packet handling service with multi-threaded processing
"""

import asyncio
import logging
import socket
import struct
import time
import threading
from typing import Dict, Optional, Callable, Any, List
from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor
import queue

from .event_bus import AudioEventBus, AudioEventType, AudioEvent
from .buffering import JitterBuffer, EventReplayBuffer, BufferedAudioPacket
from .codecs import PCMUCodec
from .rtp_basic import RTPPacket, parse_rtp_packet, serialize_rtp_packet
from .threading import MultiThreadedRTPProcessor, ThreadMetrics

logger = logging.getLogger(__name__)

@dataclass
class RTPSessionConfig:
    """Configuration for RTP streaming session"""
    session_id: str
    bind_ip: str = "0.0.0.0"
    bind_port: int = 0
    remote_ip: str = "127.0.0.1" 
    remote_port: int = 5060
    sample_rate: int = 8000
    frame_size_ms: int = 20
    jitter_buffer_depth_ms: int = 60
    replay_buffer_size: int = 100
    enable_packet_validation: bool = True
    enable_quality_monitoring: bool = True

class RTPAudioStreamer:
    """
    Main RTP audio streaming service implementing UDP + Event Bus pattern
    Handles RTP packet reception, processing, and transmission with multi-threading
    """
    
    def __init__(self, config: RTPSessionConfig, event_bus: AudioEventBus):
        self.config = config
        self.event_bus = event_bus
        
        # Core components
        self.udp_socket: Optional[socket.socket] = None
        self.transport = None
        self.protocol = None
        self.jitter_buffer = JitterBuffer(
            buffer_depth_ms=config.jitter_buffer_depth_ms,
            sample_rate=config.sample_rate,
            frame_size_ms=config.frame_size_ms
        )
        self.replay_buffer = EventReplayBuffer(
            buffer_size=config.replay_buffer_size
        )
        self.pcmu_codec = PCMUCodec()
        
        # Multi-threaded processing components
        self.mt_processor = MultiThreadedRTPProcessor(
            session_id=config.session_id,
            max_workers=6,  # Optimized for real-time audio
            ingestion_queue_size=1000,
            transmission_queue_size=500,
            processing_queue_size=800
        )
        
        # Set up processing callbacks
        self.mt_processor.set_callbacks(
            ingestion_callback=self._mt_ingestion_callback,
            processing_callback=self._mt_processing_callback,
            transmission_callback=self._mt_transmission_callback
        )
        
        # Legacy threading support (for backward compatibility)
        self._thread_pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix=f"RTP-{config.session_id}")
        self._output_queue = asyncio.Queue(maxsize=100)
        
        # State management
        self._running = False
        self._session_started = False
        self._processing_tasks: List[asyncio.Task] = []
        
        # Statistics and monitoring
        self._stats = {
            'packets_received': 0,
            'packets_sent': 0,
            'packets_processed': 0,
            'packets_dropped': 0,
            'bytes_received': 0,
            'bytes_sent': 0,
            'session_start_time': 0,
            'last_packet_time': 0,
            'packet_loss_count': 0,
            'jitter_events': 0
        }
        
        # Packet loss detection
        self._expected_seq = 0
        self._last_seq = -1
        self._seq_initialized = False
        
        logger.info(f"RTPAudioStreamer initialized for session {config.session_id}")
    
    async def start(self):
        """Start the RTP audio streaming service"""
        if self._running:
            logger.warning(f"RTPAudioStreamer already running for session {self.config.session_id}")
            return
        
        try:
            self._running = True
            self._stats['session_start_time'] = time.time()
            
            # Initialize UDP socket for RTP
            await self._initialize_udp_socket()
            
            # Start multi-threaded processors
            self.mt_processor.start_workers()
            
            # Start processing tasks
            await self._start_processing_tasks()
            
            # Subscribe to event bus events
            self._subscribe_to_events()
            
            # Publish session started event
            await self.event_bus.publish(AudioEvent(
                event_type=AudioEventType.SESSION_STARTED,
                session_id=self.config.session_id,
                timestamp=time.time(),
                data={'config': self.config.__dict__}
            ))
            
            self._session_started = True
            logger.info(f"RTPAudioStreamer started for session {self.config.session_id} "
                       f"on {self.config.bind_ip}:{self.config.bind_port}")
            
        except Exception as e:
            logger.error(f"Failed to start RTPAudioStreamer: {e}")
            await self.stop()
            raise
    
    async def stop(self):
        """Stop the RTP audio streaming service"""
        if not self._running:
            return
        
        try:
            self._running = False
            
            # Stop processing tasks
            for task in self._processing_tasks:
                if not task.done():
                    task.cancel()
            
            # Wait for tasks to complete
            if self._processing_tasks:
                await asyncio.gather(*self._processing_tasks, return_exceptions=True)
            
            # Stop UDP socket
            if self.transport:
                self.transport.close()
                self.transport = None
                self.protocol = None
            
            if self.udp_socket:
                self.udp_socket.close()
                self.udp_socket = None
            
            # Shutdown multi-threaded processor
            self.mt_processor.shutdown(timeout=5.0)
            
            # Shutdown legacy thread pool
            self._thread_pool.shutdown(wait=True)
            
            # Clear buffers
            self.jitter_buffer.clear_buffer()
            self.replay_buffer.clear_buffer()
            
            # Publish session ended event
            if self._session_started:
                await self.event_bus.publish(AudioEvent(
                    event_type=AudioEventType.SESSION_ENDED,
                    session_id=self.config.session_id,
                    timestamp=time.time(),
                    data={'stats': self._stats.copy()}
                ))
            
            logger.info(f"RTPAudioStreamer stopped for session {self.config.session_id}")
            
        except Exception as e:
            logger.error(f"Error stopping RTPAudioStreamer: {e}")
    
    async def _initialize_udp_socket(self):
        """Initialize UDP socket for RTP packet reception"""
        try:
            # Create UDP socket
            self.udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            
            # Bind to local address
            self.udp_socket.bind((self.config.bind_ip, self.config.bind_port))
            
            # Get actual bound port if auto-assigned
            if self.config.bind_port == 0:
                self.config.bind_port = self.udp_socket.getsockname()[1]
            
            # Set non-blocking
            self.udp_socket.setblocking(False)
            
            # Create asyncio transport
            loop = asyncio.get_running_loop()
            
            class RTPProtocol(asyncio.DatagramProtocol):
                def __init__(self, streamer):
                    self.streamer = streamer
                
                def connection_made(self, transport):
                    self.transport = transport
                
                def datagram_received(self, data, addr):
                    """Handle incoming RTP packet"""
                    asyncio.create_task(self.streamer._on_raw_rtp_received(data, addr))
            
            self.transport, self.protocol = await loop.create_datagram_endpoint(
                lambda: RTPProtocol(self),
                sock=self.udp_socket
            )
            
            logger.info(f"UDP socket initialized: {self.config.bind_ip}:{self.config.bind_port}")
            
        except Exception as e:
            logger.error(f"Failed to initialize UDP socket: {e}")
            raise
    
    async def _start_processing_tasks(self):
        """Start async processing tasks"""
        # Audio processing task
        self._processing_tasks.append(
            asyncio.create_task(self._audio_processing_loop())
        )
        
        # Quality monitoring task
        if self.config.enable_quality_monitoring:
            self._processing_tasks.append(
                asyncio.create_task(self._quality_monitoring_loop())
            )
        
        # Thread-based packet processing
        self._processing_tasks.append(
            asyncio.create_task(self._packet_processing_bridge())
        )
    
    def _subscribe_to_events(self):
        """Subscribe to relevant event bus events"""
        self.event_bus.subscribe(AudioEventType.PACKET_LOSS_DETECTED, self._handle_packet_loss)
        self.event_bus.subscribe(AudioEventType.JITTER_BUFFER_OVERFLOW, self._handle_jitter_overflow)
    
    async def _on_raw_rtp_received(self, rtp_data: bytes, addr):
        """Handle raw RTP packet from UDP socket"""
        try:
            # Parse RTP packet
            rtp_packet = parse_rtp_packet(rtp_data)
            if not rtp_packet:
                logger.debug("Failed to parse RTP packet")
                return
            
            # Extract audio payload and process
            await self._on_rtp_packet_received(rtp_packet.payload)
            
        except Exception as e:
            logger.error(f"Error handling raw RTP packet: {e}")
    
    async def _on_rtp_packet_received(self, audio_data: bytes):
        """Callback for received RTP packets from transport"""
        try:
            current_time = time.time()
            self._stats['packets_received'] += 1
            self._stats['bytes_received'] += len(audio_data)
            self._stats['last_packet_time'] = current_time
            
            # Create buffered packet for multi-threaded processing
            if not self._seq_initialized:
                self._expected_seq = 0
                self._seq_initialized = True
            
            packet = BufferedAudioPacket(
                sequence_number=self._expected_seq,
                timestamp=int(current_time * self.config.sample_rate),
                payload=audio_data,
                received_time=current_time,
                session_id=self.config.session_id
            )
            
            self._expected_seq = (self._expected_seq + 1) & 0xFFFF
            
            # Submit to multi-threaded processor for ingestion
            if not self.mt_processor.submit_for_ingestion(packet):
                self._stats['packets_dropped'] += 1
                logger.warning(f"MT ingestion queue full, dropping packet for session {self.config.session_id}")
            
            # Publish RTP packet event
            await self.event_bus.publish_rtp_packet(
                session_id=self.config.session_id,
                packet_data={
                    'sequence': packet.sequence_number,
                    'timestamp': packet.timestamp,
                    'payload_size': len(audio_data),
                    'received_time': current_time
                }
            )
            
        except Exception as e:
            logger.error(f"Error handling RTP packet: {e}")
    
    def _mt_ingestion_callback(self, packet: BufferedAudioPacket) -> Optional[BufferedAudioPacket]:
        """Multi-threaded ingestion callback - handles packet validation and buffering"""
        try:
            # Validate packet if enabled
            if self.config.enable_packet_validation:
                validation = self.pcmu_codec.validate_pcmu_format(
                    packet.payload, 
                    expected_frame_size=160  # 20ms @ 8kHz
                )
                if not validation['valid']:
                    logger.debug(f"Invalid PCMU packet: {validation['error']}")
                    return None
            
            # Store in replay buffer
            self.replay_buffer.store_packet(packet)
            
            # Add to jitter buffer
            if self.jitter_buffer.add_packet(packet):
                return packet
            else:
                return None
                
        except Exception as e:
            logger.error(f"Error in MT ingestion callback: {e}")
            return None
    
    def _mt_processing_callback(self, packet: BufferedAudioPacket) -> Optional[bytes]:
        """Multi-threaded processing callback - handles audio conversion and processing"""
        try:
            # Get next audio from jitter buffer
            audio_data = self.jitter_buffer.get_next_audio(interpolate_missing=True)
            
            if audio_data:
                # Convert PCMU to PCM for downstream processing
                pcm_data = self.pcmu_codec.decode_pcmu_to_pcm(audio_data)
                self._stats['packets_processed'] += 1
                
                # Schedule async event publishing (non-blocking)
                asyncio.create_task(self.event_bus.publish_audio_ready(
                    session_id=self.config.session_id,
                    audio_data=pcm_data,
                    metadata={
                        'format': 'PCM16',
                        'sample_rate': self.config.sample_rate,
                        'channels': 1,
                        'frame_size_ms': self.config.frame_size_ms
                    }
                ))
                
                return pcm_data
            
            return None
            
        except Exception as e:
            logger.error(f"Error in MT processing callback: {e}")
            return None
    
    def _mt_transmission_callback(self, audio_data: bytes):
        """Multi-threaded transmission callback - handles outbound audio"""
        try:
            # For now, just log that audio is ready for transmission
            # In a full implementation, this would handle outbound RTP
            logger.debug(f"Audio ready for transmission: {len(audio_data)} bytes")
            
        except Exception as e:
            logger.error(f"Error in MT transmission callback: {e}")
    
    async def _packet_processing_bridge(self):
        """Bridge between thread-based processing and async tasks"""
        try:
            while self._running:
                try:
                    # Get packet from queue with timeout
                    packet = await asyncio.get_event_loop().run_in_executor(
                        self._thread_pool,
                        lambda: self._processing_queue.get(timeout=1.0)
                    )
                    
                    # Process packet in thread pool
                    future = self._thread_pool.submit(self._process_packet, packet)
                    processed_packet = await asyncio.wrap_future(future)
                    
                    if processed_packet:
                        # Add to output queue
                        await self._output_queue.put(processed_packet)
                    
                except queue.Empty:
                    continue
                except Exception as e:
                    logger.error(f"Error in packet processing bridge: {e}")
                    
        except asyncio.CancelledError:
            logger.debug("Packet processing bridge cancelled")
        except Exception as e:
            logger.error(f"Fatal error in packet processing bridge: {e}")
    
    def _process_packet(self, packet: BufferedAudioPacket) -> Optional[BufferedAudioPacket]:
        """Process RTP packet in thread pool (CPU-intensive operations)"""
        try:
            # Validate packet if enabled
            if self.config.enable_packet_validation:
                validation = self.pcmu_codec.validate_pcmu_format(
                    packet.payload, 
                    expected_frame_size=160  # 20ms @ 8kHz
                )
                if not validation['valid']:
                    logger.debug(f"Invalid PCMU packet: {validation['error']}")
                    return None
            
            # Store in replay buffer
            self.replay_buffer.store_packet(packet)
            
            # Add to jitter buffer
            if self.jitter_buffer.add_packet(packet):
                self._stats['packets_processed'] += 1
                return packet
            else:
                return None
                
        except Exception as e:
            logger.error(f"Error processing packet: {e}")
            return None
    
    async def _audio_processing_loop(self):
        """Main audio processing loop - handles jitter buffer output"""
        try:
            while self._running:
                try:
                    # Get next audio from jitter buffer
                    audio_data = await asyncio.get_event_loop().run_in_executor(
                        self._thread_pool,
                        lambda: self.jitter_buffer.get_next_audio(interpolate_missing=True)
                    )
                    
                    if audio_data:
                        # Convert PCMU to PCM if needed for downstream processing
                        pcm_data = self.pcmu_codec.decode_pcmu_to_pcm(audio_data)
                        
                        # Publish audio ready event
                        await self.event_bus.publish_audio_ready(
                            session_id=self.config.session_id,
                            audio_data=pcm_data,
                            metadata={
                                'format': 'PCM16',
                                'sample_rate': self.config.sample_rate,
                                'channels': 1,
                                'frame_size_ms': self.config.frame_size_ms
                            }
                        )
                    
                    # Small delay to prevent CPU spinning
                    await asyncio.sleep(0.01)  # 10ms
                    
                except Exception as e:
                    logger.error(f"Error in audio processing loop: {e}")
                    await asyncio.sleep(0.1)
                    
        except asyncio.CancelledError:
            logger.debug("Audio processing loop cancelled")
        except Exception as e:
            logger.error(f"Fatal error in audio processing loop: {e}")
    
    async def _quality_monitoring_loop(self):
        """Monitor audio quality and publish quality events"""
        try:
            last_check = time.time()
            check_interval = 5.0  # seconds
            
            while self._running:
                await asyncio.sleep(1.0)
                
                current_time = time.time()
                if current_time - last_check >= check_interval:
                    # Get buffer status
                    jitter_status = self.jitter_buffer.get_buffer_status()
                    replay_status = self.replay_buffer.get_buffer_status()
                    
                    # Check for quality issues
                    quality_issues = []
                    
                    # High packet loss
                    if jitter_status['stats']['packets_interpolated'] > 10:
                        quality_issues.append('high_packet_loss')
                    
                    # Buffer overflow
                    if jitter_status['stats']['buffer_overflows'] > 0:
                        quality_issues.append('buffer_overflow')
                    
                    # No recent packets
                    if current_time - self._stats['last_packet_time'] > 10:
                        quality_issues.append('no_recent_packets')
                    
                    # Publish quality status
                    if quality_issues:
                        await self.event_bus.publish(AudioEvent(
                            event_type=AudioEventType.QUALITY_DEGRADED,
                            session_id=self.config.session_id,
                            timestamp=current_time,
                            data={
                                'issues': quality_issues,
                                'jitter_status': jitter_status,
                                'replay_status': replay_status,
                                'session_stats': self._stats.copy()
                            }
                        ))
                    
                    last_check = current_time
                    
        except asyncio.CancelledError:
            logger.debug("Quality monitoring loop cancelled")
        except Exception as e:
            logger.error(f"Error in quality monitoring loop: {e}")
    
    async def _handle_packet_loss(self, event: AudioEvent):
        """Handle packet loss detection events"""
        try:
            loss_info = event.data
            logger.warning(f"Packet loss detected in session {event.session_id}: {loss_info}")
            
            # Attempt replay recovery if needed
            if 'missing_sequences' in loss_info:
                missing_seqs = loss_info['missing_sequences']
                if len(missing_seqs) <= 5:  # Only try to recover small gaps
                    start_seq = min(missing_seqs)
                    end_seq = max(missing_seqs)
                    
                    replayed_packets = self.replay_buffer.replay_packets(
                        session_id=event.session_id,
                        start_sequence=start_seq,
                        end_sequence=end_seq
                    )
                    
                    if replayed_packets:
                        logger.info(f"Recovered {len(replayed_packets)} packets from replay buffer")
                        
                        # Re-add recovered packets to jitter buffer
                        for packet in replayed_packets:
                            self.jitter_buffer.add_packet(packet)
            
        except Exception as e:
            logger.error(f"Error handling packet loss: {e}")
    
    async def _handle_jitter_overflow(self, event: AudioEvent):
        """Handle jitter buffer overflow events"""
        try:
            logger.warning(f"Jitter buffer overflow in session {event.session_id}")
            self._stats['jitter_events'] += 1
            
            # Could implement adaptive buffer sizing here
            
        except Exception as e:
            logger.error(f"Error handling jitter overflow: {e}")
    
    async def send_audio(self, pcm_audio: bytes) -> bool:
        """Send PCM audio data via RTP (convert to PCMU first)"""
        try:
            if not self._running or not self.transport:
                return False
            
            # Convert PCM to PCMU
            pcmu_data = self.pcmu_codec.encode_pcm_to_pcmu(pcm_audio)
            
            # Create RTP packet
            rtp_packet = RTPPacket(
                version=2,
                payload_type=0,  # PCMU
                sequence_number=self._stats['packets_sent'] & 0xFFFF,
                timestamp=int(time.time() * self.config.sample_rate) & 0xFFFFFFFF,
                ssrc=hash(self.config.session_id) & 0xFFFFFFFF,
                payload=pcmu_data
            )
            
            # Serialize and send
            rtp_data = serialize_rtp_packet(rtp_packet)
            self.transport.sendto(rtp_data, (self.config.remote_ip, self.config.remote_port))
            
            self._stats['packets_sent'] += 1
            self._stats['bytes_sent'] += len(pcmu_data)
            
            return True
            
        except Exception as e:
            logger.error(f"Error sending audio: {e}")
            return False
    
    def get_session_status(self) -> Dict[str, Any]:
        """Get current session status and statistics"""
        status = {
            'session_id': self.config.session_id,
            'running': self._running,
            'session_started': self._session_started,
            'config': self.config.__dict__,
            'stats': self._stats.copy(),
            'jitter_buffer': self.jitter_buffer.get_buffer_status(),
            'replay_buffer': self.replay_buffer.get_buffer_status()
        }
        
        if self.udp_socket:
            status['udp_socket'] = {
                'local_endpoint': f"{self.config.bind_ip}:{self.config.bind_port}",
                'remote_endpoint': f"{self.config.remote_ip}:{self.config.remote_port}"
            }
        
        # Add multi-threading metrics
        status['multi_threading'] = self.mt_processor.get_processing_metrics()
        
        return status
    
    def get_local_endpoint(self) -> Optional[tuple]:
        """Get local RTP endpoint (IP, port)"""
        if self.udp_socket:
            return (self.config.bind_ip, self.config.bind_port)
        return None