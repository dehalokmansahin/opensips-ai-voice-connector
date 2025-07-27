"""
gRPC Server implementation for AI Voice Connector
Provides gRPC interface for other services to communicate with the main orchestrator
"""

import asyncio
from typing import Dict, Any, Optional

import grpc
from grpc import aio as aio_grpc
import structlog

logger = structlog.get_logger(__name__)


class GRPCServer:
    """gRPC server for AI Voice Connector service"""
    
    def __init__(self, port: int, pipeline_manager):
        self.port = port
        self.pipeline_manager = pipeline_manager
        self.server: Optional[aio_grpc.Server] = None
        
    async def start(self):
        """Start the gRPC server"""
        logger.info("Starting gRPC server", port=self.port)
        
        # Create server
        self.server = aio_grpc.server()
        
        # Add services here when proto definitions are ready
        # Example:
        # add_AIVoiceConnectorServicer_to_server(
        #     AIVoiceConnectorServicer(self.pipeline_manager), 
        #     self.server
        # )
        
        # Configure server
        listen_addr = f'[::]:{self.port}'
        self.server.add_insecure_port(listen_addr)
        
        # Start server
        await self.server.start()
        
        logger.info("gRPC server started", address=listen_addr)
    
    async def stop(self):
        """Stop the gRPC server"""
        if self.server:
            logger.info("Stopping gRPC server")
            await self.server.stop(grace=30)
            logger.info("gRPC server stopped")
    
    async def health_check(self) -> Dict[str, Any]:
        """Health check for gRPC server"""
        try:
            if not self.server:
                return {
                    "status": "unhealthy",
                    "message": "gRPC server not initialized",
                    "details": {}
                }
            
            # Check if server is running (placeholder implementation)
            return {
                "status": "healthy",
                "message": "gRPC server running",
                "details": {
                    "port": self.port,
                    "address": f"[::]:{self.port}"
                }
            }
            
        except Exception as e:
            return {
                "status": "unhealthy",
                "message": f"gRPC server health check failed: {str(e)}",
                "details": {"error": str(e)}
            }