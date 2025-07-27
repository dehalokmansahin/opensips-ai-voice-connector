"""
Minimal Pipeline Implementation for OpenSIPS AI Voice Connector
Simplified version of pipecat pipeline system
"""

import asyncio
import logging
from typing import List, Optional, Any
from ..frames.frames import Frame, StartFrame, EndFrame, ErrorFrame

logger = logging.getLogger(__name__)

class FrameProcessor:
    """Base frame processor"""
    
    def __init__(self, name: str = "FrameProcessor"):
        self.name = name
        self._pipeline: Optional['Pipeline'] = None
        
    async def process_frame(self, frame: Frame) -> Optional[Frame]:
        """Process a frame and return modified frame or None"""
        return frame
        
    async def push_frame(self, frame: Frame):
        """Push frame to next processor in pipeline"""
        if self._pipeline:
            await self._pipeline._process_frame(frame, self)

class Pipeline:
    """Simple pipeline for processing frames"""
    
    def __init__(self, processors: List[FrameProcessor]):
        self.processors = processors
        self._setup_processors()
        
    def _setup_processors(self):
        """Setup processor pipeline references"""
        for processor in self.processors:
            processor._pipeline = self
            
    async def _process_frame(self, frame: Frame, source_processor: FrameProcessor):
        """Process frame through remaining processors"""
        try:
            # Find source processor index
            source_index = self.processors.index(source_processor)
            
            # Process through remaining processors
            current_frame = frame
            for processor in self.processors[source_index + 1:]:
                if current_frame is None:
                    break
                current_frame = await processor.process_frame(current_frame)
                
        except Exception as e:
            logger.error(f"Pipeline error: {e}")
            error_frame = ErrorFrame(error=str(e))
            # Send error to last processor
            if self.processors:
                await self.processors[-1].process_frame(error_frame)
    
    async def start(self):
        """Start the pipeline"""
        logger.info(f"Starting pipeline with {len(self.processors)} processors")
        start_frame = StartFrame()
        if self.processors:
            await self.processors[0].process_frame(start_frame)
    
    async def stop(self):
        """Stop the pipeline"""
        logger.info("Stopping pipeline")
        end_frame = EndFrame()
        if self.processors:
            await self.processors[0].process_frame(end_frame)
    
    async def push_frame(self, frame: Frame):
        """Push frame to first processor"""
        if self.processors:
            await self.processors[0].process_frame(frame)

class AsyncFrameProcessor(FrameProcessor):
    """Async frame processor with task management"""
    
    def __init__(self, name: str = "AsyncFrameProcessor"):
        super().__init__(name)
        self._tasks: List[asyncio.Task] = []
        
    async def create_task(self, coro):
        """Create and track async task"""
        task = asyncio.create_task(coro)
        self._tasks.append(task)
        return task
    
    async def cleanup_tasks(self):
        """Cancel and cleanup all tasks"""
        for task in self._tasks:
            if not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        self._tasks.clear()

class AudioFrameProcessor(FrameProcessor):
    """Base class for audio processing"""
    
    def __init__(self, sample_rate: int = 16000, name: str = "AudioFrameProcessor"):
        super().__init__(name)
        self.sample_rate = sample_rate

class TextFrameProcessor(FrameProcessor):
    """Base class for text processing"""
    
    def __init__(self, name: str = "TextFrameProcessor"):
        super().__init__(name)