"""
OpenSIPS Integration Layer for AI Voice Connector
Handles SIP/RTP communication and OpenSIPS event processing
"""

import asyncio
import logging
import socket
from typing import Dict, Any, Optional, Callable
from dataclasses import dataclass

from .event_listener import OpenSIPSEventListener
from .sip_backend import SIPBackendListener
from .rtp_transport import RTPTransport
from ..config.settings import OpenSIPSConfig

logger = logging.getLogger(__name__)

@dataclass
class CallInfo:
    """Call information structure"""
    call_id: str
    client_ip: str
    client_port: int
    bind_ip: str = "0.0.0.0"
    bind_port: int = 0
    sdp_info: Optional[Dict[str, Any]] = None

class OpenSIPSIntegration:
    """
    OpenSIPS Integration Layer
    Coordinates event listening, SIP handling, and RTP transport
    """
    
    def __init__(
        self,
        settings: OpenSIPSConfig,
        pipeline_manager,
        on_call_start: Optional[Callable] = None,
        on_call_end: Optional[Callable] = None
    ):
        self.settings = settings
        self.pipeline_manager = pipeline_manager
        self.on_call_start = on_call_start
        self.on_call_end = on_call_end
        
        # Components
        self.event_listener: Optional[OpenSIPSEventListener] = None
        self.sip_backend: Optional[SIPBackendListener] = None
        self.active_calls: Dict[str, CallInfo] = {}
        self.rtp_transports: Dict[str, RTPTransport] = {}
        
        # State
        self._running = False
        self._tasks = []
        
    async def initialize(self):
        """Initialize OpenSIPS integration components"""
        try:
            logger.info("Initializing OpenSIPS integration")
            
            # Initialize event listener
            self.event_listener = OpenSIPSEventListener(
                opensips_host=self.settings.host,
                opensips_port=self.settings.mi_port,
                on_call_start=self._on_opensips_call_start,
                on_call_end=self._on_opensips_call_end,
                on_call_event=self._on_opensips_call_event
            )
            
            # Initialize SIP backend listener
            self.sip_backend = SIPBackendListener(
                listen_host=self.settings.sip_listen_host,
                listen_port=self.settings.sip_listen_port,
                on_invite=self._on_sip_invite,
                on_bye=self._on_sip_bye,
                on_ack=self._on_sip_ack
            )
            
            logger.info("OpenSIPS integration initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize OpenSIPS integration: {e}")
            raise
    
    async def start(self):
        """Start OpenSIPS integration"""
        try:
            logger.info("Starting OpenSIPS integration")
            self._running = True
            
            # Start event listener
            if self.event_listener:
                event_task = asyncio.create_task(self.event_listener.start())
                self._tasks.append(event_task)
            
            # Start SIP backend
            if self.sip_backend:
                sip_task = asyncio.create_task(self.sip_backend.start())
                self._tasks.append(sip_task)
            
            logger.info("OpenSIPS integration started successfully")
            
        except Exception as e:
            logger.error(f"Failed to start OpenSIPS integration: {e}")
            self._running = False
            raise
    
    async def stop(self):
        """Stop OpenSIPS integration"""
        try:
            logger.info("Stopping OpenSIPS integration")
            self._running = False
            
            # Stop all active calls
            for call_id in list(self.active_calls.keys()):
                await self._cleanup_call(call_id)
            
            # Stop components
            if self.event_listener:
                await self.event_listener.stop()
            
            if self.sip_backend:
                await self.sip_backend.stop()
            
            # Cancel tasks
            for task in self._tasks:
                if not task.done():
                    task.cancel()
                    try:
                        await task
                    except asyncio.CancelledError:
                        pass
            
            self._tasks.clear()
            logger.info("OpenSIPS integration stopped successfully")
            
        except Exception as e:
            logger.error(f"Error stopping OpenSIPS integration: {e}")
    
    def is_running(self) -> bool:
        """Check if integration is running"""
        return self._running
    
    async def _on_opensips_call_start(self, call_data: Dict[str, Any]):
        """Handle call start event from OpenSIPS"""
        try:
            call_id = call_data.get('call_id')
            client_ip = call_data.get('client_ip', '127.0.0.1')
            client_port = call_data.get('client_port', 5060)
            
            if not call_id:
                call_id = f"call_{int(asyncio.get_event_loop().time())}"
                
            logger.info(f"OpenSIPS call start: {call_id} from {client_ip}:{client_port}")
            
            # Create call info
            call_info = CallInfo(
                call_id=call_id,
                client_ip=client_ip,
                client_port=int(client_port),
                sdp_info=call_data.get('sdp_info')
            )
            
            self.active_calls[call_id] = call_info
            
            # Setup RTP transport (basic implementation)
            await self._setup_rtp_transport(call_info)
            
            # Notify application
            if self.on_call_start:
                await self.on_call_start(call_info.__dict__)
                
        except Exception as e:
            logger.error(f"Error handling OpenSIPS call start: {e}")
    
    async def _on_opensips_call_end(self, call_data: Dict[str, Any]):
        """Handle call end event from OpenSIPS"""
        try:
            call_id = call_data.get('call_id', 'unknown')
            
            logger.info(f"OpenSIPS call end: {call_id}")
            
            # Cleanup call
            await self._cleanup_call(call_id)
            
            # Notify application
            if self.on_call_end:
                await self.on_call_end({'call_id': call_id})
                
        except Exception as e:
            logger.error(f"Error handling OpenSIPS call end: {e}")
    
    async def _on_opensips_call_event(self, event_data: Dict[str, Any]):
        """Handle generic call event from OpenSIPS"""
        try:
            event_type = event_data.get('event_type')
            call_id = event_data.get('call_id')
            
            logger.debug(f"OpenSIPS call event: {event_type} for {call_id}")
            
            # Handle specific event types (basic implementation)
            if event_type == 'dtmf':
                await self._handle_dtmf_event(call_id, event_data)
            elif event_type == 'rtp_timeout':
                await self._handle_rtp_timeout(call_id, event_data)
            
        except Exception as e:
            logger.error(f"Error handling OpenSIPS call event: {e}")
    
    async def _setup_rtp_transport(self, call_info: CallInfo):
        """Setup RTP transport for call (basic implementation)"""
        try:
            # Find available port
            bind_port = 10000  # Basic implementation - use fixed port range
            for port in range(10000, 10100):
                try:
                    test_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                    test_sock.bind(('0.0.0.0', port))
                    test_sock.close()
                    bind_port = port
                    break
                except OSError:
                    continue
            
            call_info.bind_port = bind_port
            
            rtp_transport = RTPTransport(
                bind_ip=call_info.bind_ip,
                bind_port=call_info.bind_port,
                remote_ip=call_info.client_ip,
                remote_port=call_info.client_port
            )
            
            await rtp_transport.start()
            self.rtp_transports[call_info.call_id] = rtp_transport
            
            logger.info(f"RTP transport setup for call {call_info.call_id}: {bind_port}")
            
        except Exception as e:
            logger.error(f"Failed to setup RTP transport for {call_info.call_id}: {e}")
            raise
    
    async def _cleanup_call(self, call_id: str):
        """Cleanup call resources"""
        try:
            # Stop RTP transport
            if call_id in self.rtp_transports:
                await self.rtp_transports[call_id].stop()
                del self.rtp_transports[call_id]
            
            # Remove call info
            if call_id in self.active_calls:
                del self.active_calls[call_id]
            
            logger.info(f"Call {call_id} cleaned up")
            
        except Exception as e:
            logger.error(f"Error cleaning up call {call_id}: {e}")
    
    async def _on_sip_invite(self, sip_data: Dict[str, Any]):
        """Handle SIP INVITE message (basic implementation)"""
        try:
            call_id = sip_data.get('call_id', f"invite_{int(asyncio.get_event_loop().time())}")
            logger.info(f"SIP INVITE received for call {call_id}")
            
            # Basic SIP INVITE processing
            # In production: parse SDP, negotiate codec, respond with 200 OK
            
        except Exception as e:
            logger.error(f"Error handling SIP INVITE: {e}")
    
    async def _on_sip_bye(self, sip_data: Dict[str, Any]):
        """Handle SIP BYE message"""
        try:
            call_id = sip_data.get('call_id')
            logger.info(f"SIP BYE received for call {call_id}")
            
            # Cleanup call
            if call_id:
                await self._cleanup_call(call_id)
            
        except Exception as e:
            logger.error(f"Error handling SIP BYE: {e}")
    
    async def _on_sip_ack(self, sip_data: Dict[str, Any]):
        """Handle SIP ACK message"""
        try:
            call_id = sip_data.get('call_id')
            logger.debug(f"SIP ACK received for call {call_id}")
            
        except Exception as e:
            logger.error(f"Error handling SIP ACK: {e}")
    
    async def _handle_dtmf_event(self, call_id: str, event_data: Dict[str, Any]):
        """Handle DTMF event (basic implementation)"""
        try:
            dtmf_digit = event_data.get('digit')
            logger.info(f"DTMF received for call {call_id}: {dtmf_digit}")
            
        except Exception as e:
            logger.error(f"Error handling DTMF event: {e}")
    
    async def _handle_rtp_timeout(self, call_id: str, event_data: Dict[str, Any]):
        """Handle RTP timeout event"""
        try:
            logger.warning(f"RTP timeout for call {call_id}")
            
        except Exception as e:
            logger.error(f"Error handling RTP timeout: {e}")
    
    def get_call_info(self, call_id: str) -> Optional[CallInfo]:
        """Get call information"""
        return self.active_calls.get(call_id)
    
    def get_rtp_transport(self, call_id: str) -> Optional[RTPTransport]:
        """Get RTP transport for call"""
        return self.rtp_transports.get(call_id)
    
    def get_active_calls(self) -> Dict[str, CallInfo]:
        """Get all active calls"""
        return self.active_calls.copy()
    
    async def health_check(self) -> Dict[str, Any]:
        """Check integration health"""
        try:
            health_status = {
                'running': self._running,
                'active_calls': len(self.active_calls),
                'rtp_transports': len(self.rtp_transports),
                'components': {}
            }
            
            # Check components
            if self.event_listener:
                health_status['components']['event_listener'] = True  # Basic implementation
            
            if self.sip_backend:
                health_status['components']['sip_backend'] = True  # Basic implementation
            
            return health_status
            
        except Exception as e:
            logger.error(f"OpenSIPS integration health check failed: {e}")
            return {
                'running': False,
                'error': str(e),
                'active_calls': 0
            }