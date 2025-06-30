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
from pipecat.pipeline.base_task import PipelineTaskParams
from pipecat.processors.frame_processor import FrameProcessor, FrameDirection
from pipecat.pipeline.runner import PipelineRunner
from transports.oavc_adapter import OAVCAdapter

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
        
        # First, forward the frame to downstream processors
        await super().process_frame(frame, direction)
        
        if isinstance(frame, StartFrame):
            # Start the processing task
            logger.info("!!! 🚀 PipelineSource received StartFrame, creating processing task.")
            asyncio.create_task(self.start_processing())
        elif isinstance(frame, EndFrame):
            await self.stop_processing()

class PipelineSink(FrameProcessor):
    """Pipeline sink processor for collecting outputs"""
    
    def __init__(self, output_callback=None, ready_event=None, **kwargs):
        super().__init__(**kwargs)
        self._output_callback = output_callback
        self._outputs = []
        self._ready_event = ready_event
        
    async def process_frame(self, frame: Frame, direction):
        """Process output frames"""
        await super().process_frame(frame, direction)
        
        if isinstance(frame, StartFrame) and self._ready_event:
            logger.info("🏁 PipelineSink received StartFrame, signaling pipeline is ready.")
            self._ready_event.set()
        
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
        self._pipeline_ready_event = asyncio.Event()
        self._output_queue = asyncio.Queue()
        
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
        processors = []
        try:
            # VAD
            vad_config = self._config.get("vad", {})
            processors.append(VADProcessor(**vad_config))

            # STT
            if self._audio_in_enabled and self._stt_service:
                processors.append(self._stt_service)

            # LLM
            if self._llm_service:
                processors.append(self._llm_service)
            
            # TTS
            if self._audio_out_enabled and self._tts_service:
                processors.append(self._tts_service)

            logger.info("Pipeline processors created", count=len(processors))
        except Exception as e:
            logger.error(f"Error creating pipeline processors: {e}")
            raise PipelineError(f"Processor creation failed: {e}") from e

        return processors
    
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
            
            # Volume based strategy
            if interruption_config.get("use_volume_strategy", False):
                volume_config = interruption_config.get("volume_strategy_config", {})
                strategies.append(VolumeBasedInterruptionStrategy(**volume_config))
            
            # Create interruption manager
            self._interruption_manager = InterruptionManager(
                strategies=strategies,
                interruption_callback=self._handle_interruption
            )
            logger.info("Interruption manager setup complete", strategies=len(strategies))
            
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
        """Handle pipeline outputs by putting them in a queue"""
        try:
            await self._output_queue.put((output_type, data))
        except Exception as e:
            logger.error("Error in output callback", error=str(e))

    async def get_output(self):
        """Get output from the pipeline queue."""
        try:
            return await self._output_queue.get()
        except asyncio.CancelledError:
            logger.info("get_output task cancelled.")
            return None, None

    async def start(self) -> None:
        """Start the pipeline manager and create the pipeline"""
        async with self._lock:
            if self.is_running:
                logger.warning("Pipeline is already running")
                return
            
            self._is_running = True
            self._start_time = asyncio.get_event_loop().time()
            self._error_count = 0
            
            logger.info("🚀 Starting Enhanced Pipeline Manager...")
            
            try:
                # Setup thread pool executor for CPU-bound tasks
                self._executor = ThreadPoolExecutor(max_workers=4)
                
                # Validate and start services
                await self._validate_services()
                
                # Setup interruption manager
                await self._setup_interruption_manager()
                
                # Create the pipeline
                self._pipeline_ready_event.clear()
                
                # Create pipeline source and sink
                self._pipeline_source = PipelineSource()
                self._pipeline_sink = PipelineSink(
                    output_callback=self._output_callback,
                    ready_event=self._pipeline_ready_event
                )
                
                # Create pipeline processors
                processors = await self._create_pipeline_processors()
                
                # Build the pipeline
                self._pipeline = Pipeline(
                    processors=[
                        self._pipeline_source,
                        *processors,
                        self._pipeline_sink
                    ]
                )
                
                # Create and run the pipeline task
                self._pipeline_task = PipelineTask(
                    self._pipeline,
                    params=PipelineParams(
                        allow_interruptions=self._enable_interruption,
                        enable_goodbye_frame=True
                    )
                )
                
                # Run the pipeline in a background task
                asyncio.create_task(self._pipeline_task.run())
                
                # Wait for the pipeline to be ready
                await asyncio.wait_for(self._pipeline_ready_event.wait(), timeout=10.0)
                
                logger.info("✅ Enhanced Pipeline Manager started successfully")

            except asyncio.TimeoutError:
                logger.error("Pipeline readiness timed out")
                await self._cleanup_on_failure()
                raise PipelineError("Pipeline readiness timed out")
            except Exception as e:
                import traceback
                logger.error(f"Error starting pipeline manager: {e}", exc_info=True, traceback=traceback.format_exc())
                await self._cleanup_on_failure()
                raise PipelineError(f"Failed to start pipeline: {e}") from e

    async def _cleanup_on_failure(self):
        """Cleanup resources on startup failure"""
        logger.info("Cleaning up resources after startup failure")
        if self._pipeline_task:
            await self._pipeline_task.stop()
        if self._executor:
            self._executor.shutdown(wait=False)
        self._is_running = False

    async def stop(self) -> None:
        """Stop the pipeline manager and release resources"""
        async with self._lock:
            if not self.is_running:
                logger.warning("Pipeline is not running")
                return
            
            logger.info("🛑 Stopping Enhanced Pipeline Manager...")
            
            try:
                # Stop the pipeline task
                if self._pipeline_task:
                    await self._pipeline_task.stop()
                    logger.info("Pipeline task stopped")

                # Shutdown executor
                if self._executor:
                    self._executor.shutdown(wait=True)
                    logger.info("Thread pool executor shut down")

                # Log performance stats
                stats = self.get_pipeline_stats()
                logger.info("Pipeline performance stats", **stats)
                
            except Exception as e:
                logger.error(f"Error stopping pipeline manager: {e}")
            finally:
                self._is_running = False
                self._pipeline_task = None
                self._pipeline = None
                self._executor = None
                logger.info("✅ Enhanced Pipeline Manager stopped successfully")

    async def push_audio(self, pcm_bytes: bytes) -> None:
        """Push raw PCM audio data into the pipeline"""
        if not self.is_running or not self._pipeline_source:
            logger.warning("Cannot push audio, pipeline not running or no source", 
                          is_running=self.is_running,
                          has_source=bool(self._pipeline_source))
            return
            
        try:
            # Create an AudioRawFrame
            frame = AudioRawFrame(
                audio=pcm_bytes, 
                sample_rate=16000, 
                num_channels=1
            )
            
            # Feed audio to pipeline source
            await self._pipeline_source.feed_audio(frame)
            
            # Update performance tracking
            self._frame_count += 1
            
        except Exception as e:
            logger.error("Error pushing audio to pipeline", error=str(e))
            await self._handle_processor_error("push_audio", e)

    async def handle_user_text(self, text: str) -> None:
        """Push user text into the pipeline (for text-based interaction)"""
        if not self.is_running or not self._pipeline_task:
            logger.warning("Cannot handle user text, pipeline not running", is_running=self.is_running)
            return

        try:
            # Create a TextFrame and push it into the pipeline
            frame = TextFrame(text=text)
            await self._pipeline_task.queue_frame(frame)
            logger.info("User text pushed to pipeline", text=text)
            
        except Exception as e:
            logger.error("Error pushing user text to pipeline", error=str(e))
            await self._handle_processor_error("handle_user_text", e)

    async def _handle_interruption(self) -> None:
        """Handle interruption events from the InterruptionManager"""
        if not self._enable_interruption or not self._pipeline_task:
            return
        
        logger.info("🚨 INTERACTION DETECTED! Sending interruption frames.")
        
        try:
            # Send interruption frames to the pipeline
            await self._pipeline_task.queue_frame(StartInterruptionFrame())
            await asyncio.sleep(0.1)  # Give some time for processors to react
            await self._pipeline_task.queue_frame(StopInterruptionFrame())
            
            logger.info("Interruption frames sent successfully")
            
        except Exception as e:
            logger.error("Failed to handle interruption", error=str(e))

    async def set_user_speaking(self, speaking: bool) -> None:
        """Notify the interruption manager about user speaking status"""
        if self._interruption_manager:
            self._interruption_manager.set_user_speaking(speaking)

    def get_pipeline_stats(self) -> Dict[str, Any]:
        """Get performance statistics of the pipeline"""
        if not self._start_time:
            return {"status": "not_started"}
        
        run_duration = asyncio.get_event_loop().time() - self._start_time
        
        return {
            "status": "running" if self.is_running else "stopped",
            "run_duration_seconds": run_duration,
            "total_frames_processed": self._frame_count,
            "error_frames": self._error_frames,
            "error_count_since_reset": self._error_count,
            "max_errors_allowed": self._max_errors
        }

    @property
    def is_running(self) -> bool:
        """Check if the pipeline is currently running"""
        return self._is_running

    @property
    def interruption_enabled(self) -> bool:
        """Check if interruption is enabled"""
        return self._enable_interruption

    async def start_stream(self):
        """Helper to send StartFrame to the pipeline"""
        if self._pipeline_task:
            logger.info("🚀 Sending StartFrame to pipeline")
            await self._pipeline_task.queue_frame(StartFrame())

    async def stop_stream(self):
        """Helper to send EndFrame to the pipeline"""
        if self._pipeline_task:
            logger.info("🎬 Sending EndFrame to pipeline")
            await self._pipeline_task.queue_frame(EndFrame())
            
    async def stop_all_pipelines(self):
        """Stops all running pipeline tasks"""
        logger.info("Stopping all pipeline tasks")
        # In this manager, we only have one pipeline task at a time
        await self.stop()

# Backward compatibility alias
SimplePipelineManager = EnhancedPipelineManager 