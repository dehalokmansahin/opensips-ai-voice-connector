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
        
        # Active calls tracking
        self.active_calls: Dict[str, CallInfo] = {}
        self.active_transports: Dict[str, RTPTransport] = {}
        
        # State
        self._is_running = False
        
    async def initialize(self):
        """Initialize OpenSIPS integration components"""
        try:
            # Initialize event listener
            await self._initialize_event_listener()
            
            # Initialize SIP backend listener
            await self._initialize_sip_backend()
            
            logger.info("OpenSIPS integration initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize OpenSIPS integration: {e}")
            raise
    
    async def _initialize_event_listener(self):
        """Initialize OpenSIPS event listener"""
        try:
            self.event_listener = OpenSIPSEventListener(
                host=self.settings.event_ip,
                port=self.settings.event_port,
                on_call_start=self._handle_call_start_event,
                on_call_end=self._handle_call_end_event
            )
            
            logger.info(f"Event listener initialized: {self.settings.event_ip}:{self.settings.event_port}")
            
        except Exception as e:
            logger.error(f"Failed to initialize event listener: {e}")
            raise
    
    async def _initialize_sip_backend(self):
        """Initialize SIP backend listener"""
        try:
            self.sip_backend = SIPBackendListener(
                host=self.settings.sip_ip,
                port=self.settings.sip_port,
                on_invite_received=self._handle_sip_invite
            )
            
            logger.info(f"SIP backend initialized: {self.settings.sip_ip}:{self.settings.sip_port}")
            
        except Exception as e:
            logger.error(f"Failed to initialize SIP backend: {e}")
            raise
    
    async def _handle_call_start_event(self, event_data: Dict[str, Any]):
        """Handle call start event from OpenSIPS"""
        try:
            call_id = event_data.get('call_id', f"call_{id(event_data)}")
            logger.info(f"📞 Call start event received: {call_id}")
            
            # Store event data for correlation with SIP INVITE
            if call_id not in self.active_calls:
                call_info = CallInfo(
                    call_id=call_id,
                    client_ip="",
                    client_port=0
                )
                self.active_calls[call_id] = call_info
            
            # Notify application
            if self.on_call_start:
                await self.on_call_start(event_data)
                
        except Exception as e:
            logger.error(f"Error handling call start event: {e}")
    
    async def _handle_call_end_event(self, event_data: Dict[str, Any]):
        """Handle call end event from OpenSIPS"""
        try:
            call_id = event_data.get('call_id', 'unknown')
            logger.info(f"📞 Call end event received: {call_id}")
            
            # Clean up call
            await self._cleanup_call(call_id)
            
            # Notify application
            if self.on_call_end:
                await self.on_call_end(event_data)
                
        except Exception as e:
            logger.error(f"Error handling call end event: {e}")
    
    async def _handle_sip_invite(self, invite_data: Dict[str, Any]):
        """Handle SIP INVITE request"""
        try:
            call_id = invite_data.get('call_id', f"call_{id(invite_data)}")
            sdp_info = invite_data.get('sdp_info')
            
            logger.info(f"📞 SIP INVITE received for call: {call_id}")
            
            if not sdp_info or not sdp_info.get('media_ip') or not sdp_info.get('media_port'):
                logger.error(f"Invalid SDP info in INVITE: {sdp_info}")
                await self.sip_backend.send_400_bad_request(invite_data)
                return
            
            # Extract media information
            client_ip = sdp_info['media_ip']
            client_port = int(sdp_info['media_port'])
            
            # Find available RTP port
            bind_port = self._find_available_rtp_port()
            if bind_port == 0:
                logger.error("No available RTP ports")
                await self.sip_backend.send_500_internal_error(invite_data)
                return
            
            # Create or update call info
            call_info = CallInfo(
                call_id=call_id,
                client_ip=client_ip,
                client_port=client_port,
                bind_ip=self.settings.rtp_bind_ip,
                bind_port=bind_port,
                sdp_info=sdp_info
            )
            
            self.active_calls[call_id] = call_info
            
            # Create RTP transport
            rtp_transport = await self._create_rtp_transport(call_info)
            if not rtp_transport:
                logger.error(f"Failed to create RTP transport for call: {call_id}")
                await self.sip_backend.send_500_internal_error(invite_data)
                return
            
            self.active_transports[call_id] = rtp_transport
            
            # Start conversation pipeline
            success = await self._start_conversation_pipeline(call_info, rtp_transport)
            if not success:
                logger.error(f"Failed to start conversation pipeline for call: {call_id}")
                await self.sip_backend.send_500_internal_error(invite_data)
                await self._cleanup_call(call_id)
                return
            
            # Send 200 OK response
            await self._send_200_ok(invite_data, call_info)
            
            logger.info(f"📞 Call setup completed successfully: {call_id}")
            
        except Exception as e:
            logger.error(f"Error handling SIP INVITE: {e}")
            try:
                await self.sip_backend.send_500_internal_error(invite_data)
            except:
                pass
    
    def _find_available_rtp_port(self) -> int:
        """Find available RTP port in configured range"""
        for port in range(self.settings.rtp_min_port, self.settings.rtp_max_port + 1):
            try:
                test_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                test_sock.bind((self.settings.rtp_bind_ip, port))
                test_sock.close()
                return port
            except OSError:
                continue
        
        logger.warning("No available RTP ports found, using auto-assign")
        return 0
    
    async def _create_rtp_transport(self, call_info: CallInfo) -> Optional[RTPTransport]:
        """Create RTP transport for call"""
        try:
            rtp_transport = RTPTransport(
                bind_ip=call_info.bind_ip,
                bind_port=call_info.bind_port,
                remote_ip=call_info.client_ip,
                remote_port=call_info.client_port
            )
            
            await rtp_transport.start()
            logger.info(f"RTP transport created: {call_info.bind_ip}:{call_info.bind_port} <-> {call_info.client_ip}:{call_info.client_port}")
            
            return rtp_transport
            
        except Exception as e:
            logger.error(f"Failed to create RTP transport: {e}")
            return None
    
    async def _start_conversation_pipeline(self, call_info: CallInfo, rtp_transport: RTPTransport) -> bool:
        """Start conversation pipeline for call"""
        try:
            # Create pipeline session
            session = await self.pipeline_manager.create_session(
                call_id=call_info.call_id,
                rtp_transport=rtp_transport,
                call_info=call_info
            )
            
            if session:
                logger.info(f"Conversation pipeline started for call: {call_info.call_id}")
                return True
            else:
                logger.error(f"Failed to create pipeline session for call: {call_info.call_id}")
                return False
                
        except Exception as e:
            logger.error(f"Error starting conversation pipeline: {e}")
            return False
    
    async def _send_200_ok(self, invite_data: Dict[str, Any], call_info: CallInfo):
        """Send 200 OK response with SDP"""
        try:
            # Create SDP response
            bot_sdp = {
                'media_ip': call_info.bind_ip,
                'media_port': call_info.bind_port,
                'session_id': call_info.call_id
            }
            
            # Create mock transport for response
            class MockTransport:
                def get_sdp_info(self):
                    return bot_sdp
            
            await self.sip_backend.send_200_ok(invite_data, MockTransport())
            logger.info(f"200 OK sent for call: {call_info.call_id}")
            
        except Exception as e:
            logger.error(f"Error sending 200 OK: {e}")
            raise
    
    async def _cleanup_call(self, call_id: str):
        """Clean up call resources"""
        try:
            # Stop RTP transport
            if call_id in self.active_transports:
                transport = self.active_transports[call_id]
                await transport.stop()
                del self.active_transports[call_id]
                logger.info(f"RTP transport cleaned up for call: {call_id}")
            
            # Remove call info
            if call_id in self.active_calls:
                del self.active_calls[call_id]
                logger.info(f"Call info cleaned up: {call_id}")
            
            # Notify pipeline manager
            await self.pipeline_manager.cleanup_session(call_id)
            
        except Exception as e:
            logger.error(f"Error cleaning up call {call_id}: {e}")
    
    async def start(self):
        """Start OpenSIPS integration"""
        try:
            logger.info("Starting OpenSIPS integration")
            
            # Start SIP backend listener
            if self.sip_backend:
                await self.sip_backend.start()
            
            # Start event listener
            if self.event_listener:
                await self.event_listener.start()
            
            self._is_running = True
            logger.info("OpenSIPS integration started successfully")
            
        except Exception as e:
            logger.error(f"Failed to start OpenSIPS integration: {e}")
            raise
    
    async def stop(self):
        """Stop OpenSIPS integration"""
        try:
            logger.info("Stopping OpenSIPS integration")
            
            self._is_running = False
            
            # Clean up all active calls
            for call_id in list(self.active_calls.keys()):
                await self._cleanup_call(call_id)
            
            # Stop event listener
            if self.event_listener:
                await self.event_listener.stop()
            
            # Stop SIP backend
            if self.sip_backend:
                await self.sip_backend.stop()
            
            logger.info("OpenSIPS integration stopped")
            
        except Exception as e:
            logger.error(f"Error stopping OpenSIPS integration: {e}")
    
    def is_running(self) -> bool:
        """Check if integration is running"""
        return self._is_running
    
    def get_call_info(self, call_id: str) -> Optional[CallInfo]:
        """Get call information"""
        return self.active_calls.get(call_id)
    
    def get_active_calls(self) -> Dict[str, CallInfo]:
        """Get all active calls"""
        return self.active_calls.copy()
    
    def get_status(self) -> Dict[str, Any]:
        """Get integration status"""
        return {
            'running': self._is_running,
            'active_calls': len(self.active_calls),
            'active_transports': len(self.active_transports),
            'event_listener_running': self.event_listener.is_running() if self.event_listener else False,
            'sip_backend_running': self.sip_backend.is_running() if self.sip_backend else False,
            'settings': {
                'event_endpoint': f"{self.settings.event_ip}:{self.settings.event_port}",
                'sip_endpoint': f"{self.settings.sip_ip}:{self.settings.sip_port}",
                'rtp_range': f"{self.settings.rtp_min_port}-{self.settings.rtp_max_port}"
            }
        }