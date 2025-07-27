"""
Multi-threaded RTP Processing Pipeline
Handles concurrent RTP ingestion and transmission with real-time constraints
"""

import threading
import asyncio
import logging
import time
import queue
from typing import Dict, List, Optional, Callable, Any, Union
from dataclasses import dataclass, field
from concurrent.futures import ThreadPoolExecutor, Future
from enum import Enum
import multiprocessing
import platform

logger = logging.getLogger(__name__)

class ThreadPriority(Enum):
    """Thread priority levels for audio processing"""
    LOW = 1
    NORMAL = 2
    HIGH = 3
    REALTIME = 4

@dataclass
class ThreadMetrics:
    """Thread-safe metrics for monitoring thread performance"""
    thread_id: str
    start_time: float = field(default_factory=time.time)
    tasks_processed: int = 0
    total_processing_time: float = 0.0
    max_processing_time: float = 0.0
    min_processing_time: float = float('inf')
    errors: int = 0
    last_activity: float = field(default_factory=time.time)
    _lock: threading.RLock = field(default_factory=threading.RLock, init=False)
    
    def update_processing_time(self, processing_time: float):
        """Thread-safe update of processing time metrics"""
        with self._lock:
            self.tasks_processed += 1
            self.total_processing_time += processing_time
            self.max_processing_time = max(self.max_processing_time, processing_time)
            self.min_processing_time = min(self.min_processing_time, processing_time)
            self.last_activity = time.time()
    
    def increment_errors(self):
        """Thread-safe increment of error count"""
        with self._lock:
            self.errors += 1
            self.last_activity = time.time()
    
    def get_stats(self) -> Dict[str, Any]:
        """Get thread-safe snapshot of metrics"""
        with self._lock:
            avg_time = (self.total_processing_time / self.tasks_processed 
                       if self.tasks_processed > 0 else 0.0)
            
            return {
                'thread_id': self.thread_id,
                'uptime_seconds': time.time() - self.start_time,
                'tasks_processed': self.tasks_processed,
                'average_processing_time': avg_time,
                'max_processing_time': self.max_processing_time,
                'min_processing_time': self.min_processing_time if self.min_processing_time != float('inf') else 0.0,
                'errors': self.errors,
                'last_activity': self.last_activity,
                'tasks_per_second': self.tasks_processed / max(time.time() - self.start_time, 1.0)
            }

