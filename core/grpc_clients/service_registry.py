"""
gRPC Service Registry for OpenSIPS AI Voice Connector
Manages connections to ASR, LLM, TTS microservices
"""

import asyncio
import logging
import grpc
from typing import Dict, Optional, Any
from grpc import aio as aio_grpc

import sys
from pathlib import Path

# Add core directory to path for direct imports  
core_path = Path(__file__).parent.parent
sys.path.insert(0, str(core_path))

from config.settings import ServicesConfig, ServiceConfig

logger = logging.getLogger(__name__)

class ServiceRegistry:
    """Manages gRPC service connections and discovery"""
    
    def __init__(self, services_config: ServicesConfig):
        self.config = services_config
        self._channels: Dict[str, aio_grpc.Channel] = {}
        self._health_tasks: Dict[str, asyncio.Task] = {}
        self._service_status: Dict[str, bool] = {}
        
    async def initialize(self):
        """Initialize all service connections"""
        try:
            # Initialize ASR service
            await self._initialize_service('asr', self.config.asr)
            
            # Initialize LLM service  
            await self._initialize_service('llm', self.config.llm)
            
            # Initialize TTS service
            await self._initialize_service('tts', self.config.tts)
            
            # Initialize VAD service if configured
            if self.config.vad:
                await self._initialize_service('vad', self.config.vad)
            
            logger.info("Service registry initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize service registry: {e}")
            raise
    
    async def _initialize_service(self, service_name: str, service_config: ServiceConfig):
        """Initialize connection to a specific service"""
        try:
            # Create gRPC channel
            options = [
                ('grpc.keepalive_time_ms', 10000),
                ('grpc.keepalive_timeout_ms', 5000),
                ('grpc.keepalive_permit_without_calls', True),
                ('grpc.http2.max_pings_without_data', 0),
                ('grpc.http2.min_time_between_pings_ms', 10000),
                ('grpc.http2.min_ping_interval_without_data_ms', 5000)
            ]
            
            channel = aio_grpc.insecure_channel(service_config.endpoint, options=options)
            self._channels[service_name] = channel
            
            # Test connection
            await self._test_connection(service_name, channel)
            
            # Start health monitoring
            self._health_tasks[service_name] = asyncio.create_task(
                self._monitor_service_health(service_name, channel)
            )
            
            self._service_status[service_name] = True
            logger.info(f"Service {service_name} initialized: {service_config.endpoint}")
            
        except Exception as e:
            logger.error(f"Failed to initialize {service_name} service: {e}")
            self._service_status[service_name] = False
            raise
    
    async def _test_connection(self, service_name: str, channel: aio_grpc.Channel):
        """Test connection to service"""
        try:
            # Simple connectivity test
            await channel.channel_ready()
            logger.info(f"Connection test passed for {service_name}")
            
        except Exception as e:
            logger.error(f"Connection test failed for {service_name}: {e}")
            raise
    
    async def _monitor_service_health(self, service_name: str, channel: aio_grpc.Channel):
        """Monitor service health periodically"""
        while True:
            try:
                await asyncio.sleep(30)  # Health check every 30 seconds
                
                # Check channel state
                state = channel.get_state()
                if state == grpc.ChannelConnectivity.READY:
                    if not self._service_status[service_name]:
                        logger.info(f"Service {service_name} is back online")
                    self._service_status[service_name] = True
                else:
                    if self._service_status[service_name]:
                        logger.warning(f"Service {service_name} is not ready: {state}")
                    self._service_status[service_name] = False
                    
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Health check error for {service_name}: {e}")
                self._service_status[service_name] = False
    
    def get_channel(self, service_name: str) -> Optional[aio_grpc.Channel]:
        """Get gRPC channel for service"""
        return self._channels.get(service_name)
    
    def is_service_healthy(self, service_name: str) -> bool:
        """Check if service is healthy"""
        return self._service_status.get(service_name, False)
    
    def get_service_endpoint(self, service_name: str) -> Optional[str]:
        """Get service endpoint"""
        if service_name == 'asr':
            return self.config.asr.endpoint
        elif service_name == 'llm':
            return self.config.llm.endpoint
        elif service_name == 'tts':
            return self.config.tts.endpoint
        elif service_name == 'vad' and self.config.vad:
            return self.config.vad.endpoint
        return None
    
    async def wait_for_service(self, service_name: str, timeout: float = 30.0) -> bool:
        """Wait for service to become ready"""
        start_time = asyncio.get_event_loop().time()
        
        while True:
            if self.is_service_healthy(service_name):
                return True
            
            elapsed = asyncio.get_event_loop().time() - start_time
            if elapsed > timeout:
                logger.error(f"Timeout waiting for service {service_name}")
                return False
            
            await asyncio.sleep(1)
    
    async def stop(self):
        """Stop service registry and close all connections"""
        try:
            # Cancel health monitoring tasks
            for task in self._health_tasks.values():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
            
            self._health_tasks.clear()
            
            # Close all channels
            for service_name, channel in self._channels.items():
                logger.info(f"Closing connection to {service_name}")
                await channel.close()
            
            self._channels.clear()
            self._service_status.clear()
            
            logger.info("Service registry stopped")
            
        except Exception as e:
            logger.error(f"Error stopping service registry: {e}")
    
    def get_status(self) -> Dict[str, Any]:
        """Get overall service registry status"""
        return {
            'services': {
                name: {
                    'healthy': self._service_status.get(name, False),
                    'endpoint': self.get_service_endpoint(name)
                }
                for name in ['asr', 'llm', 'tts', 'vad']
                if self.get_service_endpoint(name) is not None
            },
            'total_services': len(self._channels),
            'healthy_services': sum(1 for status in self._service_status.values() if status)
        }