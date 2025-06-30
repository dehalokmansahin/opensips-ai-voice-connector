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
from fastapi import FastAPI

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
from pipeline.manager import EnhancedPipelineManager as PipelineManager

# OpenSIPS integration imports  
from utils import get_ai, FLAVORS, get_ai_flavor, get_user, get_to, indialog
from config import Config, ConfigValidationError

# Call management
from transports.call_manager import CallManager, Call, NoAvailablePorts

# OpenSIPS Event Integration
from opensips_event_listener import OpenSIPSEventListener, OpenSIPSMIClient

# OpenSIPS MI integration
try:
    from opensips.mi import OpenSIPSMI, OpenSIPSMIException
    from opensips.event import OpenSIPSEventHandler, OpenSIPSEventException
    OPENSIPS_AVAILABLE = True
except ImportError:
    OpenSIPSMI = None
    OpenSIPSMIException = Exception
    OpenSIPSEventHandler = None  
    OpenSIPSEventException = Exception
    OPENSIPS_AVAILABLE = False
    logger.warning("OpenSIPS library not available")

# Mock OpenSIPS classes for development
class MockOpenSIPSMI:
    """Mock OpenSIPS MI connection for development/testing"""
    
    def __init__(self, **kwargs):
        self.config = kwargs
        logger.info("Mock OpenSIPS MI connection initialized", config=kwargs)
    
    def execute(self, command: str, params: dict = None):
        """Mock MI command execution"""
        logger.info("Mock MI command", command=command, params=params)
        return {"status": "success", "message": "Mock response"}

class MockOpenSIPSEventHandler:
    """Mock OpenSIPS Event Handler"""
    
    def __init__(self, *args, **kwargs):
        self.config = kwargs
        logger.info("Mock OpenSIPS Event Handler initialized")
    
    def async_subscribe(self, event_name, handler):
        logger.info("Mock event subscription", event_name=event_name, handler_type=type(handler).__name__)
        return self

# SDP parsing
try:
    from aiortc.sdp import SessionDescription
    SDP_PARSING_AVAILABLE = True
except ImportError:
    SessionDescription = None
    SDP_PARSING_AVAILABLE = False
    logger.warning("SDP parsing not available")

