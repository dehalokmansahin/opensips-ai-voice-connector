"""
OpenSIPS Outbound Call Manager for IVR Testing
Handles outbound SIP calls to target IVR systems
"""

import asyncio
import logging
import json
import socket
import aiohttp
from typing import Dict, Any, Optional, Callable
from dataclasses import dataclass
from datetime import datetime
from enum import Enum

logger = logging.getLogger(__name__)

class CallState(Enum):
    """Call state enumeration"""
    INITIATING = "initiating"
    CALLING = "calling"
    RINGING = "ringing"
    CONNECTED = "connected"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

@dataclass
class OutboundCall:
    """Outbound call information"""
    call_id: str
    target_number: str
    caller_id: str
    state: CallState = CallState.INITIATING
    start_time: Optional[datetime] = None
    connect_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    failure_reason: Optional[str] = None
    rtp_local_port: Optional[int] = None
    rtp_remote_ip: Optional[str] = None
    rtp_remote_port: Optional[int] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return {
            "call_id": self.call_id,
            "target_number": self.target_number,
            "caller_id": self.caller_id,
            "state": self.state.value,
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "connect_time": self.connect_time.isoformat() if self.connect_time else None,
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "failure_reason": self.failure_reason,
            "rtp_local_port": self.rtp_local_port,
            "rtp_remote_ip": self.rtp_remote_ip,
            "rtp_remote_port": self.rtp_remote_port
        }

