"""Unified Configuration Manager

Combines INI file parsing with environment variable overrides and Pydantic validation.
Provides a single source of truth for all configuration needs.
"""
from __future__ import annotations

import os
import configparser
from pathlib import Path
from typing import Any, Dict, Optional, Union

import structlog
from pydantic import BaseModel, Field, validator

logger = structlog.get_logger()


class ServiceConfig(BaseModel):
    """Configuration for external services (STT, LLM, TTS)."""
    
    url: str = Field(..., description="WebSocket URL for the service")
    model: Optional[str] = Field(None, description="Model name/identifier")
    sample_rate: Optional[int] = Field(None, description="Audio sample rate")
    voice: Optional[str] = Field(None, description="Voice identifier for TTS")
    temperature: Optional[float] = Field(None, description="LLM temperature")
    max_tokens: Optional[int] = Field(None, description="Maximum tokens for LLM")
    timeout: Optional[float] = Field(None, description="Service timeout in seconds")
    
    @validator("url", pre=True)
    @classmethod
    def validate_url(cls, v: str) -> str:
        """Validate and clean URL."""
        if not v:
            raise ValueError("Service URL cannot be empty")
        return v.strip()


class NetworkConfig(BaseModel):
    """Network and RTP configuration."""
    
    bind_ip: str = Field("0.0.0.0", description="IP to bind RTP transport")
    bind_port: int = Field(0, description="Port to bind RTP transport (0 = auto)")
    min_port: int = Field(35000, description="Minimum RTP port range")
    max_port: int = Field(35100, description="Maximum RTP port range")
    
    @validator("bind_port", pre=True)
    @classmethod
    def validate_port(cls, v: Union[int, str]) -> int:
        """Validate port number."""
        port = int(v) if isinstance(v, str) else v
        if port < 0 or port > 65535:
            raise ValueError(f"Invalid port number: {port}")
        return port


class VoiceConfig(BaseModel):
    """Voice processing configuration."""
    
    sample_rate: int = Field(16000, description="Pipeline sample rate")
    chunk_size: int = Field(160, description="Audio chunk size in bytes")
    vad_confidence: float = Field(0.15, description="VAD confidence threshold")
    vad_start_secs: float = Field(0.1, description="VAD start delay")
    vad_stop_secs: float = Field(0.25, description="VAD stop delay")
    enable_interruption: bool = Field(True, description="Enable voice interruption")
    
    @validator("vad_confidence")
    @classmethod
    def validate_confidence(cls, v: float) -> float:
        """Validate VAD confidence is between 0 and 1."""
        if not 0 <= v <= 1:
            raise ValueError(f"VAD confidence must be between 0 and 1, got {v}")
        return v


class UnifiedConfig(BaseModel):
    """Unified configuration combining all settings."""
    
    # Core configuration
    network: NetworkConfig = Field(default_factory=NetworkConfig)
    voice: VoiceConfig = Field(default_factory=VoiceConfig)
    
    # Services
    stt: ServiceConfig = Field(
        default_factory=lambda: ServiceConfig(
            url="ws://vosk-server:2700",
            sample_rate=16000,
            model="vosk-model-tr"
        )
    )
    llm: ServiceConfig = Field(
        default_factory=lambda: ServiceConfig(
            url="ws://llm-turkish-server:8765",
            model="llama3.2:3b-instruct-turkish",
            temperature=0.2,
            max_tokens=80,
            timeout=4.0
        )
    )
    tts: ServiceConfig = Field(
        default_factory=lambda: ServiceConfig(
            url="ws://piper-tts-server:8000/tts",
            voice="tr_TR-dfki-medium",
            sample_rate=22050
        )
    )
    
    # Environment
    debug: bool = Field(False, env="OAVC_DEBUG")
    log_level: str = Field("INFO", env="OAVC_LOG_LEVEL")
    
    class Config:
        env_prefix = "OAVC_"
        case_sensitive = False


