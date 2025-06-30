"""
OpenSIPS Call Management
Eski call.py mantığını koruyarak Pipecat pipeline ile entegre eder
"""

import random
import socket
import asyncio
import logging
import secrets
import datetime
from queue import Queue, Empty
from typing import Optional, Dict, Any
import structlog

from transports.rtp_utils import decode_rtp_packet, generate_rtp_packet
from transports.audio_utils import pcmu_to_pcm16k, pcm16k_to_pcmu
from config import Config
from pipeline.ai_engine import PipelineAI

logger = structlog.get_logger()

# RTP port management - will be initialized when first Call is created
_available_ports = None
_min_rtp_port = 35000
_max_rtp_port = 65000

def _init_rtp_ports():
    """Initialize RTP port configuration"""
    global _available_ports, _min_rtp_port, _max_rtp_port
    
    if _available_ports is not None:
        return  # Already initialized
    
    try:
        rtp_cfg = Config.get("rtp")
        _min_rtp_port = int(rtp_cfg.get("min_port", "35000"))
        _max_rtp_port = int(rtp_cfg.get("max_port", "65000"))
        logger.info("RTP config loaded", min_port=_min_rtp_port, max_port=_max_rtp_port)
    except (TypeError, ValueError, AttributeError):
        # Fallback values if config is not available
        logger.warning("RTP config not available, using defaults", 
                      min_port=_min_rtp_port, max_port=_max_rtp_port)
    
    _available_ports = set(range(_min_rtp_port, _max_rtp_port + 1))  # +1 to include max_port
    logger.info("RTP port pool initialized", total_ports=len(_available_ports))


def _debug_port_status():
    """Debug function to check port pool status"""
    global _available_ports, _min_rtp_port, _max_rtp_port
    _init_rtp_ports()
    
    total_ports = _max_rtp_port - _min_rtp_port + 1
    available_count = len(_available_ports) if _available_ports else 0
    used_count = total_ports - available_count
    
    logger.info("🔍 PORT DEBUG STATUS", 
               min_port=_min_rtp_port,
               max_port=_max_rtp_port, 
               total_ports=total_ports,
               available_ports=available_count,
               used_ports=used_count,
               available_list=sorted(list(_available_ports)) if _available_ports else [])


class NoAvailablePorts(Exception):
    """There are no available ports"""
    pass


