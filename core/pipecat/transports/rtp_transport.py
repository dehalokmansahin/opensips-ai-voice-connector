"""
RTP Transport Integration for Pipecat Pipeline
Integrates OpenSIPS RTP transport with native pipecat framework
"""

import asyncio
import logging
from typing import Optional, Callable, Any, Dict
from ..pipeline.pipeline import Pipeline
from ..processors.grpc_processors import (
    RTPInputProcessor,
    RTPOutputProcessor,
    ASRProcessor,
    LLMProcessor,
    TTSProcessor
)
from ...opensips.rtp_transport import RTPTransport
from ...grpc_clients import ASRClient, LLMClient, TTSClient

logger = logging.getLogger(__name__)

class PipecatRTPTransport:
    """
    RTP Transport with Pipecat Pipeline Integration
    Combines RTP audio handling with AI processing pipeline
    """
    
    def __init__(
        self,
        rtp_transport: RTPTransport,
        asr_client: ASRClient,
        llm_client: LLMClient,
        tts_client: TTSClient,
        session_config: Dict[str, Any],
        call_id: str
    ):
        self.rtp_transport = rtp_transport
        self.asr_client = asr_client
        self.llm_client = llm_client
        self.tts_client = tts_client
        self.session_config = session_config
        self.call_id = call_id
        
        # Pipeline components
        self.pipeline: Optional[Pipeline] = None
        self.processors: Dict[str, Any] = {}
        
        # State
        self._is_running = False
        self._pipeline_task: Optional[asyncio.Task] = None
        
        logger.info(f"Pipecat RTP transport initialized for call: {call_id}")
    
    async def start(self):
        """Start the RTP transport with pipecat pipeline"""
        try:
            logger.info(f"Starting pipecat RTP transport: {self.call_id}")
            
            # Start underlying RTP transport
            await self.rtp_transport.start()
            
            # Create and start pipeline
            await self._create_pipeline()
            await self._start_pipeline()
            
            self._is_running = True
            logger.info(f"Pipecat RTP transport started: {self.call_id}")
            
        except Exception as e:
            logger.error(f"Failed to start pipecat RTP transport: {e}")
            raise
    
    async def stop(self):
        """Stop the RTP transport and pipeline"""
        try:
            logger.info(f"Stopping pipecat RTP transport: {self.call_id}")
            
            self._is_running = False
            
            # Stop pipeline
            await self._stop_pipeline()
            
            # Stop underlying RTP transport
            await self.rtp_transport.stop()
            
            logger.info(f"Pipecat RTP transport stopped: {self.call_id}")
            
        except Exception as e:
            logger.error(f"Error stopping pipecat RTP transport: {e}")
    
    async def _create_pipeline(self):
        """Create the AI processing pipeline"""
        try:
            # Create processors in order
            processors = []
            
            # 1. RTP Input Processor (RTP -> Audio Frames)
            rtp_input = RTPInputProcessor(
                rtp_transport=self.rtp_transport,
                sample_rate=8000,  # RTP audio sample rate
                target_sample_rate=16000,  # ASR expected sample rate
                name=f"RTPInput_{self.call_id}"
            )
            processors.append(rtp_input)
            self.processors['rtp_input'] = rtp_input
            
            # 2. ASR Processor (Audio -> Text)
            asr_processor = ASRProcessor(
                asr_client=self.asr_client,
                on_transcript=self._on_transcript,
                config=self.session_config.get('asr_config', {}),
                name=f"ASR_{self.call_id}"
            )
            processors.append(asr_processor)
            self.processors['asr'] = asr_processor
            
            # 3. LLM Processor (Text -> Text)
            llm_processor = LLMProcessor(
                llm_client=self.llm_client,
                conversation_id=self.call_id,
                system_prompt=self.session_config.get('system_prompt', ''),
                config=self.session_config.get('llm_config', {}),
                name=f"LLM_{self.call_id}"
            )
            processors.append(llm_processor)
            self.processors['llm'] = llm_processor
            
            # 4. TTS Processor (Text -> Audio)
            tts_processor = TTSProcessor(
                tts_client=self.tts_client,
                on_audio=self._on_tts_audio,
                config=self.session_config.get('tts_config', {}),
                name=f"TTS_{self.call_id}"
            )
            processors.append(tts_processor)
            self.processors['tts'] = tts_processor
            
            # 5. RTP Output Processor (Audio -> RTP)
            rtp_output = RTPOutputProcessor(
                rtp_transport=self.rtp_transport,
                sample_rate=22050,  # TTS output sample rate
                target_sample_rate=8000,  # RTP audio sample rate
                name=f"RTPOutput_{self.call_id}"
            )
            processors.append(rtp_output)
            self.processors['rtp_output'] = rtp_output
            
            # Create pipeline
            self.pipeline = Pipeline(processors)
            
            logger.info(f"Pipeline created with {len(processors)} processors: {self.call_id}")
            
        except Exception as e:
            logger.error(f"Failed to create pipeline: {e}")
            raise
    
    async def _start_pipeline(self):
        """Start the processing pipeline"""
        try:
            if not self.pipeline:
                raise Exception("Pipeline not created")
            
            # Start pipeline in separate task
            self._pipeline_task = asyncio.create_task(self.pipeline.start())
            
            logger.info(f"Pipeline started: {self.call_id}")
            
        except Exception as e:
            logger.error(f"Failed to start pipeline: {e}")
            raise
    
    async def _stop_pipeline(self):
        """Stop the processing pipeline"""
        try:
            if self.pipeline:
                await self.pipeline.stop()
            
            # Cancel pipeline task
            if self._pipeline_task and not self._pipeline_task.done():
                self._pipeline_task.cancel()
                try:
                    await self._pipeline_task
                except asyncio.CancelledError:
                    pass
            
            # Cleanup async processors
            for processor in self.processors.values():
                if hasattr(processor, 'cleanup_tasks'):
                    await processor.cleanup_tasks()
            
            logger.info(f"Pipeline stopped: {self.call_id}")
            
        except Exception as e:
            logger.error(f"Error stopping pipeline: {e}")
    
    async def _on_transcript(self, transcript: str):
        """Handle transcript from ASR"""
        try:
            logger.info(f"Transcript [{self.call_id}]: {transcript}")
            # This is handled automatically by the pipeline
            
        except Exception as e:
            logger.error(f"Error handling transcript: {e}")
    
    async def _on_tts_audio(self, audio_data: bytes):
        """Handle TTS audio output"""
        try:
            logger.debug(f"TTS audio generated [{self.call_id}]: {len(audio_data)} bytes")
            # This is handled automatically by the RTP output processor
            
        except Exception as e:
            logger.error(f"Error handling TTS audio: {e}")
    
    def is_running(self) -> bool:
        """Check if transport is running"""
        return self._is_running
    
    def get_stats(self) -> Dict[str, Any]:
        """Get transport statistics"""
        try:
            stats = {
                'call_id': self.call_id,
                'running': self._is_running,
                'pipeline_processors': len(self.processors),
                'rtp_stats': self.rtp_transport.get_stats() if self.rtp_transport else {}
            }
            
            # Add processor-specific stats
            for name, processor in self.processors.items():
                if hasattr(processor, 'get_stats'):
                    stats[f'{name}_stats'] = processor.get_stats()
            
            return stats
            
        except Exception as e:
            logger.error(f"Error getting transport stats: {e}")
            return {'call_id': self.call_id, 'error': str(e)}
    
    async def send_system_message(self, message: str):
        """Send system message through TTS"""
        try:
            if not self._is_running:
                logger.warning("Transport not running, cannot send system message")
                return
            
            # Get TTS processor and synthesize message
            tts_processor = self.processors.get('tts')
            if tts_processor:
                await tts_processor._synthesize_text(message)
            else:
                logger.warning("TTS processor not available for system message")
                
        except Exception as e:
            logger.error(f"Error sending system message: {e}")
    
    async def health_check(self) -> Dict[str, Any]:
        """Perform health check on transport and pipeline"""
        try:
            health_status = {
                'transport_running': self._is_running,
                'rtp_transport_running': self.rtp_transport._running if self.rtp_transport else False,
                'pipeline_created': self.pipeline is not None,
                'processors': {}
            }
            
            # Check processor health
            for name, processor in self.processors.items():
                if hasattr(processor, 'health_check'):
                    try:
                        processor_health = await processor.health_check()
                        health_status['processors'][name] = processor_health
                    except:
                        health_status['processors'][name] = False
                else:
                    health_status['processors'][name] = True  # Assume healthy if no check available
            
            # Overall health
            health_status['overall_healthy'] = (
                health_status['transport_running'] and
                health_status['rtp_transport_running'] and
                health_status['pipeline_created'] and
                all(health_status['processors'].values())
            )
            
            return health_status
            
        except Exception as e:
            logger.error(f"Health check error: {e}")
            return {
                'transport_running': False,
                'error': str(e),
                'overall_healthy': False
            }