"""
Configuration Settings for OpenSIPS AI Voice Connector
Centralized configuration management
"""

import os
import configparser
import logging
from dataclasses import dataclass
from typing import Dict, Any, Optional
from pathlib import Path

logger = logging.getLogger(__name__)

@dataclass
class OpenSIPSConfig:
    """OpenSIPS integration configuration"""
    event_ip: str = "0.0.0.0"
    event_port: int = 8090
    sip_ip: str = "0.0.0.0"
    sip_port: int = 8089
    rtp_bind_ip: str = "0.0.0.0"
    rtp_min_port: int = 35000
    rtp_max_port: int = 35100

@dataclass
class ServiceConfig:
    """gRPC service configuration"""
    host: str
    port: int
    timeout: float = 30.0
    max_retries: int = 3
    
    @property
    def endpoint(self) -> str:
        return f"{self.host}:{self.port}"

@dataclass
class ServicesConfig:
    """All gRPC services configuration"""
    asr: ServiceConfig
    tts: ServiceConfig
    intent_recognition: Optional[ServiceConfig] = None
    vad: Optional[ServiceConfig] = None

@dataclass
class AudioConfig:
    """Audio processing configuration"""
    sample_rate: int = 16000
    channels: int = 1
    chunk_size_ms: int = 20
    silence_timeout_ms: int = 1000
    vad_threshold: float = 0.5

@dataclass
class LoggingConfig:
    """Logging configuration"""
    level: str = "INFO"
    format: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    file: Optional[str] = None

