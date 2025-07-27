"""
OpenSIPS Event Listener for AI Voice Connector
Listens for OpenSIPS events via UDP datagram
Based on working implementation from legacy code
"""

import asyncio
import json
import logging
import re
from typing import Dict, Any, Optional, Callable, Tuple
from datetime import datetime

logger = logging.getLogger(__name__)

def _parse_sdp(sdp_str: str) -> Tuple[Optional[str], Optional[int]]:
    """Parse SDP to extract connection IP and media port"""
    connection_ip = None
    media_port = None
    
    for line in sdp_str.splitlines():
        line = line.strip()
        if line.startswith('c='):
            parts = line.split()
            if len(parts) >= 3:
                connection_ip = parts[2]
        elif line.startswith('m=audio'):
            parts = line.split()
            if len(parts) >= 2:
                try:
                    media_port = int(parts[1])
                except ValueError:
                    continue
    
    return connection_ip, media_port

class OpenSIPSEventListener:
    """OpenSIPS Event Datagram Listener"""
    
    def __init__(
        self,
        host: str = "0.0.0.0",
        port: int = 8090,
        on_call_start: Optional[Callable[[Dict[str, Any]], Any]] = None,
        on_call_end: Optional[Callable[[Dict[str, Any]], Any]] = None
    ):
        """
        Initialize event listener
        
        Args:
            host: Listen host
            port: Listen port  
            on_call_start: Callback for call start events
            on_call_end: Callback for call end events
        """
        self.host = host
        self.port = port
        self.transport = None
        self.protocol = None
        self._running = False
        
        # Callbacks
        self.on_call_start = on_call_start
        self.on_call_end = on_call_end
        
        # Event handlers
        self.event_handlers = {
            "OAVC_CALL_EVENT": self.handle_call_event,
            "E_CALL_SETUP": self.handle_call_setup,
            "E_CALL_ANSWERED": self.handle_call_answered,
            "E_CALL_TERMINATED": self.handle_call_terminated,
        }
        
        logger.info(f"OpenSIPS Event Listener initialized: {host}:{port}")
    
    async def start(self):
        """Start the event listener"""
        try:
            loop = asyncio.get_running_loop()
            
            class EventProtocol(asyncio.DatagramProtocol):
                def __init__(self, handler_func):
                    self.handler_func = handler_func
                    super().__init__()
                
                def connection_made(self, transport):
                    self.transport = transport
                    logger.debug("Event protocol connection established")
                
                def datagram_received(self, data, addr):
                    """Handle incoming event datagram"""
                    try:
                        logger.debug(f"Event datagram received from {addr}, size: {len(data)}")
                        # Create async task to handle the event
                        asyncio.create_task(self.handler_func(data, addr))
                    except Exception as e:
                        logger.error(f"Error in datagram_received: {e}")
            
            # Create UDP endpoint
            self.transport, self.protocol = await loop.create_datagram_endpoint(
                lambda: EventProtocol(self.process_event),
                local_addr=(self.host, self.port),
                reuse_port=True
            )
            
            self._running = True
            logger.info(f"Event listener started on {self.host}:{self.port}")
            
        except Exception as e:
            logger.error(f"Failed to start event listener: {e}")
            raise
    
    async def stop(self):
        """Stop the event listener"""
        try:
            self._running = False
            
            if self.transport:
                self.transport.close()
                self.transport = None
                self.protocol = None
            
            logger.info("Event listener stopped")
            
        except Exception as e:
            logger.error(f"Error stopping event listener: {e}")
    
    def is_running(self) -> bool:
        """Check if event listener is running"""
        return self._running
    
    async def process_event(self, data: bytes, addr: Tuple[str, int]):
        """Process incoming event datagram"""
        try:
            # Decode event data
            event_str = data.decode('utf-8').strip()
            logger.debug(f"Processing event from {addr}: {event_str[:200]}")
            
            # Parse event
            event_data = self._parse_event(event_str)
            if not event_data:
                logger.warning(f"Failed to parse event: {event_str[:100]}")
                return
            
            # Handle event based on type
            event_type = event_data.get('event_type') or event_data.get('Event')
            if event_type in self.event_handlers:
                await self.event_handlers[event_type](event_data, addr)
            else:
                logger.debug(f"Unhandled event type: {event_type}")
                await self.handle_generic_event(event_data, addr)
                
        except Exception as e:
            logger.error(f"Error processing event: {e}")
    
    def _parse_event(self, event_str: str) -> Optional[Dict[str, Any]]:
        """Parse event string to dictionary"""
        try:
            # Try JSON format first
            if event_str.startswith('{'):
                return json.loads(event_str)
            
            # Parse key=value format
            event_data = {}
            
            # Split by lines and parse each line
            for line in event_str.split('\\n'):
                line = line.strip()
                if '=' in line:
                    key, value = line.split('=', 1)
                    event_data[key.strip()] = value.strip()
            
            return event_data if event_data else None
            
        except Exception as e:
            logger.error(f"Error parsing event: {e}")
            return None
    
    async def handle_call_event(self, event_data: Dict[str, Any], addr: Tuple[str, int]):
        """Handle OAVC_CALL_EVENT"""
        try:
            action = event_data.get('action', 'unknown')
            call_id = event_data.get('call_id', f"call_{id(event_data)}")
            
            logger.info(f"📞 OAVC_CALL_EVENT: {action} for call {call_id}")
            
            if action == 'start':
                await self._handle_call_start(event_data)
            elif action == 'end':
                await self._handle_call_end(event_data)
            else:
                logger.debug(f"Unknown call event action: {action}")
                
        except Exception as e:
            logger.error(f"Error handling call event: {e}")
    
    async def handle_call_setup(self, event_data: Dict[str, Any], addr: Tuple[str, int]):
        """Handle E_CALL_SETUP event"""
        try:
            call_id = event_data.get('callid') or event_data.get('call_id', f"setup_{id(event_data)}")
            logger.info(f"📞 E_CALL_SETUP for call {call_id}")
            
            # Extract additional info
            enhanced_data = {
                **event_data,
                'call_id': call_id,
                'event_type': 'call_setup',
                'timestamp': datetime.now().isoformat()
            }
            
            await self._handle_call_start(enhanced_data)
            
        except Exception as e:
            logger.error(f"Error handling call setup: {e}")
    
    async def handle_call_answered(self, event_data: Dict[str, Any], addr: Tuple[str, int]):
        """Handle E_CALL_ANSWERED event"""
        try:
            call_id = event_data.get('callid') or event_data.get('call_id', f"answered_{id(event_data)}")
            logger.info(f"📞 E_CALL_ANSWERED for call {call_id}")
            
            # This could trigger additional logic if needed
            # For now, just log
            
        except Exception as e:
            logger.error(f"Error handling call answered: {e}")
    
    async def handle_call_terminated(self, event_data: Dict[str, Any], addr: Tuple[str, int]):
        """Handle E_CALL_TERMINATED event"""
        try:
            call_id = event_data.get('callid') or event_data.get('call_id', f"terminated_{id(event_data)}")
            logger.info(f"📞 E_CALL_TERMINATED for call {call_id}")
            
            # Enhanced termination data
            enhanced_data = {
                **event_data,
                'call_id': call_id,
                'event_type': 'call_terminated',
                'timestamp': datetime.now().isoformat()
            }
            
            await self._handle_call_end(enhanced_data)
            
        except Exception as e:
            logger.error(f"Error handling call terminated: {e}")
    
    async def handle_generic_event(self, event_data: Dict[str, Any], addr: Tuple[str, int]):
        """Handle generic/unknown events"""
        try:
            event_type = event_data.get('event_type') or event_data.get('Event', 'unknown')
            logger.debug(f"📞 Generic event: {event_type}")
            
            # Check if this might be a call-related event
            if any(key in event_data for key in ['call_id', 'callid', 'Call-ID']):
                # Extract call ID
                call_id = (event_data.get('call_id') or 
                          event_data.get('callid') or 
                          event_data.get('Call-ID', f"generic_{id(event_data)}"))
                
                # Check for patterns that indicate call start/end
                event_str = str(event_data).lower()
                if any(word in event_str for word in ['start', 'begin', 'setup', 'invite']):
                    logger.info(f"📞 Detected call start pattern in generic event for {call_id}")
                    await self._handle_call_start({**event_data, 'call_id': call_id})
                elif any(word in event_str for word in ['end', 'terminate', 'bye', 'cancel']):
                    logger.info(f"📞 Detected call end pattern in generic event for {call_id}")
                    await self._handle_call_end({**event_data, 'call_id': call_id})
                    
        except Exception as e:
            logger.error(f"Error handling generic event: {e}")
    
    async def _handle_call_start(self, event_data: Dict[str, Any]):
        """Internal call start handler"""
        try:
            call_id = event_data.get('call_id', f"start_{id(event_data)}")
            
            # Enhance event data
            enhanced_data = {
                **event_data,
                'call_id': call_id,
                'timestamp': datetime.now().isoformat(),
                'direction': 'inbound'  # Assuming inbound for OpenSIPS events
            }
            
            # Extract SDP if present
            sdp_data = event_data.get('sdp') or event_data.get('SDP')
            if sdp_data:
                media_ip, media_port = _parse_sdp(sdp_data)
                if media_ip and media_port:
                    enhanced_data['sdp_info'] = {
                        'media_ip': media_ip,
                        'media_port': media_port,
                        'raw_sdp': sdp_data
                    }
            
            logger.info(f"📞 Processing call start for {call_id}")
            
            # Call callback
            if self.on_call_start:
                if asyncio.iscoroutinefunction(self.on_call_start):
                    await self.on_call_start(enhanced_data)
                else:
                    self.on_call_start(enhanced_data)
                    
        except Exception as e:
            logger.error(f"Error in call start handler: {e}")
    
    async def _handle_call_end(self, event_data: Dict[str, Any]):
        """Internal call end handler"""
        try:
            call_id = event_data.get('call_id', f"end_{id(event_data)}")
            
            # Enhance event data
            enhanced_data = {
                **event_data,
                'call_id': call_id,
                'timestamp': datetime.now().isoformat(),
                'reason': event_data.get('reason', 'normal_clearing')
            }
            
            logger.info(f"📞 Processing call end for {call_id}")
            
            # Call callback
            if self.on_call_end:
                if asyncio.iscoroutinefunction(self.on_call_end):
                    await self.on_call_end(enhanced_data)
                else:
                    self.on_call_end(enhanced_data)
                    
        except Exception as e:
            logger.error(f"Error in call end handler: {e}")
    
    def get_stats(self) -> Dict[str, Any]:
        """Get listener statistics"""
        return {
            'running': self._running,
            'listen_address': f"{self.host}:{self.port}",
            'handlers': list(self.event_handlers.keys()),
            'has_call_start_callback': self.on_call_start is not None,
            'has_call_end_callback': self.on_call_end is not None
        }