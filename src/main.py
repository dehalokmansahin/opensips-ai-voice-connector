#!/usr/bin/env python3
"""
OpenSIPS AI Voice Connector - Main Entry Point
Pipecat tabanlı gerçek zamanlı ses işleme pipeline'ı
"""

import sys
import os
import asyncio
import signal
import socket
from pathlib import Path
import configparser
import structlog

# Python path setup
current_dir = Path(__file__).parent
src_path = current_dir
pipecat_src_path = current_dir.parent / "pipecat" / "src"

if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))
if str(pipecat_src_path) not in sys.path:
    sys.path.insert(0, str(pipecat_src_path))

# soxr compatibility stub for NumPy 2.x
import numpy as np
if not hasattr(sys.modules, 'soxr'):
    class SoxrStub:
        def resample(self, *args, **kwargs):
            return args[0]  # Return input unchanged
    sys.modules['soxr'] = SoxrStub()

# Setup logging first
logger = structlog.get_logger()

# AI Service imports
from services.llama_websocket import LlamaWebsocketLLMService
from services.vosk_websocket import VoskWebsocketSTTService
from services.piper_websocket import PiperWebsocketTTSService

# Pipeline imports
from pipeline.manager import PipelineManager

# OpenSIPS integration imports
from utils import get_ai, FLAVORS, get_ai_flavor, get_user, get_to, indialog
from config import Config

# OpenSIPS MI integration
try:
    from opensips import OpenSIPS
    OPENSIPS_MI_AVAILABLE = True
except ImportError:
    OpenSIPS = None
    OPENSIPS_MI_AVAILABLE = False
    logger.warning("OpenSIPS library not available")

# Mock OpenSIPS MI class for development
class MockOpenSIPSMI:
    """Mock OpenSIPS MI connection for development/testing"""
    
    def __init__(self, **kwargs):
        self.config = kwargs
        logger.info("Mock OpenSIPS MI connection initialized", config=kwargs)
    
    def execute(self, command: str, params: dict = None):
        """Mock MI command execution"""
        logger.info("Mock MI command", command=command, params=params)
        return {"status": "success", "message": "Mock response"}

# SDP parsing
try:
    from aiortc.sdp import SessionDescription
    SDP_PARSING_AVAILABLE = True
except ImportError:
    SessionDescription = None
    SDP_PARSING_AVAILABLE = False
    logger.warning("SDP parsing not available")

