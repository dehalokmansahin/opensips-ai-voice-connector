#!/usr/bin/env python3
"""
SIP Backend Listener - Handles INVITE requests from OpenSIPS
Based on the working SIP listener from the old main.py implementation
"""

import asyncio
import socket
import structlog
import random
import string
from typing import Dict, Any, Optional, Callable, Awaitable
from datetime import datetime

logger = structlog.get_logger()


class SIPBackendListener:
    """
    SIP Backend Listener to handle OpenSIPS INVITE requests
    Based on the working SIPListener class from old main.py
    """
    
    def __init__(
        self, 
        host: str = "0.0.0.0", 
        port: int = 8089,
        on_invite_received: Optional[Callable[[Dict[str, Any]], Awaitable[None]]] = None
    ):
        """
        Initialize SIP backend listener
        
        Args:
            host: Listen host
            port: Listen port (default 8089 for OAVC backend)
            on_invite_received: Callback for INVITE processing
        """
        self.host = host
        self.port = port
        self.on_invite_received = on_invite_received
        self.transport = None
        self.protocol = None
        self.running = False
        
        # Track SIP transactions to avoid duplicate responses (from old code)
        self._call_tags = {}  # call_id -> tag mapping
        self._sent_responses = set()  # track (call_id, status_code) to avoid duplicates
        
        logger.info("SIP Backend Listener initialized", 
                   host=host, port=port)
    
    def _parse_sdp_body(self, sdp_str: str) -> dict:
        """
        Parse SDP body - using the exact working logic from old main.py
        """
        if not sdp_str or not sdp_str.strip():
            logger.warning("Empty SDP body received")
            return {}
            
        sdp_info = {}
        lines = sdp_str.split('\r\n')
        
        logger.debug("Parsing SDP body", num_lines=len(lines), sdp_preview=sdp_str[:100])
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
                
            if line.startswith('c=IN IP4'):
                # c=IN IP4 192.168.88.1
                parts = line.split()
                if len(parts) >= 3:
                    sdp_info['media_ip'] = parts[-1]
                    logger.debug("Found media IP in SDP", media_ip=parts[-1])
                    
            elif line.startswith('m=audio'):
                # m=audio 4082 RTP/AVP 0
                parts = line.split()
                if len(parts) >= 2:
                    try:
                        sdp_info['media_port'] = int(parts[1])
                        logger.debug("Found media port in SDP", media_port=parts[1])
                    except ValueError:
                        logger.warning("Invalid media port in SDP", port_str=parts[1])
                        
                # Check audio format (payload type)
                if ' 0' in line or parts[-1] == '0':
                    sdp_info['audio_format'] = 'PCMU'
                elif ' 8' in line or parts[-1] == '8':
                    sdp_info['audio_format'] = 'PCMA'
                else:
                    sdp_info['audio_format'] = 'PCMU'  # Default fallback
                    
                logger.debug("Found audio format in SDP", audio_format=sdp_info.get('audio_format'))
        
        logger.info("SDP parsing completed", 
                   media_ip=sdp_info.get('media_ip'),
                   media_port=sdp_info.get('media_port'),
                   audio_format=sdp_info.get('audio_format'),
                   valid=bool(sdp_info.get('media_port')))
        
        return sdp_info

    async def start(self):
        """Start the SIP backend listener - using working pattern from old code"""
        try:
            loop = asyncio.get_running_loop()

            class SIPProtocol(asyncio.DatagramProtocol):
                def __init__(self, handler_func):
                    self.handler_func = handler_func
                    super().__init__()
                    
                def connection_made(self, transport):
                    self.transport = transport
                    logger.debug("SIP Backend Protocol: connection established")
                    
                def datagram_received(self, data, addr):
                    """Handle incoming SIP datagram"""
                    try:
                        sip_data = data.decode('utf-8')
                        logger.debug("SIP Backend Protocol: datagram received", 
                                    from_addr=addr, size=len(data))
                        # Create async task to handle the message
                        asyncio.create_task(self.handler_func(sip_data, addr))
                    except Exception as e:
                        logger.error("Error in datagram_received", error=str(e))
                    
            self.transport, self.protocol = await loop.create_datagram_endpoint(
                lambda: SIPProtocol(self.handle_sip_message),
                local_addr=(self.host, self.port),
            )
            
            self.running = True
            
            logger.info("✅ SIP Backend Listener started", 
                       host=self.host, port=self.port)
            logger.debug("SIP Backend Listener: UDP transport connected", 
                        local_addr=self.transport.get_extra_info('sockname'))
            
        except Exception as e:
            logger.error("Failed to start SIP Backend Listener", error=str(e))
            raise

    async def stop(self):
        """Stop the SIP backend listener"""
        try:
            self.running = False
            if self.transport:
                self.transport.close()
                self.transport = None
                self.protocol = None
                
            logger.info("✅ SIP Backend Listener stopped")
            
        except Exception as e:
            logger.error("Error stopping SIP Backend Listener", error=str(e))

    async def handle_sip_message(self, sip_data: str, addr):
        """
        Handle incoming SIP message - using old main.py logic
        """
        try:
            logger.debug("SIP Backend Listener: received UDP packet", 
                        from_addr=addr, size=len(sip_data))
            logger.debug("📞 SIP Backend Listener: received SIP message", 
                        from_addr=addr, size=len(sip_data))
            logger.debug("SIP message preview", content=sip_data[:200])
            
            lines = sip_data.split('\r\n')
            if not lines:
                logger.warning("Empty SIP message received")
                return
                
            request_line = lines[0]
            
            try:
                parts = request_line.split()
                if len(parts) < 3:
                    logger.warning("Malformed SIP request line", request_line=request_line)
                    return
                    
                method, uri, version = parts[0], parts[1], parts[2]
                
                logger.info("📞 SIP INVITE received", 
                           from_addr=addr, method=method, uri=uri)
                
            except ValueError:
                logger.warning("Failed to parse SIP request line", request_line=request_line)
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
                logger.info("Received unhandled SIP method", method=method)
                # Send a 405 Method Not Allowed if we can parse headers
                headers = self._parse_headers(lines)
                call_id = headers.get('Call-ID')
                if call_id:
                    await self.send_response(addr, call_id, '405', 'Method Not Allowed', headers)
                
        except Exception as e:
            logger.error("Error handling SIP message", error=str(e), exc_info=True)

    def _parse_headers(self, lines):
        """Parse SIP headers from lines"""
        headers = {}
        for line in lines[1:]:  # Skip request line
            if ': ' in line:
                key, value = line.split(': ', 1)
                headers[key] = value
        return headers

    async def handle_invite(self, sip_data: str, addr):
        """Handle INVITE request - using exact old main.py logic"""
        try:
            logger.info("Handling INVITE from OpenSIPS", from_addr=addr)
            
            # Split headers and SDP body
            parts = sip_data.split('\r\n\r\n')
            header_str = parts[0]
            sdp_body = parts[1] if len(parts) > 1 else ""
            
            # Parse headers with proper handling (from old code)
            headers = {}
            original_headers = {}
            
            lines = header_str.split('\r\n')
            last_key = None
            
            for line in lines[1:]:  # Skip first line (request line)
                if line.startswith((' ', '\t')) and last_key:
                    # Handle header continuation
                    if last_key in original_headers:
                        original_headers[last_key] += ' ' + line.lstrip()
                        headers[last_key.lower()] += ' ' + line.lstrip()
                elif ': ' in line:
                    key, value = line.split(': ', 1)
                    last_key = key
                    
                    # Store with original casing
                    original_headers[key] = value
                    headers[key.lower()] = value

            call_id = headers.get('call-id')
            to_header_str = headers.get('to')

            if not call_id:
                logger.error("INVITE without Call-ID, cannot process")
                return

            # Check for re-INVITE
            if 'tag=' in (to_header_str or ""):
                logger.info("Re-INVITE received, not currently supported", call_id=call_id)
                await self.send_response(addr, call_id, '481', 'Call/Transaction Does Not Exist', original_headers, sip_data=sip_data)
                return
                
            # Parse SDP body
            logger.debug("Parsing SDP body", sdp_size=len(sdp_body))
            sdp_info = self._parse_sdp_body(sdp_body)
            
            if not sdp_info or not sdp_info.get('media_port'):
                logger.warning("INVITE without valid SDP media info", sdp_info=sdp_info)
                await self.send_response(addr, call_id, '400', 'Bad Request - No Media Port', original_headers, sip_data=sip_data)
                return
                
            logger.info("Processing INVITE with valid SDP", 
                       call_id=call_id,
                       media_ip=sdp_info.get('media_ip'),
                       media_port=sdp_info.get('media_port'))
            
            # Send 100 Trying immediately
            await self.send_response(addr, call_id, '100', 'Trying', original_headers, sip_data=sip_data)
            
            # Prepare data for callback
            invite_data = {
                'call_id': call_id,
                'from': headers.get('from'),
                'to': headers.get('to'),
                'sdp': sdp_body,
                'sdp_info': sdp_info,
                'headers': original_headers,
                'addr': addr,
                'sip_data': sip_data
            }
            
            # Call the callback if available
            if self.on_invite_received:
                await self.on_invite_received(invite_data)
            else:
                # Default: send 500 if no handler
                await self.send_response(addr, call_id, '500', 'Internal Server Error', original_headers, sip_data=sip_data)
                
        except Exception as e:
            logger.error("Error handling INVITE", error=str(e), exc_info=True)
            # Try to send 500 if we have minimal info
            try:
                headers = self._parse_headers(sip_data.split('\r\n'))
                call_id = headers.get('Call-ID')
                if call_id:
                    await self.send_response(addr, call_id, '500', 'Internal Server Error', headers)
            except:
                pass

    async def handle_ack(self, sip_data: str, addr):
        """Handle ACK message - critical for RTP flow!"""
        try:
            logger.info("✅ SIP Backend Listener: ACK RECEIVED", from_addr=addr)
            logger.debug("ACK message content", content=sip_data[:200])
            
            # Parse headers
            lines = sip_data.strip().split('\r\n')
            if not lines:
                logger.warning("Empty ACK message")
                return
            
            headers = {}
            for line in lines[1:]:
                if not line.strip():
                    break
                if ': ' in line:
                    key, value = line.split(': ', 1)
                    headers[key] = value
            
            call_id = headers.get('Call-ID')
            if call_id:
                logger.info("🎯 ACK processed successfully - RTP should start now!", 
                           call_id=call_id)
            else:
                logger.warning("ACK without Call-ID")
                
        except Exception as e:
            logger.error("Error handling ACK", error=str(e), exc_info=True)

    async def handle_bye(self, sip_data: str, addr):
        """Handle BYE request"""
        try:
            headers = self._parse_headers(sip_data.split('\r\n'))
            call_id = headers.get('Call-ID')
            
            logger.info("Handling BYE", call_id=call_id, from_addr=addr)
            
            if call_id:
                # Send 200 OK for BYE
                await self.send_response(addr, call_id, '200', 'OK', headers, sip_data=sip_data)
                
                # Cleanup tracking for this call
                self._call_tags.pop(call_id, None)
                # Remove all responses for this call from tracking
                self._sent_responses = {r for r in self._sent_responses if not r.startswith(f"{call_id}_")}
                logger.debug("Cleaned up tracking for call", call_id=call_id)
            else:
                logger.warning("BYE without Call-ID received")
                
        except Exception as e:
            logger.error("Error handling BYE", error=str(e), exc_info=True)

    async def handle_cancel(self, sip_data: str, addr):
        """Handle CANCEL request"""
        try:
            headers = self._parse_headers(sip_data.split('\r\n'))
            call_id = headers.get('Call-ID')
            
            logger.info("Handling CANCEL", call_id=call_id, from_addr=addr)
            
            if call_id:
                # Send 200 OK for CANCEL
                await self.send_response(addr, call_id, '200', 'OK', headers, sip_data=sip_data)
                
                # Cleanup tracking for this call
                self._call_tags.pop(call_id, None)
                # Remove all responses for this call from tracking
                self._sent_responses = {r for r in self._sent_responses if not r.startswith(f"{call_id}_")}
                logger.debug("Cleaned up tracking for call", call_id=call_id)
            else:
                logger.warning("CANCEL without Call-ID received")
                
        except Exception as e:
            logger.error("Error handling CANCEL", error=str(e), exc_info=True)

    async def send_response(self, addr: tuple, call_id: str, status_code: str, reason_phrase: str, request_headers: dict, body: str = "", sip_data: str = ""):
        """Send SIP response - using exact old main.py logic"""
        try:
            # Check for duplicate response (same call_id + status_code)
            response_key = f"{call_id}_{status_code}"
            if response_key in self._sent_responses:
                logger.debug("Skipping duplicate response", 
                           status_code=status_code, call_id=call_id)
                return
            
            # Case-insensitive dictionary for headers
            headers = {k.lower(): v for k, v in request_headers.items()}
            original_headers = request_headers

            # Get or create consistent tag for this call
            if call_id not in self._call_tags:
                self._call_tags[call_id] = ''.join(random.choices(string.ascii_letters + string.digits, k=10))
            tag = self._call_tags[call_id]
            
            response_lines = []
            response_lines.append(f"SIP/2.0 {status_code} {reason_phrase}")
            
            # Reconstruct required headers
            to_header = original_headers.get('To', headers.get('to'))
            from_header = original_headers.get('From', headers.get('from'))
            cseq_header = original_headers.get('CSeq', headers.get('cseq'))
            
            if not to_header:
                logger.error("'To' header missing from request headers, cannot send response")
                return

            # Append tag if not present
            if 'tag=' not in to_header:
                to_header += f';tag={tag}'

            # Add headers with proper formatting
            response_lines.append(f"To: {to_header}")
            response_lines.append(f"From: {from_header}")
            
            # Extract Via headers from raw SIP properly
            via_headers_added = False
            if sip_data:
                # Extract all Via headers from raw SIP message
                sip_lines = sip_data.split('\r\n')
                for line in sip_lines:
                    if line.lower().startswith('via:'):
                        # Add Via header exactly as it appears in original request
                        response_lines.append(line)
                        via_headers_added = True
                
                if via_headers_added:
                    logger.debug("Extracted Via headers from raw SIP message")
            
            # Fallback to original method if raw extraction failed
            if not via_headers_added:
                via_header = original_headers.get('Via', headers.get('via'))
                if via_header:
                    if isinstance(via_header, list):
                        for via in via_header:
                            response_lines.append(f"Via: {via}")
                    else:
                        response_lines.append(f"Via: {via_header}")
                    logger.warning("Using fallback Via header method")
            
            response_lines.append(f"Call-ID: {call_id}")
            response_lines.append(f"CSeq: {cseq_header}")
            
            # Contact header is crucial for INVITE responses (1xx, 2xx)
            # to tell the UAC where to send subsequent requests like ACK and BYE.
            if cseq_header and 'INVITE' in cseq_header and (status_code.startswith('1') or status_code.startswith('2')):
                # Use the actual bound interface IP instead of hostname
                contact_uri = f"<sip:pipecat@{self.host}:{self.port}>"
                response_lines.append(f"Contact: {contact_uri}")
            
            response_lines.append("Server: OpenSIPS AI Voice Connector")
            response_lines.append("Allow: INVITE, ACK, CANCEL, BYE, OPTIONS")
            
            # Only set Content-Type and Content-Length if there's a body
            if body:
                response_lines.append("Content-Type: application/sdp")
                response_lines.append(f"Content-Length: {len(body)}")
            else:
                response_lines.append("Content-Length: 0")
            
            response_lines.append("")  # Empty line before body
            
            if body:
                response_lines.append(body)

            response = "\r\n".join(response_lines)
            
            if self.transport:
                self.transport.sendto(response.encode('utf-8'), addr)
                # Mark as sent to prevent duplicates
                self._sent_responses.add(response_key)
                logger.info("Sent SIP response", 
                           status_code=status_code, dest_addr=addr)
                logger.debug("SIP Response content", response=response[:300])
            else:
                logger.error("SIP transport not available, cannot send response")
                
        except Exception as e:
            logger.error("Error sending SIP response", error=str(e), exc_info=True)

    async def send_200_ok(self, invite_data: Dict[str, Any], transport_info: Any):
        """Send 200 OK response with SDP"""
        try:
            # Get transport SDP info (this should be implemented by transport)
            if hasattr(transport_info, 'get_sdp_info'):
                sdp_info = transport_info.get_sdp_info()
            else:
                # Fallback SDP - should not happen in production
                sdp_info = {
                    'media_port': 35000,
                    'media_ip': '0.0.0.0',
                    'audio_format': 'PCMU'
                }
                logger.warning("Using fallback SDP info", sdp_info=sdp_info)
            
            # Generate SDP response
            sdp_body = self._generate_sdp_response(sdp_info)
            
            # Send 200 OK with SDP
            await self.send_response(
                invite_data['addr'],
                invite_data['call_id'],
                '200',
                'OK',
                invite_data['headers'],
                body=sdp_body,
                sip_data=invite_data['sip_data']
            )
            
            logger.info("Sent 200 OK with SDP", 
                       call_id=invite_data['call_id'],
                       media_port=sdp_info.get('media_port'))
            
        except Exception as e:
            logger.error("Error sending 200 OK", error=str(e), exc_info=True)

    async def send_400_bad_request(self, invite_data: Dict[str, Any]):
        """Send 400 Bad Request response"""
        await self.send_response(
            invite_data['addr'],
            invite_data['call_id'],
            '400',
            'Bad Request',
            invite_data['headers'],
            sip_data=invite_data['sip_data']
        )

    async def send_500_internal_error(self, invite_data: Dict[str, Any]):
        """Send 500 Internal Server Error response"""
        await self.send_response(
            invite_data['addr'],
            invite_data['call_id'],
            '500',
            'Internal Server Error',
            invite_data['headers'],
            sip_data=invite_data['sip_data']
        )

    def _generate_sdp_response(self, sdp_info: Dict[str, Any]) -> str:
        """Generate SDP response body"""
        media_ip = sdp_info.get('media_ip', '0.0.0.0')
        media_port = sdp_info.get('media_port', 35000)
        
        sdp_lines = [
            "v=0",
            f"o=- {random.randint(1000000, 9999999)} {random.randint(1000000, 9999999)} IN IP4 {media_ip}",
            "s=OpenSIPS AI Voice Connector",
            f"c=IN IP4 {media_ip}",
            "t=0 0",
            f"m=audio {media_port} RTP/AVP 0",
            "a=rtpmap:0 PCMU/8000",
            "a=sendrecv"
        ]
        
        return '\r\n'.join(sdp_lines)

# vim: tabstop=8 expandtab shiftwidth=4 softtabstop=4 