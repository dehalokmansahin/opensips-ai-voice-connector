#!/usr/bin/env python3
"""
OpenSIPS AI Voice Connector - Main Entry Point
Simplified architecture using unified configuration
"""

import sys
import asyncio
import signal
from pathlib import Path
from typing import Dict, Any, Optional
import structlog
import random

# Setup Python paths
current_dir = Path(__file__).parent
src_path = current_dir
pipecat_src_path = current_dir.parent / "pipecat" / "src"

if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))
if str(pipecat_src_path) not in sys.path:
    sys.path.insert(0, str(pipecat_src_path))

logger = structlog.get_logger()

# Our modular components
from bot.config_manager import get_config_manager, get_config
from opensips_bot import run_opensips_bot, get_bot_sdp_info
from opensips_event_listener import OpenSIPSEventListener
from transports.sip_backend_listener import SIPBackendListener


class OpenSIPSAIVoiceConnector:
    """OpenSIPS AI Voice Connector - Unified Configuration Architecture"""
    
    def __init__(self, config_file: str = None):
        """Initialize the connector with unified configuration."""
        self.config_file = config_file or "cfg/opensips-ai-voice-connector.ini"
        self.config_manager = get_config_manager(self.config_file)
        self.config = None
        self.event_listener = None
        self.sip_backend_listener = None
        self.active_calls: Dict[str, asyncio.Task] = {}
        
        logger.info("OpenSIPS AI Voice Connector initialized", config_file=self.config_file)
    
    async def initialize(self):
        """Initialize all components with unified configuration."""
        try:
            # Load unified configuration
            self.config = self.config_manager.load()
            logger.info("Unified configuration loaded successfully", 
                       debug=self.config.debug,
                       log_level=self.config.log_level)
            
            await self._initialize_event_listener()
            await self._initialize_sip_backend_listener()
            logger.info("All components initialized successfully")
        except Exception as e:
            logger.error("Failed to initialize connector", error=str(e))
            raise
    
    async def _initialize_event_listener(self):
        """Initialize OpenSIPS event listener using unified config."""
        try:
            # For now, use legacy INI parsing for event listener config
            # TODO: Move event listener config to unified system
            from config import initialize as initialize_legacy_config, get_section as get_legacy_section
            
            try:
                initialize_legacy_config(self.config_file)
                engine_config = get_legacy_section('engine') or get_legacy_section('opensips')
            except Exception:
                # Fallback to defaults if legacy config fails
                engine_config = {"event_ip": "0.0.0.0", "event_port": "8090"}
            
            self.event_listener = OpenSIPSEventListener(
                host=engine_config.get('event_ip', '0.0.0.0'),
                port=int(engine_config.get('event_port', '8090')),
                on_call_start=self._on_call_start,
                on_call_end=self._on_call_end
            )
            
            logger.info("Event listener initialized")
        except Exception as e:
            logger.error("Failed to initialize event listener", error=str(e))
            raise
    
    async def _initialize_sip_backend_listener(self):
        """Initialize SIP backend listener to handle INVITE requests from OpenSIPS."""
        try:
            # Use port 8089 for SIP backend (OAVC interface)
            sip_port = 8089
            
            self.sip_backend_listener = SIPBackendListener(
                host="0.0.0.0",
                port=sip_port,
                on_invite_received=self._on_sip_invite_received
            )
            
            logger.info("SIP backend listener initialized", port=sip_port)
        except Exception as e:
            logger.error("Failed to initialize SIP backend listener", error=str(e))
            raise
    
    async def _on_call_start(self, call_info: Dict[str, Any]):
        """Handle call start event using unified configuration."""
        try:
            call_id = call_info.get('call_id', f"call_{random.randint(1000, 9999)}")
            logger.info("Call started", call_info=call_info, call_id=call_id)
            
            # Extract client info from call_info
            client_ip = call_info.get('client_ip')
            client_port = call_info.get('client_port')
            
            if client_ip and client_port:
                # Use unified configuration for bot
                bind_port = self._find_available_port(
                    self.config.network.bind_ip, 
                    self.config.network.min_port, 
                    self.config.network.max_port
                )
                
                # Start bot with unified config
                bot_task = asyncio.create_task(
                    run_opensips_bot(
                        call_id=call_id,
                        client_ip=client_ip,
                        client_port=client_port,
                        bind_ip=self.config.network.bind_ip,
                        bind_port=bind_port,
                        config_file=self.config_file
                    )
                )
                
                self.active_calls[call_id] = bot_task
                logger.info("Bot started for call", call_id=call_id)
            else:
                logger.warning("Missing client info in call start event", call_info=call_info)
            
        except Exception as e:
            logger.error("Error handling call start", call_id=call_id, error=str(e))
    
    async def _on_call_end(self, call_info: Dict[str, Any]):
        """Handle call end event."""
        try:
            call_id = call_info.get('call_id', 'unknown')
            logger.info("Call ended", call_info=call_info, call_id=call_id)
            
            # Cancel running bot if exists
            if call_id in self.active_calls:
                task = self.active_calls[call_id]
                task.cancel()
                del self.active_calls[call_id]
                logger.info("Bot task cancelled", call_id=call_id)
            
        except Exception as e:
            logger.error("Error handling call end", call_id=call_id, error=str(e))
    
    async def _on_sip_invite_received(self, invite_data: Dict[str, Any]):
        """Handle SIP INVITE request from OpenSIPS."""
        try:
            call_id = invite_data.get('call_id', f"call_{random.randint(1000, 9999)}")
            
            # Extract client RTP info from SDP
            sdp_info = invite_data.get('sdp_info', {})
            client_ip = sdp_info.get('media_ip')
            client_port = sdp_info.get('media_port')
            
            logger.info("SIP INVITE received", 
                       call_id=call_id, 
                       client_ip=client_ip, 
                       client_port=client_port)
            
            if not client_ip or not client_port:
                logger.error("Missing client info in SIP INVITE", invite_data=invite_data)
                await self.sip_backend_listener.send_400_bad_request(invite_data)
                return
            
            # Find available port for RTP
            bind_port = self._find_available_port(
                self.config.network.bind_ip, 
                self.config.network.min_port, 
                self.config.network.max_port
            )
            
            # Get SDP info for response
            sdp_info = get_bot_sdp_info(
                call_id=call_id,
                bind_ip=self.config.network.bind_ip,
                bind_port=bind_port,
                config_file=self.config_file
            )
            
            # Send 200 OK response
            await self.sip_backend_listener.send_200_ok(invite_data, sdp_info)
            
            # Start bot task
            bot_task = asyncio.create_task(
                run_opensips_bot(
                    call_id=call_id,
                    client_ip=client_ip,
                    client_port=client_port,
                    bind_ip=self.config.network.bind_ip,
                    bind_port=bind_port,
                    config_file=self.config_file
                )
            )
            
            self.active_calls[call_id] = bot_task
            logger.info("Bot started for SIP INVITE", call_id=call_id)
            
        except Exception as e:
            logger.error("Error handling SIP INVITE", error=str(e))
            if 'invite_data' in locals():
                await self.sip_backend_listener.send_500_internal_error(invite_data)
    
    def _find_available_port(self, bind_ip: str, min_port: int, max_port: int) -> int:
        """Find an available port in the specified range."""
        import socket
        
        for port in range(min_port, max_port + 1):
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                    s.bind((bind_ip, port))
                    return port
            except OSError:
                continue
        
        raise RuntimeError(f"No available ports in range {min_port}-{max_port}")
    
    async def start(self):
        """Start the connector."""
        try:
            await self.initialize()
            await self.event_listener.start()
            await self.sip_backend_listener.start()
            logger.info("OpenSIPS AI Voice Connector started successfully",
                       debug_mode=self.config.debug)
            
            # Keep running
            while True:
                await asyncio.sleep(1)
                
        except Exception as e:
            logger.error("Error starting connector", error=str(e))
            raise
    
    async def stop(self):
        """Stop the connector."""
        try:
            # Cancel all active calls
            for call_id, task in list(self.active_calls.items()):
                task.cancel()
                logger.info("Cancelled call", call_id=call_id)
            
            self.active_calls.clear()
            
            # Stop event listener
            if self.event_listener:
                await self.event_listener.stop()
            
            # Stop SIP backend listener
            if self.sip_backend_listener:
                await self.sip_backend_listener.stop()
            
            logger.info("OpenSIPS AI Voice Connector stopped")
            
        except Exception as e:
            logger.error("Error stopping connector", error=str(e))


async def main():
    """Main entry point with unified configuration."""
    import os
    
    # Allow config file override via environment
    config_file = os.getenv('OAVC_CONFIG_FILE', 'cfg/opensips-ai-voice-connector.ini')
    connector = OpenSIPSAIVoiceConnector(config_file)
    
    # Signal handlers
    def signal_handler(signum, frame):
        logger.info(f"Received signal {signum}, shutting down...")
        asyncio.create_task(connector.stop())
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        await connector.start()
    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt, shutting down...")
        await connector.stop()
    except Exception as e:
        logger.error("Fatal error", error=str(e))
        await connector.stop()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