class CallManager:
    """Call management for OpenSIPS sessions"""
    
    def __init__(self, pipeline_manager, mi_conn):
        self.pipeline_manager = pipeline_manager
        self.mi_conn = mi_conn
        self.active_calls = {}
        
    async def create_call(self, call_key: str, params: dict):
        """Yeni call oluştur ve pipeline'a bağla"""
        try:
            # Debug: param types
            logger.debug("CallManager create_call params", 
                        key=call_key, 
                        params_keys=list(params.keys()),
                        body_type=type(params.get('body', 'missing')).__name__)
            
            # SDP parsing - temporary bypass for debugging
            if 'body' not in params:
                logger.warning("No SDP body in INVITE - continuing without SDP")
                params['body'] = ""
                
            sdp_str = params['body']
            logger.info("🔍 DEBUG: SDP processing", 
                       body_type=type(sdp_str).__name__, 
                       body_length=len(str(sdp_str)),
                       body_preview=str(sdp_str)[:100])
            
            # Force string conversion for safety
            if isinstance(sdp_str, dict):
                logger.error("❌ FOUND BUG: body is dict, converting to string", body_dict=sdp_str)
                sdp_str = str(sdp_str)
            elif not isinstance(sdp_str, str):
                logger.error("❌ FOUND BUG: body is not string", body_type=type(sdp_str).__name__)
                sdp_str = str(sdp_str)
                
            # Parse SDP for audio configuration
            logger.info("✅ ENABLING SDP parsing")
            sdp = self.parse_sdp(sdp_str)
            
            if not sdp:
                logger.error("Failed to parse SDP", sdp_preview=sdp_str[:100])
                return None
            
            # AI flavor selection
            flavor = get_ai_flavor(params)
            logger.info("Selected AI flavor", key=call_key, flavor=flavor)
            
            # Create call object (simplified for now)
            call_info = {
                'key': call_key,
                'sdp': sdp,
                'flavor': flavor,
                'params': params,
                'to': get_to(params),
                'user': get_user(params)
            }
            
            # Store call
            self.active_calls[call_key] = call_info
            
            # TODO: Pipeline integration
            # await self.pipeline_manager.add_call(call_info)
            
            logger.info("Call created successfully", key=call_key, flavor=flavor)
            return call_info
            
        except Exception as e:
            logger.error("Error creating call", key=call_key, error=str(e))
            return None
    
    def parse_sdp(self, sdp_str: str) -> dict:
        """SDP string'ini parse et"""
        try:
            logger.debug("Parsing SDP", sdp_length=len(sdp_str))
            
            if not sdp_str or not sdp_str.strip():
                logger.warning("Empty SDP content")
                return None
            
            sdp_info = {
                'media_ip': None,
                'media_port': None,
                'audio_format': 'PCMU',  # Default
                'connection_ip': None
            }
            
            lines = sdp_str.strip().split('\n')
            for line in lines:
                line = line.strip()
                
                # Connection information
                if line.startswith('c='):
                    # c=IN IP4 192.168.88.1
                    parts = line.split()
                    if len(parts) >= 3:
                        sdp_info['connection_ip'] = parts[2]
                        sdp_info['media_ip'] = parts[2]  # Fallback
                
                # Media description  
                elif line.startswith('m='):
                    # m=audio 4082 RTP/AVP 0
                    parts = line.split()
                    if len(parts) >= 2 and parts[0] == 'audio':
                        try:
                            sdp_info['media_port'] = int(parts[1])
                        except ValueError:
                            logger.warning("Invalid media port", port=parts[1])
                            
                        # Audio format (payload type)
                        if len(parts) >= 4:
                            payload_type = parts[3]
                            if payload_type == '0':
                                sdp_info['audio_format'] = 'PCMU'
                            elif payload_type == '8':
                                sdp_info['audio_format'] = 'PCMA'
                            else:
                                sdp_info['audio_format'] = f'PT_{payload_type}'
            
            logger.info("SDP parsed successfully", 
                       media_ip=sdp_info['media_ip'], 
                       media_port=sdp_info['media_port'],
                       audio_format=sdp_info['audio_format'])
            
            return sdp_info
            
        except Exception as e:
            logger.error("Error parsing SDP", error=str(e), sdp_preview=sdp_str[:100])
            return None

    async def terminate_call(self, call_key: str):
        """Call'ı sonlandır"""
        try:
            if call_key in self.active_calls:
                call_info = self.active_calls[call_key]
                
                # TODO: Pipeline cleanup
                # await self.pipeline_manager.remove_call(call_key)
                
                del self.active_calls[call_key]
                logger.info("Call terminated", key=call_key)
            else:
                logger.warning("Terminate request for unknown call", key=call_key)
                
        except Exception as e:
            logger.error("Error terminating call", key=call_key, error=str(e))
    
    def get_call(self, call_key: str):
        """Call bilgilerini al"""
        return self.active_calls.get(call_key)

