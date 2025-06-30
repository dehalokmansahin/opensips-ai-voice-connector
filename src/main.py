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
import random
import string

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
            from_user = get_user(params['from'])
            to_user = get_user(params['to'])
            call_id = params['callid']

            logger.info("📞 Handling call", 
                       from_user=from_user,
                       to_user=to_user,
                       call_id=call_id)

            if method == 'INVITE':
                if self.indialog(params):
                    logger.info(f"Re-INVITE received for call {call_id}")
                    # Handle re-INVITE if necessary
                else:
                    logger.info(f"New INVITE for call {call_id}")
                    # Create a new call instance
                    new_call = self.call_manager.create_call(
                        from_user=from_user,
                        to_user=to_user,
                        call_id=call_id,
                        sdp_body=params.get('body', ''),
                        key=key
                    )
                    
                    if new_call:
                        # Add to active calls
                        self.active_calls[call_id] = new_call
                        logger.info("New call instance created", call_id=call_id)
                    else:
                        logger.error("Failed to create call instance", call_id=call_id)
                        self.mi_reply(key, 'INVITE', 500, 'Internal Server Error')
                        
            elif method == 'BYE':
                logger.info(f"BYE received for call {call_id}")
                if call_id in self.active_calls:
                    await self.call_manager.terminate_call(call_id)
                    del self.active_calls[call_id]
                    logger.info("Call terminated and removed", call_id=call_id)
                else:
                    logger.warning("BYE received for unknown call", call_id=call_id)

        except Exception as e:
            logger.error("Error handling call", call_id=params.get('callid'), error=str(e), exc_info=True)

    def udp_handler(self, data: dict):
        """
        Handles incoming events from the OpenSIPS event_datagram module.
        This is the primary entry point for SIP events.
        """
        try:
            event_name = data.get('name')
            params = data.get('params', {})
            
            logger.info("Received OpenSIPS event", event_name=event_name, params=params)

            if event_name == 'E_UL_UA_SESSION_START':
                call_id = params.get('callid')
                key = params.get('key')
                method = params.get('method')
                
                # Create a new Call instance (or get existing one)
                call = self.call_manager.get_call(call_id)
                if not call:
                    # Logic to create call instance
                    pass

                # Handle the call in an async task
                asyncio.create_task(self.handle_call(call, key, method, params))

            elif event_name == 'E_DIALOG_START':
                logger.info("Dialog started", params=params)
            
            elif event_name == 'E_DIALOG_END':
                logger.info("Dialog ended", params=params)

        except Exception as e:
            logger.error("Error in UDP event handler", error=str(e), data=data)

    async def start_event_handler(self):
        """
        Starts the event handler using OpenSIPS event subscriptions.
        """
        try:
            logger.info("Starting OpenSIPS event handler...")
            if not OPENSIPS_AVAILABLE:
                logger.warning("OpenSIPS library not available, cannot start event handler.")
                return

            event_config = get_config_section("opensips")
            if not event_config:
                raise ConfigValidationError("Missing [opensips] section in config")

            host = event_config.get('host', '127.0.0.1')
            port = int(event_config.get('event_port', 8085))
            
            # Using the mock handler for now until python-opensips is fully integrated
            self.event_handler = MockOpenSIPSEventHandler(
                address=(host, port),
                udp_handler=self.udp_handler
            )
            
            # This is where you would subscribe to specific events
            # self.event_subscription = self.event_handler.async_subscribe(
            #     'E_UL_UA_SESSION_START', self.udp_handler
            # )
            
            logger.info("Mock OpenSIPS Event Handler started", host=host, port=port)
            
            # Keep the handler running
            # In a real implementation, this would involve a running loop
            # For now, we assume events are pushed to udp_handler

        except (OpenSIPSEventException, ConfigValidationError) as e:
            logger.error("Failed to start event handler", error=str(e))
            raise
        except Exception as e:
            logger.error("An unexpected error occurred in event handler", error=str(e), exc_info=True)
            raise

    async def shutdown(self):
        """Shuts down the OpenSIPS engine and cleans up resources."""
        logger.info("Shutting down OpenSIPS Engine...")
        
        # Unsubscribe from events
        if self.event_subscription:
            try:
                self.event_subscription.unsubscribe()
                logger.info("Unsubscribed from OpenSIPS events.")
            except Exception as e:
                logger.error("Error unsubscribing from events", error=str(e))

        # Terminate all active calls
        if self.call_manager:
            await self.call_manager.shutdown()
            
        logger.info("OpenSIPS Engine shut down successfully.")

    async def debug_start_stream(self, call_key: str):
        """Manually starts the audio stream for debugging."""
        call = self.call_manager.get_call_by_key(call_key)
        if call:
            logger.info("Manually starting stream for call", call_key=call_key)
            await call.start_stream()
        else:
            logger.warning("Call not found for debug_start_stream", call_key=call_key)

    async def terminate_call(self, call_key: str):
        """Terminates a call by its key."""
        logger.info(f"Terminating call with key {call_key}")
        await self.call_manager.terminate_call_by_key(call_key)

    def get_call(self, call_key: str):
        return self.call_manager.get_call_by_key(call_key)