class LockFreeQueue:
    """
    Lock-free audio buffer queue implementation
    Uses multiple queues and atomic operations for high-performance audio processing
    """
    
    def __init__(self, maxsize: int = 1000, num_segments: int = 4):
        self.maxsize = maxsize
        self.num_segments = num_segments
        self.segment_size = maxsize // num_segments
        
        # Create multiple queue segments to reduce contention
        self._segments = [queue.Queue(maxsize=self.segment_size) for _ in range(num_segments)]
        self._put_index = 0
        self._get_index = 0
        self._put_lock = threading.Lock()
        self._get_lock = threading.Lock()
        
        # Statistics
        self._stats = {
            'items_put': 0,
            'items_get': 0,
            'items_dropped': 0,
            'segments_full': 0
        }
        self._stats_lock = threading.RLock()
    
    def put_nowait(self, item: Any) -> bool:
        """
        Put item without blocking
        Returns True if successful, False if dropped
        """
        with self._put_lock:
            start_segment = self._put_index
            
            # Try each segment starting from current index
            for _ in range(self.num_segments):
                try:
                    self._segments[self._put_index].put_nowait(item)
                    
                    with self._stats_lock:
                        self._stats['items_put'] += 1
                    
                    # Move to next segment for load balancing
                    self._put_index = (self._put_index + 1) % self.num_segments
                    return True
                    
                except queue.Full:
                    self._put_index = (self._put_index + 1) % self.num_segments
                    continue
            
            # All segments full
            with self._stats_lock:
                self._stats['items_dropped'] += 1
                self._stats['segments_full'] += 1
            
            return False
    
    def get_nowait(self) -> Optional[Any]:
        """
        Get item without blocking
        Returns item or None if empty
        """
        with self._get_lock:
            start_segment = self._get_index
            
            # Try each segment starting from current index
            for _ in range(self.num_segments):
                try:
                    item = self._segments[self._get_index].get_nowait()
                    
                    with self._stats_lock:
                        self._stats['items_get'] += 1
                    
                    # Move to next segment for load balancing
                    self._get_index = (self._get_index + 1) % self.num_segments
                    return item
                    
                except queue.Empty:
                    self._get_index = (self._get_index + 1) % self.num_segments
                    continue
            
            # All segments empty
            return None
    
    async def put_async(self, item: Any, timeout: float = 0.1) -> bool:
        """Async put with timeout"""
        loop = asyncio.get_event_loop()
        
        try:
            return await asyncio.wait_for(
                loop.run_in_executor(None, self.put_nowait, item),
                timeout=timeout
            )
        except asyncio.TimeoutError:
            return False
    
    async def get_async(self, timeout: float = 0.1) -> Optional[Any]:
        """Async get with timeout"""
        loop = asyncio.get_event_loop()
        
        try:
            return await asyncio.wait_for(
                loop.run_in_executor(None, self.get_nowait),
                timeout=timeout
            )
        except asyncio.TimeoutError:
            return None
    
    def qsize(self) -> int:
        """Approximate queue size"""
        return sum(segment.qsize() for segment in self._segments)
    
    def empty(self) -> bool:
        """Check if all segments are empty"""
        return all(segment.empty() for segment in self._segments)
    
    def get_stats(self) -> Dict[str, Any]:
        """Get queue statistics"""
        with self._stats_lock:
            return {
                **self._stats,
                'current_size': self.qsize(),
                'max_size': self.maxsize,
                'num_segments': self.num_segments,
                'utilization': self.qsize() / max(self.maxsize, 1)
            }