class Call:
    """
    Call class that handles RTP socket binding and audio processing
    Eski call.py mantığını korur, pipeline ile entegre eder
    """
    
    def __init__(self, b2b_key: str, mi_conn, sdp_info: dict, pipeline_manager, config: dict = None):
        """
        Args:
            b2b_key: OpenSIPS B2B key
            mi_conn: OpenSIPS MI connection
            sdp_info: Parsed SDP information
            pipeline_manager: Pipecat pipeline manager
            config: AI configuration
        """
        # RTP configuration
        _init_rtp_ports()  # Ensure RTP config is loaded
        
        try:
            rtp_cfg = Config.get("rtp")
            host_ip = rtp_cfg.get('bind_ip', '0.0.0.0')
            rtp_ip = rtp_cfg.get('ip', None)
        except:
            host_ip = '0.0.0.0'
            rtp_ip = None
        
        # Get hostname if rtp_ip not configured or set to 0.0.0.0
        if not rtp_ip or rtp_ip == '0.0.0.0':
            try:
                # For Docker environments, use the actual Windows host IP that client can reach
                # Client is on 192.168.88.x network, so use Windows host LAN IP
                rtp_ip = "192.168.1.120"  # Windows host LAN IP - client can reach this
                logger.info("🌐 Using Windows host LAN IP for SDP", 
                           rtp_ip=rtp_ip,
                           reason="Client accessible from 192.168.88.x network")
                    
            except Exception as e:
                logger.warning("🌐 Failed to set host IP, using fallback", error=str(e))
                rtp_ip = "127.0.0.1"

        # Call properties
        self.b2b_key = b2b_key
        self.mi_conn = mi_conn
        self.pipeline_manager = pipeline_manager
        self.config = config or {}

        # Client RTP endpoint (from SDP)
        self.client_addr = sdp_info.get('media_ip') or sdp_info.get('connection_ip')
        self.client_port = sdp_info.get('media_port')
        
        # Call state
        self.paused = False
        self.terminated = False
        self.first_packet = True
        self.last_received_packet_time = datetime.datetime.now()
        self.call_start_time = datetime.datetime.now()

        # RTP queues and events
        self.rtp_out_queue = Queue()
        self.stop_event = asyncio.Event()
        self.stop_event.clear()

        # Socket ve SDP başlangıçta None
        self.serversock = None
        self.response_sdp = None
        
        # PipelineAI başlangıçta None
        self.pipeline_ai = None
        
        logger.info("Call instance created (pre-start)", call_key=b2b_key)

    async def start(self):
        """
        Asenkron başlatma işlemlerini gerçekleştirir:
        - Socket oluşturur ve bağlar
        - SDP yanıtı oluşturur
        - PipelineAI'yi başlatır
        - RTP dinleme ve gönderme döngülerini başlatır
        """
        logger.info(f"Starting async initialization for call {self.b2b_key}...")
        
        # RTP yapılandırmasını al
        try:
            rtp_cfg = Config.get("rtp")
            host_ip = rtp_cfg.get('bind_ip', '0.0.0.0')
            rtp_ip = rtp_cfg.get('ip', None)
        except Exception:
            host_ip = '0.0.0.0'
            rtp_ip = None
            
        if not rtp_ip or rtp_ip == '0.0.0.0':
            try:
                rtp_ip = "192.168.1.120"
                logger.info("🌐 Using Windows host LAN IP for SDP", rtp_ip=rtp_ip)
            except Exception as e:
                logger.warning("🌐 Failed to set host IP, using fallback", error=str(e))
                rtp_ip = "127.0.0.1"

        # Create and bind RTP socket
        self.serversock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.bind_rtp_socket(host_ip)
        self.serversock.setblocking(False)

        # Generate SDP response
        self.response_sdp = self.generate_response_sdp(rtp_ip)

        # Initialize PipelineAI integration
        self.pipeline_ai = PipelineAI(self, self.config or {})
        
        # Start the pipeline stream now that the call is established
        # In a real scenario, this might wait for ACK, but for now, it's ok here.
        await self.pipeline_ai.start_stream()

        # Start RTP processing loops
        loop = asyncio.get_event_loop()
        self.rtp_read_task = loop.create_task(self.read_rtp_packets())
        self.rtp_send_task = loop.create_task(self.send_rtp_packets())
        self.first_packet_timeout_task = loop.create_task(self._check_first_packet_timeout())

        logger.info(f"Call {self.b2b_key} started successfully.")

    def bind_rtp_socket(self, host_ip: str):
        """Bind RTP socket to available port"""
        global _available_ports
        
        # Initialize RTP ports if not done yet
        _init_rtp_ports()
        
        if not _available_ports:
            raise NoAvailablePorts()
        
        port = secrets.choice(list(_available_ports))
        _available_ports.remove(port)
        self.serversock.bind((host_ip, port))

    def generate_response_sdp(self, rtp_ip: str) -> str:
        """Generate SDP response for 200 OK"""
        local_port = self.serversock.getsockname()[1]
        
        logger.info("🎵 Generating SDP response", 
                   rtp_ip=rtp_ip, 
                   local_port=local_port,
                   call_key=self.b2b_key)
        
        # Basic SDP template - PCMU/8000 codec
        sdp_lines = [
            "v=0",
            f"o=- {random.randint(1000000000, 9999999999)} {random.randint(1000000000, 9999999999)} IN IP4 {rtp_ip}",
            "s=OpenSIPS AI Voice Connector",
            f"c=IN IP4 {rtp_ip}",
            "t=0 0",
            f"m=audio {local_port} RTP/AVP 0",
            "a=rtpmap:0 PCMU/8000",
            "a=sendrecv"
        ]
        
        sdp_response = "\n".join(sdp_lines)
        logger.info("🎵 SDP response generated", 
                   sdp_preview=sdp_response[:100] + "..." if len(sdp_response) > 100 else sdp_response,
                   call_key=self.b2b_key)
        
        return sdp_response

    def get_sdp_body(self) -> str:
        """Get SDP body for OpenSIPS response"""
        return self.response_sdp

    async def read_rtp_packets(self):
        """Read incoming RTP packets (called by event loop)"""
        # Debug entry into read_rtp_packet
        logger.debug("🛠️ Entered read_rtp_packet", call_key=self.b2b_key)
        try:
            data, addr = self.serversock.recvfrom(4096)
            
            logger.debug("🎤 RTP data received", 
                        call_key=self.b2b_key,
                        source_addr=f"{addr[0]}:{addr[1]}", 
                        data_size=len(data),
                        first_packet=self.first_packet,
                        expected_client=f"{self.client_addr}:{self.client_port}")
            
            # Update last received packet time for timeout detection
            self.last_received_packet_time = datetime.datetime.now()
            
            # First packet sets client address - learn from actual traffic
            if self.first_packet:
                self.first_packet = False
                # Update client address to actual source (Docker network mapping)
                self.client_addr = addr[0]
                self.client_port = addr[1]
                logger.info("🎯 FIRST RTP PACKET received! Learning client address", 
                           call_key=self.b2b_key,
                           original_sdp_client=f"{self.client_addr}:{self.client_port}",
                           actual_client=f"{addr[0]}:{addr[1]}",
                           local_port=self.serversock.getsockname()[1])
                # Start sending RTP packets when first packet is received
                asyncio.create_task(self.send_rtp_packets())

            # Accept packets from learned client address OR if still first few packets
            packet_count = getattr(self, '_packet_count', 0)
            self._packet_count = packet_count + 1
            
            # Be flexible with source validation for first 10 packets (NAT/Docker network adaptation)
            if addr[0] != self.client_addr or addr[1] != self.client_port:
                if packet_count < 10:
                    logger.info("🔄 Updating client address from packet", 
                               call_key=self.b2b_key,
                               old_addr=f"{self.client_addr}:{self.client_port}",
                               new_addr=f"{addr[0]}:{addr[1]}",
                               packet_num=packet_count)
                    self.client_addr = addr[0] 
                    self.client_port = addr[1]
                else:
                    logger.debug("RTP packet from different source", 
                               call_key=self.b2b_key,
                               source=f"{addr[0]}:{addr[1]}",
                               expected=f"{self.client_addr}:{self.client_port}")
                    return

            # Drop packets if paused
            if self.paused:
                return

            # Decode RTP packet
            try:
                rtp_packet = decode_rtp_packet(data.hex())
                pcmu_payload = bytes.fromhex(rtp_packet['payload'])
                
                # Convert PCMU to PCM16k for pipeline
                pcm_data = pcmu_to_pcm16k(pcmu_payload)
                
                # Send to pipeline
                logger.debug("🎯 PIPELINE CHECK", 
                           call_key=self.b2b_key,
                           has_pipeline_manager=bool(self.pipeline_manager),
                           has_pcm_data=bool(pcm_data),
                           pcm_data_len=len(pcm_data) if pcm_data else 0)
                
                if self.pipeline_manager and pcm_data:
                    push_task = asyncio.create_task(
                        self.pipeline_manager.push_audio(pcm_data)
                    )
                    logger.debug("🛠️ Scheduled pipeline push_audio task", 
                                 call_key=self.b2b_key,
                                 task_id=id(push_task))
                    logger.info("🎵 Audio frame pushed to pipeline", 
                               call_key=self.b2b_key,
                               frame_size=len(pcm_data))
                else:
                    if not self.pipeline_manager:
                        logger.warning("❌ No pipeline manager available", call_key=self.b2b_key)
                    if not pcm_data:
                        logger.warning("❌ No PCM data after conversion", call_key=self.b2b_key)
                
                logger.info("📦 RTP packet RECEIVED and processed", 
                           call_key=self.b2b_key,
                           pcmu_size=len(pcmu_payload),
                           pcm_size=len(pcm_data) if 'pcm_data' in locals() and pcm_data else 0,
                           source_addr=f"{addr[0]}:{addr[1]}",
                           seq_num=rtp_packet.get('sequence_number'),
                           packet_num=packet_count)
                
            except ValueError as e:
                logger.warning("Invalid RTP packet", call_key=self.b2b_key, error=str(e), packet_hex=data.hex()[:100])

        except socket.error as e:
            if not self.terminated:  # Only log errors if not already terminated
                logger.error("RTP socket read error", call_key=self.b2b_key, error=str(e))

    async def send_rtp_packets(self):
        """Send outgoing RTP packets"""
        # Wait for client address to be set (first packet received)
        wait_count = 0
        while not self.client_addr or not self.client_port:
            await asyncio.sleep(0.1)
            wait_count += 1
            if wait_count > 50:  # 5 seconds timeout
                logger.error("Timeout waiting for client address", call_key=self.b2b_key)
                return
        
        # RTP packet parameters
        sequence_number = random.randint(0, 10000)
        timestamp = random.randint(0, 10000)
        ssrc = random.randint(0, 2**31)
        payload_type = 0  # PCMU
        ts_increment = 160  # 20ms at 8kHz
        ptime = 20  # 20ms
        marker = 1
        packet_no = 0
        start_time = datetime.datetime.now()
        
        # Track client activity
        self.last_received_packet_time = datetime.datetime.now()
        self.client_timeout = 30.0  # 30 seconds timeout for client inactivity
        
        logger.info("RTP sender started", call_key=self.b2b_key, client_addr=self.client_addr, client_port=self.client_port)

        while not self.stop_event.is_set():
            try:
                # Check for client timeout
                now = datetime.datetime.now()
                if (now - self.last_received_packet_time).total_seconds() > self.client_timeout:
                    logger.info("Client timeout detected, terminating call", call_key=self.b2b_key)
                    self.terminated = True
                    self.stop_event.set()
                    asyncio.create_task(self.close())
                    break
                
                # Get audio from pipeline or queue
                payload = None
                try:
                    # Try to get generated audio from pipeline
                    payload = self.rtp_out_queue.get_nowait()
                except Empty:
                    if self.terminated:
                        logger.info("RTP sender terminating", call_key=self.b2b_key)
                        break
                    # Send silence if no audio available and not paused
                    if not self.paused:
                        # Generate silence (PCMU 0xFF)
                        payload = bytes([0xFF] * 160)  # 20ms silence
                    else:
                        payload = None
                
                # Send RTP packet if we have payload
                if payload:
                    rtp_packet = generate_rtp_packet({
                        'version': 2,
                        'padding': 0,
                        'extension': 0,
                        'csi_count': 0,
                        'marker': marker,
                        'payload_type': payload_type,
                        'sequence_number': sequence_number,
                        'timestamp': timestamp,
                        'ssrc': ssrc,
                        'payload': payload.hex()
                    })
                    marker = 0  # Only set on first packet
                    sequence_number += 1
                    
                    # Send packet to client
                    self.serversock.sendto(
                        bytes.fromhex(rtp_packet),
                        (self.client_addr, self.client_port)
                    )
                    
                    logger.info("📤 RTP packet SENT", 
                               call_key=self.b2b_key,
                               payload_size=len(payload),
                               seq=sequence_number,
                               dest_addr=f"{self.client_addr}:{self.client_port}")
                
                # Update timestamp and calculate next packet time
                timestamp += ts_increment
                packet_no += 1
                next_time = start_time + datetime.timedelta(milliseconds=ptime * packet_no)
                now = datetime.datetime.now()
                
                # Calculate sleep time to maintain timing
                drift = (next_time - now).total_seconds()
                if drift > 0:
                    await asyncio.sleep(drift)
                
            except Exception as e:
                logger.error("Error in RTP send loop", 
                           call_key=self.b2b_key, 
                           error=str(e))
                await asyncio.sleep(0.02)  # Avoid tight loop on error

    def queue_audio(self, pcm_data: bytes):
        """
        Queue audio data to be sent via RTP
        
        Args:
            pcm_data: PCM 16-bit audio data
        """
        try:
            # Convert PCM16k to PCMU for RTP
            pcmu_data = pcm16k_to_pcmu(pcm_data)
            
            if pcmu_data and len(pcmu_data) > 0:
                # Split into 20ms chunks (160 bytes at 8kHz)
                chunk_size = 160
                for i in range(0, len(pcmu_data), chunk_size):
                    chunk = pcmu_data[i:i+chunk_size]
                    # Pad if needed
                    if len(chunk) < chunk_size:
                        chunk = chunk + bytes([0xFF] * (chunk_size - len(chunk)))
                    self.rtp_out_queue.put_nowait(chunk)
        
        except Exception as e:
            logger.error("Error queuing audio", error=str(e), key=self.b2b_key)

    def resume(self):
        """Resume call audio"""
        if not self.paused:
            return
        logger.info("Call resumed", key=self.b2b_key)
        self.paused = False

    def pause(self):
        """Pause call audio"""
        if self.paused:
            return
        logger.info("Call paused", key=self.b2b_key)
        self.paused = True

    async def close(self):
        """Close call and release resources"""
        logger.info("🔚 CALL CLOSING", key=self.b2b_key, terminated=self.terminated)
        
        # Mark as terminated to stop processing
        if self.terminated:
            return # Already closing
        self.terminated = True
        logger.info("📋 Call marked as terminated", key=self.b2b_key)

        # Pipeline will automatically stop when call ends
        logger.info("🎬 Pipeline will stop automatically when call ends", call_key=self.b2b_key)
        
        # Stop RTP processing
        self.stop_event.set()
        logger.info("🛑 RTP stop event set", key=self.b2b_key)
        
        # Remove socket reader
        try:
            loop = asyncio.get_running_loop()
            loop.remove_reader(self.serversock.fileno())
        except Exception as e:
            logger.error("Error removing socket reader", error=str(e), key=self.b2b_key)
        
        # Release RTP port
        try:
            free_port = self.serversock.getsockname()[1]
            self.serversock.close()
            
            global _available_ports
            if _available_ports is not None and free_port >= _min_rtp_port and free_port <= _max_rtp_port:
                _available_ports.add(free_port)
                logger.info("RTP port released", port=free_port, key=self.b2b_key)
                # Debug port status after release
                _debug_port_status()
        except Exception as e:
            logger.error("Error closing RTP socket", error=str(e), key=self.b2b_key)

    def terminate(self):
        """Terminate the call and release resources"""
        if self.terminated:
            return

        self.terminated = True
        logger.info("Terminating call", call_key=self.b2b_key)

        # Stop the pipeline stream
        if self.pipeline_ai:
            asyncio.create_task(self.pipeline_ai.stop_stream())

        # Stop RTP packet reading and close socket
        loop = asyncio.get_running_loop()
        try:
            loop.remove_reader(self.serversock.fileno())
        except Exception as e:
            logger.error("Error removing socket reader", error=str(e), key=self.b2b_key)
        
        # Release RTP port
        try:
            free_port = self.serversock.getsockname()[1]
            self.serversock.close()
            
            global _available_ports
            if _available_ports is not None and free_port >= _min_rtp_port and free_port <= _max_rtp_port:
                _available_ports.add(free_port)
                logger.info("RTP port released", port=free_port, key=self.b2b_key)
                # Debug port status after release
                _debug_port_status()
        except Exception as e:
            logger.error("Error closing RTP socket", error=str(e), key=self.b2b_key)

    async def _check_first_packet_timeout(self):
        """İlk RTP paketi için zaman aşımı kontrolü"""
        timeout_seconds = 10.0
        check_interval = 2.0
        
        while not self.terminated and self.first_packet:
            await asyncio.sleep(check_interval)
            elapsed = (datetime.datetime.now() - self.call_start_time).total_seconds()
            
            if elapsed > timeout_seconds:
                logger.warning("⏰ No RTP packets received after 10 seconds", 
                             call_key=self.b2b_key,
                             expected_client=f"{self.client_addr}:{self.client_port}",
                             rtp_port=self.serversock.getsockname()[1],
                             sdp_sent="200 OK with SDP sent to client")
                # Wait another 10 seconds before next warning
                await asyncio.sleep(timeout_seconds)


