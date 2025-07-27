"""
Pipeline Manager for OpenSIPS AI Voice Connector
Manages conversation pipelines and sessions
"""

import asyncio
import logging
from typing import Dict, Any, Optional
from dataclasses import dataclass
from datetime import datetime

from ..grpc_clients import ServiceRegistry, ASRClient, LLMClient, TTSClient
from ..grpc_clients.asr_client import StreamingSession as ASRStreamingSession
from ..grpc_clients.llm_client import ConversationManager
from ..grpc_clients.tts_client import SentenceFlushAggregator
from ..opensips.rtp_transport import RTPTransport
from ..config.settings import Settings
from .session import ConversationSession

logger = logging.getLogger(__name__)

@dataclass
class SessionConfig:
    """Configuration for conversation session"""
    system_prompt: str = "Sen Türkçe konuşan bir yapay zeka asistanısın. Kısa ve net cevaplar ver."
    asr_config: Dict[str, Any] = None
    llm_config: Dict[str, Any] = None
    tts_config: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.asr_config is None:
            self.asr_config = {
                'sample_rate': 16000,
                'show_words': True,
                'max_alternatives': 0
            }
        
        if self.llm_config is None:
            self.llm_config = {
                'temperature': 0.7,
                'max_tokens': 150,
                'use_rag': True
            }
        
        if self.tts_config is None:
            self.tts_config = {
                'voice': 'tr_TR-dfki-medium',
                'sample_rate': 22050,
                'format': 'pcm16'
            }

