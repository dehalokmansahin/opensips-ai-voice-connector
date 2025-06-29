#!/usr/bin/env python3
"""
OpenSIPS AI Voice Connector - Main Entry Point
Docker Container için ana giriş noktası
"""

import sys
import os
import asyncio
import signal
import socket
from pathlib import Path

# Python path setup
current_dir = Path(__file__).parent
src_path = current_dir
pipecat_src_path = current_dir.parent / "pipecat" / "src"

if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))
if str(pipecat_src_path) not in sys.path:
    sys.path.insert(0, str(pipecat_src_path))

# soxr compatibility stub for NumPy 2.x
import numpy as np
if not hasattr(sys.modules, 'soxr'):
    class SoxrStub:
        def resample(self, *args, **kwargs):
            return np.array([])
    sys.modules['soxr'] = SoxrStub()

# Imports
import structlog
from pipeline.manager import PipelineManager
from services.llama_websocket import LlamaWebsocketLLMService
from services.vosk_websocket import VoskWebsocketSTTService
from services.piper_websocket import PiperWebsocketTTSService
from call import Call
import configparser

# Setup logging
logger = structlog.get_logger()

class SIPCallHandler:
    """SIP Call Handler - OpenSIPS'den gelen çağrıları işler"""
    
    def __init__(self, host="0.0.0.0", port=8088):
        self.host = host
        self.port = port
        self.socket = None
        self.running = False
        
    async def start(self):
        """SIP handler'ı başlat"""
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.socket.bind((self.host, self.port))
            self.socket.setblocking(False)
            self.running = True
            
            logger.info("SIP Call Handler started", host=self.host, port=self.port)
            
            # Listen for incoming SIP messages
            while self.running:
                try:
                    loop = asyncio.get_event_loop()
                    data, addr = await loop.sock_recvfrom(self.socket, 4096)
                    
                    # Process SIP message
                    await self.handle_sip_message(data.decode('utf-8'), addr)
                    
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    logger.error("Error in SIP handler", error=str(e))
                    await asyncio.sleep(0.1)
                    
        except Exception as e:
            logger.error("Failed to start SIP handler", error=str(e))
            raise
    
    async def handle_sip_message(self, message: str, addr):
        """SIP mesajını işle"""
        try:
            logger.info("Received SIP message", 
                       from_addr=f"{addr[0]}:{addr[1]}", 
                       message_preview=message[:200])
            
            # Basic SIP INVITE handling
            if "INVITE" in message and "sip:" in message:
                logger.info("Processing SIP INVITE call")
                
                # Extract basic call information
                lines = message.split('\n')
                call_id = None
                from_header = None
                to_header = None
                
                for line in lines:
                    if line.startswith('Call-ID:'):
                        call_id = line.split(':', 1)[1].strip()
                    elif line.startswith('From:'):
                        from_header = line.split(':', 1)[1].strip()
                    elif line.startswith('To:'):
                        to_header = line.split(':', 1)[1].strip()
                
                # Send SIP 200 OK response
                response = self.create_sip_200_ok(call_id, from_header, to_header)
                await self.send_sip_response(response, addr)
                
                logger.info("Sent SIP 200 OK response", call_id=call_id)
                
            elif "BYE" in message:
                logger.info("Processing SIP BYE")
                # Send 200 OK for BYE
                response = "SIP/2.0 200 OK\r\n\r\n"
                await self.send_sip_response(response, addr)
                
        except Exception as e:
            logger.error("Error handling SIP message", error=str(e))
    
    def create_sip_200_ok(self, call_id, from_header, to_header):
        """SIP 200 OK response oluştur"""
        response = f"""SIP/2.0 200 OK
Via: SIP/2.0/UDP {self.host}:{self.port}
Call-ID: {call_id or 'unknown'}
From: {from_header or 'unknown'}
To: {to_header or 'unknown'}
CSeq: 1 INVITE
Contact: <sip:{self.host}:{self.port}>
Content-Type: application/sdp
Content-Length: 0

"""
        return response
    
    async def send_sip_response(self, response: str, addr):
        """SIP response gönder"""
        try:
            loop = asyncio.get_event_loop()
            await loop.sock_sendto(self.socket, response.encode('utf-8'), addr)
            logger.debug("Sent SIP response", to_addr=f"{addr[0]}:{addr[1]}")
        except Exception as e:
            logger.error("Error sending SIP response", error=str(e))
    
    async def stop(self):
        """SIP handler'ı durdur"""
        self.running = False
        if self.socket:
            self.socket.close()
        logger.info("SIP Call Handler stopped")

