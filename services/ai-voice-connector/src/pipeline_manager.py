"""
Pipeline Manager for AI Voice Connector
Manages the orchestration of the AI voice processing pipeline
"""

import asyncio
import time
from typing import Dict, Any, Optional
from dataclasses import dataclass
from enum import Enum

import structlog

logger = structlog.get_logger(__name__)


class PipelineStatus(Enum):
    """Pipeline execution status"""
    IDLE = "idle"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class PipelineSession:
    """Represents an active pipeline session"""
    session_id: str
    call_id: str
    caller: str
    called: str
    status: PipelineStatus
    created_at: float
    last_activity: float
    pipeline_data: Dict[str, Any]


class PipelineManger:
    """Manages AI voice processing pipelines"""
    
    def __init__(self, settings):
        self.settings = settings
        self.active_sessions: Dict[str, PipelineSession] = {}
        self._session_lock = asyncio.Lock()
        self._cleanup_task: Optional[asyncio.Task] = None
        
    async def initialize(self):
        """Initialize the pipeline manager"""
        logger.info("Initializing Pipeline Manager")
        
        # Start cleanup task for expired sessions
        self._cleanup_task = asyncio.create_task(self._cleanup_expired_sessions())
        
        logger.info("Pipeline Manager initialized")
    
    async def shutdown(self):
        """Shutdown the pipeline manager"""
        logger.info("Shutting down Pipeline Manager")
        
        # Cancel cleanup task
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
        
        # Clean up active sessions
        async with self._session_lock:
            for session in self.active_sessions.values():
                session.status = PipelineStatus.CANCELLED
            self.active_sessions.clear()
        
        logger.info("Pipeline Manager shut down")
    
    async def create_session(self, call_id: str, caller: str, called: str) -> str:
        """Create a new pipeline session"""
        session_id = f"session_{int(time.time() * 1000)}_{call_id}"
        
        async with self._session_lock:
            session = PipelineSession(
                session_id=session_id,
                call_id=call_id,
                caller=caller,
                called=called,
                status=PipelineStatus.IDLE,
                created_at=time.time(),
                last_activity=time.time(),
                pipeline_data={}
            )
            self.active_sessions[session_id] = session
        
        logger.info("Created pipeline session", 
                   session_id=session_id, 
                   call_id=call_id,
                   caller=caller)
        
        return session_id
    
    async def end_session(self, session_id: str) -> bool:
        """End a pipeline session"""
        async with self._session_lock:
            if session_id in self.active_sessions:
                session = self.active_sessions[session_id]
                session.status = PipelineStatus.COMPLETED
                session.last_activity = time.time()
                
                logger.info("Ended pipeline session", 
                           session_id=session_id,
                           call_id=session.call_id)
                
                # Remove from active sessions
                del self.active_sessions[session_id]
                return True
            
        logger.warning("Attempted to end non-existent session", session_id=session_id)
        return False
    
    async def get_session(self, session_id: str) -> Optional[PipelineSession]:
        """Get session information"""
        async with self._session_lock:
            return self.active_sessions.get(session_id)
    
    async def update_session_activity(self, session_id: str):
        """Update session last activity timestamp"""
        async with self._session_lock:
            if session_id in self.active_sessions:
                self.active_sessions[session_id].last_activity = time.time()
    
    async def process_audio_chunk(self, session_id: str, audio_data: bytes) -> Dict[str, Any]:
        """Process audio chunk through the AI pipeline"""
        session = await self.get_session(session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found")
        
        await self.update_session_activity(session_id)
        
        # Update session status
        async with self._session_lock:
            session.status = PipelineStatus.PROCESSING
        
        try:
            # This is a placeholder implementation
            # In the full implementation, this would:
            # 1. Send audio to VAD service
            # 2. If voice detected, send to ASR service
            # 3. Send transcript to LLM service
            # 4. Send LLM response to TTS service
            # 5. Return synthesized audio
            
            logger.info("Processing audio chunk", 
                       session_id=session_id,
                       audio_size=len(audio_data))
            
            # Simulate processing delay
            await asyncio.sleep(0.1)
            
            # Placeholder response
            result = {
                "session_id": session_id,
                "status": "processed",
                "audio_response": b"",  # Placeholder for synthesized audio
                "transcript": "Placeholder transcript",
                "llm_response": "Placeholder response",
                "processing_time_ms": 100
            }
            
            # Update session status
            async with self._session_lock:
                session.status = PipelineStatus.IDLE
            
            return result
            
        except Exception as e:
            logger.error("Pipeline processing failed", 
                        session_id=session_id,
                        error=str(e))
            
            # Update session status
            async with self._session_lock:
                session.status = PipelineStatus.FAILED
            
            raise
    
    async def get_active_sessions_count(self) -> int:
        """Get count of active sessions"""
        async with self._session_lock:
            return len(self.active_sessions)
    
    async def get_session_stats(self) -> Dict[str, Any]:
        """Get pipeline session statistics"""
        async with self._session_lock:
            total_sessions = len(self.active_sessions)
            status_counts = {}
            
            for session in self.active_sessions.values():
                status = session.status.value
                status_counts[status] = status_counts.get(status, 0) + 1
            
            return {
                "total_active_sessions": total_sessions,
                "status_breakdown": status_counts,
                "oldest_session_age": self._get_oldest_session_age(),
                "average_session_age": self._get_average_session_age()
            }
    
    def _get_oldest_session_age(self) -> Optional[float]:
        """Get age of oldest session in seconds"""
        if not self.active_sessions:
            return None
        
        current_time = time.time()
        oldest_time = min(session.created_at for session in self.active_sessions.values())
        return current_time - oldest_time
    
    def _get_average_session_age(self) -> Optional[float]:
        """Get average age of sessions in seconds"""
        if not self.active_sessions:
            return None
        
        current_time = time.time()
        total_age = sum(current_time - session.created_at for session in self.active_sessions.values())
        return total_age / len(self.active_sessions)
    
    async def _cleanup_expired_sessions(self):
        """Background task to clean up expired sessions"""
        while True:
            try:
                await asyncio.sleep(60)  # Check every minute
                
                current_time = time.time()
                timeout_seconds = self.settings.pipeline.session_timeout_seconds
                expired_sessions = []
                
                async with self._session_lock:
                    for session_id, session in self.active_sessions.items():
                        if (current_time - session.last_activity) > timeout_seconds:
                            expired_sessions.append(session_id)
                    
                    # Remove expired sessions
                    for session_id in expired_sessions:
                        session = self.active_sessions.pop(session_id, None)
                        if session:
                            logger.info("Cleaned up expired session",
                                       session_id=session_id,
                                       call_id=session.call_id,
                                       age_seconds=current_time - session.created_at)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Error in session cleanup task", error=str(e))
    
    async def health_check(self) -> Dict[str, Any]:
        """Health check for pipeline manager"""
        try:
            stats = await self.get_session_stats()
            
            # Check if we have too many stuck sessions
            max_sessions = 100  # Configurable threshold
            total_sessions = stats["total_active_sessions"]
            
            if total_sessions > max_sessions:
                return {
                    "status": "degraded",
                    "message": f"High number of active sessions: {total_sessions}",
                    "details": stats
                }
            
            # Check for very old sessions (potential leaks)
            oldest_age = stats.get("oldest_session_age")
            if oldest_age and oldest_age > 3600:  # 1 hour
                return {
                    "status": "degraded", 
                    "message": f"Very old session detected: {oldest_age:.1f}s",
                    "details": stats
                }
            
            return {
                "status": "healthy",
                "message": "Pipeline manager operating normally",
                "details": stats
            }
            
        except Exception as e:
            return {
                "status": "unhealthy",
                "message": f"Pipeline manager health check failed: {str(e)}",
                "details": {"error": str(e)}
            }