class OpenSIPSEngine:
    """
    OpenSIPS AI Voice Connector Engine
    Eski engine.py mantığını koruyarak Pipecat pipeline ile entegre eder
    """
    
    def __init__(self, pipeline_manager):
        """
        Args:
            pipeline_manager: Pipecat pipeline manager
        """
        self.pipeline_manager = pipeline_manager
        
        # OpenSIPS MI configuration
        mi_cfg = Config.get("opensips", {})
        mi_ip = mi_cfg.get("ip", "127.0.0.1")
        mi_port = int(mi_cfg.get("port", "8080"))
        
        # Initialize MI connection
        if OPENSIPS_AVAILABLE:
            self.mi_conn = OpenSIPSMI(conn="datagram", datagram_ip=mi_ip, datagram_port=mi_port)
            logger.info("OpenSIPS MI connection initialized", ip=mi_ip, port=mi_port)
        else:
            self.mi_conn = MockOpenSIPSMI(ip=mi_ip, port=mi_port)
            logger.warning("Using mock OpenSIPS MI connection")
        
        # Call manager
        self.call_manager = CallManager(pipeline_manager, self.mi_conn)
        self.active_calls = {}
        
        # Event handler
        self.event_handler = None
        self.event_subscription = None
        
        logger.info("OpenSIPS Engine initialized")

    def mi_reply(self, key: str, method: str, code: int, reason: str, body: str = None):
        """Send reply to OpenSIPS via MI"""
        try:
            params = {
                'key': key,
                'method': method,
                'code': code,
                'reason': reason
            }
            if body:
                params["body"] = body
            
            result = self.mi_conn.execute('ua_session_reply', params)
            logger.info("MI reply sent", key=key, method=method, code=code, reason=reason)
            return result
            
        except Exception as e:
            logger.error("Error sending MI reply", key=key, method=method, error=str(e))
            return None

    def parse_sdp(self, sdp_str: str) -> dict:
        """Parse SDP string - eski mantık korunuyor"""
        try:
            if not sdp_str or not sdp_str.strip():
                logger.warning("Empty SDP content")
                return None
            
            # Clean SDP - remove rtcp lines that cause parser errors
            clean_lines = []
            for line in sdp_str.split('\n'):
                line = line.strip()
                if not line.startswith("a=rtcp:"):
                    clean_lines.append(line)
            
            sdp_str = '\n'.join(clean_lines)
            
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
                    if len(parts) >= 2 and parts[0] == 'm=audio':
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
            logger.error("Error parsing SDP", error=str(e))
            return None

    def get_header(self, params: dict, header_name: str) -> str:
        """Extract header value from OpenSIPS parameters"""
        if 'headers' not in params:
            return None
            
        headers = params['headers']
        if header_name in headers:
            return headers[header_name]
            
        return None

    def indialog(self, params: dict) -> bool:
        """Check if request is in-dialog"""
        if 'to' not in params:
            return False
        to = params['to']
        return ';tag=' in to

    async def handle_call(self, call: Call, key: str, method: str, params: dict):
        """Handle SIP call - eski engine.py handle_call mantığı"""
        try:
            if method == 'INVITE':
                if 'body' not in params:
                    self.mi_reply(key, method, 415, 'Unsupported Media Type')
                    return

                sdp_str = params['body']
                sdp_info = self.parse_sdp(sdp_str)
                
                if not sdp_info:
                    self.mi_reply(key, method, 400, 'Bad Request')
                    return

                if call:
                    # Handle in-dialog re-INVITE
                    # TODO: Check SDP direction for pause/resume
                    call.resume()
                    try:
                        self.mi_reply(key, method, 200, 'OK', call.get_sdp_body())
                    except Exception as e:
                        logger.error("Error sending re-INVITE response", error=str(e))
                    return

                try:
                    # Create new call with Pipecat pipeline
                    config = {'flavor': 'pipecat'}  # Default config
                    new_call = await self.call_manager.create_call(key, sdp_info, config)
                    
                    if new_call:
                        # Send 200 OK with SDP
                        sdp_body = new_call.get_sdp_body()
                        logger.warning("🎯 Generated SDP response", 
                                      local_ip=sdp_info.get('connection_ip', '0.0.0.0'), 
                                      rtp_port=new_call.serversock.getsockname()[1],
                                      sdp_full=sdp_body)
                        logger.warning("🎯 SENDING 200 OK WITH SDP!", 
                                      call_id=key, 
                                      rtp_port=new_call.serversock.getsockname()[1])
                        self.mi_reply(key, method, 200, 'OK', sdp_body)
                    else:
                        # Call creation failed
                        self.mi_reply(key, method, 500, 'Server Internal Error')
                        
                except NoAvailablePorts:
                    logger.error("No available RTP ports", key=key)
                    self.mi_reply(key, method, 503, 'Service Unavailable')
                except Exception as e:
                    logger.error("Error creating call", key=key, error=str(e))
                    self.mi_reply(key, method, 500, 'Server Internal Error')
            
            elif method == 'NOTIFY':
                # Handle NOTIFY messages (e.g., subscription state)
                self.mi_reply(key, method, 200, 'OK')
                
                # Check for terminated subscription
                sub_state = self.get_header(params, "Subscription-State")
                if sub_state and "terminated" in sub_state:
                    if call:
                        call.terminated = True
                        logger.info("Call marked for termination via NOTIFY", key=key)
                        # Ensure call is actually terminated
                        await self.call_manager.terminate_call(key)
            
            elif method == 'BYE':
                # Handle BYE - terminate call
                logger.info("BYE received, terminating call", key=key)
                self.mi_reply(key, method, 200, 'OK')
                if call:
                    # Ensure call is properly terminated
                    call.terminated = True
                    call.stop_event.set()
                    await self.call_manager.terminate_call(key)
            
            elif method == 'CANCEL':
                # Handle CANCEL - terminate call
                logger.info("CANCEL received, terminating call", key=key)
                self.mi_reply(key, method, 200, 'OK')
                if call:
                    # Ensure call is properly terminated
                    call.terminated = True
                    call.stop_event.set()
                    await self.call_manager.terminate_call(key)
            
            else:
                # Unsupported method
                if not call:
                    self.mi_reply(key, method, 481, 'Call/Transaction Does Not Exist')
                else:
                    self.mi_reply(key, method, 405, 'Method Not Allowed')

        except Exception as e:
            logger.error("Error handling call", key=key, method=method, error=str(e))
            self.mi_reply(key, method, 500, 'Server Internal Error')

    def udp_handler(self, data: dict):
        """UDP handler for OpenSIPS events"""
        try:
            if 'params' not in data:
                logger.warning("Invalid event data: missing params")
                return
                
            params = data['params']
            
            if 'key' not in params:
                logger.warning("Invalid event data: missing key")
                return
                
            key = params['key']
            
            if 'method' not in params:
                logger.warning("Invalid event data: missing method")
                return
                
            method = params['method']
            
            # Check if in-dialog
            if self.indialog(params):
                # Get existing call
                call = self.call_manager.get_call(key)
                if not call:
                    logger.warning("Call not found for in-dialog request", key=key, method=method)
                    self.mi_reply(key, method, 481, 'Call/Transaction Does Not Exist')
                    return
            else:
                call = None
            
            # Log the request
            from_header = params.get('from', 'unknown')
            to_header = params.get('to', 'unknown')
            logger.info(f"Processing {method} from OpenSIPS", from_addr=params.get('remote_addr'))
            logger.info(f"INVITE details", call_id=key, from_=from_header, to=to_header)
            
            # Handle the call
            asyncio.create_task(self.handle_call(call, key, method, params))
            
        except Exception as e:
            logger.error("Error in UDP handler", error=str(e))

    async def start_event_handler(self):
        """Start OpenSIPS event handler"""
        try:
            # Get configuration
            engine_cfg = Config.get("engine")
            host_ip = engine_cfg.get("event_ip", "0.0.0.0")
            port = int(engine_cfg.get("event_port", "8090"))
            
            # Initialize event handler
            if OPENSIPS_AVAILABLE:
                self.event_handler = OpenSIPSEventHandler(
                    host=host_ip, port=port, mi_conn=self.mi_conn
                )
                # Subscribe to E_UA_SESSION events
                self.event_subscription = self.event_handler.async_subscribe(
                    "E_UA_SESSION", self.udp_handler
                )
                
                # Get actual bound port
                _, actual_port = self.event_subscription.socket.sock.getsockname()
                logger.info("OpenSIPS event handler started", ip=host_ip, port=actual_port)
                
            else:
                # Mock event handler for development
                self.event_handler = MockOpenSIPSEventHandler()
                logger.warning("Using mock OpenSIPS event handler", ip=host_ip, port=port)
                
            return True
            
        except Exception as e:
            logger.error("Failed to start OpenSIPS event handler", error=str(e))
            return False

    async def shutdown(self):
        """Shutdown OpenSIPS engine"""
        logger.info("Shutting down OpenSIPS engine")
        
        # Terminate all active calls
        await self.call_manager.shutdown()
        
        # Unsubscribe from events
        if OPENSIPS_AVAILABLE and self.event_subscription:
            try:
                self.event_subscription.unsubscribe()
                logger.info("Unsubscribed from OpenSIPS events")
            except (OpenSIPSEventException, OpenSIPSMIException) as e:
                logger.error("Error unsubscribing from events", error=str(e))
        
        logger.info("OpenSIPS engine shutdown complete")

    async def debug_start_stream(self, call_key: str):
        """Debug endpoint to manually start stream for existing calls"""
        try:
            call = self.call_manager.get_call(call_key)
            if call and call.pipeline_manager:
                logger.info("🔧 DEBUG: Manually starting stream for call", call_key=call_key)
                await call.pipeline_manager.start_stream()
                logger.info("✅ DEBUG: Stream started successfully", call_key=call_key)
                return {"status": "success", "message": f"Stream started for call {call_key}"}
            else:
                logger.warning("⚠️ DEBUG: Call not found or no pipeline manager", call_key=call_key)
                return {"status": "error", "message": f"Call {call_key} not found or no pipeline manager"}
        except Exception as e:
            logger.error("💥 DEBUG: Error starting stream", call_key=call_key, error=str(e))
            return {"status": "error", "message": str(e)}

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
        self.sock = None  # Direct socket reference for compatibility
        self.running = False
        self.mi_conn = mi_conn
        self.call_manager = None
        
        # Socket wrapper for compatibility
        class SocketWrapper:
            def __init__(self, parent):
                self.parent = parent
                self.sock = None
                
            def getsockname(self):
                if self.sock:
                    return self.sock.getsockname()
                return (self.parent.host, self.parent.port)
        
        self.socket = SocketWrapper(self)
        
    def set_call_manager(self, call_manager):
        """Call manager'ı set et"""
        self.call_manager = call_manager
    
    def async_subscribe(self, event_name, handler):
        """Event subscription için compatibility method"""
        logger.info("Event subscription", event_name=event_name, handler_type=type(handler).__name__)
        
        # Initialize socket if not already done
        if not self.socket.sock:
            import socket as socket_module
            real_socket = socket_module.socket(socket_module.AF_INET, socket_module.SOCK_DGRAM)
            real_socket.setsockopt(socket_module.SOL_SOCKET, socket_module.SO_REUSEADDR, 1)
            real_socket.bind((self.host, self.port))
            self.socket.sock = real_socket
            self.sock = real_socket  # Direct reference for compatibility
            logger.info("Socket initialized for event subscription", host=self.host, port=self.port)
        
        # Return a mock subscription object with socket attribute
        class MockSubscription:
            def __init__(self, parent):
                self.socket = parent  # parent has socket attribute
            
            def unsubscribe(self):
                logger.info("Event unsubscribed")
        
        return MockSubscription(self)
        
    async def start(self):
        """Event handler'ı başlat"""
        try:
            import socket as socket_module
            real_socket = socket_module.socket(socket_module.AF_INET, socket_module.SOCK_DGRAM)
            real_socket.setsockopt(socket_module.SOL_SOCKET, socket_module.SO_REUSEADDR, 1)
            real_socket.bind((self.host, self.port))
            real_socket.setblocking(False)
            
            # Update wrapper with real socket
            self.socket.sock = real_socket
            self.running = True
            
            logger.info("OpenSIPS Event Handler started", host=self.host, port=self.port)
            
            # Listen for incoming OpenSIPS events
            while self.running:
                try:
                    loop = asyncio.get_event_loop()
                    data, addr = await loop.sock_recvfrom(real_socket, 4096)
                    
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
            logger.error("Error handling BYE", error=str(e))
    
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
    
    def _parse_sdp_body(self, sdp_str: str) -> dict:
        """Parse SDP string - utility method"""
        try:
            if not sdp_str or not sdp_str.strip():
                logger.warning("Empty SDP content")
                return None
            
            # Clean SDP - remove rtcp lines that cause parser errors
            clean_lines = []
            for line in sdp_str.split('\n'):
                line = line.strip()
                if not line.startswith("a=rtcp:"):
                    clean_lines.append(line)
            
            sdp_str = '\n'.join(clean_lines)
            
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
                    if len(parts) >= 2 and parts[0] == 'm=audio':
                        try:
                            sdp_info['media_port'] = int(parts[1])
                        except ValueError:
                            logger.warning("Invalid media port", port=parts[1])
                
                # RTP map
                elif line.startswith('a=rtpmap:'):
                    # a=rtpmap:0 PCMU/8000
                    if 'PCMU' in line:
                        sdp_info['audio_format'] = 'PCMU'
                    elif 'PCMA' in line:
                        sdp_info['audio_format'] = 'PCMA'
            
            # Validation
            if not sdp_info['media_ip'] or not sdp_info['media_port']:
                logger.error("Invalid SDP - missing media information", sdp_info=sdp_info)
                return None
            
            logger.info("SDP parsed successfully", 
                       audio_format=sdp_info['audio_format'],
                       media_ip=sdp_info['media_ip'], 
                       media_port=sdp_info['media_port'])
            
            return sdp_info
            
        except Exception as e:
            logger.error("Error parsing SDP", error=str(e), sdp_content=sdp_str[:200])
            return None
        
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
            
            # Debug: Full SIP message for ACK detection
            logger.debug("Full SIP message details", method=first_line, full_message=sip_data)
            
            if first_line.startswith('INVITE'):
                await self.handle_invite(sip_data, addr)
            elif first_line.startswith('BYE'):
                await self.handle_bye(sip_data, addr)
            elif first_line.startswith('CANCEL'):
                await self.handle_cancel(sip_data, addr)
            elif first_line.startswith('ACK'):
                logger.warning("🎯 ACK MESSAGE DETECTED! Processing...", from_addr=addr)
                await self.handle_ack(sip_data, addr)
            else:
                logger.warning("❓ Unhandled SIP method", method=first_line, from_addr=addr)
                
        except Exception as e:
            logger.error("Error handling SIP message", error=str(e))
    
    async def handle_invite(self, sip_data: str, addr):
        """INVITE mesajını işle"""
        try:
            logger.info("Processing INVITE from OpenSIPS", from_addr=addr)
            
            # Parse basic SIP headers - handle multiple Via headers and Record-Route
            headers = {}
            via_headers = []  # Store all Via headers
            record_route_headers = []  # Store all Record-Route headers
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
                    key_lower = key.strip().lower()
                    value_clean = value.strip()
                    
                    # Handle multiple Via headers specially
                    if key_lower == 'via':
                        via_headers.append(value_clean)
                        headers['via'] = via_headers[0]  # Keep first for compatibility
                    # Handle Record-Route headers (critical for ACK routing!)
                    elif key_lower == 'record-route':
                        record_route_headers.append(value_clean)
                        headers['record-route'] = value_clean  # Store for response
                    else:
                        headers[key_lower] = value_clean
            
            # Extract call information
            call_id = headers.get('call-id', 'unknown')
            from_header = headers.get('from', '')
            to_header = headers.get('to', '')
            
            logger.info("INVITE details", call_id=call_id, from_=from_header, to=to_header)
            
            # Parse SDP from body
            sdp_body = body.strip()
            if not sdp_body:
                logger.error("No SDP body in INVITE", call_id=call_id)
                await self.send_response(addr, call_id, '400', 'Bad Request - Missing SDP')
                return
            
            logger.info("SDP body received", call_id=call_id, sdp_preview=sdp_body[:100])
            
            # Parse SDP using static utility method
            sdp_info = self._parse_sdp_body(sdp_body)
            
            if not sdp_info:
                logger.error("Failed to parse SDP", call_id=call_id)
                await self.send_response(addr, call_id, '400', 'Bad Request - Invalid SDP')
                return
            
            logger.info("SDP parsed successfully", call_id=call_id, sdp_info=sdp_info)
            
            # Create call via call manager
            if self.call_manager:
                logger.info("🔧 CALLING create_call method", call_id=call_id, call_manager_type=type(self.call_manager).__name__)
                
                try:
                    call = await self.call_manager.create_call(call_id, sdp_info)
                    logger.info("🔧 create_call RETURNED", call_id=call_id, call_result=call, call_type=type(call).__name__ if call else "None")
                except Exception as e:
                    import traceback
                    logger.error("💥 EXCEPTION in create_call CALL", call_id=call_id, error=str(e), traceback=traceback.format_exc())
                    call = None
                
                if call:
                    # Send 200 OK response with SDP
                    response_sdp = call.get_sdp_body()
                    logger.info("🎯 Sending 200 OK with Record-Route", 
                               call_id=call_id, 
                               has_record_route='record-route' in headers,
                               record_route=headers.get('record-route', 'N/A'))
                    await self.send_response(addr, call_id, '200', 'OK', headers, response_sdp, via_headers)
                    logger.info("Call created and 200 OK sent", call_id=call_id)
                else:
                    logger.error("Failed to create call", call_id=call_id)
                    await self.send_response(addr, call_id, '500', 'Internal Server Error', headers, None, via_headers)
            else:
                logger.error("No call manager available")
                await self.send_response(addr, call_id, '500', 'Internal Server Error', headers, None, via_headers)
                
        except Exception as e:
            logger.error("Error handling INVITE", error=str(e))
    
    async def handle_bye(self, sip_data: str, addr):
        """BYE mesajını işle"""
        try:
            # Parse Call-ID and Via headers
            call_id = 'unknown'
            via_headers = []
            
            for line in sip_data.split('\n'):
                line = line.strip()
                if line.lower().startswith('call-id:'):
                    call_id = line.split(':', 1)[1].strip()
                elif line.lower().startswith('via:'):
                    via_headers.append(line.split(':', 1)[1].strip())
            
            logger.info("📞 Processing BYE message", call_id=call_id, from_addr=addr, via_count=len(via_headers))
            
            # Terminate call
            if self.call_manager:
                logger.info("🔚 Calling CallManager.terminate_call", call_id=call_id)
                await self.call_manager.terminate_call(call_id)
                logger.info("✅ CallManager.terminate_call completed", call_id=call_id)
            
            # Send 200 OK response  
            await self.send_response(addr, call_id, '200', 'OK', None, None, via_headers)
            
        except Exception as e:
            logger.error("Error handling BYE", error=str(e))
    
    async def handle_cancel(self, sip_data: str, addr):
        """CANCEL mesajını işle"""
        try:
            # Parse Call-ID and Via headers
            call_id = 'unknown'
            via_headers = []
            
            for line in sip_data.split('\n'):
                line = line.strip()
                if line.lower().startswith('call-id:'):
                    call_id = line.split(':', 1)[1].strip()
                elif line.lower().startswith('via:'):
                    via_headers.append(line.split(':', 1)[1].strip())
            
            logger.info("Processing CANCEL", call_id=call_id, from_addr=addr)
            
            # Terminate call
            if self.call_manager:
                await self.call_manager.terminate_call(call_id)
            
            # Send 200 OK response
            await self.send_response(addr, call_id, '200', 'OK', None, None, via_headers)
            
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
            
            logger.info("✅ Processing ACK - Call established!", call_id=call_id, from_addr=addr)
            # ACK doesn't need response - but this confirms call is established
            
        except Exception as e:
            logger.error("Error handling ACK", error=str(e))
    
    async def send_response(self, addr, call_id: str, code: str, reason: str, request_headers: dict = None, body: str = None, via_headers: list = None):
        """SIP response gönder"""
        try:
            # Build SIP response
            response = f"SIP/2.0 {code} {reason}\r\n"
            
            if request_headers:
                # Handle Via headers first (in original order)
                if via_headers:
                    for via_value in via_headers:
                        response += f"Via: {via_value}\r\n"
                elif 'via' in request_headers:
                    response += f"Via: {request_headers['via']}\r\n"
                
                # Copy Record-Route header for dialog establishment (CRITICAL for ACK routing!)
                if 'record-route' in request_headers and code == '200':
                    response += f"Record-Route: {request_headers['record-route']}\r\n"
                    logger.debug("Added Record-Route to 200 OK response", record_route=request_headers['record-route'])
                
                # Copy other required headers from request
                for header in ['from', 'to', 'call-id', 'cseq']:
                    if header in request_headers:
                        if header == 'to' and code == '200':
                            # Add tag to To header for 200 OK
                            to_value = request_headers[header]
                            if 'tag=' not in to_value:
                                to_value += f";tag={call_id[:8]}"
                            response += f"To: {to_value}\r\n"
                        else:
                            response += f"{header.title()}: {request_headers[header]}\r\n"
            else:
                response += f"Call-ID: {call_id}\r\n"
            
            # Add Contact header for 200 OK
            if code == '200':
                # Use container IP instead of 0.0.0.0 for Contact header
                contact_host = self.host
                if contact_host == '0.0.0.0':
                    try:
                        import socket
                        contact_host = socket.gethostbyname(socket.gethostname())
                        logger.debug("Resolved container IP for Contact header", ip=contact_host)
                    except:
                        contact_host = self.host  # Fallback to original
                
                response += f"Contact: <sip:oavc@{contact_host}:{self.port}>\r\n"
            
            # Add body if provided (SDP for 200 OK)
            if body:
                response += f"Content-Type: application/sdp\r\n"
                response += f"Content-Length: {len(body)}\r\n"
                response += "\r\n"
                response += body
            else:
                response += f"Content-Length: 0\r\n"
                response += "\r\n"
            
            # Send response
            await asyncio.get_event_loop().sock_sendto(
                self.socket, 
                response.encode('utf-8'), 
                addr
            )
            
            logger.info("Sent SIP response", code=code, reason=reason, to=addr, has_body=bool(body))
            logger.debug("SIP response content", response_preview=response[:200] + "..." if len(response) > 200 else response)
            
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
        
        # OpenSIPS Engine - yeni implementasyon
        self.opensips_engine = None
        
        # Legacy components (will be removed)
        self.call_manager = None
        self.opensips_handler = None
        self.sip_listener = None
        
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
            if not OPENSIPS_AVAILABLE:
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
        """Initialize all AI services with comprehensive validation and error handling"""
        try:
            logger.info("🚀 Starting AI services initialization...", test_mode=self.test_mode)
            
            if self.test_mode:
                logger.info("🧪 TEST MODE: Skipping AI service validation and initialization")
                # Mock services for testing
                self.services['llm'] = None
                self.services['stt'] = None
                self.services['tts'] = None
                
                # Create minimal Pipeline Manager for test mode
                logger.info("Creating minimal pipeline manager for test mode...")
                self.pipeline_manager = PipelineManager(
                    llm_service=None,
                    stt_service=None, 
                    tts_service=None,
                    config={"max_pipeline_errors": 5}  # Reduced for test mode
                )
                logger.info("Mock pipeline manager created for testing")
                
                # Initialize OpenSIPS Engine (test mode)
                logger.info("Initializing OpenSIPS Engine...")
                self.opensips_engine = OpenSIPSEngine(self.pipeline_manager)
                logger.info("OpenSIPS Engine initialized successfully")
                
                # Initialize OpenSIPS Event Listener (test mode)
                logger.info("🔔 Initializing OpenSIPS Event Listener...")
                event_port = int(self.config.get('engine', 'event_port', fallback='8090'))
                self.opensips_event_listener = OpenSIPSEventListener(port=event_port)
                
                # Initialize OpenSIPS MI Client (test mode)
                opensips_ip = self.config.get('opensips', 'ip', fallback='172.20.0.6')
                opensips_port = int(self.config.get('opensips', 'port', fallback='8087'))
                self.opensips_mi_client = OpenSIPSMIClient(host=opensips_ip, port=opensips_port)
                
                logger.info("✅ OpenSIPS Event integration initialized",
                           event_port=event_port,
                           mi_host=opensips_ip,
                           mi_port=opensips_port)
                                                
                # Initialize Call Manager  
                self.call_manager = CallManager(self.pipeline_manager, self.mi_conn)
                logger.info("Call manager initialized successfully")
                return
            
            # Normal mode - Validate configuration first
            try:
                # First validate service configurations using Config class
                validation_results = await Config.validate_services_config()
                logger.info("✅ Service configuration validation completed", 
                           results=validation_results)
            except ConfigValidationError as e:
                logger.error("❌ Service configuration validation failed", error=str(e))
                raise
            except Exception as e:
                logger.warning("⚠️ Service configuration validation skipped (missing dependencies)", error=str(e))
                # Continue without validation if optional dependencies are missing
            
            # Initialize services with enhanced error handling
            services_to_initialize = []
            failed_services = []
            
            # LLM Service
            try:
                llm_url = self.config.get('llm', 'url', fallback='ws://127.0.0.1:8765')
                if not llm_url:
                    raise ConfigValidationError("LLM service URL is required")
                
                logger.info("📡 Creating LLM service", url=llm_url)
                self.services['llm'] = LlamaWebsocketLLMService(url=llm_url)
                services_to_initialize.append(("LLM", self.services['llm']))
                logger.info("✅ LLM service created successfully")
                
            except Exception as e:
                logger.error("❌ Failed to create LLM service", error=str(e))
                failed_services.append("LLM")
                self.services['llm'] = None
            
            # STT Service  
            try:
                stt_url = self.config.get('stt', 'url', fallback='ws://127.0.0.1:2700')
                if not stt_url:
                    raise ConfigValidationError("STT service URL is required")
                
                logger.info("📡 Creating STT service", url=stt_url)
                self.services['stt'] = VoskWebsocketSTTService(url=stt_url)
                services_to_initialize.append(("STT", self.services['stt']))
                logger.info("✅ STT service created successfully")
                
            except Exception as e:
                logger.error("❌ Failed to create STT service", error=str(e))
                failed_services.append("STT")
                self.services['stt'] = None
            
            # TTS Service
            try:
                tts_url = self.config.get('tts', 'url', fallback='ws://127.0.0.1:8000/tts')
                if not tts_url:
                    raise ConfigValidationError("TTS service URL is required")
                
                logger.info("📡 Creating TTS service", url=tts_url)
                self.services['tts'] = PiperWebsocketTTSService(url=tts_url)
                services_to_initialize.append(("TTS", self.services['tts']))
                logger.info("✅ TTS service created successfully")
                
            except Exception as e:
                logger.error("❌ Failed to create TTS service", error=str(e))
                failed_services.append("TTS")
                self.services['tts'] = None
            
            # Check if any critical services failed during creation
            if failed_services:
                error_msg = f"Critical services failed to initialize: {', '.join(failed_services)}"
                logger.critical("🚨 " + error_msg)
                raise ConfigValidationError(error_msg)
            
            # Start all services with timeout and retry logic
            startup_timeout = 10.0  # 10 seconds timeout per service
            for service_name, service in services_to_initialize:
                logger.info(f"🚀 Starting {service_name} service...")
                try:
                    # Start service with timeout
                    await asyncio.wait_for(service.start(), timeout=startup_timeout)
                    logger.info(f"✅ {service_name} service started successfully")
                    
                except asyncio.TimeoutError:
                    logger.error(f"⏰ {service_name} service startup timeout ({startup_timeout}s)")
                    failed_services.append(service_name)
                    
                except Exception as e:
                    logger.error(f"❌ Failed to start {service_name} service", error=str(e))
                    failed_services.append(service_name)
            
            # Check if any services failed to start
            if failed_services:
                # Cleanup started services
                await self._cleanup_services()
                error_msg = f"Services failed to start: {', '.join(failed_services)}"
                logger.critical("🚨 " + error_msg)
                raise ConfigValidationError(error_msg)
            
            # Create enhanced pipeline configuration
            pipeline_config = {
                "max_pipeline_errors": int(self.config.get('pipeline', 'max_errors', fallback='10')),
                "error_reset_interval": int(self.config.get('pipeline', 'error_reset_interval', fallback='300')),
                "max_threads": int(self.config.get('pipeline', 'max_threads', fallback='4')),
                "interruption": {
                    "min_words": int(self.config.get('interruption', 'min_words', fallback='2')),
                    "volume_threshold": float(self.config.get('interruption', 'volume_threshold', fallback='0.6')),
                    "min_duration_ms": int(self.config.get('interruption', 'min_duration_ms', fallback='300'))
                }
            }
            
            # Initialize Enhanced Pipeline Manager
            logger.info("🔧 Initializing Enhanced Pipeline Manager...")
            self.pipeline_manager = PipelineManager(
                llm_service=self.services['llm'],
                stt_service=self.services['stt'], 
                tts_service=self.services['tts'],
                config=pipeline_config
            )
            
            # Start pipeline with timeout
            pipeline_start_timeout = 15.0  # 15 seconds for pipeline startup
            try:
                await asyncio.wait_for(self.pipeline_manager.start(), timeout=pipeline_start_timeout)
                logger.info("✅ Enhanced Pipeline Manager started successfully")
                
                # Log pipeline statistics
                stats = self.pipeline_manager.get_pipeline_stats()
                logger.info("📊 Pipeline statistics", stats=stats)
                
            except asyncio.TimeoutError:
                logger.error(f"⏰ Pipeline manager startup timeout ({pipeline_start_timeout}s)")
                raise ConfigValidationError("Pipeline manager startup timeout")
            except Exception as e:
                logger.error("❌ Failed to start Pipeline Manager", error=str(e))
                raise ConfigValidationError(f"Pipeline manager startup failed: {str(e)}")
            
            # Initialize OpenSIPS Engine (yeni implementasyon)
            logger.info("🔌 Initializing OpenSIPS Engine...")
            try:
                self.opensips_engine = OpenSIPSEngine(self.pipeline_manager)
                logger.info("✅ OpenSIPS Engine initialized successfully")
            except Exception as e:
                logger.error("❌ OpenSIPS Engine initialization failed", error=str(e))
                raise ConfigValidationError(f"OpenSIPS Engine initialization failed: {str(e)}")
            
            # Initialize OpenSIPS Event Listener (normal mode)
            logger.info("🔔 Initializing OpenSIPS Event Listener...")
            try:
                event_port = int(self.config.get('engine', 'event_port', fallback='8090'))
                self.opensips_event_listener = OpenSIPSEventListener(port=event_port)
                
                # Initialize OpenSIPS MI Client  
                opensips_ip = self.config.get('opensips', 'ip', fallback='172.20.0.6')
                opensips_port = int(self.config.get('opensips', 'port', fallback='8087'))
                self.opensips_mi_client = OpenSIPSMIClient(host=opensips_ip, port=opensips_port)
                
                logger.info("✅ OpenSIPS Event integration initialized",
                           event_port=event_port,
                           mi_host=opensips_ip,
                           mi_port=opensips_port)
            except Exception as e:
                logger.error("❌ OpenSIPS Event integration failed", error=str(e))
                raise ConfigValidationError(f"OpenSIPS Event integration failed: {str(e)}")
            
            # Initialize Call Manager (compatibility)
            logger.info("🔧 Initializing Call Manager...")
            try:
                self.call_manager = CallManager(self.pipeline_manager, self.mi_conn)
                logger.info("✅ Call manager initialized successfully")
            except Exception as e:
                logger.error("❌ Call Manager initialization failed", error=str(e))
                raise ConfigValidationError(f"Call Manager initialization failed: {str(e)}")
            
            # Final success message
            logger.info("🎉 All AI services initialized successfully!")
            logger.info("📋 Service summary:")
            logger.info(f"   ✅ LLM Service: {self.services['llm'].__class__.__name__}")
            logger.info(f"   ✅ STT Service: {self.services['stt'].__class__.__name__}")
            logger.info(f"   ✅ TTS Service: {self.services['tts'].__class__.__name__}")
            logger.info(f"   ✅ Pipeline Config: {pipeline_config}")
            
        except Exception as e:
            logger.error("💥 Failed to initialize services", error=str(e))
            # Cleanup on failure
            await self._cleanup_services()
            raise
    
    async def _cleanup_services(self):
        """Cleanup partially initialized services with proper error handling"""
        try:
            logger.info("🧹 Starting service cleanup...")
            cleanup_tasks = []
            
            # Add cleanup tasks for each service
            for service_name in ['llm', 'stt', 'tts']:
                service = self.services.get(service_name)
                if service and hasattr(service, 'stop'):
                    cleanup_tasks.append(self._safe_service_stop(service_name, service))
            
            # Pipeline manager cleanup
            if hasattr(self, 'pipeline_manager') and self.pipeline_manager:
                cleanup_tasks.append(self._safe_pipeline_stop())
            
            # Execute all cleanup tasks with timeout
            if cleanup_tasks:
                cleanup_results = await asyncio.gather(*cleanup_tasks, return_exceptions=True)
                
                # Log cleanup results
                for i, result in enumerate(cleanup_results):
                    if isinstance(result, Exception):
                        logger.warning(f"⚠️ Cleanup task {i} failed", error=str(result))
                    else:
                        logger.debug(f"✅ Cleanup task {i} completed")
                
                logger.info("🧹 Service cleanup completed")
            else:
                logger.info("🧹 No services to cleanup")
                
        except Exception as e:
            logger.error("❌ Error during service cleanup", error=str(e))
    
    async def _safe_service_stop(self, service_name: str, service):
        """Safely stop a service with timeout and error handling"""
        try:
            stop_timeout = 5.0  # 5 seconds timeout
            await asyncio.wait_for(service.stop(), timeout=stop_timeout)
            logger.info(f"✅ {service_name} service stopped cleanly")
        except asyncio.TimeoutError:
            logger.warning(f"⏰ {service_name} service stop timeout ({stop_timeout}s)")
        except Exception as e:
            logger.error(f"❌ Error stopping {service_name} service", error=str(e))
    
    async def _safe_pipeline_stop(self):
        """Safely stop the pipeline manager"""
        try:
            stop_timeout = 10.0  # 10 seconds timeout for pipeline
            await asyncio.wait_for(self.pipeline_manager.stop(), timeout=stop_timeout)
            logger.info("✅ Pipeline manager stopped cleanly")
        except asyncio.TimeoutError:
            logger.warning(f"⏰ Pipeline manager stop timeout ({stop_timeout}s)")
        except Exception as e:
            logger.error("❌ Error stopping pipeline manager", error=str(e))
    
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
        """Ana servisi başlat - Yeni OpenSIPSEngine ile"""
        try:
            self.running = True
            
            # 1. Load configuration
            logger.info("📄 Loading configuration...")
            self.load_config()
            
            # 2. Initialize MI connection
            logger.info("🔗 Initializing MI connection...")
            self.initialize_mi_connection()
            
            # 3. Initialize AI services
            logger.info("🤖 Initializing AI services...")
            await self.initialize_services()
            
            logger.info("🎉 OpenSIPS AI Voice Connector initialized successfully!")
            logger.info("🎯 Services ready:")
            logger.info("   ✅ LLM (Custom LLaMA WebSocket)")
            logger.info("   ✅ STT (Vosk WebSocket)")
            logger.info("   ✅ TTS (Piper WebSocket)")
            logger.info("   ✅ Pipeline Manager")
            logger.info("   ✅ OpenSIPS Engine (NEW)")
            
            # 4. Start OpenSIPS Engine (Event Handler)
            if self.opensips_engine:
                logger.info("🚀 Starting OpenSIPS Engine...")
                try:
                    await self.opensips_engine.start_event_handler()
                    logger.info("✅ OpenSIPS Engine started successfully!")
                except Exception as e:
                    logger.error("❌ Failed to start OpenSIPS Engine", error=str(e), exc_info=True)
                    raise
            else:
                logger.error("❌ OpenSIPS Engine not initialized!")
                raise Exception("OpenSIPS Engine initialization failed")
            
            # 5. Initialize OpenSIPS Event Handler (Critical - This was missing!)
            logger.info("🎯 Starting OpenSIPS Event Handler on port 8090...")
            try:
                await self.start_opensips_handler()
                logger.info("✅ OpenSIPS Event Handler initialized successfully!")
            except Exception as e:
                logger.error("❌ Failed to initialize OpenSIPS Event Handler", error=str(e), exc_info=True)
                raise
            
            # 6. Initialize SIP Listener (Critical - This was missing!)
            logger.info("🎯 Starting SIP Listener on port 8089...")
            try:
                await self.start_sip_listener()
                logger.info("✅ SIP Listener initialized successfully!")
            except Exception as e:
                logger.error("❌ Failed to initialize SIP Listener", error=str(e), exc_info=True)
                raise
            
            # 7. Start both listeners in parallel
            opensips_task = asyncio.create_task(self.run_opensips_handler_loop())
            sip_task = asyncio.create_task(self.run_sip_listener_loop()) 
            
            logger.info("🔥 OpenSIPS AI Voice Connector is ready for calls!")
            logger.info("   📡 OpenSIPS Event Handler: 0.0.0.0:8090")
            logger.info("   📞 SIP Listener: 0.0.0.0:8089")
            
            # Wait for both tasks to complete (or until shutdown)
            try:
                await asyncio.gather(opensips_task, sip_task)
            except asyncio.CancelledError:
                logger.info("Application shutdown requested")
            finally:
                # Cancel remaining tasks
                for task in [opensips_task, sip_task]:
                    if not task.done():
                        task.cancel()
                        try:
                            await task
                        except asyncio.CancelledError:
                            pass
            
        except Exception as e:
            logger.error("⚠️ Critical error during startup", error=str(e))
            logger.error("Exception details", exc_info=True)
            await self.stop()
            raise
    
    async def stop(self):
        """Servisi durdur - Yeni OpenSIPSEngine ile"""
        logger.info("Stopping OpenSIPS AI Voice Connector...")
        self.running = False
        
        # Stop OpenSIPS Engine (yeni implementasyon)
        if self.opensips_engine:
            try:
                await self.opensips_engine.shutdown()
                logger.info("OpenSIPS Engine stopped")
            except Exception as e:
                logger.error("Error stopping OpenSIPS Engine", error=str(e))
        
        # Cancel background tasks (legacy)
        for task in self._background_tasks:
            if not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        self._background_tasks.clear()
        
        # Stop legacy components
        if self.sip_listener:
            await self.sip_listener.stop()
            logger.info("SIP listener stopped")
        
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

# Test endpoints for development
app = FastAPI()

@app.get("/test/pipeline")
async def test_pipeline():
    """Test pipeline functionality"""
    if connector.pipeline_manager:
        stats = connector.pipeline_manager.get_performance_stats()
        return {
            "status": "Pipeline active",
            "stats": stats,
            "running": connector.pipeline_manager._is_running
        }
    return {"status": "Pipeline not available"}

@app.post("/debug/start_stream/{call_key}")
async def debug_start_stream_endpoint(call_key: str):
    """Debug endpoint to manually start stream for a call"""
    try:
        result = await connector.debug_start_stream(call_key)
        return result
    except Exception as e:
        return {"status": "error", "message": str(e)}

# Run the application
exit_code = asyncio.run(main())
sys.exit(exit_code)

# vim: tabstop=8 expandtab shiftwidth=4 softtabstop=4
