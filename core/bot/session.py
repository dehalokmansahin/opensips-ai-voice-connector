"""
Conversation Session for OpenSIPS AI Voice Connector
Manages individual conversation flows
"""

import asyncio
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime
from enum import Enum

try:
    from ..grpc_clients import ASRClient, TTSClient, IntentClient
    from ..grpc_clients.asr_client import StreamingSession as ASRStreamingSession
    from ..grpc_clients.tts_client import SentenceFlushAggregator
except ImportError:
    # Fallback for external imports
    from core.grpc_clients import ASRClient, TTSClient, IntentClient
    from core.grpc_clients.asr_client import StreamingSession as ASRStreamingSession
    from core.grpc_clients.tts_client import SentenceFlushAggregator
try:
    from ..opensips.rtp_transport import RTPTransport
    from ..pipecat.transports import PipecatRTPTransport
except ImportError:
    # Fallback for external imports
    from core.opensips.rtp_transport import RTPTransport
    from core.pipecat.transports import PipecatRTPTransport

logger = logging.getLogger(__name__)

class SessionState(Enum):
    """Session state enumeration"""
    INITIALIZING = "initializing"
    ACTIVE = "active"
    WAITING_FOR_INPUT = "waiting_for_input"
    PROCESSING = "processing"
    RESPONDING = "responding"
    PAUSED = "paused"
    ENDING = "ending"
    CLOSED = "closed"