class PipelineManager:
    """
    Manages conversation pipelines and sessions
    Coordinates ASR, LLM, and TTS services
    """
    
    def __init__(self, service_registry: ServiceRegistry, settings: Settings):
        self.service_registry = service_registry
        self.settings = settings
        
        # Service clients
        self.asr_client: Optional[ASRClient] = None
        self.llm_client: Optional[LLMClient] = None
        self.tts_client: Optional[TTSClient] = None
        
        # Active sessions
        self.active_sessions: Dict[str, ConversationSession] = {}
        
        # Default session config
        self.default_config = SessionConfig()
        
    async def initialize(self):
        """Initialize pipeline manager and service clients"""
        try:
            # Create service clients
            self.asr_client = ASRClient(self.service_registry)
            self.llm_client = LLMClient(self.service_registry)
            self.tts_client = TTSClient(self.service_registry)
            
            # Wait for services to be ready
            logger.info("Waiting for services to be ready...")
            
            ready_services = 0
            for service_name in ['asr', 'llm', 'tts']:
                if await self.service_registry.wait_for_service(service_name, timeout=30.0):
                    ready_services += 1
                    logger.info(f"Service {service_name} is ready")
                else:
                    logger.warning(f"Service {service_name} not ready")
            
            if ready_services == 0:
                raise Exception("No services are ready")
            
            logger.info(f"Pipeline manager initialized with {ready_services}/3 services ready")
            
        except Exception as e:
            logger.error(f"Failed to initialize pipeline manager: {e}")
            raise
    
    async def create_session(
        self,
        call_id: str = None,
        rtp_transport: RTPTransport = None,
        call_info: Any = None,
        session_config: SessionConfig = None
    ) -> Optional[ConversationSession]:
        """Create new conversation session"""
        try:
            if not call_id:
                call_id = f"session_{int(datetime.now().timestamp())}"
            
            if call_id in self.active_sessions:
                logger.warning(f"Session already exists: {call_id}")
                return self.active_sessions[call_id]
            
            # Use default config if not provided
            config = session_config or self.default_config
            
            # Create conversation session
            session = ConversationSession(
                call_id=call_id,
                asr_client=self.asr_client,
                llm_client=self.llm_client,
                tts_client=self.tts_client,
                rtp_transport=rtp_transport,
                config=config,
                call_info=call_info
            )
            
            # Initialize session
            await session.initialize()
            
            # Store session
            self.active_sessions[call_id] = session
            
            logger.info(f"Conversation session created: {call_id}")
            return session
            
        except Exception as e:
            logger.error(f"Failed to create session {call_id}: {e}")
            return None
    
    async def get_session(self, call_id: str) -> Optional[ConversationSession]:
        """Get existing session"""
        return self.active_sessions.get(call_id)
    
    async def cleanup_session(self, call_id: str):
        """Clean up conversation session"""
        try:
            if call_id in self.active_sessions:
                session = self.active_sessions[call_id]
                await session.cleanup()
                del self.active_sessions[call_id]
                logger.info(f"Session cleaned up: {call_id}")
            else:
                logger.warning(f"Session not found for cleanup: {call_id}")
                
        except Exception as e:
            logger.error(f"Error cleaning up session {call_id}: {e}")
    
    async def stop(self):
        """Stop pipeline manager and clean up all sessions"""
        try:
            logger.info("Stopping pipeline manager")
            
            # Clean up all active sessions
            for call_id in list(self.active_sessions.keys()):
                await self.cleanup_session(call_id)
            
            # Clean up service clients
            if self.asr_client:
                await self.asr_client.cleanup()
            
            if self.llm_client:
                await self.llm_client.cleanup()
            
            if self.tts_client:
                await self.tts_client.cleanup()
            
            logger.info("Pipeline manager stopped")
            
        except Exception as e:
            logger.error(f"Error stopping pipeline manager: {e}")
    
    async def health_check(self) -> Dict[str, Any]:
        """Check health of pipeline manager and services"""
        try:
            health_status = {
                'pipeline_manager': True,
                'active_sessions': len(self.active_sessions),
                'services': {}
            }
            
            # Check service health
            for service_name in ['asr', 'llm', 'tts']:
                is_healthy = self.service_registry.is_service_healthy(service_name)
                health_status['services'][service_name] = is_healthy
            
            # Test service clients if healthy
            if health_status['services'].get('asr'):
                try:
                    asr_healthy = await self.asr_client.health_check()
                    health_status['services']['asr_client'] = asr_healthy
                except:
                    health_status['services']['asr_client'] = False
            
            if health_status['services'].get('llm'):
                try:
                    llm_healthy = await self.llm_client.health_check()
                    health_status['services']['llm_client'] = llm_healthy
                except:
                    health_status['services']['llm_client'] = False
            
            if health_status['services'].get('tts'):
                try:
                    tts_healthy = await self.tts_client.health_check()
                    health_status['services']['tts_client'] = tts_healthy
                except:
                    health_status['services']['tts_client'] = False
            
            return health_status
            
        except Exception as e:
            logger.error(f"Pipeline manager health check failed: {e}")
            return {
                'pipeline_manager': False,
                'error': str(e),
                'active_sessions': len(self.active_sessions)
            }
    
    def get_session_stats(self) -> Dict[str, Any]:
        """Get statistics for all sessions"""
        try:
            stats = {
                'total_sessions': len(self.active_sessions),
                'sessions': {}
            }
            
            for call_id, session in self.active_sessions.items():
                stats['sessions'][call_id] = session.get_stats()
            
            return stats
            
        except Exception as e:
            logger.error(f"Error getting session stats: {e}")
            return {'total_sessions': 0, 'error': str(e)}
    
    async def broadcast_to_sessions(self, message: str):
        """Broadcast message to all active sessions (for debugging/admin)"""
        try:
            logger.info(f"Broadcasting message to {len(self.active_sessions)} sessions: {message}")
            
            for call_id, session in self.active_sessions.items():
                try:
                    # This could be used for system announcements, shutdown notices, etc.
                    await session.send_system_message(message)
                except Exception as e:
                    logger.error(f"Error broadcasting to session {call_id}: {e}")
                    
        except Exception as e:
            logger.error(f"Error broadcasting message: {e}")
    
    def update_default_config(self, new_config: SessionConfig):
        """Update default session configuration"""
        self.default_config = new_config
        logger.info("Default session configuration updated")
    
    async def create_test_session(self, call_id: str = None) -> Optional[ConversationSession]:
        """Create test session without RTP transport (for testing)"""
        try:
            if not call_id:
                call_id = f"test_{int(datetime.now().timestamp())}"
            
            # Create session without RTP transport
            session = await self.create_session(
                call_id=call_id,
                rtp_transport=None,
                call_info={'test': True}
            )
            
            if session:
                logger.info(f"Test session created: {call_id}")
            
            return session
            
        except Exception as e:
            logger.error(f"Failed to create test session: {e}")
            return None