class OpenSIPSEventHandler:
    """OpenSIPS Event Handler - E_UA_SESSION eventlerini işler"""
    
    def __init__(self, host="0.0.0.0", port=8090, mi_conn=None):
        self.host = host
        self.port = port
        self.socket = None
        self.running = False
        self.mi_conn = mi_conn
        self.call_manager = None
        
    def set_call_manager(self, call_manager):
        """Call manager'ı set et"""
        self.call_manager = call_manager
        
    async def start(self):
        """Event handler'ı başlat"""
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.socket.bind((self.host, self.port))
            self.socket.setblocking(False)
            self.running = True
            
            logger.info("OpenSIPS Event Handler started", host=self.host, port=self.port)
            
            # Listen for incoming OpenSIPS events
            while self.running:
                try:
                    loop = asyncio.get_event_loop()
                    data, addr = await loop.sock_recvfrom(self.socket, 4096)
                    
                    # Process OpenSIPS event
                    await self.handle_opensips_event(data.decode('utf-8'), addr)
                    
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    logger.error("Error in OpenSIPS event handler", error=str(e))
                    await asyncio.sleep(0.1)
                    
        except Exception as e:
            logger.error("Failed to start OpenSIPS event handler", error=str(e))
            raise
    
    async def handle_opensips_event(self, event_data: str, addr):
        """OpenSIPS event'ini işle"""
        try:
            logger.debug("Received OpenSIPS event", 
                       from_addr=f"{addr[0]}:{addr[1]}", 
                       event_preview=event_data[:200])
            
            # Parse OpenSIPS event (E_UA_SESSION format)
            # Format: "E_UA_SESSION::key=value;key=value;..."
            if "E_UA_SESSION" in event_data:
                await self.handle_ua_session_event(event_data)
            else:
                logger.warning("Unknown OpenSIPS event format", event=event_data[:100])
                
        except Exception as e:
            logger.error("Error handling OpenSIPS event", error=str(e))
    
    async def handle_ua_session_event(self, event_data: str):
        """UA Session event'ini işle"""
        try:
            # Parse event parameters
            params = {}
            if "::" in event_data:
                param_string = event_data.split("::", 1)[1]
                for param in param_string.split(";"):
                    if "=" in param:
                        key, value = param.split("=", 1)
                        params[key.strip()] = value.strip()
            
            call_key = params.get("key")
            method = params.get("method", "UNKNOWN")
            
            logger.info("UA Session event", key=call_key, method=method)
            
            if method == "INVITE":
                await self.handle_invite(call_key, params)
            elif method == "BYE":
                await self.handle_bye(call_key, params)
            elif method == "CANCEL":
                await self.handle_cancel(call_key, params)
            else:
                logger.info("Unhandled UA session method", method=method, key=call_key)
                
        except Exception as e:
            logger.error("Error handling UA session event", error=str(e))
    
    async def handle_invite(self, call_key: str, params: dict):
        """INVITE event'ini işle - yeni çağrı başlat"""
        try:
            logger.info("Processing INVITE", key=call_key)
            
            if not self.call_manager:
                logger.error("Call manager not available")
                await self.send_response(call_key, "INVITE", 500, "Server Internal Error")
                return
            
            # Create call
            call_info = await self.call_manager.create_call(call_key, params)
            
            if call_info:
                # Success - send 200 OK
                # TODO: Generate proper SDP response
                await self.send_response(call_key, "INVITE", 200, "OK", "")
                logger.info("INVITE processed successfully", key=call_key)
            else:
                # Error - send 500
                await self.send_response(call_key, "INVITE", 500, "Server Internal Error")
                
        except Exception as e:
            logger.error("Error handling INVITE", key=call_key, error=str(e))
            await self.send_response(call_key, "INVITE", 500, "Server Internal Error")
    
    async def handle_bye(self, call_key: str, params: dict):
        """BYE event'ini işle - çağrıyı sonlandır"""
        try:
            logger.info("Processing BYE", key=call_key)
            
            if self.call_manager:
                await self.call_manager.terminate_call(call_key)
            
            # Send 200 OK for BYE
            await self.send_response(call_key, "BYE", 200, "OK")
                
        except Exception as e:
            logger.error("Error handling BYE", key=call_key, error=str(e))
    
    async def handle_cancel(self, call_key: str, params: dict):
        """CANCEL event'ini işle"""
        try:
            logger.info("Processing CANCEL", key=call_key)
            
            if self.call_manager:
                await self.call_manager.terminate_call(call_key)
                
        except Exception as e:
            logger.error("Error handling CANCEL", key=call_key, error=str(e))
    
    async def send_response(self, call_key: str, method: str, code: int, reason: str, body: str = None):
        """OpenSIPS'e MI response gönder"""
        try:
            if not self.mi_conn:
                logger.warning("MI connection not available")
                return
                
            params = {
                'key': call_key,
                'method': method,
                'code': code,
                'reason': reason
            }
            
            if body:
                params['body'] = body
                
            # Send MI command
            result = self.mi_conn.execute('ua_session_reply', params)
            logger.debug("Sent MI response", key=call_key, code=code, result=result)
            
        except Exception as e:
            logger.error("Error sending MI response", key=call_key, error=str(e))
    
    async def stop(self):
        """Event handler'ı durdur"""
        self.running = False
        if self.socket:
            self.socket.close()
        logger.info("OpenSIPS Event Handler stopped")