class ConversationSession:
    """
    Individual conversation session
    Manages the complete conversation flow for one call
    """
    
    def __init__(
        self,
        call_id: str,
        asr_client: ASRClient,
        intent_client: IntentClient,
        tts_client: TTSClient,
        rtp_transport: Optional[RTPTransport] = None,
        config: Any = None,
        call_info: Any = None
    ):
        self.call_id = call_id
        self.asr_client = asr_client
        self.intent_client = intent_client
        self.tts_client = tts_client
        self.rtp_transport = rtp_transport
        self.config = config
        self.call_info = call_info
        
        # Session state
        self.state = SessionState.INITIALIZING
        self.created_at = datetime.now()
        self.last_activity = datetime.now()
        
        # Conversation components
        self.asr_session: Optional[ASRStreamingSession] = None
        self.conversation_manager: Optional[ConversationManager] = None
        self.tts_aggregator: Optional[SentenceFlushAggregator] = None
        
        # Pipecat integration
        self.pipecat_transport: Optional[PipecatRTPTransport] = None
        self.use_pipecat = True  # Enable pipecat integration
        
        # Conversation tracking
        self.transcript: List[Dict[str, Any]] = []
        self.message_count = 0
        self.error_count = 0
        
        # Audio processing
        self.audio_buffer = bytearray()
        self.silence_timeout = 3.0  # seconds
        self.silence_task: Optional[asyncio.Task] = None
        
        # Control flags
        self._processing_audio = False
        self._generating_response = False
        self._cleanup_started = False
        
    async def initialize(self):
        """Initialize conversation session"""
        try:
            logger.info(f"Initializing conversation session: {self.call_id}")
            
            if self.use_pipecat and self.rtp_transport:
                # Use pipecat-integrated transport
                await self._initialize_pipecat_transport()
            else:
                # Use legacy approach
                await self._initialize_legacy_components()
            
            # Send welcome message
            await self._send_welcome_message()
            
            self.state = SessionState.ACTIVE
            logger.info(f"Conversation session initialized: {self.call_id}")
            
        except Exception as e:
            logger.error(f"Failed to initialize session {self.call_id}: {e}")
            self.state = SessionState.CLOSED
            raise
    
    async def _initialize_pipecat_transport(self):
        """Initialize pipecat-integrated RTP transport"""
        try:
            logger.info(f"Initializing pipecat transport: {self.call_id}")
            
            # Create session configuration for pipecat
            session_config = {
                'asr_config': self.config.asr_config if self.config else {},
                'intent_config': self.config.intent_config if self.config else {},
                'tts_config': self.config.tts_config if self.config else {}
            }
            
            # Create pipecat RTP transport
            self.pipecat_transport = PipecatRTPTransport(
                rtp_transport=self.rtp_transport,
                asr_client=self.asr_client,
                intent_client=self.intent_client,
                tts_client=self.tts_client,
                session_config=session_config,
                call_id=self.call_id
            )
            
            # Start the integrated transport
            await self.pipecat_transport.start()
            
            logger.info(f"Pipecat transport initialized: {self.call_id}")
            
        except Exception as e:
            logger.error(f"Failed to initialize pipecat transport: {e}")
            raise
    
    async def _initialize_legacy_components(self):
        """Initialize intent-based conversation components"""
        try:
            logger.info(f"Initializing intent-based components: {self.call_id}")
            
            # Initialize TTS aggregator
            self.tts_aggregator = SentenceFlushAggregator(
                tts_client=self.tts_client,
                on_audio=self._on_tts_audio
            )
            
            # Set up RTP transport if available
            if self.rtp_transport:
                self.rtp_transport.on_audio_received = self._on_audio_received
            
            # Initialize ASR streaming session
            await self._initialize_asr_session()
            
            logger.info(f"Intent-based components initialized: {self.call_id}")
            
        except Exception as e:
            logger.error(f"Failed to initialize intent-based components: {e}")
            raise
    
    async def _initialize_asr_session(self):
        """Initialize ASR streaming session"""
        try:
            if not self.asr_client:
                logger.warning("No ASR client available")
                return
            
            # Configure ASR
            asr_config = self.config.asr_config if self.config else {}
            
            # Create ASR streaming session
            self.asr_session = await self.asr_client.start_streaming_session(
                on_transcript=self._on_partial_transcript,
                on_final=self._on_final_transcript,
                config=asr_config
            )
            
            # Start ASR session
            await self.asr_session.start()
            logger.info(f"ASR session started for call: {self.call_id}")
            
        except Exception as e:
            logger.error(f"Failed to initialize ASR session: {e}")
            raise
    
    async def _send_welcome_message(self):
        """Send welcome message to user"""
        try:
            welcome_message = "Merhaba! Size nasıl yardımcı olabilirim?"
            
            if self.pipecat_transport:
                # Use pipecat transport
                await self.pipecat_transport.send_system_message(welcome_message)
            else:
                # Use legacy method
                await self._generate_and_send_tts(welcome_message)
            
            # Add to transcript
            self._add_to_transcript("assistant", welcome_message)
            
        except Exception as e:
            logger.error(f"Failed to send welcome message: {e}")
    
    async def _on_audio_received(self, audio_data: bytes):
        """Handle incoming audio from RTP"""
        try:
            if self.state not in [SessionState.ACTIVE, SessionState.WAITING_FOR_INPUT]:
                return
            
            self.last_activity = datetime.now()
            
            # Convert from 8kHz PCMU to 16kHz PCM if needed
            processed_audio = await self._process_incoming_audio(audio_data)
            
            # Send to ASR
            if self.asr_session and processed_audio:
                await self.asr_session.add_audio(processed_audio)
            
            # Reset silence timeout
            await self._reset_silence_timeout()
            
        except Exception as e:
            logger.error(f"Error processing audio: {e}")
            self.error_count += 1
    
    async def _process_incoming_audio(self, audio_data: bytes) -> bytes:
        """Process incoming RTP audio for ASR"""
        try:
            # For now, assume audio is already in correct format
            # In production, you might need format conversion here
            return audio_data
            
        except Exception as e:
            logger.error(f"Error processing incoming audio: {e}")
            return b''
    
    async def _on_partial_transcript(self, transcript: str):
        """Handle partial transcript from ASR"""
        try:
            logger.debug(f"Partial transcript [{self.call_id}]: {transcript}")
            
            # Could be used for real-time feedback, but for now just log
            self.last_activity = datetime.now()
            
        except Exception as e:
            logger.error(f"Error handling partial transcript: {e}")
    
    async def _on_final_transcript(self, transcript: str):
        """Handle final transcript from ASR"""
        try:
            if not transcript or not transcript.strip():
                return
            
            logger.info(f"Final transcript [{self.call_id}]: {transcript}")
            
            # Add to transcript
            self._add_to_transcript("user", transcript)
            
            # Process user input
            await self._process_user_input(transcript)
            
        except Exception as e:
            logger.error(f"Error handling final transcript: {e}")
            self.error_count += 1
    
    async def _process_user_input(self, user_text: str):
        """Process user input and generate response"""
        try:
            if self._generating_response:
                logger.debug("Already generating response, ignoring new input")
                return
            
            self._generating_response = True
            self.state = SessionState.PROCESSING
            
            logger.info(f"Processing user input [{self.call_id}]: {user_text}")
            
            # Get LLM response
            llm_config = self.config.llm_config if self.config else {}
            
            response = await self.conversation_manager.send_message(
                user_text=user_text,
                **llm_config
            )
            
            if response:
                logger.info(f"LLM response [{self.call_id}]: {response}")
                
                # Add to transcript
                self._add_to_transcript("assistant", response)
                
                # Generate TTS
                await self._generate_and_send_tts(response)
            else:
                logger.warning(f"No response from LLM for call: {self.call_id}")
                await self._handle_error_response()
            
        except Exception as e:
            logger.error(f"Error processing user input: {e}")
            await self._handle_error_response()
        finally:
            self._generating_response = False
            self.state = SessionState.WAITING_FOR_INPUT
    
    async def _generate_and_send_tts(self, text: str):
        """Generate TTS and send audio"""
        try:
            self.state = SessionState.RESPONDING
            
            # Use TTS aggregator for sentence-based synthesis
            await self.tts_aggregator.add_text(text)
            await self.tts_aggregator.flush()
            
        except Exception as e:
            logger.error(f"Error generating TTS: {e}")
            self.error_count += 1
    
    async def _on_tts_audio(self, audio_data: bytes):
        """Handle TTS audio output"""
        try:
            if self.rtp_transport:
                # Convert from 22kHz to 8kHz if needed for RTP
                processed_audio = await self._process_outgoing_audio(audio_data)
                await self.rtp_transport.send_audio(processed_audio)
            else:
                logger.debug(f"TTS audio generated (no RTP transport): {len(audio_data)} bytes")
                
        except Exception as e:
            logger.error(f"Error sending TTS audio: {e}")
    
    async def _process_outgoing_audio(self, audio_data: bytes) -> bytes:
        """Process TTS audio for RTP transmission"""
        try:
            # For now, assume audio is in correct format
            # In production, you might need sample rate conversion here
            return audio_data
            
        except Exception as e:
            logger.error(f"Error processing outgoing audio: {e}")
            return audio_data
    
    async def _handle_error_response(self):
        """Handle error by sending error message"""
        try:
            error_message = "Üzgünüm, anlayamadım. Tekrar söyleyebilir misiniz?"
            await self._generate_and_send_tts(error_message)
            
        except Exception as e:
            logger.error(f"Error handling error response: {e}")
    
    async def _reset_silence_timeout(self):
        """Reset silence timeout timer"""
        try:
            # Cancel existing timeout
            if self.silence_task and not self.silence_task.done():
                self.silence_task.cancel()
            
            # Start new timeout
            self.silence_task = asyncio.create_task(self._handle_silence_timeout())
            
        except Exception as e:
            logger.error(f"Error resetting silence timeout: {e}")
    
    async def _handle_silence_timeout(self):
        """Handle silence timeout"""
        try:
            await asyncio.sleep(self.silence_timeout)
            
            # Check if still silent
            if self.state == SessionState.WAITING_FOR_INPUT:
                logger.info(f"Silence timeout for call: {self.call_id}")
                
                # Send prompt message
                prompt_message = "Hala orada mısınız? Size nasıl yardımcı olabilirim?"
                await self._generate_and_send_tts(prompt_message)
                
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Error handling silence timeout: {e}")
    
    def _add_to_transcript(self, role: str, content: str):
        """Add message to transcript"""
        self.transcript.append({
            'role': role,
            'content': content,
            'timestamp': datetime.now().isoformat()
        })
        
        if role == "user":
            self.message_count += 1
    
    async def send_system_message(self, message: str):
        """Send system message (for broadcasting, etc.)"""
        try:
            system_message = f"Sistem mesajı: {message}"
            
            if self.pipecat_transport:
                # Use pipecat transport
                await self.pipecat_transport.send_system_message(system_message)
            else:
                # Use legacy method
                await self._generate_and_send_tts(system_message)
            
        except Exception as e:
            logger.error(f"Error sending system message: {e}")
    
    async def pause(self):
        """Pause the session"""
        self.state = SessionState.PAUSED
        logger.info(f"Session paused: {self.call_id}")
    
    async def resume(self):
        """Resume the session"""
        self.state = SessionState.ACTIVE
        logger.info(f"Session resumed: {self.call_id}")
    
    async def cleanup(self):
        """Clean up session resources"""
        try:
            if self._cleanup_started:
                return
            
            self._cleanup_started = True
            self.state = SessionState.ENDING
            
            logger.info(f"Cleaning up session: {self.call_id}")
            
            # Cancel silence timeout
            if self.silence_task and not self.silence_task.done():
                self.silence_task.cancel()
                try:
                    await self.silence_task
                except asyncio.CancelledError:
                    pass
            
            # Clean up pipecat transport
            if self.pipecat_transport:
                await self.pipecat_transport.stop()
                self.pipecat_transport = None
            
            # Stop ASR session (legacy)
            if self.asr_session:
                await self.asr_session.stop()
            
            # Clean up RTP transport (don't stop it, just remove callback)
            if self.rtp_transport:
                self.rtp_transport.on_audio_received = None
            
            self.state = SessionState.CLOSED
            logger.info(f"Session cleanup completed: {self.call_id}")
            
        except Exception as e:
            logger.error(f"Error cleaning up session {self.call_id}: {e}")
    
    def get_stats(self) -> Dict[str, Any]:
        """Get session statistics"""
        try:
            duration = (datetime.now() - self.created_at).total_seconds()
            idle_time = (datetime.now() - self.last_activity).total_seconds()
            
            stats = {
                'call_id': self.call_id,
                'state': self.state.value,
                'created_at': self.created_at.isoformat(),
                'duration_seconds': duration,
                'idle_time_seconds': idle_time,
                'message_count': self.message_count,
                'error_count': self.error_count,
                'transcript_length': len(self.transcript),
                'has_rtp_transport': self.rtp_transport is not None,
                'generating_response': self._generating_response,
                'processing_audio': self._processing_audio,
                'use_pipecat': self.use_pipecat,
                'has_pipecat_transport': self.pipecat_transport is not None
            }
            
            # Add pipecat transport stats if available
            if self.pipecat_transport:
                stats['pipecat_transport_stats'] = self.pipecat_transport.get_stats()
            
            return stats
            
        except Exception as e:
            logger.error(f"Error getting session stats: {e}")
            return {'call_id': self.call_id, 'error': str(e)}
    
    def get_transcript(self) -> List[Dict[str, Any]]:
        """Get session transcript"""
        return self.transcript.copy()