class Settings:
    """Main settings class"""
    
    def __init__(self, config_file: str):
        self.config_file = config_file
        self.opensips: OpenSIPSConfig = OpenSIPSConfig()
        self.services: ServicesConfig = None
        self.audio: AudioConfig = AudioConfig()
        self.logging: LoggingConfig = LoggingConfig()
        self._config: Optional[configparser.ConfigParser] = None
    
    async def load(self):
        """Load configuration from file"""
        try:
            # Check if config file exists
            config_path = Path(self.config_file)
            if not config_path.exists():
                logger.warning(f"Config file not found: {self.config_file}, using defaults")
                await self._load_from_env()
                return
            
            # Load from file
            self._config = configparser.ConfigParser()
            self._config.read(self.config_file)
            
            await self._load_opensips_config()
            await self._load_services_config()
            await self._load_audio_config()
            await self._load_logging_config()
            
            logger.info(f"Configuration loaded from: {self.config_file}")
            
        except Exception as e:
            logger.error(f"Failed to load configuration: {e}")
            # Fallback to environment variables
            await self._load_from_env()
    
    async def _load_opensips_config(self):
        """Load OpenSIPS configuration"""
        if not self._config or 'opensips' not in self._config:
            return
        
        section = self._config['opensips']
        self.opensips = OpenSIPSConfig(
            event_ip=section.get('event_ip', self.opensips.event_ip),
            event_port=section.getint('event_port', self.opensips.event_port),
            sip_ip=section.get('sip_ip', self.opensips.sip_ip),
            sip_port=section.getint('sip_port', self.opensips.sip_port),
            rtp_bind_ip=section.get('rtp_bind_ip', self.opensips.rtp_bind_ip),
            rtp_min_port=section.getint('rtp_min_port', self.opensips.rtp_min_port),
            rtp_max_port=section.getint('rtp_max_port', self.opensips.rtp_max_port),
        )
    
    async def _load_services_config(self):
        """Load gRPC services configuration"""
        # ASR Service  
        asr_host = self._get_config_value('asr', 'host', 'localhost')
        asr_port = self._get_config_value('asr', 'port', '50051', int)
        asr_timeout = self._get_config_value('asr', 'timeout', '30.0', float)
        
        
        # TTS Service
        tts_host = self._get_config_value('tts', 'host', 'localhost')
        tts_port = self._get_config_value('tts', 'port', '50053', int)
        tts_timeout = self._get_config_value('tts', 'timeout', '30.0', float)
        
        # Intent Recognition Service (REST)
        intent_host = self._get_config_value('intent', 'host', 'localhost')
        intent_port = self._get_config_value('intent', 'port', '5000', int)
        intent_timeout = self._get_config_value('intent', 'timeout', '30.0', float)
        
        self.services = ServicesConfig(
            asr=ServiceConfig(host=asr_host, port=asr_port, timeout=asr_timeout),
            tts=ServiceConfig(host=tts_host, port=tts_port, timeout=tts_timeout),
            intent_recognition=ServiceConfig(host=intent_host, port=intent_port, timeout=intent_timeout)
        )
    
    async def _load_audio_config(self):
        """Load audio configuration"""
        if not self._config or 'audio' not in self._config:
            return
        
        section = self._config['audio']
        self.audio = AudioConfig(
            sample_rate=section.getint('sample_rate', self.audio.sample_rate),
            channels=section.getint('channels', self.audio.channels),
            chunk_size_ms=section.getint('chunk_size_ms', self.audio.chunk_size_ms),
            silence_timeout_ms=section.getint('silence_timeout_ms', self.audio.silence_timeout_ms),
            vad_threshold=section.getfloat('vad_threshold', self.audio.vad_threshold),
        )
    
    async def _load_logging_config(self):
        """Load logging configuration"""
        if not self._config or 'logging' not in self._config:
            return
        
        section = self._config['logging']
        self.logging = LoggingConfig(
            level=section.get('level', self.logging.level),
            format=section.get('format', self.logging.format),
            file=section.get('file', self.logging.file),
        )
    
    def _get_config_value(self, section: str, key: str, default: str, value_type=str):
        """Get configuration value with type conversion"""
        if self._config and section in self._config:
            if value_type == int:
                return self._config[section].getint(key, int(default))
            elif value_type == float:
                return self._config[section].getfloat(key, float(default))
            elif value_type == bool:
                return self._config[section].getboolean(key, bool(default))
            else:
                return self._config[section].get(key, default)
        return value_type(default)
    
    async def _load_from_env(self):
        """Load configuration from environment variables as fallback"""
        logger.info("Loading configuration from environment variables")
        
        # OpenSIPS config
        self.opensips = OpenSIPSConfig(
            event_ip=os.getenv('OPENSIPS_EVENT_IP', '0.0.0.0'),
            event_port=int(os.getenv('OPENSIPS_EVENT_PORT', '8090')),
            sip_ip=os.getenv('OPENSIPS_SIP_IP', '0.0.0.0'),
            sip_port=int(os.getenv('OPENSIPS_SIP_PORT', '8089')),
            rtp_bind_ip=os.getenv('OPENSIPS_RTP_BIND_IP', '0.0.0.0'),
            rtp_min_port=int(os.getenv('OPENSIPS_RTP_MIN_PORT', '35000')),
            rtp_max_port=int(os.getenv('OPENSIPS_RTP_MAX_PORT', '35100')),
        )
        
        # Services config
        self.services = ServicesConfig(
            asr=ServiceConfig(
                host=os.getenv('ASR_SERVICE_HOST', 'localhost'),
                port=int(os.getenv('ASR_SERVICE_PORT', '50051'))
            ),
            tts=ServiceConfig(
                host=os.getenv('TTS_SERVICE_HOST', 'localhost'),
                port=int(os.getenv('TTS_SERVICE_PORT', '50053'))
            ),
            intent_recognition=ServiceConfig(
                host=os.getenv('INTENT_SERVICE_HOST', 'localhost'),
                port=int(os.getenv('INTENT_SERVICE_PORT', '5000'))
            )
        )
        
        # Audio config
        self.audio = AudioConfig(
            sample_rate=int(os.getenv('AUDIO_SAMPLE_RATE', '16000')),
            channels=int(os.getenv('AUDIO_CHANNELS', '1')),
            chunk_size_ms=int(os.getenv('AUDIO_CHUNK_SIZE_MS', '20')),
            silence_timeout_ms=int(os.getenv('AUDIO_SILENCE_TIMEOUT_MS', '1000')),
            vad_threshold=float(os.getenv('AUDIO_VAD_THRESHOLD', '0.5')),
        )
        
        # Logging config
        self.logging = LoggingConfig(
            level=os.getenv('LOG_LEVEL', 'INFO'),
            format=os.getenv('LOG_FORMAT', '%(asctime)s - %(name)s - %(levelname)s - %(message)s'),
            file=os.getenv('LOG_FILE', None),
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert settings to dictionary"""
        return {
            'opensips': {
                'event_ip': self.opensips.event_ip,
                'event_port': self.opensips.event_port,
                'sip_ip': self.opensips.sip_ip,
                'sip_port': self.opensips.sip_port,
                'rtp_bind_ip': self.opensips.rtp_bind_ip,
                'rtp_min_port': self.opensips.rtp_min_port,
                'rtp_max_port': self.opensips.rtp_max_port,
            },
            'services': {
                'asr': {'host': self.services.asr.host, 'port': self.services.asr.port},
                'tts': {'host': self.services.tts.host, 'port': self.services.tts.port},
            },
            'audio': {
                'sample_rate': self.audio.sample_rate,
                'channels': self.audio.channels,
                'chunk_size_ms': self.audio.chunk_size_ms,
                'silence_timeout_ms': self.audio.silence_timeout_ms,
                'vad_threshold': self.audio.vad_threshold,
            },
            'logging': {
                'level': self.logging.level,
                'format': self.logging.format,
                'file': self.logging.file,
            }
        }