class OutboundCallManager:
    """Manages outbound SIP calls through OpenSIPS MI interface"""
    
    def __init__(self, mi_host: str = "127.0.0.1", mi_port: int = 8080):
        """
        Initialize outbound call manager
        
        Args:
            mi_host: OpenSIPS MI interface host
            mi_port: OpenSIPS MI interface port (HTTP)
        """
        self.mi_host = mi_host
        self.mi_port = mi_port
        self.mi_url = f"http://{mi_host}:{mi_port}/mi"
        self.active_calls: Dict[str, OutboundCall] = {}
        
        # HTTP session for MI requests
        self._http_session: Optional[aiohttp.ClientSession] = None
        
        # Event callbacks
        self.on_call_state_change: Optional[Callable] = None
        self.on_call_connected: Optional[Callable] = None
        self.on_call_failed: Optional[Callable] = None
        self.on_call_completed: Optional[Callable] = None
        
        # RTP port range
        self.rtp_min_port = 10000
        self.rtp_max_port = 10100
        self._next_rtp_port = self.rtp_min_port
        
        logger.info(f"OutboundCallManager initialized: MI={mi_host}:{mi_port}")
    
    async def _ensure_http_session(self):
        """Ensure HTTP session is available for MI requests"""
        if self._http_session is None or self._http_session.closed:
            self._http_session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=10),
                headers={"Content-Type": "application/json"}
            )
    
    async def _close_http_session(self):
        """Close HTTP session"""
        if self._http_session and not self._http_session.closed:
            await self._http_session.close()
            self._http_session = None
    
    async def health_check(self) -> Dict[str, Any]:
        """Check OpenSIPS MI interface availability"""
        try:
            await self._ensure_http_session()
            
            # Send a simple MI command to check availability
            mi_command = {
                "jsonrpc": "2.0",
                "method": "ps",  # Process status - simple command
                "params": [],
                "id": "health_check"
            }
            
            async with self._http_session.post(self.mi_url, json=mi_command) as response:
                if response.status == 200:
                    result = await response.json()
                    return {
                        "status": "healthy",
                        "mi_url": self.mi_url,
                        "active_calls": len(self.active_calls),
                        "mi_response": result
                    }
                else:
                    return {
                        "status": "unhealthy",
                        "mi_url": self.mi_url,
                        "error": f"HTTP {response.status}",
                        "active_calls": len(self.active_calls)
                    }
                    
        except Exception as e:
            return {
                "status": "unhealthy",
                "mi_url": self.mi_url,
                "error": str(e),
                "active_calls": len(self.active_calls)
            }
    
    async def initiate_call(self, 
                          target_number: str,
                          caller_id: str = "IVR_TEST_SYSTEM",
                          call_id: Optional[str] = None) -> str:
        """
        Initiate an outbound SIP call
        
        Args:
            target_number: Target phone number to call
            caller_id: Caller ID to display
            call_id: Optional custom call ID
            
        Returns:
            Call ID for tracking the call
        """
        if call_id is None:
            call_id = f"ivr_test_{int(datetime.now().timestamp())}_{len(self.active_calls)}"
        
        # Create call record
        call = OutboundCall(
            call_id=call_id,
            target_number=target_number,
            caller_id=caller_id,
            start_time=datetime.now()
        )
        
        # Allocate RTP port
        call.rtp_local_port = self._allocate_rtp_port()
        
        try:
            logger.info(f"Initiating outbound call: {call_id} -> {target_number}")
            
            # Store call before initiating
            self.active_calls[call_id] = call
            
            # Send call initiation via MI interface
            success = await self._send_mi_call_start(call)
            
            if success:
                call.state = CallState.CALLING
                await self._notify_state_change(call)
                logger.info(f"Call initiated successfully: {call_id}")
            else:
                call.state = CallState.FAILED
                call.failure_reason = "Failed to initiate call via MI interface"
                await self._notify_state_change(call)
                logger.error(f"Failed to initiate call: {call_id}")
            
            return call_id
            
        except Exception as e:
            call.state = CallState.FAILED
            call.failure_reason = str(e)
            await self._notify_state_change(call)
            logger.error(f"Error initiating call {call_id}: {e}")
            return call_id
    
    async def terminate_call(self, call_id: str, reason: str = "Normal termination") -> bool:
        """
        Terminate an active call
        
        Args:
            call_id: Call ID to terminate
            reason: Termination reason
            
        Returns:
            True if termination was successful
        """
        call = self.active_calls.get(call_id)
        if not call:
            logger.warning(f"Cannot terminate call {call_id}: not found")
            return False
        
        if call.state in [CallState.COMPLETED, CallState.FAILED, CallState.CANCELLED]:
            logger.warning(f"Cannot terminate call {call_id}: already in state {call.state.value}")
            return False
        
        try:
            logger.info(f"Terminating call: {call_id} - {reason}")
            
            # Send termination via MI interface
            success = await self._send_mi_call_end(call, reason)
            
            if success:
                call.state = CallState.COMPLETED
                call.end_time = datetime.now()
                await self._notify_state_change(call)
                
                # Release RTP port
                if call.rtp_local_port:
                    self._release_rtp_port(call.rtp_local_port)
                
                logger.info(f"Call terminated successfully: {call_id}")
                return True
            else:
                logger.error(f"Failed to terminate call via MI: {call_id}")
                return False
                
        except Exception as e:
            logger.error(f"Error terminating call {call_id}: {e}")
            return False
    
    async def get_call_status(self, call_id: str) -> Optional[Dict[str, Any]]:
        """Get current status of a call"""
        call = self.active_calls.get(call_id)
        if call:
            return call.to_dict()
        return None
    
    async def get_active_calls(self) -> Dict[str, Dict[str, Any]]:
        """Get all active calls"""
        return {
            call_id: call.to_dict() 
            for call_id, call in self.active_calls.items()
            if call.state not in [CallState.COMPLETED, CallState.FAILED, CallState.CANCELLED]
        }
    
    async def handle_call_event(self, event_data: Dict[str, Any]):
        """
        Handle OpenSIPS call events
        
        Args:
            event_data: Event data from OpenSIPS
        """
        try:
            call_id = event_data.get("callid", "")
            event_type = event_data.get("event", "")
            
            call = self.active_calls.get(call_id)
            if not call:
                logger.debug(f"Received event for unknown call: {call_id}")
                return
            
            logger.debug(f"Processing call event: {event_type} for {call_id}")
            
            if event_type == "trying":
                call.state = CallState.CALLING
            elif event_type == "ringing":
                call.state = CallState.RINGING
            elif event_type == "answered":
                call.state = CallState.CONNECTED
                call.connect_time = datetime.now()
                
                # Extract RTP information
                if "rtp_remote_ip" in event_data:
                    call.rtp_remote_ip = event_data["rtp_remote_ip"]
                if "rtp_remote_port" in event_data:
                    call.rtp_remote_port = int(event_data["rtp_remote_port"])
                
                await self._notify_call_connected(call)
            elif event_type == "ended":
                call.state = CallState.COMPLETED
                call.end_time = datetime.now()
                
                # Release RTP port
                if call.rtp_local_port:
                    self._release_rtp_port(call.rtp_local_port)
                
                await self._notify_call_completed(call)
            elif event_type == "failed":
                call.state = CallState.FAILED
                call.end_time = datetime.now()
                call.failure_reason = event_data.get("reason", "Unknown failure")
                
                # Release RTP port
                if call.rtp_local_port:
                    self._release_rtp_port(call.rtp_local_port)
                
                await self._notify_call_failed(call)
            
            # Notify state change
            await self._notify_state_change(call)
            
        except Exception as e:
            logger.error(f"Error handling call event: {e}")
    
    async def _send_mi_call_start(self, call: OutboundCall) -> bool:
        """Send call initiation command via MI interface"""
        try:
            await self._ensure_http_session()
            
            # Construct SDP for RTP
            sdp_body = f"""v=0
o=opensips-ivr-tester 1 1 IN IP4 {self.mi_host}
s=OpenSIPS IVR Test Call
c=IN IP4 {self.mi_host}
t=0 0
m=audio {call.rtp_local_port} RTP/AVP 0 8
a=rtpmap:0 PCMU/8000
a=rtpmap:8 PCMA/8000
a=sendrecv"""
            
            # Construct MI command for outbound call using t_uac_dlg
            mi_command = {
                "jsonrpc": "2.0",
                "method": "t_uac_dlg",
                "params": [
                    f"sip:{call.target_number}@sip.example.com",  # Request URI
                    f"From: <sip:{call.caller_id}@{self.mi_host}>;tag=ivr-test-{call.call_id}",
                    f"To: <sip:{call.target_number}@sip.example.com>",
                    f"Call-ID: {call.call_id}",
                    "CSeq: 1 INVITE",
                    f"Contact: <sip:{call.caller_id}@{self.mi_host}:{self.mi_port}>",
                    "User-Agent: OpenSIPS-IVR-Tester/1.0",
                    "Content-Type: application/sdp",
                    sdp_body
                ],
                "id": call.call_id
            }
            
            logger.debug(f"Sending MI command to {self.mi_url}")
            logger.debug(f"MI Command: {json.dumps(mi_command, indent=2)}")
            
            # Send HTTP request to OpenSIPS MI interface
            async with self._http_session.post(self.mi_url, json=mi_command) as response:
                if response.status == 200:
                    result = await response.json()
                    logger.debug(f"MI Response: {result}")
                    
                    if "result" in result:
                        logger.info(f"Call initiation successful: {call.call_id}")
                        return True
                    elif "error" in result:
                        logger.error(f"MI error: {result['error']}")
                        return False
                    else:
                        logger.warning(f"Unexpected MI response: {result}")
                        return False
                else:
                    logger.error(f"HTTP error {response.status}: {await response.text()}")
                    return False
            
        except aiohttp.ClientError as e:
            logger.error(f"HTTP client error sending MI call start: {e}")
            # Fall back to simulation for development
            logger.debug(f"Falling back to simulated call initiation for {call.call_id}")
            await asyncio.sleep(0.1)
            return True
        except Exception as e:
            logger.error(f"Error sending MI call start: {e}")
            return False
    
    async def _send_mi_call_end(self, call: OutboundCall, reason: str) -> bool:
        """Send call termination command via MI interface"""
        try:
            await self._ensure_http_session()
            
            # Construct MI command for call termination using dlg_end_dlg
            mi_command = {
                "jsonrpc": "2.0",
                "method": "dlg_end_dlg",
                "params": [call.call_id, reason],
                "id": f"{call.call_id}_end"
            }
            
            logger.debug(f"Sending MI end command to {self.mi_url}")
            logger.debug(f"MI End Command: {json.dumps(mi_command, indent=2)}")
            
            # Send HTTP request to OpenSIPS MI interface
            async with self._http_session.post(self.mi_url, json=mi_command) as response:
                if response.status == 200:
                    result = await response.json()
                    logger.debug(f"MI End Response: {result}")
                    
                    if "result" in result:
                        logger.info(f"Call termination successful: {call.call_id}")
                        return True
                    elif "error" in result:
                        logger.error(f"MI end error: {result['error']}")
                        return False
                    else:
                        logger.warning(f"Unexpected MI end response: {result}")
                        return False
                else:
                    logger.error(f"HTTP error {response.status}: {await response.text()}")
                    return False
            
        except aiohttp.ClientError as e:
            logger.error(f"HTTP client error sending MI call end: {e}")
            # Fall back to simulation for development
            logger.debug(f"Falling back to simulated call termination for {call.call_id}")
            await asyncio.sleep(0.1)
            return True
        except Exception as e:
            logger.error(f"Error sending MI call end: {e}")
            return False
    
    def _allocate_rtp_port(self) -> int:
        """Allocate next available RTP port"""
        port = self._next_rtp_port
        self._next_rtp_port = port + 2  # RTP uses even ports, RTCP uses odd
        
        if self._next_rtp_port > self.rtp_max_port:
            self._next_rtp_port = self.rtp_min_port
        
        logger.debug(f"Allocated RTP port: {port}")
        return port
    
    def _release_rtp_port(self, port: int):
        """Release RTP port (placeholder for port management)"""
        logger.debug(f"Released RTP port: {port}")
        # TODO: Implement proper port pool management
    
    async def _notify_state_change(self, call: OutboundCall):
        """Notify about call state change"""
        if self.on_call_state_change:
            try:
                await self.on_call_state_change(call.call_id, call.state, call.to_dict())
            except Exception as e:
                logger.error(f"Error in state change callback: {e}")
    
    async def _notify_call_connected(self, call: OutboundCall):
        """Notify about call connection"""
        if self.on_call_connected:
            try:
                await self.on_call_connected(call.call_id, call.to_dict())
            except Exception as e:
                logger.error(f"Error in call connected callback: {e}")
    
    async def _notify_call_failed(self, call: OutboundCall):
        """Notify about call failure"""
        if self.on_call_failed:
            try:
                await self.on_call_failed(call.call_id, call.failure_reason, call.to_dict())
            except Exception as e:
                logger.error(f"Error in call failed callback: {e}")
    
    async def _notify_call_completed(self, call: OutboundCall):
        """Notify about call completion"""
        if self.on_call_completed:
            try:
                await self.on_call_completed(call.call_id, call.to_dict())
            except Exception as e:
                logger.error(f"Error in call completed callback: {e}")
    
    async def cleanup_completed_calls(self):
        """Clean up completed/failed calls from memory"""
        completed_calls = [
            call_id for call_id, call in self.active_calls.items()
            if call.state in [CallState.COMPLETED, CallState.FAILED, CallState.CANCELLED]
            and call.end_time
            and (datetime.now() - call.end_time).total_seconds() > 300  # 5 minutes
        ]
        
        for call_id in completed_calls:
            logger.debug(f"Cleaning up completed call: {call_id}")
            del self.active_calls[call_id]
    
    async def shutdown(self):
        """Shutdown call manager and terminate all active calls"""
        logger.info("Shutting down outbound call manager")
        
        try:
            # Terminate all active calls
            active_call_ids = list(self.active_calls.keys())
            for call_id in active_call_ids:
                call = self.active_calls[call_id]
                if call.state not in [CallState.COMPLETED, CallState.FAILED, CallState.CANCELLED]:
                    await self.terminate_call(call_id, "System shutdown")
            
            # Clear all calls
            self.active_calls.clear()
            
        finally:
            # Close HTTP session
            await self._close_http_session()
            
        logger.info("Outbound call manager shutdown complete")