class SIPListener:
    """SIP Listener - OpenSIPS'ten gelen SIP çağrılarını dinler (port 8089)"""
    
    def __init__(self, host="0.0.0.0", port=8089, call_manager=None):
        self.host = host
        self.port = port
        self.socket = None
        self.running = False
        self.call_manager = call_manager
        
    async def start(self):
        """SIP listener'ı başlat"""
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.socket.bind((self.host, self.port))
            self.socket.setblocking(False)
            self.running = True
            
            logger.info("SIP Listener started", host=self.host, port=self.port)
            
            # Listen for incoming SIP messages from OpenSIPS
            while self.running:
                try:
                    loop = asyncio.get_event_loop()
                    data, addr = await loop.sock_recvfrom(self.socket, 4096)
                    
                    # Process SIP message
                    await self.handle_sip_message(data.decode('utf-8'), addr)
                    
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    logger.error("Error in SIP listener", error=str(e))
                    await asyncio.sleep(0.1)
                    
        except Exception as e:
            logger.error("Failed to start SIP listener", error=str(e))
            raise
    
    async def handle_sip_message(self, sip_data: str, addr):
        """SIP mesajını işle"""
        try:
            logger.info("Received SIP message", from_addr=addr, message_preview=sip_data[:200])
            
            # Parse SIP method
            lines = sip_data.strip().split('\n')
            if not lines:
                return
                
            first_line = lines[0].strip()
            
            if first_line.startswith('INVITE'):
                await self.handle_invite(sip_data, addr)
            elif first_line.startswith('BYE'):
                await self.handle_bye(sip_data, addr)
            elif first_line.startswith('CANCEL'):
                await self.handle_cancel(sip_data, addr)
            elif first_line.startswith('ACK'):
                await self.handle_ack(sip_data, addr)
            else:
                logger.debug("Unhandled SIP method", method=first_line)
                
        except Exception as e:
            logger.error("Error handling SIP message", error=str(e))
    
    async def handle_invite(self, sip_data: str, addr):
        """INVITE mesajını işle"""
        try:
            logger.info("Processing INVITE from OpenSIPS", from_addr=addr)
            
            # Parse basic SIP headers
            headers = {}
            body = ""
            in_body = False
            
            for line in sip_data.split('\n'):
                line = line.strip()
                if not line:
                    in_body = True
                    continue
                    
                if in_body:
                    body += line + '\n'
                elif ':' in line:
                    key, value = line.split(':', 1)
                    headers[key.strip().lower()] = value.strip()
            
            # Extract call information
            call_id = headers.get('call-id', 'unknown')
            from_header = headers.get('from', '')
            to_header = headers.get('to', '')
            
            logger.info("INVITE details", call_id=call_id, from_=from_header, to=to_header)
            
            # Create call via call manager
            if self.call_manager:
                call_params = {
                    'method': 'INVITE',
                    'call_id': call_id,
                    'from': from_header,
                    'to': to_header,
                    'body': body.strip(),
                    'headers': headers,
                    'remote_addr': addr
                }
                
                await self.call_manager.create_call(call_id, call_params)
                
                # Send 200 OK response
                await self.send_response(addr, call_id, '200', 'OK', headers)
            else:
                logger.error("No call manager available")
                await self.send_response(addr, call_id, '500', 'Internal Server Error')
                
        except Exception as e:
            logger.error("Error handling INVITE", error=str(e))
    
    async def handle_bye(self, sip_data: str, addr):
        """BYE mesajını işle"""
        try:
            # Parse Call-ID
            call_id = 'unknown'
            for line in sip_data.split('\n'):
                if line.lower().startswith('call-id:'):
                    call_id = line.split(':', 1)[1].strip()
                    break
            
            logger.info("Processing BYE", call_id=call_id, from_addr=addr)
            
            # Terminate call
            if self.call_manager:
                await self.call_manager.terminate_call(call_id)
            
            # Send 200 OK response  
            await self.send_response(addr, call_id, '200', 'OK')
            
        except Exception as e:
            logger.error("Error handling BYE", error=str(e))
    
    async def handle_cancel(self, sip_data: str, addr):
        """CANCEL mesajını işle"""
        try:
            # Parse Call-ID
            call_id = 'unknown'
            for line in sip_data.split('\n'):
                if line.lower().startswith('call-id:'):
                    call_id = line.split(':', 1)[1].strip()
                    break
            
            logger.info("Processing CANCEL", call_id=call_id, from_addr=addr)
            
            # Terminate call
            if self.call_manager:
                await self.call_manager.terminate_call(call_id)
            
            # Send 200 OK response
            await self.send_response(addr, call_id, '200', 'OK')
            
        except Exception as e:
            logger.error("Error handling CANCEL", error=str(e))
    
    async def handle_ack(self, sip_data: str, addr):
        """ACK mesajını işle"""
        try:
            # Parse Call-ID
            call_id = 'unknown'
            for line in sip_data.split('\n'):
                if line.lower().startswith('call-id:'):
                    call_id = line.split(':', 1)[1].strip()
                    break
            
            logger.debug("Processing ACK", call_id=call_id, from_addr=addr)
            # ACK doesn't need response
            
        except Exception as e:
            logger.error("Error handling ACK", error=str(e))
    
    async def send_response(self, addr, call_id: str, code: str, reason: str, request_headers: dict = None):
        """SIP response gönder"""
        try:
            # Build SIP response
            response = f"SIP/2.0 {code} {reason}\r\n"
            
            if request_headers:
                # Copy required headers from request
                for header in ['via', 'from', 'to', 'call-id', 'cseq']:
                    if header in request_headers:
                        response += f"{header.title()}: {request_headers[header]}\r\n"
            else:
                response += f"Call-ID: {call_id}\r\n"
            
            response += f"Content-Length: 0\r\n"
            response += "\r\n"
            
            # Send response
            await asyncio.get_event_loop().sock_sendto(
                self.socket, 
                response.encode('utf-8'), 
                addr
            )
            
            logger.info("Sent SIP response", code=code, reason=reason, to=addr)
            
        except Exception as e:
            logger.error("Error sending SIP response", error=str(e))
    
    async def stop(self):
        """SIP listener'ı durdur"""
        try:
            self.running = False
            if self.socket:
                self.socket.close()
                self.socket = None
            logger.info("SIP listener stopped")
        except Exception as e:
            logger.error("Error stopping SIP listener", error=str(e))