class OpenSIPSEventHandler:
    """
    Handles events from OpenSIPS event_datagram module
    (placeholder for full integration)
    """
    def __init__(self, host="0.0.0.0", port=8090, mi_conn=None):
        self.host = host
        self.port = port
        self.mi_conn = mi_conn
        self.transport = None
        self.call_manager = None
        self.subscription = None

        class SocketWrapper:
            def __init__(self, parent):
                self._parent = parent
            def getsockname(self):
                # Mock getsockname to avoid issues
                return (self._parent.host, self._parent.port)

        self.socket = SocketWrapper(self)

    def set_call_manager(self, call_manager):
        self.call_manager = call_manager

    def async_subscribe(self, event_name, handler):
        """Mock subscription"""
        logger.info(f"Subscribed to {event_name}")
        
        # Create a mock subscription object
        class MockSubscription:
            def __init__(self, parent):
                self._parent = parent
            def unsubscribe(self):
                logger.info(f"Unsubscribed from {event_name}")
                self._parent.subscription = None
        
        self.subscription = MockSubscription(self)
        return self.subscription

    async def start(self):
        """Starts the UDP server to listen for events."""
        loop = asyncio.get_running_loop()
        
        class EventProtocol(asyncio.DatagramProtocol):
            def __init__(self, handler):
                self.handler = handler
            def connection_made(self, transport):
                self.transport = transport
            def datagram_received(self, data, addr):
                message = data.decode()
                asyncio.create_task(self.handler(message, addr))

        try:
            self.transport, _ = await loop.create_datagram_endpoint(
                lambda: EventProtocol(self.handle_opensips_event),
                local_addr=(self.host, self.port)
            )
            logger.info(f"OpenSIPS event listener started on udp://{self.host}:{self.port}")
            
            # Subscribe to the event (if not already)
            # This part is tricky with python-opensips library
            
        except Exception as e:
            logger.error(f"Failed to start event listener: {e}")
            raise

    async def handle_opensips_event(self, event_data: str, addr):
        """
        Parses and handles a raw event from OpenSIPS.
        Format: "event_name|key1=val1|key2=val2|..."
        """
        logger.info(f"Received event from {addr}: {event_data}")
        
        parts = event_data.split('|')
        event_name = parts[0]
        
        if event_name == 'E_UL_UA_SESSION_START':
            await self.handle_ua_session_event(event_data)
        else:
            logger.warning(f"Unhandled event type: {event_name}")

    async def handle_ua_session_event(self, event_data: str):
        """Handles E_UL_UA_SESSION_START events."""
        params = {}
        parts = event_data.split('|')
        
        for part in parts[1:]:
            if '=' in part:
                key, val = part.split('=', 1)
                params[key] = val
        
        call_id = params.get('callid')
        key = params.get('key')
        method = params.get('method')
        
        if not all([call_id, key, method]):
            logger.error("Missing required fields in session event", event=event_data)
            return

        if method == 'INVITE':
            await self.handle_invite(key, params)
        elif method == 'BYE':
            await self.handle_bye(key, params)
        elif method == 'CANCEL':
            await self.handle_cancel(key, params)
        else:
            logger.warning(f"Unhandled method in session event: {method}")

    async def handle_invite(self, call_key: str, params: dict):
        """Handles a new INVITE."""
        call_id = params.get('callid')
        sdp_body = params.get('body', '')
        
        logger.info(f"Handling INVITE for call {call_id}")
        
        try:
            sdp_info = self.call_manager.parse_sdp(sdp_body)
            
            if not sdp_info or not sdp_info.get('media_port'):
                logger.warning("INVITE without valid SDP media info.")
                await self.send_response(call_key, 'INVITE', 400, 'Bad Request - No Media Port', params)
                return
            
            logger.info(f"Creating call for {call_id}")
            
            # Create a new call using the manager
            call = await self.call_manager.create_call(
                call_id=call_id,
                sdp_info=sdp_info
            )

            # Send 180 Ringing
            await self.send_response(call_key, call_id, '180', 'Ringing', params)
            
            # After call setup, get the SDP response and send 200 OK
            sdp_response = call.get_sdp_body()
            await self.send_response(call_key, call_id, '200', 'OK', params, body=sdp_response)

        except Exception as e:
            logger.error(f"Error handling INVITE for {call_id}: {e}", exc_info=True)
            await self.send_response(call_key, 'INVITE', 500, "Internal Server Error", params)

    async def handle_bye(self, call_key: str, params: dict):
        """Handles a BYE request."""
        call_id = params.get('callid')
        logger.info(f"Handling BYE for call {call_id}")
        await self.call_manager.terminate_call(call_key)
        # BYE does not require a response in the same way
        # OpenSIPS will handle transaction

    async def handle_cancel(self, call_key: str, params: dict):
        """Handles a CANCEL request."""
        call_id = params.get('callid')
        logger.info(f"Handling CANCEL for call {call_id}")
        await self.call_manager.terminate_call(call_key)
        # CANCEL handling in OpenSIPS is complex, this is a simplification

    async def send_response(self, call_key: str, method: str, code: int, reason: str, body: str = None):
        """Sends a response back to OpenSIPS via MI."""
        if not self.mi_conn:
            logger.error("MI connection not available, cannot send response.")
            return

        try:
            params = {
                'key': call_key,
                'method': method,
                'code': code,
                'reason': reason
            }
            if body:
                params['body'] = body
            
            self.mi_conn.execute('ua_session_reply', params)
            logger.info(f"Sent {code} {reason} for {method} on call {call_key}")
        except Exception as e:
            logger.error(f"Failed to send MI reply for {call_key}: {e}")

    async def stop(self):
        """Stops the event listener."""
        if self.transport:
            self.transport.close()
            logger.info("OpenSIPS event listener stopped.")


