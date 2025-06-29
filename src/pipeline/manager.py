"""
Enhanced Pipeline Manager - Pipecat Native Pipeline ile
Frame-based processing, interruption handling ve robust error management
"""

import asyncio
import logging
from typing import Optional, List, Dict, Any
import structlog
from concurrent.futures import ThreadPoolExecutor

from pipecat.frames.frames import (
    Frame, AudioRawFrame, StartFrame, EndFrame, TextFrame, 
    ErrorFrame, StartInterruptionFrame, StopInterruptionFrame,
    SystemFrame
)
from pipecat.clocks.system_clock import SystemClock
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.processors.frame_processor import FrameProcessor

# Local imports
from pipeline.stages import VADProcessor, STTProcessor, LLMProcessor, TTSProcessor
from pipeline.interruption import InterruptionManager, MinWordsInterruptionStrategy, VolumeBasedInterruptionStrategy
from config import ConfigValidationError

logger = structlog.get_logger()

class PipelineError(Exception):
    """Custom exception for pipeline-related errors"""
    pass

class PipelineSource(FrameProcessor):
    """Pipeline source processor for external audio input"""
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._audio_buffer = asyncio.Queue()
        self._running = False
        
    async def start_processing(self):
        """Start the audio processing loop"""
        logger.info("🔁 PipelineSource start_processing loop started")
        self._running = True
        try:
            while self._running:
                try:
                    logger.info("🔂 PipelineSource waiting for audio frame")
                    audio_frame = await asyncio.wait_for(
                        self._audio_buffer.get(), 
                        timeout=0.1
                    )
                    logger.info("🔂 PipelineSource got audio frame", frame_type=type(audio_frame).__name__)
                    await self.push_frame(audio_frame)
                    
                except asyncio.TimeoutError:
                    continue
                except Exception as e:
                    logger.error("Error in pipeline source processing", error=str(e))
                    await self.push_error(ErrorFrame(f"Pipeline source error: {str(e)}"))
                    
        except Exception as e:
            logger.error("Fatal error in pipeline source", error=str(e))
            await self.push_error(ErrorFrame(f"Fatal pipeline source error: {str(e)}", fatal=True))
    
    async def feed_audio(self, audio_frame: AudioRawFrame):
        """Feed audio frame to the pipeline"""
        if self._running:
            await self._audio_buffer.put(audio_frame)
    
    async def stop_processing(self):
        """Stop the audio processing"""
        self._running = False
        
    async def process_frame(self, frame: Frame, direction):
        logger.info("🔍 PipelineSource.process_frame called", frame_type=type(frame).__name__)
        """Process frames - mainly for system frames"""
        await super().process_frame(frame, direction)
        
        if isinstance(frame, StartFrame):
            # Start the processing task
            logger.info("!!! 🚀 PipelineSource received StartFrame, creating processing task.")
            asyncio.create_task(self.start_processing())
        elif isinstance(frame, EndFrame):
            await self.stop_processing()

class PipelineSink(FrameProcessor):
    """Pipeline sink processor for collecting outputs"""
    
    def __init__(self, output_callback=None, **kwargs):
        super().__init__(**kwargs)
        self._output_callback = output_callback
        self._outputs = []
        
    async def process_frame(self, frame: Frame, direction):
        """Process output frames"""
        await super().process_frame(frame, direction)
        
        try:
            # Collect outputs
            if isinstance(frame, AudioRawFrame):
                self._outputs.append(('audio', frame.audio))
                if self._output_callback:
                    await self._output_callback('audio', frame.audio)
                    
            elif isinstance(frame, TextFrame):
                self._outputs.append(('text', frame.text))
                if self._output_callback:
                    await self._output_callback('text', frame.text)
                    
            elif isinstance(frame, ErrorFrame):
                logger.error("Pipeline error received in sink", error=frame.error)
                if self._output_callback:
                    await self._output_callback('error', frame.error)
                    
        except Exception as e:
            logger.error("Error in pipeline sink", error=str(e))
            await self.push_error(ErrorFrame(f"Pipeline sink error: {str(e)}"))

