"""
AI Voice Connector Main Service
Banking IVR Voice Assistant System - Main Orchestrator

This service acts as the main orchestrator for the AI voice pipeline,
integrating with OpenSIPS for SIP call handling and coordinating
with other microservices via gRPC.
"""

import asyncio
import logging
import signal
import sys
from contextlib import asynccontextmanager
from typing import Dict, Any

import structlog
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import make_asgi_app, Counter, Histogram, Gauge
import grpc
from grpc import aio as aio_grpc

from .config import Settings
from .health import HealthManager
from .grpc_server import GRPCServer
from .opensips_integration import OpenSIPSEventListener
from .pipeline_manager import PipelineManger


# Metrics
REQUEST_COUNT = Counter('ai_voice_requests_total', 'Total requests', ['method', 'endpoint', 'status'])
REQUEST_DURATION = Histogram('ai_voice_request_duration_seconds', 'Request duration')
ACTIVE_CALLS = Gauge('ai_voice_active_calls', 'Number of active calls')
PIPELINE_LATENCY = Histogram('ai_voice_pipeline_latency_ms', 'Pipeline processing latency in milliseconds')

# Setup structured logging
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        structlog.processors.JSONRenderer()
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    wrapper_class=structlog.stdlib.BoundLogger,
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger(__name__)