class CallManager:
    """Aramaları yöneten ve pipeline ile entegrasyonu sağlayan sınıf"""

    def __init__(self, mi_conn):
        """
        Args:
            mi_conn: OpenSIPS MI connection
        """
        self.mi_conn = mi_conn
        self.calls: Dict[str, Call] = {}
        self.shutdown_event = asyncio.Event()
        self._output_queue = asyncio.Queue()
        self.pipeline_manager = None # Will be set later
        
        # Pipeline'dan gelen verileri işlemek için bir görev başlat
        asyncio.create_task(self._process_pipeline_output())
        
        logger.info("CallManager initialized")

    def set_pipeline_manager(self, pipeline_manager):
        """Sets the pipeline manager and its output callback."""
        self.pipeline_manager = pipeline_manager
        if hasattr(self.pipeline_manager, '_output_callback'):
             # This is a bit of a hack, directly setting the callback.
             # A better approach would be to pass it in the constructor.
            self.pipeline_manager._output_callback = self._pipeline_output_callback
            logger.info("Pipeline manager output callback configured.")

    async def _pipeline_output_callback(self, output_type: str, data: Any):
        """Callback to receive data from the pipeline and put it in a queue."""
        await self._output_queue.put((output_type, data))

    async def _process_pipeline_output(self):
        """Pipeline'dan gelen ses ve sistem mesajlarını işler"""
        while not self.shutdown_event.is_set():
            try:
                output_type, data = await self._output_queue.get()
                if output_type == "audio":
                    # For now, assume one call and broadcast audio
                    for call in self.calls.values():
                        if not call.paused:
                            call.queue_audio(data)
                elif output_type == "event":
                    logger.info("Pipeline event received", event=data)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Error in pipeline output handler", error=str(e))

    async def create_call(self, b2b_key: str, sdp_info: dict, config: dict = None) -> Optional['Call']:
        """Yeni bir arama oluşturur ve başlatır"""
        logger.info("🚀 Creating call STARTED", key=b2b_key, sdp_info=sdp_info)
        
        if not sdp_info or 'media_ip' not in sdp_info or 'media_port' not in sdp_info:
            logger.error("❌ Cannot create call, missing SDP info", key=b2b_key)
            return None
        
        logger.info("✅ SDP validation passed", key=b2b_key)

        if not self.pipeline_manager:
            logger.error("❌ Cannot create call, no pipeline manager", key=b2b_key)
            return None
            
        logger.info("✅ Pipeline manager available", key=b2b_key)

        if not self.mi_conn:
            logger.error("❌ Cannot create call, no MI connection", key=b2b_key)
            return None
            
        logger.info("✅ MI connection available", key=b2b_key)
        
        _debug_port_status()
        
        logger.debug("🔄 Pipeline will handle StartFrame automatically")
        
        try:
            logger.info("🔧 Creating Call instance...", key=b2b_key)
            call = Call(b2b_key, self.mi_conn, sdp_info, self.pipeline_manager, config)
            
            logger.info("🔧 Starting async resources for call...", key=b2b_key)
            await call.start() # Asenkron başlatma
            
            self.calls[b2b_key] = call
            logger.info(f"✅ Call {b2b_key} created and started successfully.")
            return call
            
        except NoAvailablePorts:
            logger.error("❌ No available RTP ports to create call", key=b2b_key)
            return None
        except Exception as e:
            import traceback
            logger.error(f"❌ Exception creating call {b2b_key}", error=str(e), traceback=traceback.format_exc())
            return None

    async def terminate_call(self, b2b_key: str):
        """Bir aramayı sonlandırır"""
        logger.info("🔚 TERMINATING call", key=b2b_key, active_calls_before=len(self.calls))
        
        call = self.calls.get(b2b_key)
        if call:
            await call.close()
            self.calls.pop(b2b_key, None)
            logger.info("✅ Call terminated successfully", key=b2b_key, active_calls_after=len(self.calls))
        else:
            logger.warning("⚠️ Call not found for termination", key=b2b_key, available_calls=list(self.calls.keys()))

    def get_call(self, b2b_key: str) -> Optional[Call]:
        """Get call by key"""
        return self.calls.get(b2b_key)

    async def shutdown(self):
        """Shutdown all active calls"""
        logger.info("Shutting down call manager", active_calls=len(self.calls))
        
        # Make a copy of keys to avoid modification during iteration
        call_keys = list(self.calls.keys())
        
        for key in call_keys:
            await self.terminate_call(key) 