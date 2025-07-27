#!/usr/bin/env python3
"""
OpenSIPS AI Voice Connector - New Core Application
Clean microservices architecture with minimal dependencies
"""

import asyncio
import logging
import os
import signal
import sys
from pathlib import Path
from typing import Dict, Any, Optional

# Add core to path
sys.path.insert(0, str(Path(__file__).parent))

# Core imports
from config.settings import Settings
from opensips.integration import OpenSIPSIntegration
from bot.pipeline_manager import PipelineManager
from grpc_clients.service_registry import ServiceRegistry
from utils.logging import setup_logging, get_development_logger
from utils.file_watcher import setup_hot_reload

logger = logging.getLogger(__name__)

class OpenSIPSAIVoiceConnector:
    """
    New Clean OpenSIPS AI Voice Connector
    Microservices architecture with gRPC communication
    """
    
    def __init__(self, config_file: str = None):
        """Initialize the connector"""
        self.config_file = config_file or "config/app.ini"
        
        # Core components
        self.settings: Optional[Settings] = None
        self.service_registry: Optional[ServiceRegistry] = None
        self.opensips_integration: Optional[OpenSIPSIntegration] = None
        self.pipeline_manager: Optional[PipelineManager] = None
        
        # Active sessions tracking
        self.active_sessions: Dict[str, Any] = {}
        
        # Development features
        self.hot_reload_watcher = None
        self.development_mode = os.getenv('DEVELOPMENT_MODE', '0') == '1'
        
        logger.info("OpenSIPS AI Voice Connector initialized (new architecture)")
    
    async def initialize(self):
        """Initialize all components"""
        try:
            # Load configuration
            await self._initialize_settings()
            
            # Setup service registry for gRPC services
            await self._initialize_service_registry()
            
            # Initialize pipeline manager
            await self._initialize_pipeline_manager()
            
            # Initialize OpenSIPS integration
            await self._initialize_opensips_integration()
            
            logger.info("All components initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize connector: {e}")
            raise
    
    async def _initialize_settings(self):
        """Initialize configuration settings"""
        try:
            self.settings = Settings(self.config_file)
            await self.settings.load()
            logger.info(f"Configuration loaded: {self.config_file}")
        except Exception as e:
            logger.error(f"Failed to load configuration: {e}")
            raise
    
    async def _initialize_service_registry(self):
        """Initialize gRPC service registry"""
        try:
            self.service_registry = ServiceRegistry(self.settings.services)
            await self.service_registry.initialize()
            logger.info("Service registry initialized")
        except Exception as e:
            logger.error(f"Failed to initialize service registry: {e}")
            raise
    
    async def _initialize_pipeline_manager(self):
        """Initialize conversation pipeline manager"""
        try:
            self.pipeline_manager = PipelineManager(
                service_registry=self.service_registry,
                settings=self.settings
            )
            await self.pipeline_manager.initialize()
            logger.info("Pipeline manager initialized")
        except Exception as e:
            logger.error(f"Failed to initialize pipeline manager: {e}")
            raise
    
    async def _initialize_opensips_integration(self):
        """Initialize OpenSIPS integration layer"""
        try:
            self.opensips_integration = OpenSIPSIntegration(
                settings=self.settings.opensips,
                pipeline_manager=self.pipeline_manager,
                on_call_start=self._on_call_start,
                on_call_end=self._on_call_end
            )
            await self.opensips_integration.initialize()
            logger.info("OpenSIPS integration initialized")
        except Exception as e:
            logger.error(f"Failed to initialize OpenSIPS integration: {e}")
            raise
    
    async def _on_call_start(self, call_info: Dict[str, Any]):
        """Handle new call start"""
        try:
            call_id = call_info.get('call_id')
            logger.info(f"New call started: {call_id}")
            
            # Create new conversation session
            session = await self.pipeline_manager.create_session(call_info)
            self.active_sessions[call_id] = session
            
            logger.info(f"Conversation session created for call: {call_id}")
            
        except Exception as e:
            logger.error(f"Error handling call start: {e}")
    
    async def _on_call_end(self, call_info: Dict[str, Any]):
        """Handle call end"""
        try:
            call_id = call_info.get('call_id')
            logger.info(f"Call ended: {call_id}")
            
            # Cleanup session
            if call_id in self.active_sessions:
                session = self.active_sessions[call_id]
                await session.cleanup()
                del self.active_sessions[call_id]
                logger.info(f"Session cleaned up for call: {call_id}")
            
        except Exception as e:
            logger.error(f"Error handling call end: {e}")
    
    def _setup_hot_reload(self):
        """Setup hot-reload for development"""
        try:
            app_root = Path(__file__).parent.parent
            
            def on_code_change(changed_file):
                """Handle code changes"""
                logger.info(f"Code change detected: {changed_file}")
                logger.info("Hot-reload: Gracefully shutting down for restart...")
                
                # Create a restart task
                asyncio.create_task(self._hot_reload_restart())
            
            self.hot_reload_watcher = setup_hot_reload(app_root, on_code_change)
            if self.hot_reload_watcher:
                logger.info("Hot-reload enabled for development")
            
        except Exception as e:
            logger.warning(f"Failed to setup hot-reload: {e}")
    
    async def _hot_reload_restart(self):
        """Graceful restart for hot-reload"""
        try:
            logger.info("Hot-reload: Starting graceful restart...")
            
            # Stop current instance
            await self.stop()
            
            # Exit to trigger container restart
            logger.info("Hot-reload: Exiting for restart")
            os._exit(0)
            
        except Exception as e:
            logger.error(f"Hot-reload restart failed: {e}")
            os._exit(1)
    
    async def start(self):
        """Start the application"""
        try:
            logger.info("Starting OpenSIPS AI Voice Connector (new architecture)")
            
            # Setup hot-reload in development mode
            if self.development_mode:
                self._setup_hot_reload()
            
            # Start OpenSIPS integration
            await self.opensips_integration.start()
            
            logger.info("OpenSIPS AI Voice Connector started successfully")
            
        except Exception as e:
            logger.error(f"Failed to start application: {e}")
            raise
    
    async def stop(self):
        """Stop the application"""
        try:
            logger.info("Stopping OpenSIPS AI Voice Connector")
            
            # Stop all active sessions
            for call_id, session in list(self.active_sessions.items()):
                logger.info(f"Stopping session: {call_id}")
                await session.cleanup()
            
            self.active_sessions.clear()
            
            # Stop OpenSIPS integration
            if self.opensips_integration:
                await self.opensips_integration.stop()
            
            # Stop pipeline manager
            if self.pipeline_manager:
                await self.pipeline_manager.stop()
            
            # Stop service registry
            if self.service_registry:
                await self.service_registry.stop()
            
            # Stop hot-reload watcher
            if self.hot_reload_watcher:
                self.hot_reload_watcher.stop()
            
            logger.info("OpenSIPS AI Voice Connector stopped successfully")
            
        except Exception as e:
            logger.error(f"Error stopping application: {e}")

