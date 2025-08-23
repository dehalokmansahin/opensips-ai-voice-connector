#!/usr/bin/env python3
"""
OpenSIPS AI Voice Connector - Simplified Main Entry Point
Following Twilio/Telnyx pattern with simplified architecture
"""

import sys
import os
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

# Configuration
from config import (
    initialize as initialize_config,
    get_section as get_config_section
)

# Our simplified bot
from opensips_bot import run_opensips_bot, get_bot_sdp_info

# OpenSIPS Event Integration
from opensips_event_listener import OpenSIPSEventListener
from call_manager import CallManager
from port_utils import find_available_port


class OpenSIPSAIVoiceConnector:
    """
    Simplified OpenSIPS AI Voice Connector
    Following Twilio/Telnyx pattern - much cleaner!
    """
    
    def __init__(self, config_file: str = None):
        """Initialize the connector following simplified pattern"""
        self.config_file = config_file or "cfg/opensips-ai-voice-connector.ini"
        
        # Core components
        self.config = None
        self.event_listener = None
        self.sip_listener = None
        
        # Active calls tracking handled by CallManager
        self.call_manager = CallManager()
        
        logger.info("OpenSIPS AI Voice Connector initialized (simplified)",
                   config_file=self.config_file,
                   pattern="twilio_telnyx_compliant")
    
    async def initialize(self):
        """Initialize all components - much simpler now!"""
        try:
            await self._initialize_config()
            await self._initialize_event_listener()
            await self._initialize_sip_listener()
            
            logger.info("All components initialized successfully", 
                       pattern="twilio_telnyx_compliant")
            
        except Exception as e:
            logger.error("Failed to initialize connector", error=str(e))
            raise
    
    async def _initialize_config(self):
        """Initialize configuration"""
        try:
            self.config = initialize_config(self.config_file)
            logger.info("Configuration loaded successfully", config_file=self.config_file)
        except Exception as e:
            logger.error("Failed to load configuration", error=str(e))
            raise
    
    async def _initialize_event_listener(self):
        """Initialize OpenSIPS event listener"""
        try:
            engine_config = get_config_section('engine') or get_config_section('opensips')
            
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
    
    async def _initialize_sip_listener(self):
        """Initialize SIP backend listener for OpenSIPS INVITE requests"""
        try:
            from transports.sip_backend_listener import SIPBackendListener
            
            engine_config = get_config_section('engine') or get_config_section('opensips')
            
            self.sip_listener = SIPBackendListener(
                host=engine_config.get('sip_ip', '0.0.0.0'),
                port=int(engine_config.get('sip_port', '8089')),
                on_invite_received=self._on_sip_invite_received
            )
            
            await self.sip_listener.start()
            logger.info("SIP backend listener initialized")
            
        except Exception as e:
            logger.error("Failed to initialize SIP backend listener", error=str(e))
            raise
    
    async def _on_call_start(self, call_info: Dict[str, Any]):
        """Handle call start event - simplified"""
        try:
            call_id = call_info.get('call_id', f"call_{random.randint(1000, 9999)}")
            logger.info("Call started", call_info=call_info, call_id=call_id)
            
            # Note: Actual bot start happens in SIP INVITE handler
            # This is just for logging/tracking
            
        except Exception as e:
            logger.error("Error handling call start", call_id=call_id, error=str(e))
    
    async def _on_call_end(self, call_info: Dict[str, Any]):
        """Handle call end event - simplified"""
        try:
            call_id = call_info.get('call_id', 'unknown')
            logger.info("Call ended", call_info=call_info, call_id=call_id)
            
            # Cancel running bot if exists
            self.call_manager.end_call(call_id)
            
        except Exception as e:
            logger.error("Error handling call end", call_id=call_id, error=str(e))
    
    async def _on_sip_invite_received(self, invite_data: Dict[str, Any]):
        """
        Handle SIP INVITE - Start bot following Twilio/Telnyx pattern
        This is where the magic happens!
        """
        try:
            call_id = invite_data.get('call_id', f"call_{random.randint(1000, 9999)}")
            sdp_info = invite_data.get('sdp_info')
            
            logger.info("SIP INVITE received", call_id=call_id, sdp_info=sdp_info)
            
            if sdp_info and sdp_info.get('media_ip') and sdp_info.get('media_port'):
                client_ip = sdp_info['media_ip']
                client_port = sdp_info['media_port']
                
                logger.info("Valid SDP received", 
                           call_id=call_id,
                           client_ip=client_ip, 
                           client_port=client_port)
                
                # Get RTP configuration
                rtp_config = get_config_section('rtp') or get_config_section('RTP')
                bind_ip = rtp_config.get('bind_ip', '0.0.0.0')
                
                # Find available port
                min_port = int(rtp_config.get('min_port', '35000'))
                max_port = int(rtp_config.get('max_port', '35100'))
                bind_port = find_available_port(bind_ip, min_port, max_port)
                
                # Get configuration for services
                config_dict = {
                    'stt': dict(get_config_section('stt') or {}),
                    'llm': dict(get_config_section('llm') or {}),
                    'tts': dict(get_config_section('tts') or {}),
                    'openai': dict(get_config_section('openai') or {})
                }
                
                # Start bot using Twilio/Telnyx pattern - single function call!
                self.call_manager.start_call(
                    call_id,
                    run_opensips_bot(
                        call_id=call_id,
                        client_ip=client_ip,
                        client_port=client_port,
                        bind_ip=bind_ip,
                        bind_port=bind_port,
                        config=config_dict
                    ),
                    pattern="twilio_telnyx_compliant"
                )
                
                # Send 200 OK using bot's SDP info
                try:
                    # Get SDP info from bot
                    bot_sdp = get_bot_sdp_info(call_id, bind_ip, bind_port)
                    
                    # Create mock transport with SDP info for 200 OK
                    class MockTransport:
                        def get_sdp_info(self):
                            return bot_sdp
                    
                    await self.sip_listener.send_200_ok(invite_data, MockTransport())
                    
                    logger.info("SIP INVITE processed successfully", 
                               call_id=call_id, 
                               pattern="twilio_telnyx_compliant")
                               
                except Exception as send_error:
                    logger.error("Failed to send 200 OK", error=str(send_error), exc_info=True)
                    await self.sip_listener.send_500_internal_error(invite_data)
                    
                    # Cancel bot task if 200 OK failed
                    self.call_manager.end_call(call_id)

            else:
                logger.error("Invalid SDP info in INVITE request", 
                           sdp_info=sdp_info,
                           call_id=call_id)
                await self.sip_listener.send_400_bad_request(invite_data)
                
        except Exception as e:
            logger.error("Error handling SIP INVITE", error=str(e), exc_info=True)
            try:
                await self.sip_listener.send_500_internal_error(invite_data)
            except:
                pass
    
    
    async def start(self):
        """Start the application - much simpler!"""
        try:
            logger.info("Starting OpenSIPS AI Voice Connector (simplified)", 
                       pattern="twilio_telnyx_compliant")
            
            # Start event listener
            if self.event_listener:
                await self.event_listener.start()
            
            logger.info("OpenSIPS AI Voice Connector started successfully")
            
        except Exception as e:
            logger.error("Failed to start application", error=str(e))
            raise
    
    async def stop(self):
        """Stop the application - cleanup"""
        try:
            logger.info("Stopping OpenSIPS AI Voice Connector")
            
            # Cancel all active bot tasks
            self.call_manager.end_all()

            # Stop listeners
            if self.event_listener:
                await self.event_listener.stop()
            
            if self.sip_listener:
                await self.sip_listener.stop()
            
            logger.info("OpenSIPS AI Voice Connector stopped successfully")
            
        except Exception as e:
            logger.error("Error stopping application", error=str(e))


async def main():
    """Main entry point - much simpler!"""
    config_file = os.getenv('OAVC_CONFIG_FILE', 'cfg/opensips-ai-voice-connector.ini')
    
    try:
        # Initialize connector
        connector = OpenSIPSAIVoiceConnector(config_file)
        await connector.initialize()
        
        # Setup signal handlers
        def signal_handler(signum, frame):
            logger.info("Signal received, shutting down", signal=signum)
            if connector:
                asyncio.create_task(connector.stop())
        
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        
        # Start connector
        await connector.start()
        
        # Keep running
        logger.info("Application running, press Ctrl+C to stop")
        while True:
            await asyncio.sleep(1)
        
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received")
    except Exception as e:
        logger.error("Application error", error=str(e))
    finally:
        if 'connector' in locals():
            await connector.stop()


if __name__ == "__main__":
    asyncio.run(main())

# vim: tabstop=8 expandtab shiftwidth=4 softtabstop=4