class EnhancedPipelineManager:
    """Enhanced Pipeline Manager using Pipecat native Pipeline with robust error handling"""
    
    def __init__(self, llm_service=None, stt_service=None, tts_service=None, 
                 enable_interruption: bool = True, audio_in_enabled: bool = True, 
                 audio_out_enabled: bool = True, config: Dict[str, Any] = None):
        
        # Core pipeline components
        self._pipeline: Optional[Pipeline] = None
        self._pipeline_task: Optional[PipelineTask] = None
        self._pipeline_source: Optional[PipelineSource] = None
        self._pipeline_sink: Optional[PipelineSink] = None
        
        # Services with validation
        self._llm_service = llm_service
        self._stt_service = stt_service
        self._tts_service = tts_service
        
        # Configuration
        self._config = config or {}
        self._audio_in_enabled = audio_in_enabled
        self._audio_out_enabled = audio_out_enabled
        self._enable_interruption = enable_interruption
        
        # State management
        self._is_running = False
        self._lock = asyncio.Lock()
        self._executor = None
        
        # Error handling
        self._error_count = 0
        self._max_errors = self._config.get("max_pipeline_errors", 10)
        self._error_reset_interval = self._config.get("error_reset_interval", 300)  # 5 minutes
        self._last_error_reset = asyncio.get_event_loop().time()
        
        # Interruption management
        self._interruption_manager = None
        self._bot_speaking = False
        self._user_speaking = False
        
        # Performance tracking
        self._frame_count = 0
        self._error_frames = 0
        self._start_time = None
        
        logger.info("Enhanced Pipeline Manager initialized", 
                   enable_interruption=enable_interruption,
                   audio_in_enabled=audio_in_enabled,
                   audio_out_enabled=audio_out_enabled,
                   max_errors=self._max_errors)
    
    async def _validate_services(self):
        """Validate that all required services are available"""
        missing_services = []
        
        if not self._llm_service:
            missing_services.append("LLM")
        if not self._stt_service:
            missing_services.append("STT")
        if not self._tts_service:
            missing_services.append("TTS")
            
        if missing_services:
            raise PipelineError(f"Missing required services: {', '.join(missing_services)}")
        
        # Test service connectivity if they have a start method
        for service_name, service in [
            ("LLM", self._llm_service),
            ("STT", self._stt_service), 
            ("TTS", self._tts_service)
        ]:
            if hasattr(service, 'start'):
                try:
                    await service.start()
                    logger.info(f"✅ {service_name} service started successfully")
                except Exception as e:
                    logger.error(f"❌ {service_name} service failed to start", error=str(e))
                    raise PipelineError(f"{service_name} service initialization failed: {str(e)}")
    
    async def _create_pipeline_processors(self) -> List[FrameProcessor]:
        """Create and configure pipeline processors"""
        try:
            # Import VAD config
            from pipeline.vad_config import DEFAULT_VAD_CONFIG
            
            # Create processors with enhanced error handling
            processors = [
                VADProcessor(
                    vad_config=DEFAULT_VAD_CONFIG,
                    error_callback=self._handle_processor_error
                ),
                STTProcessor(
                    stt_service=self._stt_service,
                    error_callback=self._handle_processor_error
                ),
                LLMProcessor(
                    llm_service=self._llm_service,
                    error_callback=self._handle_processor_error
                ),
                TTSProcessor(
                    tts_service=self._tts_service,
                    error_callback=self._handle_processor_error
                )
            ]
            
            logger.info("Pipeline processors created successfully", 
                       processor_count=len(processors))
            return processors
            
        except Exception as e:
            logger.error("Failed to create pipeline processors", error=str(e))
            raise PipelineError(f"Processor creation failed: {str(e)}")
    
    async def _setup_interruption_manager(self):
        """Setup interruption manager with enhanced configuration"""
        if not self._enable_interruption:
            return
            
        try:
            # Get interruption config from configuration
            interruption_config = self._config.get("interruption", {})
            
            # Create interruption strategies
            strategies = []
            
            # Min words strategy
            min_words = interruption_config.get("min_words", 2)
            strategies.append(MinWordsInterruptionStrategy(min_words=min_words))
            
            # Volume-based strategy
            volume_threshold = interruption_config.get("volume_threshold", 0.6)
            min_duration_ms = interruption_config.get("min_duration_ms", 300)
            strategies.append(VolumeBasedInterruptionStrategy(
                volume_threshold=volume_threshold,
                min_duration_ms=min_duration_ms
            ))
            
            self._interruption_manager = InterruptionManager(strategies=strategies)
            
            logger.info("Interruption manager setup completed",
                       strategies=[type(s).__name__ for s in strategies],
                       min_words=min_words,
                       volume_threshold=volume_threshold,
                       min_duration_ms=min_duration_ms)
                       
        except Exception as e:
            logger.error("Failed to setup interruption manager", error=str(e))
            raise PipelineError(f"Interruption manager setup failed: {str(e)}")
    
    async def _handle_processor_error(self, processor_name: str, error: Exception):
        """Handle processor-specific errors"""
        self._error_count += 1
        self._error_frames += 1
        
        logger.error(f"Processor error in {processor_name}", 
                    error=str(error),
                    error_count=self._error_count,
                    processor=processor_name)
        
        # Check if we've exceeded error threshold
        if self._error_count >= self._max_errors:
            logger.critical("Maximum pipeline errors exceeded, shutting down",
                           max_errors=self._max_errors,
                           error_count=self._error_count)
            await self._handle_critical_error(f"Too many errors ({self._error_count})")
        
        # Reset error count periodically
        current_time = asyncio.get_event_loop().time()
        if current_time - self._last_error_reset > self._error_reset_interval:
            self._error_count = 0
            self._last_error_reset = current_time
            logger.info("Error count reset", interval=self._error_reset_interval)
    
    async def _handle_critical_error(self, error_message: str):
        """Handle critical pipeline errors"""
        logger.critical("Critical pipeline error", error=error_message)
        
        try:
            # Stop the pipeline gracefully
            await self.stop()
        except Exception as e:
            logger.error("Error during emergency pipeline shutdown", error=str(e))
        
        # Raise the error to be handled by the caller
        raise PipelineError(f"Critical pipeline error: {error_message}")
    
    async def _output_callback(self, output_type: str, data: Any):
        """Handle pipeline outputs"""
        try:
            if output_type == 'audio' and self._audio_out_enabled:
                logger.debug("Audio output received", size=len(data) if data else 0)
                # Here you would typically send the audio to the output stream
                
            elif output_type == 'text':
                logger.info("Text output received", text=data[:100] if data else "")
                # Handle text output (could be LLM response or STT transcription)
                
            elif output_type == 'error':
                await self._handle_processor_error("output_callback", Exception(data))
                
        except Exception as e:
            logger.error("Error in output callback", error=str(e))
    
    async def start(self) -> None:
        """Start the enhanced pipeline with comprehensive error handling"""
        async with self._lock:
            if self._is_running:
                logger.warning("Pipeline already running")
                return
            
            try:
                self._start_time = asyncio.get_event_loop().time()
                
                # Validate services first
                await self._validate_services()
                
                # Create thread pool executor
                self._executor = ThreadPoolExecutor(
                    max_workers=self._config.get("max_threads", 4),
                    thread_name_prefix="pipeline"
                )
                
                # Setup interruption manager
                await self._setup_interruption_manager()
                
                # Create pipeline processors
                processors = await self._create_pipeline_processors()
                
                # Create pipeline source and sink
                self._pipeline_source = PipelineSource()
                self._pipeline_sink = PipelineSink(output_callback=self._output_callback)
                
                # Create the complete processor chain
                complete_processors = [self._pipeline_source] + processors + [self._pipeline_sink]
                
                # Create Pipecat native pipeline
                self._pipeline = Pipeline(complete_processors)
                
                # Create pipeline task with proper parameters
                params = PipelineParams(
                    allow_interruptions=self._enable_interruption,
                    enable_metrics=True,
                    enable_usage_metrics=True
                )
                
                self._pipeline_task = PipelineTask(self._pipeline, params=params)
                
                # Start the pipeline task
                logger.info("🎬 QUEUEING initial StartFrame to pipeline task...")
                await self._pipeline_task.queue_frame(StartFrame())
                logger.info("✅ Initial StartFrame has been queued.")
                
                self._is_running = True
                self._frame_count = 0
                self._error_frames = 0
                self._start_frame_sent = False  # Reset StartFrame flag
                
                logger.info("✅ Enhanced pipeline started successfully", 
                           interruption_enabled=self._enable_interruption,
                           processor_count=len(complete_processors),
                           max_errors=self._max_errors)
                
            except Exception as e:
                logger.error("❌ Failed to start enhanced pipeline", error=str(e))
                # Cleanup on failure
                await self._cleanup_on_failure()
                raise PipelineError(f"Pipeline start failed: {str(e)}")
    
    async def _cleanup_on_failure(self):
        """Cleanup resources on pipeline start failure"""
        try:
            if self._executor:
                self._executor.shutdown(wait=False)
                self._executor = None
                
            if self._pipeline_task:
                self._pipeline_task = None
                
            if self._pipeline:
                self._pipeline = None
                
            self._is_running = False
            
            logger.info("Pipeline cleanup completed after failure")
            
        except Exception as e:
            logger.error("Error during pipeline cleanup", error=str(e))
    
    async def stop(self) -> None:
        """Stop the pipeline with proper cleanup"""
        async with self._lock:
            if not self._is_running:
                logger.info("Pipeline already stopped")
                return
            
            try:
                # Send end frame to pipeline
                if self._pipeline_task:
                    await self._pipeline_task.queue_frame(EndFrame())
                
                # Stop interruption manager
                if self._interruption_manager:
                    await self._interruption_manager.reset_interruption()
                
                # Shutdown executor
                if self._executor:
                    self._executor.shutdown(wait=True)
                    self._executor = None
                
                # Calculate runtime stats
                if self._start_time:
                    runtime = asyncio.get_event_loop().time() - self._start_time
                    logger.info("Pipeline runtime statistics",
                               runtime_seconds=round(runtime, 2),
                               total_frames=self._frame_count,
                               error_frames=self._error_frames,
                               error_rate=round(self._error_frames / max(self._frame_count, 1) * 100, 2))
                
                # Reset state
                self._pipeline_task = None
                self._pipeline = None
                self._pipeline_source = None
                self._pipeline_sink = None
                self._is_running = False
                
                logger.info("✅ Enhanced pipeline stopped successfully")
                
            except Exception as e:
                logger.error("❌ Error stopping enhanced pipeline", error=str(e))
                raise PipelineError(f"Pipeline stop failed: {str(e)}")
    
    async def push_audio(self, pcm_bytes: bytes) -> None:
        """Push audio data to the pipeline with error handling"""
        if not self._is_running:
            logger.warning("Pipeline not running, cannot push audio")
            return
            
        if not self._audio_in_enabled:
            logger.debug("Audio input disabled, skipping audio processing")
            return
        
        try:
            # Send StartFrame on first audio if not already sent
            logger.debug("🔍 STARTFRAME CHECK", 
                        has_start_frame_sent=hasattr(self, '_start_frame_sent') and self._start_frame_sent,
                        has_pipeline_task=bool(self._pipeline_task))
            
            if not hasattr(self, '_start_frame_sent') or not self._start_frame_sent:
                if self._pipeline_task:
                    logger.info("!!! 🎬 QUEUEING StartFrame from push_audio...")
                    start_frame = StartFrame()
                    await self._pipeline_task.queue_frame(start_frame)
                    self._start_frame_sent = True
                    logger.info("!!! 🚀 StartFrame SENT to pipeline from push_audio! VAD/STT/LLM/TTS should start now")
                else:
                    logger.warning("❌ Cannot send StartFrame - no pipeline_task")
            else:
                logger.debug("✅ StartFrame already sent previously")
            
            # Create audio frame
            audio_frame = AudioRawFrame(
                audio=pcm_bytes,
                sample_rate=16000,
                num_channels=1
            )
            
            # Feed to pipeline source
            if self._pipeline_source:
                await self._pipeline_source.feed_audio(audio_frame)
                self._frame_count += 1
                
                # Interruption handling
                if self._interruption_manager and self._user_speaking:
                    await self._interruption_manager.append_user_audio(pcm_bytes, 16000)
                
                logger.debug("Audio frame pushed to pipeline", 
                           size=len(pcm_bytes),
                           frame_count=self._frame_count)
            else:
                logger.warning("Pipeline source not available")
                
        except Exception as e:
            logger.error("Error pushing audio to pipeline", error=str(e))
            await self._handle_processor_error("push_audio", e)
    
    async def handle_user_text(self, text: str) -> None:
        """Handle user text input with interruption management"""
        if not self._is_running:
            logger.warning("Pipeline not running, cannot handle user text")
            return
            
        try:
            # Interruption handling
            if self._interruption_manager:
                await self._interruption_manager.append_user_text(text)
                
                # Check for interruption
                interrupted = await self._interruption_manager.check_interruption()
                if interrupted:
                    logger.info("🛑 User interrupted bot!", text=text[:30])
                    await self._handle_interruption()
            
            # Send text frame to pipeline
            if self._pipeline_task:
                text_frame = TextFrame(text=text)
                await self._pipeline_task.queue_frame(text_frame)
                self._frame_count += 1
                
                logger.info("User text processed", text=text[:50], frame_count=self._frame_count)
            
        except Exception as e:
            logger.error("Error handling user text", error=str(e), text=text[:50])
            await self._handle_processor_error("handle_user_text", e)
    
    async def _handle_interruption(self) -> None:
        """Handle user interruption"""
        try:
            if self._pipeline_task:
                # Send interruption frames
                await self._pipeline_task.queue_frame(StartInterruptionFrame())
                
                # Cancel current bot speech
                self._bot_speaking = False
                
                # Reset TTS if needed
                if self._tts_service and hasattr(self._tts_service, 'cancel_current_speech'):
                    await self._tts_service.cancel_current_speech()
                
                # Send stop interruption frame
                await self._pipeline_task.queue_frame(StopInterruptionFrame())
                
                logger.info("Interruption handled successfully")
                
        except Exception as e:
            logger.error("Error handling interruption", error=str(e))
            await self._handle_processor_error("handle_interruption", e)
    
    async def set_user_speaking(self, speaking: bool) -> None:
        """Update user speaking state"""
        self._user_speaking = speaking
        
        if self._interruption_manager:
            await self._interruption_manager.set_user_speaking(speaking)
        
        logger.debug("User speaking state updated", speaking=speaking)
    
    def get_pipeline_stats(self) -> Dict[str, Any]:
        """Get pipeline performance statistics"""
        runtime = 0
        if self._start_time:
            runtime = asyncio.get_event_loop().time() - self._start_time
            
        return {
            "is_running": self._is_running,
            "runtime_seconds": round(runtime, 2),
            "total_frames": self._frame_count,
            "error_frames": self._error_frames,
            "error_rate": round(self._error_frames / max(self._frame_count, 1) * 100, 2),
            "error_count": self._error_count,
            "interruption_enabled": self._enable_interruption,
            "audio_in_enabled": self._audio_in_enabled,
            "audio_out_enabled": self._audio_out_enabled,
            "bot_speaking": self._bot_speaking,
            "user_speaking": self._user_speaking
        }
    
    @property
    def is_running(self) -> bool:
        """Check if pipeline is running"""
        return self._is_running
    
    @property
    def interruption_enabled(self) -> bool:
        """Check if interruption is enabled"""
        return self._enable_interruption

# Backward compatibility alias
SimplePipelineManager = EnhancedPipelineManager 