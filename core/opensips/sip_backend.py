"""
SIP Backend Listener for OpenSIPS AI Voice Connector
Handles INVITE requests from OpenSIPS
Based on working implementation from legacy code
"""

import asyncio
import logging
import socket
import random
import string
from typing import Dict, Any, Optional, Callable, Tuple, Set
from datetime import datetime

logger = logging.getLogger(__name__)

class SIPBackendListener:
    """
    SIP Backend Listener to handle OpenSIPS INVITE requests
    Processes SIP messages and extracts SDP information
    """
    
    def __init__(
        self,
        host: str = "0.0.0.0",
        port: int = 8089,
        on_invite_received: Optional[Callable[[Dict[str, Any]], Any]] = None
    ):
        """
        Initialize SIP backend listener
        
        Args:
            host: Listen host
            port: Listen port
            on_invite_received: Callback for INVITE processing
        """
        self.host = host
        self.port = port
        self.on_invite_received = on_invite_received
        self.transport = None
        self.protocol = None
        self._running = False
        
        # Track SIP transactions
        self._call_tags: Dict[str, str] = {}
        self._sent_responses: Set[Tuple[str, int]] = set()
        
        logger.info(f"SIP Backend Listener initialized: {host}:{port}")
    
    async def start(self):
        """Start SIP backend listener"""
        try:
            loop = asyncio.get_running_loop()
            
            class SIPProtocol(asyncio.DatagramProtocol):
                def __init__(self, handler_func):
                    self.handler_func = handler_func
                    super().__init__()
                
                def connection_made(self, transport):
                    self.transport = transport
                    logger.debug("SIP protocol connection established")
                
                def datagram_received(self, data, addr):
                    """Handle incoming SIP datagram"""
                    try:
                        logger.debug(f"SIP datagram received from {addr}, size: {len(data)}")
                        # Create async task to handle SIP message
                        asyncio.create_task(self.handler_func(data, addr))
                    except Exception as e:
                        logger.error(f"Error in SIP datagram_received: {e}")
            
            # Create UDP endpoint for SIP
            self.transport, self.protocol = await loop.create_datagram_endpoint(
                lambda: SIPProtocol(self.process_sip_message),
                local_addr=(self.host, self.port),
                reuse_port=True
            )
            
            self._running = True
            logger.info(f"SIP backend listener started on {self.host}:{self.port}")
            
        except Exception as e:
            logger.error(f"Failed to start SIP backend listener: {e}")
            raise
    
    async def stop(self):
        """Stop SIP backend listener"""
        try:
            self._running = False
            
            if self.transport:
                self.transport.close()
                self.transport = None
                self.protocol = None
            
            logger.info("SIP backend listener stopped")
            
        except Exception as e:
            logger.error(f"Error stopping SIP backend listener: {e}")
    
    def is_running(self) -> bool:
        """Check if SIP backend listener is running"""
        return self._running
    
    async def process_sip_message(self, data: bytes, addr: Tuple[str, int]):
        """Process incoming SIP message"""
        try:
            # Decode SIP message
            sip_message = data.decode('utf-8', errors='ignore')
            logger.debug(f"Processing SIP message from {addr}: {sip_message[:200]}")
            
            # Parse SIP message
            parsed_sip = self._parse_sip_message(sip_message)
            if not parsed_sip:
                logger.warning(f"Failed to parse SIP message from {addr}")
                return
            
            # Handle INVITE requests
            if parsed_sip.get('method') == 'INVITE':
                await self._handle_invite(parsed_sip, addr)
            else:
                logger.debug(f"Ignoring non-INVITE SIP method: {parsed_sip.get('method')}")
                
        except Exception as e:
            logger.error(f"Error processing SIP message: {e}")
    
    def _parse_sip_message(self, sip_message: str) -> Optional[Dict[str, Any]]:
        """Parse SIP message to extract headers and body"""
        try:
            lines = sip_message.split('\\r\\n')
            if not lines:
                return None
            
            # Parse request line
            request_line = lines[0].strip()
            parts = request_line.split(' ')
            if len(parts) < 2:
                return None
            
            method = parts[0]
            
            # Parse headers
            headers = {}
            body_start_idx = -1
            
            for i, line in enumerate(lines[1:], 1):
                line = line.strip()
                if not line:  # Empty line indicates start of body
                    body_start_idx = i + 1
                    break
                
                if ':' in line:
                    header_name, header_value = line.split(':', 1)
                    headers[header_name.strip().lower()] = header_value.strip()
            
            # Extract body (SDP)
            body = ""
            if body_start_idx > 0 and body_start_idx < len(lines):
                body = '\\r\\n'.join(lines[body_start_idx:])
            
            # Extract key information
            call_id = headers.get('call-id', f"sip_{random.randint(1000, 9999)}")
            from_header = headers.get('from', '')
            to_header = headers.get('to', '')
            
            return {
                'method': method,
                'call_id': call_id,
                'headers': headers,
                'body': body,
                'from': from_header,
                'to': to_header,
                'raw_message': sip_message
            }
            
        except Exception as e:
            logger.error(f"Error parsing SIP message: {e}")
            return None
    
    async def _handle_invite(self, sip_data: Dict[str, Any], addr: Tuple[str, int]):
        """Handle SIP INVITE request"""
        try:
            call_id = sip_data.get('call_id')
            body = sip_data.get('body', '')
            
            logger.info(f"📞 Processing SIP INVITE for call: {call_id}")
            
            # Parse SDP from body
            sdp_info = self._parse_sdp_body(body) if body else {}
            
            # Create invite data structure
            invite_data = {
                'call_id': call_id,
                'sdp_info': sdp_info,
                'sip_headers': sip_data.get('headers', {}),
                'from_addr': addr,
                'raw_sip': sip_data.get('raw_message', ''),
                'timestamp': datetime.now().isoformat()
            }
            
            logger.info(f"📞 INVITE data prepared for call: {call_id}, SDP: {sdp_info}")
            
            # Call the invite handler
            if self.on_invite_received:
                if asyncio.iscoroutinefunction(self.on_invite_received):
                    await self.on_invite_received(invite_data)
                else:
                    self.on_invite_received(invite_data)
            else:
                logger.warning(f"No INVITE handler configured for call: {call_id}")
                
        except Exception as e:
            logger.error(f"Error handling INVITE: {e}")
    
    def _parse_sdp_body(self, sdp_str: str) -> Dict[str, Any]:
        """Parse SDP body to extract media information"""
        if not sdp_str or not sdp_str.strip():
            logger.warning("Empty SDP body received")
            return {}
        
        sdp_info = {}
        lines = sdp_str.split('\\r\\n')
        
        logger.debug(f"Parsing SDP body: {len(lines)} lines")
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            if line.startswith('c=IN IP4'):
                # c=IN IP4 192.168.88.1
                parts = line.split()
                if len(parts) >= 3:
                    sdp_info['media_ip'] = parts[-1]
                    logger.debug(f"Found media IP: {parts[-1]}")
            
            elif line.startswith('m=audio'):
                # m=audio 4082 RTP/AVP 0
                parts = line.split()
                if len(parts) >= 2:
                    try:
                        sdp_info['media_port'] = int(parts[1])
                        logger.debug(f"Found media port: {parts[1]}")
                    except ValueError:
                        logger.warning(f"Invalid media port: {parts[1]}")
                
                # Determine audio format
                if ' 0' in line or (len(parts) > 3 and parts[-1] == '0'):
                    sdp_info['audio_format'] = 'PCMU'
                elif ' 8' in line or (len(parts) > 3 and parts[-1] == '8'):
                    sdp_info['audio_format'] = 'PCMA'
                else:
                    sdp_info['audio_format'] = 'PCMU'  # Default
                
                logger.debug(f"Audio format: {sdp_info.get('audio_format')}")
        
        # Add session-level info
        sdp_info['session_id'] = self._generate_session_id()
        sdp_info['raw_sdp'] = sdp_str
        
        logger.info(f"SDP parsing completed: IP={sdp_info.get('media_ip')}, "
                   f"Port={sdp_info.get('media_port')}, "
                   f"Format={sdp_info.get('audio_format')}")
        
        return sdp_info
    
    def _generate_session_id(self) -> str:
        """Generate unique session ID"""
        return ''.join(random.choices(string.ascii_letters + string.digits, k=8))
    
    async def send_200_ok(self, invite_data: Dict[str, Any], transport_mock):
        """Send 200 OK response with SDP"""
        try:
            call_id = invite_data.get('call_id')
            
            # Avoid sending duplicate responses
            response_key = (call_id, 200)
            if response_key in self._sent_responses:
                logger.debug(f"200 OK already sent for call: {call_id}")
                return
            
            # Get SDP info from transport mock
            sdp_info = transport_mock.get_sdp_info()
            
            # Generate SDP response
            sdp_response = self._generate_sdp_response(sdp_info)
            
            # Create SIP 200 OK response
            sip_response = self._create_sip_200_ok(invite_data, sdp_response)
            
            # Send response to client
            from_addr = invite_data.get('from_addr')
            if from_addr and self.transport:
                self.transport.sendto(sip_response.encode('utf-8'), from_addr)
                self._sent_responses.add(response_key)
                logger.info(f"📞 200 OK sent for call: {call_id}")
            else:
                logger.error(f"Cannot send 200 OK: no transport or address for call: {call_id}")
                
        except Exception as e:
            logger.error(f"Error sending 200 OK: {e}")
            raise
    
    async def send_400_bad_request(self, invite_data: Dict[str, Any]):
        """Send 400 Bad Request response"""
        try:
            call_id = invite_data.get('call_id')
            
            # Create SIP 400 response
            sip_response = self._create_sip_error_response(invite_data, 400, "Bad Request")
            
            # Send response
            from_addr = invite_data.get('from_addr')
            if from_addr and self.transport:
                self.transport.sendto(sip_response.encode('utf-8'), from_addr)
                logger.info(f"📞 400 Bad Request sent for call: {call_id}")
            
        except Exception as e:
            logger.error(f"Error sending 400 Bad Request: {e}")
    
    async def send_500_internal_error(self, invite_data: Dict[str, Any]):
        """Send 500 Internal Server Error response"""
        try:
            call_id = invite_data.get('call_id')
            
            # Create SIP 500 response
            sip_response = self._create_sip_error_response(invite_data, 500, "Internal Server Error")
            
            # Send response
            from_addr = invite_data.get('from_addr')
            if from_addr and self.transport:
                self.transport.sendto(sip_response.encode('utf-8'), from_addr)
                logger.info(f"📞 500 Internal Server Error sent for call: {call_id}")
            
        except Exception as e:
            logger.error(f"Error sending 500 Internal Server Error: {e}")
    
    def _generate_sdp_response(self, sdp_info: Dict[str, Any]) -> str:
        """Generate SDP response for 200 OK"""
        session_id = sdp_info.get('session_id', str(random.randint(1000000, 9999999)))
        media_ip = sdp_info.get('media_ip', '127.0.0.1')
        media_port = sdp_info.get('media_port', 5060)
        
        sdp = f"""v=0\r
o=OAVC {session_id} {session_id} IN IP4 {media_ip}\r
s=OpenSIPS AI Voice Connector\r
c=IN IP4 {media_ip}\r
t=0 0\r
m=audio {media_port} RTP/AVP 0\r
a=rtpmap:0 PCMU/8000\r
a=sendrecv\r
"""
        return sdp
    
    def _create_sip_200_ok(self, invite_data: Dict[str, Any], sdp: str) -> str:
        """Create SIP 200 OK response"""
        call_id = invite_data.get('call_id')
        headers = invite_data.get('sip_headers', {})
        
        # Generate tag if not exists
        tag = self._call_tags.get(call_id, self._generate_session_id())
        self._call_tags[call_id] = tag
        
        response = f"""SIP/2.0 200 OK\r
Via: {headers.get('via', 'SIP/2.0/UDP 127.0.0.1:5060')}\r
From: {headers.get('from', '')}\r
To: {headers.get('to', '')};tag={tag}\r
Call-ID: {call_id}\r
CSeq: {headers.get('cseq', '1 INVITE')}\r
Contact: <sip:oavc@{self.host}:{self.port}>\r
Content-Type: application/sdp\r
Content-Length: {len(sdp)}\r
\r
{sdp}"""
        
        return response
    
    def _create_sip_error_response(self, invite_data: Dict[str, Any], status_code: int, reason: str) -> str:
        """Create SIP error response"""
        call_id = invite_data.get('call_id')
        headers = invite_data.get('sip_headers', {})
        
        response = f"""SIP/2.0 {status_code} {reason}\r
Via: {headers.get('via', 'SIP/2.0/UDP 127.0.0.1:5060')}\r
From: {headers.get('from', '')}\r
To: {headers.get('to', '')}\r
Call-ID: {call_id}\r
CSeq: {headers.get('cseq', '1 INVITE')}\r
Content-Length: 0\r
\r
"""
        
        return response
    
    def get_stats(self) -> Dict[str, Any]:
        """Get SIP backend listener statistics"""
        return {
            'running': self._running,
            'listen_address': f"{self.host}:{self.port}",
            'active_calls': len(self._call_tags),
            'sent_responses': len(self._sent_responses),
            'has_invite_callback': self.on_invite_received is not None
        }