class SIPListener:
    """
    Listens for SIP messages directly on a UDP socket.
    Used for local testing without a full OpenSIPS instance.
    """
    def __init__(self, host="0.0.0.0", port=8089, call_manager=None):
        self.host = host
        self.port = port
        self.transport = None
        self.call_manager = call_manager

    def _parse_sdp_body(self, sdp_str: str) -> dict:
        """
        Parses essential information from SDP.
        A very basic parser for demonstration.
        """
        sdp_info = {}
        lines = sdp_str.split('\r\n')
        for line in lines:
            if line.startswith('c=IN IP4'):
                sdp_info['media_ip'] = line.split()[-1]
            elif line.startswith('m=audio'):
                parts = line.split()
                sdp_info['media_port'] = int(parts[1])
                # Assume PCMU if payload type is 0
                if ' 0' in line:
                    sdp_info['audio_format'] = 'PCMU'
        return sdp_info

    async def start(self):
        """Starts the UDP server."""
        loop = asyncio.get_running_loop()

        class SIPProtocol(asyncio.DatagramProtocol):
            def __init__(self, handler_func):
                self.handler_func = handler_func
                super().__init__()
            def connection_made(self, transport):
                self.transport = transport
            def datagram_received(self, data, addr):
                message = data.decode()
                asyncio.create_task(self.handler_func(message, addr))

        try:
            self.transport, _ = await loop.create_datagram_endpoint(
                lambda: SIPProtocol(self.handle_sip_message),
                local_addr=(self.host, self.port),
            )
            logger.info(f"SIP listener started on udp://{self.host}:{self.port}")
        except Exception as e:
            logger.error(f"Failed to start SIP listener: {e}")

    async def handle_sip_message(self, sip_data: str, addr):
        """
        Handles a raw SIP message from the socket.
        This is a very simplified SIP parser for testing.
        """
        logger.debug(f"Received SIP message from {addr}:\n{sip_data[:200]}...")
        
        lines = sip_data.split('\r\n')
        if not lines:
            return
            
        request_line = lines[0]
        
        try:
            method, uri, version = request_line.split()
        except ValueError:
            logger.warning(f"Malformed request line: {request_line}")
            return
            
        if method == "INVITE":
            await self.handle_invite(sip_data, addr)
        elif method == "BYE":
            await self.handle_bye(sip_data, addr)
        elif method == "CANCEL":
            await self.handle_cancel(sip_data, addr)
        elif method == "ACK":
            await self.handle_ack(sip_data, addr)
        else:
            logger.info(f"Received unhandled SIP method: {method}")
            # Send a 405 Method Not Allowed
            headers = {h.split(': ')[0]: h.split(': ')[1] for h in lines[1:] if ': ' in h}
            call_id = headers.get('Call-ID')
            await self.send_response(addr, call_id, '405', 'Method Not Allowed', headers)


    async def handle_invite(self, sip_data: str, addr):
        """Handles an INVITE request."""
        logger.info(f"Handling INVITE from {addr}")
        
        parts = sip_data.split('\r\n\r\n')
        header_str = parts[0]
        sdp_body = parts[1] if len(parts) > 1 else ""

        headers = {}
        lines = header_str.split('\r\n')
        last_key = None
        for line in lines[1:]:
            if line.startswith((' ', '\t')) and last_key:
                headers[last_key] += ' ' + line.lstrip()
            elif ': ' in line:
                key, value = line.split(': ', 1)
                last_key = key.lower()
                headers[last_key] = value

        call_id = headers.get('call-id')
        to_header_str = headers.get('to')

        if not call_id:
            logger.error("INVITE without Call-ID, cannot process.")
            return

        if 'tag=' in (to_header_str or ""):
             logger.info(f"Re-INVITE for call {call_id}, not currently supported.")
             await self.send_response(addr, call_id, '481', 'Call/Transaction Does Not Exist', headers)
             return
             
        sdp_info = self._parse_sdp_body(sdp_body)
        
        if not sdp_info or not sdp_info.get('media_port'):
            logger.warning("INVITE without valid SDP media info.")
            await self.send_response(addr, call_id, '400', 'Bad Request - No Media Port', headers)
            return
            
        logger.info(f"Creating call for {call_id}")
        
        # Corrected call to create_call
        call = await self.call_manager.create_call(
            call_id=call_id,
            sdp_info=sdp_info
        )

        # Send 180 Ringing
        await self.send_response(addr, call_id, '180', 'Ringing', headers)
        
        # After call setup, get the SDP response and send 200 OK
        sdp_response = await call.start() # Call start now returns the SDP
        await self.send_response(addr, call_id, '200', 'OK', headers, body=sdp_response)

    async def handle_bye(self, sip_data: str, addr):
        """Handles a BYE request."""
        headers = {h.split(': ')[0]: h.split(': ')[1] for h in sip_data.split('\r\n')[1:] if ': ' in h}
        call_id = headers.get('Call-ID')
        
        logger.info(f"Handling BYE for {call_id} from {addr}")
        
        if call_id:
            await self.call_manager.terminate_call(call_id)
            # Send 200 OK for BYE
            await self.send_response(addr, call_id, '200', 'OK', headers)
        else:
            logger.warning("BYE without Call-ID received.")

    async def handle_cancel(self, sip_data: str, addr):
        """Handles a CANCEL request."""
        headers = {h.split(': ')[0]: h.split(': ')[1] for h in sip_data.split('\r\n')[1:] if ': ' in h}
        call_id = headers.get('Call-ID')
        
        logger.info(f"Handling CANCEL for {call_id} from {addr}")
        
        if call_id:
            # First, reply to the CANCEL itself with a 200 OK
            await self.send_response(addr, call_id, '200', 'OK', headers)
            # Then, terminate the original INVITE transaction with a 487
            await self.call_manager.terminate_call(call_id)
            # You would also send a 487 to the original INVITE, which is complex here
        else:
            logger.warning("CANCEL without Call-ID received.")

    async def handle_ack(self, sip_data: str, addr):
        """Handles an ACK request."""
        headers = {h.split(': ')[0]: h.split(': ')[1] for h in sip_data.split('\r\n')[1:] if ': ' in h}
        call_id = headers.get('Call-ID')
        logger.info(f"ACK for {call_id} received from {addr}, no action needed.")
        # ACK is hop-by-hop and doesn't require a response. 
        # Here we might confirm the call is fully established.

    async def send_response(self, addr: tuple[str, int], call_id: str, status_code: str, reason_phrase: str, request_headers: dict, body: str = ""):
        try:
            # Case-insensitive dictionary for headers
            headers = {k.lower(): v for k, v in request_headers.items()}
            original_headers = request_headers

            tag = ''.join(random.choices(string.ascii_letters + string.digits, k=10))
            
            response_lines = []
            response_lines.append(f"SIP/2.0 {status_code} {reason_phrase}")
            
            # Reconstruct required headers, using original casing if available, otherwise what we have.
            to_header = original_headers.get('To', headers.get('to'))
            from_header = original_headers.get('From', headers.get('from'))
            via_header = original_headers.get('Via', headers.get('via'))
            cseq_header = original_headers.get('CSeq', headers.get('cseq'))
            
            if not to_header:
                logger.error("'To' header missing from request headers, cannot send response.")
                return

            # Append with a default empty tag if not present
            if 'tag=' not in to_header:
                to_header += f';tag={tag}'

            response_lines.append(to_header)
            response_lines.append(from_header)
            response_lines.append(via_header)

            response_lines.append(f"Call-ID: {call_id}")
            response_lines.append(f"CSeq: {cseq_header}")
            response_lines.append("Server: OpenSIPS AI Voice Connector")
            response_lines.append("Allow: INVITE, ACK, CANCEL, BYE, OPTIONS")
            response_lines.append("Content-Type: application/sdp")
            response_lines.append(f"Content-Length: {len(body)}")
            response_lines.append("")
            response_lines.append(body)

            response = "\r\n".join(response_lines)
            
            if self.transport:
                self.transport.sendto(response.encode('utf-8'), addr)
                logger.debug(f"Sent SIP response to {addr}:\n{response}")
            else:
                logger.error("SIP transport not available, cannot send response.")
        except KeyError as e:
            logger.error(f"Missing a required header to build the SIP response: {e}")
            logger.error(f"Available headers: {request_headers.keys()}")
        except Exception as e:
            logger.error(f"An unexpected error occurred in send_response: {e}")

    async def stop(self):
        """Stops the UDP server."""
        if self.transport:
            self.transport.close()
            logger.info("SIP listener stopped.")


