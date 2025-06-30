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
from typing import Dict, Any

# FastAPI is optional for test mode
try:
    from fastapi import FastAPI
    FASTAPI_AVAILABLE = True
except ImportError:
    FastAPI = None
    FASTAPI_AVAILABLE = False

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
# Native transport handles pipeline management directly

# OpenSIPS integration imports  
from utils import get_ai, FLAVORS, get_ai_flavor, get_user, get_to, indialog
from config import (
    initialize as initialize_config,
    get as get_config,
    get_section as get_config_section,
    ConfigValidationError
)

# Call management - Native Pipecat Transport
from transports.native_call_manager import NativeCallManager as CallManager
from transports.native_call_manager import NativeCall as Call
logger.info("🎵 Using Native Pipecat Transport")

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
    
    def __init__(self, call_manager, mi_conn):
        """
        Args:
            call_manager: The application's CallManager instance.
            mi_conn: The application's MI connection instance.
        """
        self.call_manager = call_manager
        self.mi_conn = mi_conn
        self.active_calls = {}
        
        # Event handler
        self.event_handler = None
        self.event_subscription = None
        
        # SIP Listener - OpenSIPS'den gelen INVITE'ları dinler
        self.sip_listener = None
        self.sip_listener_task = None
        
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
        """Start OpenSIPS event handler and SIP listener"""
        try:
            # Get configuration
            engine_cfg = get_config_section("engine")
            host_ip = engine_cfg.get("event_ip", "0.0.0.0")
            event_port = int(engine_cfg.get("event_port", "8090"))
            sip_port = int(engine_cfg.get("sip_port", "8089"))
            
            # 1. Initialize event handler for E_UA_SESSION events
            if OPENSIPS_AVAILABLE:
                self.event_handler = OpenSIPSEventHandler(
                    host=host_ip, port=event_port, mi_conn=self.mi_conn
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
                logger.warning("Using mock OpenSIPS event handler", ip=host_ip, port=event_port)
            
            # 2. Initialize and start SIP Listener for INVITE messages
            self.sip_listener = SIPListener(host=host_ip, port=sip_port, call_manager=self.call_manager)
            self.sip_listener_task = asyncio.create_task(self.sip_listener.start())
            logger.info("SIP Listener started", ip=host_ip, port=sip_port)
                
            return True
            
        except Exception as e:
            logger.error("Failed to start OpenSIPS event handler and SIP listener", error=str(e))
            return False

    async def shutdown(self):
        """Shutdown OpenSIPS engine"""
        logger.info("Shutting down OpenSIPS engine")
        
        # Stop SIP Listener
        if self.sip_listener:
            try:
                await self.sip_listener.stop()
                logger.info("SIP Listener stopped")
            except Exception as e:
                logger.error("Error stopping SIP Listener", error=str(e))
        
        # Cancel SIP Listener task
        if self.sip_listener_task and not self.sip_listener_task.done():
            self.sip_listener_task.cancel()
            try:
                await self.sip_listener_task
            except asyncio.CancelledError:
                pass
        
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
            if call:
                logger.info("🎵 Native call found", call_key=call_key)
                # Native calls handle their own streaming
                return {"status": "success", "message": f"Native call {call_key} is running"}
            else:
                logger.warning("⚠️ DEBUG: Call not found", call_key=call_key)
                return {"status": "error", "message": f"Call {call_key} not found"}
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
            
            # Enhanced logging for diagnostics
            actual_host, actual_port = self.socket.getsockname()
            logger.info("🚀 SIP Listener started successfully", 
                       configured_host=self.host, 
                       configured_port=self.port,
                       actual_host=actual_host,
                       actual_port=actual_port)
            
            # Log container network info for diagnostics
            try:
                import socket as sock_module
                hostname = sock_module.gethostname()
                local_ip = sock_module.gethostbyname(hostname)
                logger.info("📡 Container network info", 
                           hostname=hostname, 
                           local_ip=local_ip)
            except Exception as e:
                logger.warning("Could not get container network info", error=str(e))
            
            # Listen for incoming SIP messages from OpenSIPS
            message_count = 0
            while self.running:
                try:
                    loop = asyncio.get_event_loop()
                    data, addr = await loop.sock_recvfrom(self.socket, 4096)
                    
                    message_count += 1
                    logger.info("📨 SIP message received", 
                               message_number=message_count,
                               from_addr=f"{addr[0]}:{addr[1]}",
                               data_size=len(data))
                    
                    # Process SIP message
                    await self.handle_sip_message(data.decode('utf-8'), addr)
                    
                except asyncio.CancelledError:
                    logger.info("SIP listener cancelled")
                    break
                except Exception as e:
                    logger.error("Error in SIP listener", error=str(e))
                    await asyncio.sleep(0.1)
                    
        except Exception as e:
            logger.error("💥 Failed to start SIP listener", 
                        host=self.host, 
                        port=self.port, 
                        error=str(e))
            raise
    
    async def handle_sip_message(self, sip_data: str, addr):
        """SIP mesajını işle"""
        try:
            logger.info("🔍 Processing SIP message", 
                       from_addr=f"{addr[0]}:{addr[1]}", 
                       message_size=len(sip_data))
            logger.debug("SIP message content preview", 
                        content=sip_data[:300] + "..." if len(sip_data) > 300 else sip_data)
            
            # Parse SIP method
            lines = sip_data.strip().split('\n')
            if not lines:
                logger.warning("Empty SIP message received")
                return
                
            first_line = lines[0].strip()
            logger.info("📋 SIP method detected", method_line=first_line)
            
            # Debug: Full SIP message for ACK detection
            logger.debug("Full SIP message details", method=first_line, full_message=sip_data[:500])
            
            if first_line.startswith('INVITE'):
                logger.info("🎯 Processing INVITE message")
                await self.handle_invite(sip_data, addr)
            elif first_line.startswith('BYE'):
                logger.info("📞 Processing BYE message")
                await self.handle_bye(sip_data, addr)
            elif first_line.startswith('CANCEL'):
                logger.info("🚫 Processing CANCEL message")
                await self.handle_cancel(sip_data, addr)
            elif first_line.startswith('ACK'):
                logger.info("✅ Processing ACK message")
                await self.handle_ack(sip_data, addr)
            else:
                logger.warning("❓ Unhandled SIP method", 
                              method=first_line, 
                              from_addr=f"{addr[0]}:{addr[1]}")
                
        except Exception as e:
            logger.error("💥 Error handling SIP message", 
                        error=str(e), 
                        from_addr=f"{addr[0]}:{addr[1]}")
            import traceback
            logger.debug("SIP message handling traceback", traceback=traceback.format_exc())
    
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
    """
    Main application class.
    Manages the lifecycle of all components.
    """

    def __init__(self, config_file: str = None, test_mode: bool = False):
        """
        Initializes the application.
        Args:
            config_file: Path to the configuration file.
            test_mode: Flag to run in test mode (not fully implemented).
        """
        self.config_file = config_file
        self.test_mode = test_mode
        
        # Core components
        self.mi_conn = None
        self.call_manager = None
        # Native transport handles pipeline management directly
        self.engine = None
        
        # Service registry
        self.services = {}
        self._background_tasks = {}
        
        self.running = False

    def load_config(self):
        """Loads the configuration from the file."""
        logger.info("📄 Loading configuration...")
        if not self.config_file or not Path(self.config_file).exists():
            raise FileNotFoundError(f"Configuration file not found: {self.config_file}")
            
        initialize_config(self.config_file)
        logger.info("✅ Configuration loaded successfully.")
        
    def initialize_mi_connection(self):
        """Initializes the OpenSIPS MI connection."""
        logger.info("🔗 Initializing MI connection...")
        mi_config = get_config_section("opensips")
        if not mi_config:
            raise ConfigValidationError("Missing [opensips] section in configuration file.")
            
        mi_type = mi_config.get("mi_transport")
        
        if mi_type == "fifo":
            # This is not configured in the default .ini but provided for completeness
            fifo_path = mi_config.get("fifo_path")
            if not fifo_path:
                raise ConfigValidationError("mi_transport is 'fifo' but 'fifo_path' is not set in [opensips] section.")
            self.mi_conn = OpenSIPSMI(fifo_path)
        elif mi_type == "datagram":
            host = mi_config.get("host")
            port = mi_config.getint("port")
            if not host or not port:
                raise ConfigValidationError("mi_transport is 'datagram' but 'host' or 'port' is missing from [opensips] section.")
            
            # The python-opensips library expects keyword arguments here
            self.mi_conn = OpenSIPSMI(conn="datagram", datagram_ip=host, datagram_port=port)
        else:
            raise ValueError(f"Unsupported MI transport type: {mi_type}")
            
        logger.info("✅ MI connection initialized.", transport=mi_type)
        
        # Clear any stale registrations on startup
        # self.mi_conn.execute('ul_rm', {'table': 'location', 'avp': 'ruri_user'})
        # logger.info("Cleared previous registrations from OpenSIPS location table.")
        logger.warning("Skipping clearing of location table on startup.")

    async def initialize_services(self):
        """Initializes AI services and the pipeline manager."""
        logger.info("🔧 Initializing AI services...")

        # Initialize services, allowing individual services to fail without stopping the app
        for service_name in ["llm", "stt", "tts"]:
            try:
                service_config = get_config_section(service_name)
                if not service_config:
                    logger.warning(f"Skipping {service_name.upper()} service: section not found in config.")
                    continue

                logger.info(f"📡 Creating {service_name.upper()} service...")
                if service_name == "llm":
                    self.services['llm'] = LlamaWebsocketLLMService(url=service_config.get('url'), model=service_config.get('model'))
                elif service_name == "stt":
                    self.services['stt'] = VoskWebsocketSTTService(url=service_config.get('url'))
                elif service_name == "tts":
                    self.services['tts'] = PiperWebsocketTTSService(url=service_config.get('url'))
                logger.info(f"✅ {service_name.upper()} service created.")
            except Exception as e:
                logger.error(f"❌ Failed to create {service_name.upper()} service", error=str(e))
                self.services[service_name] = None
        
        # Native transport uses direct service integration, no separate pipeline manager needed
        logger.info("✅ Services initialized - Native transport handles pipeline management")

    async def _cleanup_services(self):
        """Stops all running services and the pipeline manager."""
        logger.info("🧹 Cleaning up services...")
        
        # Stop all services in parallel
        stop_tasks = [
            self._safe_service_stop(name, service)
            for name, service in self.services.items() if service
        ]
        if stop_tasks:
            await asyncio.gather(*stop_tasks)

        # Native transport handles its own pipeline cleanup
        
        logger.info("🧹 Service cleanup completed.")

    async def _safe_service_stop(self, service_name: str, service):
        """Safely stops a single service."""
        try:
            await service.stop()
            logger.info(f"Service {service_name} stopped.")
        except Exception as e:
            logger.error(f"Error stopping service {service_name}", error=str(e))



    async def start_opensips_handler(self):
        """Initializes and starts the OpenSIPS event handler."""
        if self.engine:
            logger.info("▶️ Starting OpenSIPS event handler...")
            await self.engine.start_event_handler()
            logger.info("✅ OpenSIPS event handler started.")

    async def start(self):
        """Starts all application components in the correct order."""
        try:
            logger.info("🚀 Starting OpenSIPS AI Voice Connector...")

            # 1. Load configuration
            self.load_config()

            # 2. Initialize MI connection
            self.initialize_mi_connection()

            # 3. Initialize services first
            await self.initialize_services()
            
            # 4. Create Native Call Manager with services
            self.call_manager = CallManager(services=self.services)
            logger.info("✅ Native Call Manager created with services")
            
            # 5. Native Call Manager uses direct service integration
            logger.info("✅ Native Call Manager uses direct service integration")
            
            # 6. Initialize OpenSIPS Engine
            self.engine = OpenSIPSEngine(self.call_manager, self.mi_conn)
            
            # 7. Set engine in CallManager
            self.call_manager.set_engine(self.engine)
            
            # 8. Start the OpenSIPS event handler
            await self.start_opensips_handler()
            
            logger.info("✅ Application started successfully!")
            self.running = True

        except Exception as e:
            logger.error("💥 Application failed to start", error=str(e), exc_info=True)
            await self.stop()
            raise

    async def stop(self):
        """Stops all application components gracefully."""
        if not self.running:
            return
            
        logger.info("🛑 Stopping OpenSIPS AI Voice Connector...")
        self.running = False

        # 1. Stop the OpenSIPS event handler first
        if self.engine and hasattr(self.engine, 'shutdown'):
            await self.engine.shutdown()
            logger.info("OpenSIPS Engine stopped.")

        # 2. Stop services and pipeline
        await self._cleanup_services()
        
        # Shutdown Call Manager
        if self.call_manager:
            await self.call_manager.shutdown()
            logger.info("Call Manager stopped.")
        
        # Cancel any lingering background tasks
        for task in self._background_tasks.values():
            if not task.done():
                task.cancel()
        if self._background_tasks:
            await asyncio.gather(*self._background_tasks.values(), return_exceptions=True)

        logger.info("✅ OpenSIPS AI Voice Connector stopped successfully.")

async def main():
    """Main entry point for the application"""
    
    # Determine config file path
    # In Docker, the app runs from /app, so the cfg directory is at /app/cfg
    config_file = os.environ.get("OAVC_CONFIG_FILE", "cfg/opensips-ai-voice-connector.ini")
    
    # Check for test mode
    test_mode = os.environ.get("OAVC_TEST_MODE", "false").lower() == "true"
    
    # Create the application instance
    app_instance = OpenSIPSAIVoiceConnector(
        config_file=config_file,
        test_mode=test_mode
    )

    # Setup signal handlers for graceful shutdown (Windows compatible)
    loop = asyncio.get_event_loop()
    
    # Use only signals available on Windows
    stop_signals = []
    if hasattr(signal, 'SIGTERM'):
        stop_signals.append(signal.SIGTERM)
    if hasattr(signal, 'SIGINT'):
        stop_signals.append(signal.SIGINT)
    
    try:
        for signum in stop_signals:
            loop.add_signal_handler(signum, lambda signum=signum: asyncio.create_task(app_instance.stop()))
    except NotImplementedError:
        # Windows doesn't support signal handlers with asyncio
        logger.info("Signal handlers not available on this platform")

    # Start the connector
    await app_instance.start()

    if test_mode:
        logger.info("🧪 TEST MODE: Application started successfully!")
        print("\n🧪 TEST MODE: Application running successfully!")
        print("✅ Configuration loaded")
        print("✅ Mock services initialized") 
        print("✅ OpenSIPS event handler ready")
        print("✅ Call manager ready")
        print("\nPress Ctrl+C to stop...")
        
        # Keep running in test mode
        while app_instance.running:
            await asyncio.sleep(1)
    else:
        # Normal mode - wait for events
        while app_instance.running:
            await asyncio.sleep(0.1)

    return 0

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)

# vim: tabstop=8 expandtab shiftwidth=4 softtabstop=4