class ConfigManager:
    """Unified configuration manager."""
    
    def __init__(self, config_file: Optional[str] = None):
        """Initialize configuration manager."""
        self.config_file = config_file or "cfg/opensips-ai-voice-connector.ini"
        self._config: Optional[UnifiedConfig] = None
        
    def load(self) -> UnifiedConfig:
        """Load configuration from file and environment."""
        if self._config is not None:
            return self._config
            
        # Start with defaults (includes env vars via Pydantic)
        config_dict = {}
        
        # Load INI file if it exists
        if os.path.exists(self.config_file):
            config_dict = self._load_ini_file()
            logger.info("Configuration loaded from INI file", file=self.config_file)
        else:
            logger.warning("Configuration file not found, using defaults", file=self.config_file)
        
        # Create unified config (Pydantic will handle env vars automatically)
        try:
            self._config = UnifiedConfig(**config_dict)
            logger.info("Configuration validated successfully")
            return self._config
        except Exception as e:
            logger.error("Configuration validation failed", error=str(e))
            raise ValueError(f"Invalid configuration: {e}")
    
    def _load_ini_file(self) -> Dict[str, Any]:
        """Load and parse INI configuration file."""
        try:
            parser = configparser.ConfigParser()
            parser.read(self.config_file)
            
            config_dict = {}
            
            # Network configuration
            if parser.has_section("rtp"):
                rtp_section = dict(parser["rtp"])
                config_dict["network"] = {
                    "bind_ip": rtp_section.get("bind_ip", "0.0.0.0"),
                    "bind_port": int(rtp_section.get("bind_port", "0")),
                    "min_port": int(rtp_section.get("min_port", "35000")),
                    "max_port": int(rtp_section.get("max_port", "35100")),
                }
            
            # Voice configuration
            voice_config = {}
            if parser.has_section("audio"):
                audio_section = dict(parser["audio"])
                voice_config.update({
                    "sample_rate": int(audio_section.get("sample_rate", "16000")),
                    "chunk_size": int(audio_section.get("chunk_size", "160")),
                })
            
            if parser.has_section("VAD"):
                vad_section = dict(parser["VAD"])
                voice_config.update({
                    "vad_confidence": float(vad_section.get("confidence", "0.15")),
                    "vad_start_secs": float(vad_section.get("start_secs", "0.1")),
                    "vad_stop_secs": float(vad_section.get("stop_secs", "0.25")),
                })
            
            if parser.has_section("interruption"):
                int_section = dict(parser["interruption"])
                voice_config.update({
                    "enable_interruption": int_section.get("enabled", "true").lower() == "true",
                })
            
            if voice_config:
                config_dict["voice"] = voice_config
            
            # Service configurations
            for service_name in ["stt", "llm", "tts"]:
                if parser.has_section(service_name):
                    section = dict(parser[service_name])
                    service_config = {"url": section.get("url", "")}
                    
                    # Add service-specific fields
                    for key in ["model", "voice", "sample_rate", "temperature", "max_tokens", "timeout"]:
                        if key in section:
                            value = section[key]
                            # Convert numeric values
                            if key in ["sample_rate", "max_tokens"]:
                                service_config[key] = int(value)
                            elif key in ["temperature", "timeout"]:
                                service_config[key] = float(value)
                            else:
                                service_config[key] = value
                    
                    config_dict[service_name] = service_config
            
            # General settings
            if parser.has_section("general"):
                general = dict(parser["general"])
                config_dict.update({
                    "log_level": general.get("loglevel", "INFO").upper(),
                    "debug": general.get("loglevel", "INFO").upper() == "DEBUG",
                })
            
            return config_dict
            
        except Exception as e:
            logger.error("Failed to parse INI file", file=self.config_file, error=str(e))
            raise ValueError(f"Failed to parse configuration file: {e}")
    
    def get_legacy_dict(self) -> Dict[str, Any]:
        """Convert to legacy dictionary format for backward compatibility."""
        config = self.load()
        
        return {
            "bind_ip": config.network.bind_ip,
            "bind_port": config.network.bind_port,
            "stt": {
                "url": config.stt.url,
                "sample_rate": config.stt.sample_rate,
                "model": config.stt.model,
            },
            "llm": {
                "url": config.llm.url,
                "model": config.llm.model,
                "temperature": config.llm.temperature,
                "max_tokens": config.llm.max_tokens,
                "timeout": config.llm.timeout,
            },
            "tts": {
                "url": config.tts.url,
                "voice": config.tts.voice,
                "sample_rate": config.tts.sample_rate,
            },
        }


# Global instance for easy access
_config_manager: Optional[ConfigManager] = None


def get_config_manager(config_file: Optional[str] = None) -> ConfigManager:
    """Get or create global configuration manager."""
    global _config_manager
    if _config_manager is None:
        _config_manager = ConfigManager(config_file)
    return _config_manager


def get_config(config_file: Optional[str] = None) -> UnifiedConfig:
    """Get unified configuration."""
    return get_config_manager(config_file).load() 