class OpenSIPSAIVoiceConnector:
    """OpenSIPS AI Voice Connector Ana Sınıfı"""
    
    def __init__(self, config_file: str = None):
        self.config_file = config_file or os.getenv('CONFIG_FILE', '/app/cfg/opensips-ai-voice-connector.ini')
        self.config = configparser.ConfigParser()
        self.pipeline_manager = None
        self.services = {}
        self.sip_handler = None
        self.running = False
        
        logger.info("OpenSIPS AI Voice Connector initializing", config_file=self.config_file)
    
    def load_config(self):
        """Konfigürasyon dosyasını yükle"""
        try:
            self.config.read(self.config_file)
            logger.info("Configuration loaded successfully", config_file=self.config_file)
            
            # Log some key config values
            if 'llm' in self.config:
                logger.info("LLM config", 
                           url=self.config.get('llm', 'url', fallback='ws://llm-turkish-server:8765'),
                           model=self.config.get('llm', 'model', fallback='llama3.2:3b'))
            
            if 'stt' in self.config:
                logger.info("STT config",
                           url=self.config.get('stt', 'url', fallback='ws://vosk-server:2700'))
            
            if 'tts' in self.config:
                logger.info("TTS config",
                           url=self.config.get('tts', 'url', fallback='ws://piper-tts-server:8000/tts'))
                           
        except Exception as e:
            logger.error("Failed to load configuration", error=str(e))
            raise
    
    async def initialize_services(self):
        """Servisleri başlat"""
        try:
            logger.info("Initializing AI services...")
            
            # LLM Service
            llm_url = self.config.get('llm', 'url', fallback='ws://llm-turkish-server:8765')
            self.services['llm'] = LlamaWebsocketLLMService(url=llm_url)
            
            # STT Service  
            stt_url = self.config.get('stt', 'url', fallback='ws://vosk-server:2700')
            self.services['stt'] = VoskWebsocketSTTService(url=stt_url)
            
            # TTS Service
            tts_url = self.config.get('tts', 'url', fallback='ws://piper-tts-server:8000/tts')
            self.services['tts'] = PiperWebsocketTTSService(url=tts_url)
            
            # Start all services
            for service_name, service in self.services.items():
                logger.info(f"Starting {service_name} service...")
                await service.start()
                logger.info(f"{service_name} service started successfully")
            
            # Initialize Pipeline Manager
            self.pipeline_manager = PipelineManager(
                llm_service=self.services['llm'],
                stt_service=self.services['stt'], 
                tts_service=self.services['tts']
            )
            
            await self.pipeline_manager.start()
            logger.info("Pipeline manager started successfully")
            
        except Exception as e:
            logger.error("Failed to initialize services", error=str(e))
            raise
    
    async def start_call_handler(self):
        """Call handler'ı başlat"""
        try:
            logger.info("Starting SIP call handler...")
            
            # SIP configuration
            sip_port = int(self.config.get('sip', 'port', fallback='8088'))
            sip_host = self.config.get('sip', 'host', fallback='0.0.0.0')
            
            # Initialize SIP handler
            self.sip_handler = SIPCallHandler(host=sip_host, port=sip_port)
            
            # Start SIP handler
            await self.sip_handler.start()
                
        except Exception as e:
            logger.error("Call handler error", error=str(e))
            raise
    
    async def start(self):
        """Ana servisi başlat"""
        try:
            self.running = True
            
            # Load configuration
            self.load_config()
            
            # Initialize services
            await self.initialize_services()
            
            logger.info("🎉 OpenSIPS AI Voice Connector started successfully!")
            logger.info("🎯 Services ready:")
            logger.info("   ✅ LLM (Custom LLaMA WebSocket)")
            logger.info("   ✅ STT (Vosk WebSocket)")
            logger.info("   ✅ TTS (Piper WebSocket)")
            logger.info("   ✅ Pipeline Manager")
            logger.info("   ✅ SIP Call Handler")
            
            # Start call handler
            await self.start_call_handler()
            
        except Exception as e:
            logger.error("Failed to start OpenSIPS AI Voice Connector", error=str(e))
            await self.stop()
            raise
    
    async def stop(self):
        """Servisi durdur"""
        logger.info("Stopping OpenSIPS AI Voice Connector...")
        self.running = False
        
        # Stop SIP handler
        if self.sip_handler:
            await self.sip_handler.stop()
            logger.info("SIP handler stopped")
        
        # Stop pipeline manager
        if self.pipeline_manager:
            await self.pipeline_manager.stop()
            logger.info("Pipeline manager stopped")
        
        # Stop all services
        for service_name, service in self.services.items():
            try:
                await service.stop()
                logger.info(f"{service_name} service stopped")
            except Exception as e:
                logger.error(f"Error stopping {service_name}", error=str(e))
        
        logger.info("OpenSIPS AI Voice Connector stopped")

async def main():
    """Ana fonksiyon"""
    
    # Setup signal handlers
    connector = OpenSIPSAIVoiceConnector()
    
    def signal_handler(signum, frame):
        logger.info("Received signal, shutting down...", signal=signum)
        asyncio.create_task(connector.stop())
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        await connector.start()
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received")
    except Exception as e:
        logger.error("Application error", error=str(e))
        return 1
    finally:
        await connector.stop()
    
    return 0

if __name__ == "__main__":
    print("🚀 OpenSIPS AI Voice Connector Starting...")
    print("=" * 50)
    
    # Configure logging
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="ISO"),
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
    
    # Run the application
    exit_code = asyncio.run(main())
    sys.exit(exit_code)

# vim: tabstop=8 expandtab shiftwidth=4 softtabstop=4
