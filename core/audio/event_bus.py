"""
Audio Event Bus for decoupling RTP reception from processing
Implements event bus pattern for scalable audio processing pipeline
"""

import asyncio
import logging
from typing import Dict, List, Callable, Any, Optional
from dataclasses import dataclass
from enum import Enum
import time

logger = logging.getLogger(__name__)

class AudioEventType(Enum):
    """Audio event types for the event bus"""
    RTP_PACKET_RECEIVED = "rtp_packet_received"
    AUDIO_DATA_READY = "audio_data_ready" 
    JITTER_BUFFER_OVERFLOW = "jitter_buffer_overflow"
    PACKET_LOSS_DETECTED = "packet_loss_detected"
    SESSION_STARTED = "session_started"
    SESSION_ENDED = "session_ended"
    QUALITY_DEGRADED = "quality_degraded"

@dataclass
class AudioEvent:
    """Audio event structure"""
    event_type: AudioEventType
    session_id: str
    timestamp: float
    data: Dict[str, Any]
    correlation_id: Optional[str] = None

class AudioEventBus:
    """
    Event bus for decoupling RTP reception from audio processing
    Implements async event handling with subscriber patterns
    """
    
    def __init__(self, max_queue_size: int = 1000):
        self.max_queue_size = max_queue_size
        self._subscribers: Dict[AudioEventType, List[Callable]] = {}
        self._event_queue = asyncio.Queue(maxsize=max_queue_size)
        self._running = False
        self._processing_task: Optional[asyncio.Task] = None
        self._stats = {
            'events_published': 0,
            'events_processed': 0,
            'events_dropped': 0,
            'subscribers_count': 0
        }
        
        logger.info(f"AudioEventBus initialized with max_queue_size={max_queue_size}")
    
    async def start(self):
        """Start the event bus processing"""
        if self._running:
            logger.warning("AudioEventBus already running")
            return
            
        self._running = True
        self._processing_task = asyncio.create_task(self._process_events())
        logger.info("AudioEventBus started")
    
    async def stop(self):
        """Stop the event bus processing"""
        if not self._running:
            return
            
        self._running = False
        
        if self._processing_task and not self._processing_task.done():
            self._processing_task.cancel()
            try:
                await self._processing_task
            except asyncio.CancelledError:
                pass
        
        # Clear remaining events
        while not self._event_queue.empty():
            try:
                self._event_queue.get_nowait()
            except asyncio.QueueEmpty:
                break
        
        logger.info("AudioEventBus stopped")
    
    def subscribe(self, event_type: AudioEventType, callback: Callable[[AudioEvent], Any]):
        """Subscribe to specific event types"""
        if event_type not in self._subscribers:
            self._subscribers[event_type] = []
        
        self._subscribers[event_type].append(callback)
        self._stats['subscribers_count'] += 1
        
        logger.debug(f"Subscribed to {event_type.value}, total subscribers: {len(self._subscribers[event_type])}")
    
    def unsubscribe(self, event_type: AudioEventType, callback: Callable[[AudioEvent], Any]):
        """Unsubscribe from specific event types"""
        if event_type in self._subscribers and callback in self._subscribers[event_type]:
            self._subscribers[event_type].remove(callback)
            self._stats['subscribers_count'] -= 1
            
            # Clean up empty subscriber lists
            if not self._subscribers[event_type]:
                del self._subscribers[event_type]
            
            logger.debug(f"Unsubscribed from {event_type.value}")
    
    async def publish(self, event: AudioEvent):
        """Publish an event to the bus"""
        if not self._running:
            logger.warning("Cannot publish event - AudioEventBus not running")
            return False
        
        try:
            # Try to put event in queue without blocking
            self._event_queue.put_nowait(event)
            self._stats['events_published'] += 1
            
            logger.debug(f"Published event: {event.event_type.value} for session {event.session_id}")
            return True
            
        except asyncio.QueueFull:
            self._stats['events_dropped'] += 1
            logger.warning(f"Event queue full, dropping event: {event.event_type.value}")
            return False
    
    async def publish_rtp_packet(self, session_id: str, packet_data: Dict[str, Any], correlation_id: str = None):
        """Convenience method for publishing RTP packet events"""
        event = AudioEvent(
            event_type=AudioEventType.RTP_PACKET_RECEIVED,
            session_id=session_id,
            timestamp=time.time(),
            data=packet_data,
            correlation_id=correlation_id
        )
        return await self.publish(event)
    
    async def publish_audio_ready(self, session_id: str, audio_data: bytes, metadata: Dict[str, Any] = None):
        """Convenience method for publishing audio ready events"""
        event = AudioEvent(
            event_type=AudioEventType.AUDIO_DATA_READY,
            session_id=session_id,
            timestamp=time.time(),
            data={
                'audio_data': audio_data,
                'metadata': metadata or {}
            }
        )
        return await self.publish(event)
    
    async def publish_packet_loss(self, session_id: str, loss_info: Dict[str, Any]):
        """Convenience method for publishing packet loss events"""
        event = AudioEvent(
            event_type=AudioEventType.PACKET_LOSS_DETECTED,
            session_id=session_id,
            timestamp=time.time(),
            data=loss_info
        )
        return await self.publish(event)
    
    async def _process_events(self):
        """Internal event processing loop"""
        try:
            while self._running:
                try:
                    # Get event with timeout to allow for graceful shutdown
                    event = await asyncio.wait_for(self._event_queue.get(), timeout=1.0)
                    await self._handle_event(event)
                    self._stats['events_processed'] += 1
                    
                except asyncio.TimeoutError:
                    # Normal timeout, continue loop
                    continue
                except Exception as e:
                    logger.error(f"Error processing event: {e}")
                    
        except asyncio.CancelledError:
            logger.debug("Event processing cancelled")
            raise
        except Exception as e:
            logger.error(f"Fatal error in event processing: {e}")
    
    async def _handle_event(self, event: AudioEvent):
        """Handle individual events by notifying subscribers"""
        if event.event_type not in self._subscribers:
            logger.debug(f"No subscribers for event type: {event.event_type.value}")
            return
        
        # Notify all subscribers for this event type
        subscribers = self._subscribers[event.event_type].copy()  # Copy to avoid modification during iteration
        
        for callback in subscribers:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(event)
                else:
                    callback(event)
                    
            except Exception as e:
                logger.error(f"Error in event subscriber callback: {e}")
    
    def get_stats(self) -> Dict[str, Any]:
        """Get event bus statistics"""
        return {
            **self._stats,
            'queue_size': self._event_queue.qsize(),
            'max_queue_size': self.max_queue_size,
            'running': self._running,
            'event_types_subscribed': list(self._subscribers.keys())
        }
    
    def clear_stats(self):
        """Clear statistics counters"""
        self._stats = {
            'events_published': 0,
            'events_processed': 0,
            'events_dropped': 0,
            'subscribers_count': len([cb for callbacks in self._subscribers.values() for cb in callbacks])
        }
        logger.info("AudioEventBus stats cleared")