class AIVoiceConnectorService:
    """Main AI Voice Connector service implementation"""
    
    def __init__(self):
        self.settings = Settings()
        self.health_manager = HealthManager()
        self.grpc_server: GRPCServer = None
        self.opensips_listener: OpenSIPSEventListener = None
        self.pipeline_manager: PipelineManger = None
        self.app: FastAPI = None
        self._shutdown_event = asyncio.Event()
        
    async def initialize(self):
        """Initialize all service components"""
        logger.info("Initializing AI Voice Connector service", 
                   version="0.1.0", 
                   environment=self.settings.environment)
        
        try:
            # Initialize pipeline manager
            self.pipeline_manager = PipelineManger(self.settings)
            await self.pipeline_manager.initialize()
            
            # Initialize gRPC server
            self.grpc_server = GRPCServer(
                port=self.settings.grpc_port,
                pipeline_manager=self.pipeline_manager
            )
            await self.grpc_server.start()
            
            # Initialize OpenSIPS event listener
            self.opensips_listener = OpenSIPSEventListener(
                host=self.settings.opensips_host,
                event_port=self.settings.opensips_event_port,
                pipeline_manager=self.pipeline_manager
            )
            await self.opensips_listener.start()
            
            # Register health checks
            await self._register_health_checks()
            
            logger.info("AI Voice Connector service initialized successfully")
            
        except Exception as e:
            logger.error("Failed to initialize service", error=str(e))
            raise
    
    async def _register_health_checks(self):
        """Register health check endpoints"""
        self.health_manager.add_check("grpc_server", self.grpc_server.health_check)
        self.health_manager.add_check("opensips_listener", self.opensips_listener.health_check)
        self.health_manager.add_check("pipeline_manager", self.pipeline_manager.health_check)
        
        # Add external service health checks
        self.health_manager.add_check("vad_service", self._check_vad_service)
        self.health_manager.add_check("asr_service", self._check_asr_service)
        self.health_manager.add_check("llm_service", self._check_llm_service)
        self.health_manager.add_check("tts_service", self._check_tts_service)
    
    async def _check_vad_service(self) -> Dict[str, Any]:
        """Health check for VAD service"""
        try:
            # Implement gRPC health check to VAD service
            async with aio_grpc.insecure_channel(f"{self.settings.vad_service_host}:{self.settings.vad_service_port}") as channel:
                # Add health check call here
                return {"status": "healthy", "service": "vad"}
        except Exception as e:
            return {"status": "unhealthy", "error": str(e)}
    
    async def _check_asr_service(self) -> Dict[str, Any]:
        """Health check for ASR service"""
        try:
            async with aio_grpc.insecure_channel(f"{self.settings.asr_service_host}:{self.settings.asr_service_port}") as channel:
                return {"status": "healthy", "service": "asr"}
        except Exception as e:
            return {"status": "unhealthy", "error": str(e)}
    
    async def _check_llm_service(self) -> Dict[str, Any]:
        """Health check for LLM service"""
        try:
            async with aio_grpc.insecure_channel(f"{self.settings.llm_service_host}:{self.settings.llm_service_port}") as channel:
                return {"status": "healthy", "service": "llm"}
        except Exception as e:
            return {"status": "unhealthy", "error": str(e)}
    
    async def _check_tts_service(self) -> Dict[str, Any]:
        """Health check for TTS service"""
        try:
            async with aio_grpc.insecure_channel(f"{self.settings.tts_service_host}:{self.settings.tts_service_port}") as channel:
                return {"status": "healthy", "service": "tts"}
        except Exception as e:
            return {"status": "unhealthy", "error": str(e)}
    
    async def shutdown(self):
        """Graceful shutdown of all components"""
        logger.info("Shutting down AI Voice Connector service")
        
        try:
            # Stop OpenSIPS listener
            if self.opensips_listener:
                await self.opensips_listener.stop()
            
            # Stop gRPC server
            if self.grpc_server:
                await self.grpc_server.stop()
            
            # Shutdown pipeline manager
            if self.pipeline_manager:
                await self.pipeline_manager.shutdown()
                
            self._shutdown_event.set()
            logger.info("AI Voice Connector service shut down successfully")
            
        except Exception as e:
            logger.error("Error during shutdown", error=str(e))
            raise
    
    def create_fastapi_app(self) -> FastAPI:
        """Create and configure FastAPI application"""
        
        @asynccontextmanager
        async def lifespan(app: FastAPI):
            # Startup
            await self.initialize()
            yield
            # Shutdown
            await self.shutdown()
        
        app = FastAPI(
            title="AI Voice Connector",
            description="Banking IVR Voice Assistant - Main Orchestrator Service",
            version="0.1.0",
            lifespan=lifespan
        )
        
        # Add CORS middleware
        app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],  # Configure appropriately for production
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )
        
        # Health check endpoint
        @app.get("/health")
        async def health_check():
            """Comprehensive health check endpoint"""
            try:
                health_status = await self.health_manager.check_all()
                
                overall_status = "healthy"
                if any(check["status"] != "healthy" for check in health_status.values()):
                    if any(check["status"] == "unhealthy" for check in health_status.values()):
                        overall_status = "unhealthy"
                    else:
                        overall_status = "degraded"
                
                return {
                    "status": overall_status,
                    "timestamp": health_status.get("timestamp"),
                    "services": health_status,
                    "version": "0.1.0"
                }
            except Exception as e:
                logger.error("Health check failed", error=str(e))
                raise HTTPException(status_code=503, detail="Health check failed")
        
        # Basic service info endpoint
        @app.get("/info")
        async def service_info():
            """Service information endpoint"""
            return {
                "service": "ai-voice-connector",
                "version": "0.1.0",
                "description": "Banking IVR Voice Assistant - Main Orchestrator",
                "endpoints": {
                    "health": "/health",
                    "metrics": "/metrics",
                    "grpc": f":{self.settings.grpc_port}"
                },
                "environment": self.settings.environment
            }
        
        # Add Prometheus metrics endpoint
        metrics_app = make_asgi_app()
        app.mount("/metrics", metrics_app)
        
        self.app = app
        return app


# Global service instance
service_instance = AIVoiceConnectorService()


def handle_shutdown_signal(signum, frame):
    """Handle shutdown signals"""
    logger.info("Received shutdown signal", signal=signum)
    asyncio.create_task(service_instance.shutdown())


async def main():
    """Main entry point for the service"""
    # Setup signal handlers
    signal.signal(signal.SIGINT, handle_shutdown_signal)
    signal.signal(signal.SIGTERM, handle_shutdown_signal)
    
    try:
        # Create FastAPI app
        app = service_instance.create_fastapi_app()
        
        # Configure uvicorn
        config = uvicorn.Config(
            app,
            host="0.0.0.0",
            port=service_instance.settings.http_port,
            log_level=service_instance.settings.log_level.lower(),
            access_log=True,
            server_header=False,
            date_header=False
        )
        
        server = uvicorn.Server(config)
        
        logger.info("Starting AI Voice Connector service",
                   http_port=service_instance.settings.http_port,
                   grpc_port=service_instance.settings.grpc_port)
        
        await server.serve()
        
    except Exception as e:
        logger.error("Failed to start service", error=str(e))
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())