async def main():
    """Main entry point"""
    # Detect development mode early
    development_mode = os.getenv('DEVELOPMENT_MODE', '0') == '1'
    log_level = os.getenv('CORE_LOG_LEVEL', 'DEBUG' if development_mode else 'INFO')
    
    # Setup enhanced logging
    setup_logging(level=log_level, development_mode=development_mode)
    
    # Get config file from environment
    config_file = os.getenv('OAVC_CONFIG_FILE', 'config/app.ini')
    
    try:
        # Create and initialize connector
        connector = OpenSIPSAIVoiceConnector(config_file)
        await connector.initialize()
        
        # Setup signal handlers for graceful shutdown
        def signal_handler(signum, frame):
            logger.info(f"Signal {signum} received, shutting down gracefully")
            asyncio.create_task(connector.stop())
        
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        
        # Start the connector
        await connector.start()
        
        # Keep running
        logger.info("Application running, press Ctrl+C to stop")
        try:
            while True:
                await asyncio.sleep(1)
                
                # Health check - ensure critical components are running
                if connector.opensips_integration and not connector.opensips_integration.is_running():
                    logger.error("OpenSIPS integration stopped unexpectedly")
                    break
                    
        except KeyboardInterrupt:
            logger.info("Keyboard interrupt received")
        
    except Exception as e:
        logger.error(f"Application error: {e}")
        return 1
    finally:
        if 'connector' in locals():
            await connector.stop()
    
    return 0

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)