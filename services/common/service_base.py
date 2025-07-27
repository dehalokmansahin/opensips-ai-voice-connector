"""
Common Service Base for OpenSIPS AI Voice Connector Services
Shared functionality for all gRPC microservices
"""

import asyncio
import logging
import os
import signal
import time
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from concurrent import futures

import grpc
from grpc import aio as aio_grpc

class ServiceConfig:
    """Service configuration base class"""
    
    def __init__(self, service_name: str):
        self.service_name = service_name
        self.listen_addr = os.getenv(f'{service_name.upper()}_SERVICE_LISTEN_ADDR', '[::]:50050')
        self.max_workers = int(os.getenv(f'{service_name.upper()}_MAX_WORKERS', '10'))
        self.log_level = os.getenv('LOG_LEVEL', 'INFO')
        self.graceful_shutdown_timeout = int(os.getenv('GRACEFUL_SHUTDOWN_TIMEOUT', '30'))
        
        # Service-specific config can be added by subclasses
        self._load_service_config()
    
    def _load_service_config(self):
        """Override in subclasses for service-specific configuration"""
        pass

class BaseService(ABC):
    """Base service class for all gRPC microservices"""
    
    def __init__(self, service_name: str, config: ServiceConfig = None):
        self.service_name = service_name
        self.config = config or ServiceConfig(service_name)
        
        # Setup logging
        self._setup_logging()
        
        # Service state
        self.start_time = time.time()
        self.request_count = 0
        self.error_count = 0
        self.is_healthy = False
        
        # gRPC server
        self.server: Optional[aio_grpc.Server] = None
        
        self.logger = logging.getLogger(service_name)
        self.logger.info(f"🚀 {service_name} service initializing")
    
    def _setup_logging(self):
        """Setup service logging"""
        log_level = getattr(logging, self.config.log_level.upper(), logging.INFO)
        logging.basicConfig(
            level=log_level,
            format=f'%(asctime)s - {self.service_name} - %(levelname)s - %(message)s'
        )
    
    @abstractmethod
    async def initialize(self):
        """Initialize service-specific components"""
        pass
    
    @abstractmethod
    def create_servicer(self):
        """Create gRPC servicer instance"""
        pass
    
    @abstractmethod
    def add_servicer_to_server(self, servicer, server):
        """Add servicer to gRPC server"""
        pass
    
    async def start(self):
        """Start the gRPC service"""
        try:
            self.logger.info(f"Starting {self.service_name} service")
            
            # Initialize service
            await self.initialize()
            
            # Create gRPC server
            self.server = aio_grpc.server(
                futures.ThreadPoolExecutor(max_workers=self.config.max_workers)
            )
            
            # Add servicer
            servicer = self.create_servicer()
            self.add_servicer_to_server(servicer, self.server)
            
            # Start listening
            self.server.add_insecure_port(self.config.listen_addr)
            await self.server.start()
            
            self.is_healthy = True
            self.logger.info(f"✅ {self.service_name} service started on {self.config.listen_addr}")
            
            # Setup signal handlers
            self._setup_signal_handlers()
            
            # Wait for termination
            await self.server.wait_for_termination()
            
        except Exception as e:
            self.logger.error(f"❌ Failed to start {self.service_name} service: {e}")
            self.is_healthy = False
            raise
    
    async def stop(self):
        """Stop the gRPC service"""
        try:
            self.logger.info(f"Stopping {self.service_name} service")
            self.is_healthy = False
            
            if self.server:
                await self.server.stop(grace=self.config.graceful_shutdown_timeout)
                self.logger.info(f"✅ {self.service_name} service stopped gracefully")
            
        except Exception as e:
            self.logger.error(f"❌ Error stopping {self.service_name} service: {e}")
    
    def _setup_signal_handlers(self):
        """Setup signal handlers for graceful shutdown"""
        def signal_handler(signum, frame):
            self.logger.info(f"Signal {signum} received, initiating graceful shutdown")
            asyncio.create_task(self.stop())
        
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
    
    def increment_request_count(self):
        """Increment request counter"""
        self.request_count += 1
    
    def increment_error_count(self):
        """Increment error counter"""
        self.error_count += 1
    
    def get_stats(self) -> Dict[str, Any]:
        """Get service statistics"""
        uptime = time.time() - self.start_time
        return {
            'service_name': self.service_name,
            'uptime_seconds': int(uptime),
            'total_requests': self.request_count,
            'total_errors': self.error_count,
            'is_healthy': self.is_healthy,
            'listen_address': self.config.listen_addr,
            'max_workers': self.config.max_workers
        }
    
    async def health_check(self) -> Dict[str, Any]:
        """Base health check - override in subclasses for specific checks"""
        try:
            # Basic health check
            if not self.is_healthy:
                return {
                    'status': 'NOT_SERVING',
                    'message': 'Service not healthy',
                    'service_name': self.service_name
                }
            
            # Service-specific health check
            service_health = await self._service_specific_health_check()
            
            return {
                'status': 'SERVING' if service_health['healthy'] else 'NOT_SERVING',
                'message': service_health.get('message', 'Service healthy'),
                'service_name': self.service_name,
                'details': service_health.get('details', {})
            }
            
        except Exception as e:
            self.logger.error(f"Health check failed: {e}")
            return {
                'status': 'NOT_SERVING',
                'message': f'Health check error: {e}',
                'service_name': self.service_name
            }
    
    @abstractmethod
    async def _service_specific_health_check(self) -> Dict[str, Any]:
        """Service-specific health check - implement in subclasses"""
        pass

class ServiceRegistry:
    """Simple service registry for service discovery"""
    
    def __init__(self):
        self.services: Dict[str, Dict[str, Any]] = {}
    
    def register_service(self, name: str, address: str, port: int, metadata: Dict[str, Any] = None):
        """Register a service"""
        self.services[name] = {
            'name': name,
            'address': address,
            'port': port,
            'endpoint': f"{address}:{port}",
            'registered_at': time.time(),
            'metadata': metadata or {}
        }
    
    def get_service(self, name: str) -> Optional[Dict[str, Any]]:
        """Get service information"""
        return self.services.get(name)
    
    def list_services(self) -> Dict[str, Dict[str, Any]]:
        """List all registered services"""
        return self.services.copy()
    
    def unregister_service(self, name: str):
        """Unregister a service"""
        if name in self.services:
            del self.services[name]