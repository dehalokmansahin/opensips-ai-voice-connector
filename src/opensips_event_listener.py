#!/usr/bin/env python3
"""
OpenSIPS Event Datagram Listener
Event and MI datagram.md dokümanına göre OpenSIPS olaylarını dinler
"""

import asyncio
import socket
import structlog
from typing import Dict, Any, Optional, Callable, Awaitable, Tuple
from datetime import datetime

logger = structlog.get_logger()

def _parse_sdp(sdp_str: str) -> Tuple[Optional[str], Optional[int]]:
    """Parse SDP to extract connection IP and media port."""
    connection_ip = None
    media_port = None
    for line in sdp_str.splitlines():
        line = line.strip()
        if line.startswith('c='):
            parts = line.split()
            if len(parts) >= 3:
                connection_ip = parts[2]
        if line.startswith('m=audio'):
            parts = line.split()
            if len(parts) >= 2:
                try:
                    media_port = int(parts[1])
                except ValueError:
                    continue
    return connection_ip, media_port

class OpenSIPSEventListener:
    """OpenSIPS Event Datagram dinleyicisi"""
    
    def __init__(
        self, 
        host: str = "0.0.0.0", 
        port: int = 8090,
        on_call_start: Optional[Callable[[Dict[str, Any]], Awaitable[None]]] = None,
        on_call_end: Optional[Callable[[Dict[str, Any]], Awaitable[None]]] = None
    ):
        """
        Initialize event listener
        
        Args:
            host: Listen host
            port: Listen port (config'te event_port = 8090)
            on_call_start: Callback for call start events
            on_call_end: Callback for call end events
        """
        self.host = host
        self.port = port
        self.transport = None
        self.protocol = None
        self.running = False
        
        # Callback handlers
        self.on_call_start = on_call_start
        self.on_call_end = on_call_end
        
        # Event handlers
        self.event_handlers = {
            "OAVC_CALL_EVENT": self.handle_call_event,
            "E_CALL_SETUP": self.handle_call_setup,
            "E_CALL_ANSWERED": self.handle_call_answered,
            "E_CALL_TERMINATED": self.handle_call_terminated,
        }
        
        logger.info("OpenSIPS Event Listener initialized", host=host, port=port)
        logger.debug("OpenSIPSEventListener: event handlers registered", handlers=list(self.event_handlers.keys()))
    
    async def start(self):
        """Event listener'ı başlat - using working pattern from old code"""
        try:
            loop = asyncio.get_running_loop()

            class EventProtocol(asyncio.DatagramProtocol):
                def __init__(self, handler_func):
                    self.handler_func = handler_func
                    super().__init__()
                    
                def connection_made(self, transport):
                    self.transport = transport
                    logger.debug("OpenSIPS Event Protocol: connection established")
                    
                def datagram_received(self, data, addr):
                    """Handle incoming event datagram"""
                    try:
                        logger.debug("OpenSIPS Event Protocol: datagram received", 
                                    from_addr=addr, size=len(data))
                        # Create async task to handle the event
                        asyncio.create_task(self.handler_func(data, addr))
                    except Exception as e:
                        logger.error("Error in event datagram_received", error=str(e))
            
            self.transport, self.protocol = await loop.create_datagram_endpoint(
                lambda: EventProtocol(self.process_event),
                local_addr=(self.host, self.port),
            )
            
            self.running = True
            
            logger.info("✅ OpenSIPS Event Listener started", host=self.host, port=self.port)
            logger.debug("OpenSIPSEventListener: UDP transport connected", 
                        local_addr=self.transport.get_extra_info('sockname'))
                    
        except Exception as e:
            logger.error("Failed to start OpenSIPS Event Listener", error=str(e))
            raise
    
    async def stop(self):
        """Event listener'ı durdur"""
        try:
            self.running = False
            if self.transport:
                self.transport.close()
                self.transport = None
                self.protocol = None
            
            logger.info("OpenSIPS Event Listener stopped")
            
        except Exception as e:
            logger.error("Error stopping OpenSIPS Event Listener", error=str(e))
    
    async def process_event(self, data: bytes, addr: tuple):
        """
        Gelen event'i işle
        
        Args:
            data: Event data bytes
            addr: Sender address (IP, port)
        """
        try:
            # Event data'yı decode et
            event_str = data.decode('utf-8').strip()
            
            logger.debug("Received event", data=event_str[:100], sender=f"{addr[0]}:{addr[1]}")
            
            # Event parsing - OpenSIPS event format
            # Format genellikle: "EVENT_NAME:param1:param2:..."
            parts = event_str.split(':', 1)
            if len(parts) >= 1:
                event_name = parts[0]
                event_data = parts[1] if len(parts) > 1 else ""
                logger.debug("OpenSIPSEventListener: parsed event", event_name=event_name, event_data=event_data)
                await self.handle_event(event_name, event_data, addr)
            else:
                logger.warning("Invalid event format", data=event_str)
                
        except Exception as e:
            logger.error("Error processing event", 
                        error=str(e), 
                        data=data[:100] if data else None)
    
    async def handle_event(self, event_name: str, event_data: str, addr: tuple):
        """
        Event'i uygun handler'a yönlendir
        
        Args:
            event_name: Event adı
            event_data: Event verisi
            addr: Sender address
        """
        try:
            handler = self.event_handlers.get(event_name)
            logger.debug("OpenSIPSEventListener: dispatching event", event_name=event_name, handler=handler.__name__ if handler else None)
            if handler:
                await handler(event_data, addr)
            else:
                # Bilinmeyen event - log et
                logger.info("Unknown event received", 
                           event_name=event_name,
                           event_data=event_data[:50],
                           sender=f"{addr[0]}:{addr[1]}")
                
        except Exception as e:
            logger.error("Error handling event", 
                        event_name=event_name,
                        error=str(e))
    
    async def handle_call_event(self, event_data: str, addr: tuple):
        """OAVC call event handler"""
        try:
            # Format: "CALL_START:call_id:from:to" veya "CALL_ESTABLISHED:call_id:status"
            parts = event_data.split(':', 3)
            if len(parts) >= 2:
                sub_event = parts[0]  # CALL_START, CALL_ESTABLISHED, etc.
                call_id = parts[1]
                
                if sub_event == "CALL_START":
                    from_uri = parts[2] if len(parts) > 2 else "unknown"
                    to_uri = parts[3] if len(parts) > 3 else "unknown"
                    
                    logger.info("🔄 New call started", 
                               call_id=call_id,
                               from_uri=from_uri,
                               to_uri=to_uri,
                               timestamp=datetime.now().isoformat())
                    
                    # Trigger callback
                    if self.on_call_start:
                        call_info = {
                            'call_id': call_id,
                            'from_uri': from_uri,
                            'to_uri': to_uri,
                            'client_ip': addr[0],
                            'client_port': addr[1]
                        }
                        await self.on_call_start(call_info)
                
                elif sub_event == "CALL_ESTABLISHED":
                    status = parts[2] if len(parts) > 2 else "200"
                    
                    logger.info("✅ Call established", 
                               call_id=call_id,
                               status=status,
                               timestamp=datetime.now().isoformat())
                
                else:
                    logger.info("📞 Call event", 
                               sub_event=sub_event,
                               call_id=call_id,
                               data=event_data)
            
        except Exception as e:
            logger.error("Error handling call event", 
                        event_data=event_data,
                        error=str(e))
    
    async def handle_call_setup(self, event_data: str, addr: tuple):
        """Call setup event handler"""
        logger.info("📞 Call setup event", event_data=event_data)
        # Parse call_id and SDP from event_data
        parts = event_data.split(':', 1)
        call_id = parts[0]
        sdp = parts[1] if len(parts) > 1 else ""
        # Extract connection IP and port from SDP
        client_ip, client_port = _parse_sdp(sdp)
        logger.debug("OpenSIPSEventListener: parsed SDP in call setup", call_id=call_id, client_ip=client_ip, client_port=client_port, sdp=sdp)
        if not client_ip or not client_port:
            logger.error("Failed to parse SDP", sdp=sdp)
            return
        # Trigger on_call_start callback with client info
        if self.on_call_start:
            call_info = {
                'call_id': call_id,
                'client_ip': client_ip,
                'client_port': client_port,
                'sdp': sdp
            }
            await self.on_call_start(call_info)
    
    async def handle_call_answered(self, event_data: str, addr: tuple):
        """Call answered event handler"""  
        logger.info("📞 Call answered event", event_data=event_data)
    
    async def handle_call_terminated(self, event_data: str, addr: tuple):
        """Call terminated event handler"""
        logger.info("📞 Call terminated event", event_data=event_data)
        
        # Trigger callback
        if self.on_call_end:
            # Extract call_id from event_data if possible
            parts = event_data.split(':', 1)
            call_id = parts[0] if parts else "unknown"
            
            call_info = {
                'call_id': call_id,
                'event_data': event_data
            }
            await self.on_call_end(call_info)

# vim: tabstop=8 expandtab shiftwidth=4 softtabstop=4 