class OpenSIPSAIVoiceConnector:
    """OpenSIPS AI Voice Connector Ana Sınıfı"""
    
    def __init__(self, config_file: str = None, test_mode: bool = False):
        self.test_mode = test_mode
        self.config = None
        self.config_file = config_file or 'cfg/opensips-ai-voice-connector.ini'
        self.running = False
        
        # Services
        self.services = {}
        self.pipeline_manager = None
        self.call_manager = None
        self.opensips_handler = None
        self.sip_listener = None  # SIP listener eklendi
        
        # Background tasks
        self._background_tasks = []
        
        # OpenSIPS MI connection
        self.mi_conn = None
        
        logger.info("OpenSIPS AI Voice Connector initialized", test_mode=test_mode)
    
    def load_config(self):
        """Konfigürasyon dosyasını yükle"""
        try:
            # Initialize Config singleton
            Config.init(self.config_file)
            
            # Load configuration
            config_parser = configparser.ConfigParser()
            config_parser.read(self.config_file)
            self.config = config_parser
            
            logger.info("Configuration loaded successfully", config_file=self.config_file)
            
            # Log key config sections
            if 'llm' in self.config:
                logger.info("LLM config", 
                           url=self.config.get('llm', 'url', fallback='ws://llm-turkish-server:8765'),
                           model=self.config.get('llm', 'model', fallback='llama3.2:3b'))
            
            if 'stt' in self.config:
                logger.info("STT config",
                           url=self.config.get('stt', 'url', fallback='ws://vosk-server:2700'))
            
            if 'tts' in self.config:
                logger.info("TTS config",
                           url=self.config.get('tts', 'url', fallback='ws://piper-tts-server:8000/tts'))
            
            # Log available AI flavors
            logger.info("Available AI flavors", flavors=list(FLAVORS.keys()))
                           
        except Exception as e:
            logger.error("Failed to load configuration", error=str(e))
            raise
    
    def initialize_mi_connection(self):
        """OpenSIPS MI bağlantısını başlat"""
        try:
            if not OPENSIPS_MI_AVAILABLE:
                logger.warning("OpenSIPS MI library not available, using mock")
                self.mi_conn = MockOpenSIPSMI()
                return
                
            # MI configuration
            mi_ip = self.config.get('opensips', 'ip', fallback='127.0.0.1')
            mi_port = int(self.config.get('opensips', 'port', fallback='8080'))
            
            # Create MI connection - using mock for now
            logger.info("Using Mock OpenSIPS MI connection for development")
            self.mi_conn = MockOpenSIPSMI(ip=mi_ip, port=mi_port)
            
        except Exception as e:
            logger.error("Failed to initialize MI connection", error=str(e))
            self.mi_conn = MockOpenSIPSMI()
    
    async def initialize_services(self):
        """AI servislerini başlat"""
        try:
            logger.info("Initializing AI services...", test_mode=self.test_mode)
            
            if self.test_mode:
                logger.info("🧪 TEST MODE: Skipping AI service initialization")
                # Mock services for testing
                self.services['llm'] = None
                self.services['stt'] = None
                self.services['tts'] = None
                
                # Mock Pipeline Manager
                self.pipeline_manager = None
                logger.info("Mock services initialized for testing")
                
                # Initialize Call Manager with mock pipeline
                self.call_manager = CallManager(None, self.mi_conn)
                logger.info("Call manager initialized (test mode)")
                return
            
            # Normal mode - Real AI services
            # LLM Service
            llm_url = self.config.get('llm', 'url', fallback='ws://127.0.0.1:8765')
            logger.info("Creating LLM service", url=llm_url)
            self.services['llm'] = LlamaWebsocketLLMService(url=llm_url)
            
            # STT Service  
            stt_url = self.config.get('stt', 'url', fallback='ws://127.0.0.1:2700')
            logger.info("Creating STT service", url=stt_url)
            self.services['stt'] = VoskWebsocketSTTService(url=stt_url)
            
            # TTS Service
            tts_url = self.config.get('tts', 'url', fallback='ws://127.0.0.1:8000/tts')
            logger.info("Creating TTS service", url=tts_url)
            self.services['tts'] = PiperWebsocketTTSService(url=tts_url)
            
            # Start all services
            for service_name, service in self.services.items():
                logger.info(f"Starting {service_name} service...")
                try:
                    await service.start()
                    logger.info(f"{service_name} service started successfully")
                except Exception as e:
                    logger.error(f"Failed to start {service_name} service", error=str(e))
                    raise
            
            # Initialize Pipeline Manager
            logger.info("Initializing Pipeline Manager...")
            self.pipeline_manager = PipelineManager(
                llm_service=self.services['llm'],
                stt_service=self.services['stt'], 
                tts_service=self.services['tts']
            )
            
            await self.pipeline_manager.start()
            logger.info("Pipeline manager started successfully")
            
            # Initialize Call Manager
            self.call_manager = CallManager(self.pipeline_manager, self.mi_conn)
            logger.info("Call manager initialized")
            
        except Exception as e:
            logger.error("Failed to initialize services", error=str(e))
            raise
    
    async def start_opensips_handler(self):
        """OpenSIPS event handler'ı initialize et (infinite loop başlatmadan)"""
        try:
            logger.info("Initializing OpenSIPS event handler...", test_mode=self.test_mode)
            
            # OpenSIPS event configuration
            event_port = int(self.config.get('engine', 'event_port', fallback='8090'))
            event_host = self.config.get('engine', 'event_ip', fallback='0.0.0.0')
            
            # Initialize OpenSIPS event handler
            self.opensips_handler = OpenSIPSEventHandler(
                host=event_host, 
                port=event_port, 
                mi_conn=self.mi_conn
            )
            
            # Set call manager
            self.opensips_handler.set_call_manager(self.call_manager)
            
            logger.info("✅ OpenSIPS Event Handler initialized on", host=event_host, port=event_port)
            
        except Exception as e:
            logger.error("OpenSIPS event handler initialization error", error=str(e))
            raise

    async def start_sip_listener(self):
        """SIP listener'ı initialize et (infinite loop başlatmadan)"""
        try:
            logger.info("Initializing SIP listener...", test_mode=self.test_mode)
            
            # SIP listener configuration
            sip_port = int(self.config.get('engine', 'sip_port', fallback='8089'))
            sip_host = self.config.get('engine', 'sip_ip', fallback='0.0.0.0')
            
            # Initialize SIP listener
            self.sip_listener = SIPListener(
                host=sip_host,
                port=sip_port,
                call_manager=self.call_manager
            )
            
            logger.info("✅ SIP Listener initialized on", host=sip_host, port=sip_port)
                
        except Exception as e:
            logger.error("SIP listener initialization error", error=str(e))
            raise
    
    async def run_opensips_handler_loop(self):
        """OpenSIPS event handler infinite loop'unu çalıştır"""
        try:
            logger.info("🔄 Starting OpenSIPS Event Handler infinite loop...")
            await self.opensips_handler.start()
        except Exception as e:
            logger.error("OpenSIPS handler loop error", error=str(e))
            raise
    
    async def run_sip_listener_loop(self):
        """SIP listener infinite loop'unu çalıştır"""
        try:
            logger.info("🔄 Starting SIP Listener infinite loop...")
            await self.sip_listener.start()
        except Exception as e:
            logger.error("SIP listener loop error", error=str(e))
            raise
    
    async def start(self):
        """Ana servisi başlat"""
        try:
            self.running = True
            
            # Load configuration
            self.load_config()
            
            # Initialize MI connection
            self.initialize_mi_connection()
            
            # Initialize AI services
            await self.initialize_services()
            
            logger.info("🎉 OpenSIPS AI Voice Connector started successfully!")
            logger.info("🎯 Services ready:")
            logger.info("   ✅ LLM (Custom LLaMA WebSocket)")
            logger.info("   ✅ STT (Vosk WebSocket)")
            logger.info("   ✅ TTS (Piper WebSocket)")
            logger.info("   ✅ Pipeline Manager")
            logger.info("   ✅ Call Manager")
            logger.info("   ✅ OpenSIPS Event Handler")
            logger.info("   ✅ SIP Listener (Port 8089)")  # SIP listener eklendi
            if self.mi_conn:
                logger.info("   ✅ OpenSIPS MI Connection")
            else:
                logger.info("   ⚠️ OpenSIPS MI Connection (Mock)")
            
            # Start services concurrently
            logger.info("🔍 DEBUG: test_mode = " + str(self.test_mode))
            if self.test_mode:
                # Test mode - just initialize but don't start listeners
                await self.start_opensips_handler()
                await self.start_sip_listener()
                logger.info("🧪 TEST MODE: Both handlers initialized but not actively listening")
            else:
                # Normal mode - start both listeners as background tasks
                logger.info("🚀 NORMAL MODE: Starting listeners as background tasks...")
                try:
                    # Initialize both handlers first
                    logger.info("🔧 Initializing OpenSIPS Event Handler...")
                    await self.start_opensips_handler()
                    logger.info("✅ OpenSIPS Event Handler initialized successfully")
                    
                    logger.info("🔧 Initializing SIP Listener...")
                    await self.start_sip_listener()
                    logger.info("✅ SIP Listener initialized successfully")
                    
                    # Now start background loops
                    logger.info("📡 Creating OpenSIPS Event Handler background task...")
                    opensips_task = asyncio.create_task(self.run_opensips_handler_loop())
                    
                    logger.info("📞 Creating SIP Listener background task...")  
                    sip_task = asyncio.create_task(self.run_sip_listener_loop())
                    
                    # Store tasks for cleanup
                    self._background_tasks = [opensips_task, sip_task]
                    logger.info("✅ Both background tasks created and stored")
                    
                    # Wait for initialization
                    logger.info("⏳ Waiting for listeners to initialize...")
                    await asyncio.sleep(1.0)
                    
                    # Check task status in detail
                    logger.info("🔍 Checking task statuses...")
                    logger.info(f"   📡 OpenSIPS task done: {opensips_task.done()}")
                    logger.info(f"   📞 SIP task done: {sip_task.done()}")
                    
                    # Check for exceptions
                    if opensips_task.done() and opensips_task.exception():
                        logger.error("❌ OpenSIPS handler failed", error=str(opensips_task.exception()))
                    if sip_task.done() and sip_task.exception():
                        logger.error("❌ SIP listener failed", error=str(sip_task.exception()))
                    
                    # Both tasks should be running (not done) for infinite loops
                    opensips_running = not opensips_task.done()
                    sip_running = not sip_task.done()
                    
                    logger.info(f"📊 Task status: OpenSIPS={opensips_running}, SIP={sip_running}")
                    
                    if opensips_running and sip_running:
                        logger.info("✅ Both listeners started as background tasks")
                        logger.info("🔥 READY: OpenSIPS AI Voice Connector is now listening for calls!")
                        logger.info("   📞 SIP Listener: 0.0.0.0:8089") 
                        logger.info("   📡 Event Handler: 0.0.0.0:8090")
                    else:
                        logger.error("❌ One or both listeners failed to start properly")
                        raise Exception("One or more listeners failed to start")
                        
                except Exception as e:
                    logger.error("💥 Critical error starting listeners", error=str(e))
                    raise
            
        except Exception as e:
            logger.error("⚠️ EXCEPTION in start() method", error=str(e))
            logger.error("Exception details", exc_info=True)
            await self.stop()
            raise
    
    async def stop(self):
        """Servisi durdur"""
        logger.info("Stopping OpenSIPS AI Voice Connector...")
        self.running = False
        
        # Cancel background tasks
        for task in self._background_tasks:
            if not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        self._background_tasks.clear()
        logger.info("Background tasks cancelled")
        
        # Stop SIP listener
        if self.sip_listener:
            await self.sip_listener.stop()
            logger.info("SIP listener stopped")
        
        # Stop OpenSIPS handler
        if self.opensips_handler:
            await self.opensips_handler.stop()
            logger.info("OpenSIPS event handler stopped")
        
        # Stop pipeline manager
        if self.pipeline_manager:
            await self.pipeline_manager.stop()
            logger.info("Pipeline manager stopped")
        
        # Stop all services
        for service_name, service in self.services.items():
            try:
                await service.stop()
                logger.info(f"{service_name} service stopped")
            except Exception as e:
                logger.error(f"Error stopping {service_name}", error=str(e))
        
        logger.info("OpenSIPS AI Voice Connector stopped")

