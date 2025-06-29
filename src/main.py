#!/usr/bin/env python3
"""
OpenSIPS AI Voice Connector - Main Entry Point
Docker Container için ana giriş noktası
"""

import sys
import os
import asyncio
import signal
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

class OpenSIPSAIVoiceConnector:
    """OpenSIPS AI Voice Connector Ana Sınıfı"""
    
    def __init__(self, config_file: str = None):
        self.config_file = config_file or os.getenv('CONFIG_FILE', '/app/cfg/opensips-ai-voice-connector.ini')
        self.config = configparser.ConfigParser()
        self.pipeline_manager = None
        self.services = {}
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
                           url=self.config.get('llm', 'url', fallback='http://ollama:11434/api/generate'),
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
            llm_url = self.config.get('llm', 'url', fallback='ws://llama-server:8765')
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
            logger.info("Starting call handler...")
            
            # SIP configuration
            sip_port = int(self.config.get('sip', 'port', fallback='8088'))
            sip_host = self.config.get('sip', 'host', fallback='0.0.0.0')
            
            # Call handler setup - basit bir implementasyon
            logger.info("Call handler ready", host=sip_host, port=sip_port)
            
            # Burada gerçek SIP call handling implementasyonu olacak
            # Şimdilik placeholder
            while self.running:
                await asyncio.sleep(1)
                
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