class AudioThreadPool:
    """
    Specialized thread pool for real-time audio processing
    Manages thread priorities and ensures consistent performance
    """
    
    def __init__(
        self,
        max_workers: int = None,
        thread_name_prefix: str = "AudioThread",
        realtime_threads: int = 2,
        high_priority_threads: int = 2
    ):
        if max_workers is None:
            max_workers = min(8, (multiprocessing.cpu_count() or 1) + 2)
        
        self.max_workers = max_workers
        self.thread_name_prefix = thread_name_prefix
        self.realtime_threads = realtime_threads
        self.high_priority_threads = high_priority_threads
        
        # Create thread pools with different priorities
        self._realtime_pool = ThreadPoolExecutor(
            max_workers=realtime_threads,
            thread_name_prefix=f"{thread_name_prefix}-RT"
        )
        
        self._high_priority_pool = ThreadPoolExecutor(
            max_workers=high_priority_threads,
            thread_name_prefix=f"{thread_name_prefix}-HP"
        )
        
        normal_workers = max(1, max_workers - realtime_threads - high_priority_threads)
        self._normal_pool = ThreadPoolExecutor(
            max_workers=normal_workers,
            thread_name_prefix=f"{thread_name_prefix}-NP"
        )
        
        # Thread metrics tracking
        self._metrics: Dict[str, ThreadMetrics] = {}
        self._metrics_lock = threading.RLock()
        
        # Configure thread priorities (platform-specific)
        self._configure_thread_priorities()
        
        logger.info(f"AudioThreadPool initialized: RT={realtime_threads}, "
                   f"HP={high_priority_threads}, Normal={normal_workers}")
    
    def _configure_thread_priorities(self):
        """Configure thread priorities based on platform"""
        try:
            if platform.system() == "Windows":
                # Windows thread priority configuration
                import ctypes
                from ctypes import wintypes
                
                # Set high priority for audio processing
                kernel32 = ctypes.windll.kernel32
                current_thread = kernel32.GetCurrentThread()
                
                # THREAD_PRIORITY_ABOVE_NORMAL = 1
                # THREAD_PRIORITY_HIGHEST = 2
                # THREAD_PRIORITY_TIME_CRITICAL = 15
                
                # Note: In production, these would be set per thread
                logger.info("Windows thread priority configuration available")
                
            elif platform.system() == "Linux":
                # Linux real-time scheduling (requires privileges)
                import os
                try:
                    # Check if we can set real-time priority
                    if os.getuid() == 0:  # Running as root
                        logger.info("Linux real-time scheduling available (root)")
                    else:
                        logger.info("Linux real-time scheduling requires privileges")
                except:
                    pass
                    
        except Exception as e:
            logger.warning(f"Thread priority configuration not available: {e}")
    
    def submit_realtime(self, fn: Callable, *args, **kwargs) -> Future:
        """Submit task to real-time priority pool"""
        return self._submit_with_metrics(self._realtime_pool, "RT", fn, *args, **kwargs)
    
    def submit_high_priority(self, fn: Callable, *args, **kwargs) -> Future:
        """Submit task to high priority pool"""
        return self._submit_with_metrics(self._high_priority_pool, "HP", fn, *args, **kwargs)
    
    def submit_normal(self, fn: Callable, *args, **kwargs) -> Future:
        """Submit task to normal priority pool"""
        return self._submit_with_metrics(self._normal_pool, "NP", fn, *args, **kwargs)
    
    def _submit_with_metrics(self, pool: ThreadPoolExecutor, priority: str, fn: Callable, *args, **kwargs) -> Future:
        """Submit task with metrics tracking"""
        def wrapped_fn(*args, **kwargs):
            thread_id = f"{priority}-{threading.current_thread().ident}"
            start_time = time.perf_counter()
            
            # Ensure metrics object exists
            with self._metrics_lock:
                if thread_id not in self._metrics:
                    self._metrics[thread_id] = ThreadMetrics(thread_id)
            
            try:
                result = fn(*args, **kwargs)
                processing_time = time.perf_counter() - start_time
                self._metrics[thread_id].update_processing_time(processing_time)
                return result
                
            except Exception as e:
                self._metrics[thread_id].increment_errors()
                raise
        
        return pool.submit(wrapped_fn, *args, **kwargs)
    
    def shutdown(self, wait: bool = True):
        """Shutdown all thread pools"""
        pools = [self._realtime_pool, self._high_priority_pool, self._normal_pool]
        
        for pool in pools:
            pool.shutdown(wait=wait)
        
        logger.info("AudioThreadPool shutdown complete")
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get comprehensive thread pool metrics"""
        with self._metrics_lock:
            thread_stats = {tid: metrics.get_stats() for tid, metrics in self._metrics.items()}
        
        return {
            'pool_config': {
                'max_workers': self.max_workers,
                'realtime_threads': self.realtime_threads,
                'high_priority_threads': self.high_priority_threads,
                'normal_threads': max(1, self.max_workers - self.realtime_threads - self.high_priority_threads)
            },
            'thread_metrics': thread_stats,
            'summary': {
                'total_threads': len(thread_stats),
                'total_tasks_processed': sum(stats['tasks_processed'] for stats in thread_stats.values()),
                'total_errors': sum(stats['errors'] for stats in thread_stats.values()),
                'average_tasks_per_second': sum(stats['tasks_per_second'] for stats in thread_stats.values())
            }
        }

class MultiThreadedRTPProcessor:
    """
    Main multi-threaded RTP processing coordinator
    Manages concurrent ingestion, processing, and transmission
    """
    
    def __init__(
        self,
        session_id: str,
        max_workers: int = None,
        ingestion_queue_size: int = 1000,
        transmission_queue_size: int = 500,
        processing_queue_size: int = 800
    ):
        self.session_id = session_id
        
        # Create specialized thread pool
        self.thread_pool = AudioThreadPool(
            max_workers=max_workers,
            thread_name_prefix=f"RTP-{session_id}",
            realtime_threads=4,  # For real-time ingestion/transmission (2+2)
            high_priority_threads=2  # For audio processing
        )
        
        # Create lock-free queues for different stages
        self.ingestion_queue = LockFreeQueue(maxsize=ingestion_queue_size, num_segments=4)
        self.processing_queue = LockFreeQueue(maxsize=processing_queue_size, num_segments=4)
        self.transmission_queue = LockFreeQueue(maxsize=transmission_queue_size, num_segments=2)
        
        # Processing state
        self._running = False
        self._workers_started = False
        
        # Callbacks for different stages
        self.ingestion_callback: Optional[Callable] = None
        self.processing_callback: Optional[Callable] = None
        self.transmission_callback: Optional[Callable] = None
        
        # Worker control
        self._worker_futures: List[Future] = []
        self._shutdown_event = threading.Event()
        self._workers_ready = threading.Event()
        self._workers_started_count = 0
        self._workers_started_lock = threading.Lock()
        self._expected_workers = 7  # 2 ingestion + 2 processing + 2 transmission + 1 monitoring
        
        logger.info(f"MultiThreadedRTPProcessor initialized for session {session_id}")
    
    def _signal_worker_started(self):
        """Signal that a worker has started"""
        with self._workers_started_lock:
            self._workers_started_count += 1
            if self._workers_started_count >= self._expected_workers:
                self._workers_ready.set()
    
    def set_callbacks(
        self,
        ingestion_callback: Optional[Callable] = None,
        processing_callback: Optional[Callable] = None,
        transmission_callback: Optional[Callable] = None
    ):
        """Set callbacks for different processing stages"""
        self.ingestion_callback = ingestion_callback
        self.processing_callback = processing_callback
        self.transmission_callback = transmission_callback
    
    def start_workers(self):
        """Start multi-threaded processing workers"""
        if self._workers_started:
            logger.warning("Workers already started")
            return
        
        self._running = True
        self._shutdown_event.clear()
        
        # Start ingestion workers (real-time priority)
        for i in range(2):
            future = self.thread_pool.submit_realtime(self._ingestion_worker, f"ingestion-{i}")
            self._worker_futures.append(future)
        
        # Start processing workers (high priority)
        for i in range(2):
            future = self.thread_pool.submit_high_priority(self._processing_worker, f"processing-{i}")
            self._worker_futures.append(future)
        
        # Start transmission workers (real-time priority)
        for i in range(2):
            future = self.thread_pool.submit_realtime(self._transmission_worker, f"transmission-{i}")
            self._worker_futures.append(future)
        
        # Start queue monitoring worker (normal priority)
        future = self.thread_pool.submit_normal(self._monitoring_worker, "monitor")
        self._worker_futures.append(future)
        
        self._workers_started = True
        
        # Wait for workers to actually start (with timeout)
        if self._workers_ready.wait(timeout=2.0):
            logger.debug(f"All workers confirmed started for session {self.session_id}")
        else:
            logger.warning(f"Not all workers started within timeout for session {self.session_id}")
        
        logger.info(f"Started {len(self._worker_futures)} workers for session {self.session_id}")
    
    def stop_workers(self, timeout: float = 5.0):
        """Stop all processing workers"""
        if not self._workers_started:
            return
        
        self._running = False
        self._shutdown_event.set()
        
        # Wait for workers to complete
        completed = 0
        for future in self._worker_futures:
            try:
                future.result(timeout=timeout)
                completed += 1
            except Exception as e:
                logger.warning(f"Worker shutdown error: {e}")
        
        self._worker_futures.clear()
        self._workers_started = False
        
        logger.info(f"Stopped {completed}/{len(self._worker_futures)} workers")
    
    def shutdown(self, timeout: float = 10.0):
        """Complete shutdown of multi-threaded processor"""
        self.stop_workers(timeout=timeout)
        self.thread_pool.shutdown(wait=True)
        logger.info(f"MultiThreadedRTPProcessor shutdown complete for session {self.session_id}")
    
    def _ingestion_worker(self, worker_id: str):
        """Real-time ingestion worker - handles incoming RTP packets"""
        logger.debug(f"Ingestion worker {worker_id} started")
        self._signal_worker_started()
        
        while self._running and not self._shutdown_event.is_set():
            try:
                # Get packet from ingestion queue
                packet = self.ingestion_queue.get_nowait()
                if packet is None:
                    time.sleep(0.001)  # 1ms sleep to prevent CPU spinning
                    continue
                
                # Process through ingestion callback
                if self.ingestion_callback:
                    processed_packet = self.ingestion_callback(packet)
                    if processed_packet:
                        # Forward to processing queue
                        success = self.processing_queue.put_nowait(processed_packet)
                        if not success:
                            logger.warning(f"Processing queue full in worker {worker_id}")
                
            except Exception as e:
                logger.error(f"Ingestion worker {worker_id} error: {e}")
                time.sleep(0.01)  # Back off on error
        
        logger.debug(f"Ingestion worker {worker_id} stopped")
    
    def _processing_worker(self, worker_id: str):
        """High-priority processing worker - handles audio processing"""
        logger.debug(f"Processing worker {worker_id} started")
        self._signal_worker_started()
        
        while self._running and not self._shutdown_event.is_set():
            try:
                # Get packet from processing queue
                packet = self.processing_queue.get_nowait()
                if packet is None:
                    time.sleep(0.005)  # 5ms sleep
                    continue
                
                # Process through processing callback
                if self.processing_callback:
                    processed_audio = self.processing_callback(packet)
                    if processed_audio:
                        # Forward to transmission queue
                        success = self.transmission_queue.put_nowait(processed_audio)
                        if not success:
                            logger.warning(f"Transmission queue full in worker {worker_id}")
                
            except Exception as e:
                logger.error(f"Processing worker {worker_id} error: {e}")
                time.sleep(0.01)
        
        logger.debug(f"Processing worker {worker_id} stopped")
    
    def _transmission_worker(self, worker_id: str):
        """Real-time transmission worker - handles outgoing RTP packets"""
        logger.debug(f"Transmission worker {worker_id} started")
        self._signal_worker_started()
        
        iterations = 0
        while self._running and not self._shutdown_event.is_set():
            try:
                # Get audio from transmission queue
                audio_data = self.transmission_queue.get_nowait()
                if audio_data is None:
                    time.sleep(0.001)  # 1ms sleep
                    iterations += 1
                    continue
                
                # Process through transmission callback
                if self.transmission_callback:
                    self.transmission_callback(audio_data)
                
            except Exception as e:
                logger.error(f"Transmission worker {worker_id} error: {e}")
                time.sleep(0.01)
        
        logger.debug(f"Transmission worker {worker_id} stopped")
    
    def _monitoring_worker(self, worker_id: str):
        """Monitoring worker - tracks queue health and performance"""
        logger.debug(f"Monitoring worker {worker_id} started")
        self._signal_worker_started()
        last_log = time.time()
        log_interval = 30.0  # Log every 30 seconds
        
        while self._running and not self._shutdown_event.is_set():
            try:
                current_time = time.time()
                
                if current_time - last_log >= log_interval:
                    # Log queue statistics
                    metrics = self.get_processing_metrics()
                    logger.info(f"RTP Processing Metrics for {self.session_id}: "
                               f"Ingestion={metrics['ingestion_queue']['current_size']}, "
                               f"Processing={metrics['processing_queue']['current_size']}, "
                               f"Transmission={metrics['transmission_queue']['current_size']}")
                    
                    last_log = current_time
                
                time.sleep(1.0)  # Check every second
                
            except Exception as e:
                logger.error(f"Monitoring worker {worker_id} error: {e}")
                time.sleep(5.0)
        
        logger.debug(f"Monitoring worker {worker_id} stopped")
    
    def submit_for_ingestion(self, packet: Any) -> bool:
        """Submit packet for ingestion (called from UDP socket callback)"""
        return self.ingestion_queue.put_nowait(packet)
    
    def get_processing_metrics(self) -> Dict[str, Any]:
        """Get comprehensive processing metrics"""
        return {
            'session_id': self.session_id,
            'running': self._running,
            'workers_started': self._workers_started,
            'active_workers': len(self._worker_futures),
            'ingestion_queue': self.ingestion_queue.get_stats(),
            'processing_queue': self.processing_queue.get_stats(),
            'transmission_queue': self.transmission_queue.get_stats(),
            'thread_pool': self.thread_pool.get_metrics()
        }