async def main():
    """Ana fonksiyon"""
    
    # Test mode check
    test_mode = '--test' in sys.argv or os.getenv('TEST_MODE', 'false').lower() == 'true'
    
    try:
        logger.info("🚀 OpenSIPS AI Voice Connector Starting...", test_mode=test_mode)
        print("🚀 OpenSIPS AI Voice Connector Starting...")
        print("=" * 50)
        
        if test_mode:
            print("🧪 TEST MODE ENABLED - AI services will be mocked")
            print("=" * 50)
        
        # Create and start connector
        connector = OpenSIPSAIVoiceConnector(test_mode=test_mode)
        
        # Setup signal handlers
        def signal_handler(signum, frame):
            logger.info("Received signal, shutting down...", signal=signum)
            asyncio.create_task(connector.stop())
        
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        
        # Start the connector
        await connector.start()
        
        if test_mode:
            logger.info("🧪 TEST MODE: Application started successfully!")
            print("\n🧪 TEST MODE: Application running successfully!")
            print("✅ Configuration loaded")
            print("✅ Mock services initialized") 
            print("✅ OpenSIPS event handler ready")
            print("✅ Call manager ready")
            print("\nPress Ctrl+C to stop...")
            
            # Keep running in test mode
            while connector.running:
                await asyncio.sleep(1)
        else:
            # Normal mode - wait for events
            while connector.running:
                await asyncio.sleep(0.1)
        
    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt")
        print("\n👋 Shutting down...")
    except Exception as e:
        logger.error("Application error", error=str(e))
        print(f"❌ Error: {e}")
        return 1
    
    return 0

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)

# vim: tabstop=8 expandtab shiftwidth=4 softtabstop=4