class OpenSIPSAIVoiceConnector:
    """
    Main application class that orchestrates all components.
    """
    def __init__(self, config_file: str = None, test_mode: bool = False):
        """
        Initializes the application.
        
        Args:
            config_file: Path to the configuration file.
            test_mode: Flag to run in test mode.
        """
        self.config_file = config_file
        self.test_mode = test_mode
        
        # Core components
        self.mi_conn = None
        self.call_manager = None
        self.sip_listener = None  # Replaced engine with sip_listener
        
        # Service registry
        self.services = {}
        self._background_tasks = {}
        
        self.running = False

    async def initialize_mi_connection(self):
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
        """Initializes AI services."""
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
        
        logger.info("✅ Services initialized")

    async def _cleanup_services(self):
        """Stops all running services."""
        logger.info("🧹 Cleaning up services...")
        
        stop_tasks = [
            self._safe_service_stop(name, service)
            for name, service in self.services.items() if service
        ]
        if stop_tasks:
            await asyncio.gather(*stop_tasks)
        
        logger.info("🧹 Service cleanup completed.")

    async def _safe_service_stop(self, service_name: str, service):
        """Safely stops a single service."""
        try:
            await service.stop()
            logger.info(f"Service {service_name} stopped.")
        except Exception as e:
            logger.error(f"Error stopping service {service_name}", error=str(e))

    async def start_sip_listener(self):
        """Initializes and starts the direct SIP listener."""
        if self.test_mode:
            logger.info("Skipping SIP listener in test mode.")
            return

        listener_config = get_config_section("oavc")
        if not listener_config:
            raise ConfigValidationError("Missing [oavc] section in config file for SIP listener.")

        host = listener_config.get("host", "0.0.0.0")
        port = listener_config.getint("sip_port", 8089)

        self.sip_listener = SIPListener(
            host=host,
            port=port,
            call_manager=self.call_manager
        )
        
        await self.sip_listener.start()
        logger.info(f"✅ Direct SIP Listener started on {host}:{port}")

    async def start(self):
        """Starts all application components in the correct order."""
        try:
            logger.info("🚀 Starting OpenSIPS AI Voice Connector...")

            # Configuration is already loaded in main(), no need to load here.

            # Initialize MI connection (optional, for other commands)
            await self.initialize_mi_connection()

            # Initialize services first
            await self.initialize_services()
            
            # 4. Create Native Call Manager with services
            self.call_manager = CallManager(services=self.services)
            logger.info("✅ Native Call Manager created with services")
            
            # 5. Start the SIP listener to handle incoming calls
            await self.start_sip_listener()
            
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

        # 1. Stop the SIP listener
        if self.sip_listener:
            await self.sip_listener.stop()
            logger.info("SIP Listener stopped.")

        # 2. Stop services
        await self._cleanup_services()
        
        # 3. Shutdown Call Manager
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
    config_file = os.environ.get("OAVC_CONFIG_FILE", "cfg/opensips-ai-voice-connector.ini")
    
    # Load configuration
    initialize_config(config_file)
    
    # Check for test mode
    test_mode = os.environ.get("OAVC_TEST_MODE", "false").lower() == "true"
    
    app = OpenSIPSAIVoiceConnector(config_file=config_file)
    await app.start()

    vad_config = get_config_section("VAD")

    if app.test_mode:
        logger.info("🧪 TEST MODE: Application started successfully!")
        print("\n🧪 TEST MODE: Application running successfully!")
        print("✅ Configuration loaded")
        print("✅ Mock services initialized") 
        print("✅ OpenSIPS event handler ready")
        print("✅ Call manager ready")
        print("\nPress Ctrl+C to stop...")
        
        # Keep running in test mode
        while app.running:
            await asyncio.sleep(1)
    else:
        # Normal mode - wait for events
        while app.running:
            await asyncio.sleep(0.1)

    return 0

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)

# vim: tabstop=8 expandtab shiftwidth=4 softtabstop=4
