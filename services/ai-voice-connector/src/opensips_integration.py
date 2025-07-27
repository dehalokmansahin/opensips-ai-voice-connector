"""
OpenSIPS Integration for AI Voice Connector
Handles communication with OpenSIPS via event datagram interface
"""

import asyncio
import json
import socket
from typing import Dict, Any, Optional

import structlog

logger = structlog.get_logger(__name__)


class OpenSIPSEventListener:
    """Listens for events from OpenSIPS via datagram interface"""
    
    def __init__(self, host: str, event_port: int, pipeline_manager):
        self.host = host
        self.event_port = event_port
        self.pipeline_manager = pipeline_manager
        self.socket: Optional[socket.socket] = None
        self.running = False
        self.listener_task: Optional[asyncio.Task] = None
        
    async def start(self):
        """Start listening for OpenSIPS events"""
        logger.info("Starting OpenSIPS event listener", 
                   host=self.host, 
                   port=self.event_port)
        
        try:
            # Create UDP socket
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.socket.setblocking(False)
            self.socket.bind(('0.0.0.0', 8091))  # Listen on dedicated port for AI backend events
            
            self.running = True
            self.listener_task = asyncio.create_task(self._listen_for_events())
            
            logger.info("OpenSIPS event listener started")
            
        except Exception as e:
            logger.error("Failed to start OpenSIPS event listener", error=str(e))
            raise
    
    async def stop(self):
        """Stop the event listener"""
        logger.info("Stopping OpenSIPS event listener")
        
        self.running = False
        
        if self.listener_task:
            self.listener_task.cancel()
            try:
                await self.listener_task
            except asyncio.CancelledError:
                pass
        
        if self.socket:
            self.socket.close()
            self.socket = None
        
        logger.info("OpenSIPS event listener stopped")
    
    async def _listen_for_events(self):
        """Background task to listen for OpenSIPS events"""
        while self.running:
            try:
                # Use asyncio to handle socket operations
                loop = asyncio.get_event_loop()
                
                try:
                    data, addr = await loop.sock_recvfrom(self.socket, 4096)
                    await self._handle_event(data.decode(), addr)
                except socket.error as e:
                    if e.errno != socket.EWOULDBLOCK:
                        logger.error("Socket error in event listener", error=str(e))
                        await asyncio.sleep(1)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Error in event listener", error=str(e))
                await asyncio.sleep(1)
    
    async def _handle_event(self, data: str, addr):
        """Handle incoming OpenSIPS event"""
        try:
            # Parse JSON event data
            event_data = json.loads(data)
            event_type = event_data.get("event")
            
            logger.info("Received OpenSIPS event", 
                       event_type=event_type,
                       source=addr,
                       data=event_data)
            
            # Handle different event types
            if event_type == "call_start":
                await self._handle_call_start(event_data)
            elif event_type == "call_end":
                await self._handle_call_end(event_data)
            elif event_type == "call_failed":
                await self._handle_call_failed(event_data)
            else:
                logger.warning("Unknown event type", event_type=event_type)
                
        except json.JSONDecodeError as e:
            logger.error("Failed to parse event JSON", error=str(e), data=data)
        except Exception as e:
            logger.error("Error handling OpenSIPS event", error=str(e))
    
    async def _handle_call_start(self, event_data: Dict[str, Any]):
        """Handle call start event"""
        call_id = event_data.get("call_id")
        caller = event_data.get("caller")
        called = event_data.get("called")
        
        if not all([call_id, caller, called]):
            logger.error("Missing required fields in call_start event", event_data=event_data)
            return
        
        try:
            # Create new pipeline session
            session_id = await self.pipeline_manager.create_session(call_id, caller, called)
            
            logger.info("Created session for incoming call",
                       session_id=session_id,
                       call_id=call_id,
                       caller=caller,
                       called=called)
            
        except Exception as e:
            logger.error("Failed to create session for call", 
                        call_id=call_id,
                        error=str(e))
    
    async def _handle_call_end(self, event_data: Dict[str, Any]):
        """Handle call end event"""
        call_id = event_data.get("call_id")
        
        if not call_id:
            logger.error("Missing call_id in call_end event", event_data=event_data)
            return
        
        try:
            # Find and end the session for this call
            # This is a simplified approach - in production we'd need better session tracking
            active_sessions = await self.pipeline_manager.get_session_stats()
            
            logger.info("Call ended", 
                       call_id=call_id,
                       reason=event_data.get("reason", "unknown"))
            
        except Exception as e:
            logger.error("Failed to handle call end", 
                        call_id=call_id,
                        error=str(e))
    
    async def _handle_call_failed(self, event_data: Dict[str, Any]):
        """Handle call failed event"""
        call_id = event_data.get("call_id")
        code = event_data.get("code")
        reason = event_data.get("reason")
        
        logger.warning("Call failed",
                      call_id=call_id,
                      code=code,
                      reason=reason)
    
    async def health_check(self) -> Dict[str, Any]:
        """Health check for OpenSIPS event listener"""
        try:
            if not self.running or not self.socket:
                return {
                    "status": "unhealthy",
                    "message": "OpenSIPS event listener not running",
                    "details": {}
                }
            
            if self.listener_task and self.listener_task.done():
                # Check if task ended with exception
                try:
                    exception = self.listener_task.exception()
                    if exception:
                        return {
                            "status": "unhealthy",
                            "message": f"Event listener task failed: {str(exception)}",
                            "details": {"error": str(exception)}
                        }
                except asyncio.InvalidStateError:
                    pass
            
            return {
                "status": "healthy",
                "message": "OpenSIPS event listener running",
                "details": {
                    "host": self.host,
                    "event_port": self.event_port,
                    "listening": self.running
                }
            }
            
        except Exception as e:
            return {
                "status": "unhealthy",
                "message": f"OpenSIPS event listener health check failed: {str(e)}",
                "details": {"error": str(e)}
            }