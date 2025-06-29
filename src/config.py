#!/usr/bin/env python
#
# Copyright (C) 2024 SIP Point Consulting SRL
#
# This file is part of the OpenSIPS AI Voice Connector project
# (see https://github.com/OpenSIPS/opensips-ai-voice-connector-ce).
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program. If not, see <http://www.gnu.org/licenses/>.
#

"""
Parses the configuration file with enhanced validation and service initialization checks
"""

import os
import configparser
import structlog
from typing import Dict, List, Optional, Union
import asyncio

# Optional dependencies for enhanced validation
try:
    import validators
    import aiohttp
    VALIDATORS_AVAILABLE = True
except ImportError:
    VALIDATORS_AVAILABLE = False

logger = structlog.get_logger()

_Config = configparser.ConfigParser()


class ConfigValidationError(Exception):
    """Custom exception for configuration validation errors"""
    pass


class ServiceConfigValidator:
    """Validates service configurations and checks connectivity"""
    
    @staticmethod
    def validate_url(url: str) -> bool:
        """URL formatını validate et"""
        if not VALIDATORS_AVAILABLE:
            return True  # Skip validation if validators not available
        return validators.url(url) is True
    
    @staticmethod
    async def check_service_connectivity(url: str, timeout: float = 5.0) -> bool:
        """Service connectivity kontrolü"""
        if not VALIDATORS_AVAILABLE:
            return True  # Skip connectivity check if aiohttp not available
        
        try:
            # WebSocket URL'leri için HTTP health check endpoint varsayıyoruz
            http_url = url.replace('ws://', 'http://').replace('wss://', 'https://')
            if http_url.endswith('/tts'):
                http_url = http_url.replace('/tts', '/health')
            elif not http_url.endswith('/health'):
                http_url += '/health'
            
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=timeout)) as session:
                async with session.get(http_url) as response:
                    return response.status < 500  # Accept any non-server-error status
        except Exception as e:
            logger.warning("Service connectivity check failed", url=url, error=str(e))
            return False  # Connectivity check failed, but continue anyway


class ConfigSection(dict):
    """ class that handles a config section """

    def __init__(self, section, custom=None):
        super().__init__(section)
        self.update(custom)

    def getenv(self, env, fallback=None):
        """ returns the configuration from environment """
        if not env:
            return fallback
        if isinstance(env, list):
            # check to see whether we have any of the keys
            for e in env:
                if e in os.environ:
                    return os.getenv(e)
            # no key found - check if env is a list
            return fallback
        return os.getenv(env, fallback)

    def get(self, option, env=None, fallback=None):
        """ returns the configuration for the required option """
        if isinstance(option, list):
            # check to see whether we have any of the keys
            for o in option:
                if o in self.keys():
                    return super().get(o)
            # no key found - check if env is a list
            return self.getenv(env, fallback)
        return super().get(option, self.getenv(env, fallback))

    def getboolean(self, option, env=None, fallback=None):
        """ returns a boolean value from the configuration """
        val = self.get(option, env, None)
        if not val:
            return fallback
        if val.isnumeric():
            return int(val) != 0
        if val.lower() in ["yes", "true", "on"]:
            return True
        if val.lower() in ["no", "false", "off"]:
            return False
        return fallback

    def getint(self, option, env=None, fallback=None):
        """ returns an integer value from the configuration """
        val = self.get(option, env, fallback)
        try:
            return int(val) if val is not None else fallback
        except (ValueError, TypeError):
            logger.warning(f"Invalid integer value for {option}: {val}, using fallback: {fallback}")
            return fallback

    def getfloat(self, option, env=None, fallback=None):
        """ returns a float value from the configuration """
        val = self.get(option, env, fallback)
        try:
            return float(val) if val is not None else fallback
        except (ValueError, TypeError):
            logger.warning(f"Invalid float value for {option}: {val}, using fallback: {fallback}")
            return fallback


class Config():
    """ class that handles the config with enhanced validation """

    @staticmethod
    def init(config_file):
        """ Initializes the config with a configuration file """
        config_file = config_file or os.getenv('CONFIG_FILE')
        if config_file:
            if not os.path.exists(config_file):
                raise ConfigValidationError(f"Configuration file not found: {config_file}")
            
            try:
                _Config.read(config_file)
                logger.info("Configuration file loaded successfully", file=config_file)
            except configparser.Error as e:
                raise ConfigValidationError(f"Error parsing configuration file {config_file}: {str(e)}")
        else:
            logger.warning("No configuration file specified, using defaults and environment variables")

    @staticmethod
    def get(section, init_data=None):
        """ Retrieves a specific section from the config file """
        if section not in _Config:
            _Config.add_section(section)
        if not init_data:
            init_data = {}
        return ConfigSection(_Config[section], init_data)

    @staticmethod
    def engine(option, env=None, fallback=None):
        """ Special handling for the engine section """
        section = Config.get("engine")
        return section.get(option, env, fallback)

    @staticmethod
    def sections():
        """ Retrieves the sections from the config file """
        return _Config.sections()

    @staticmethod
    async def validate_services_config() -> Dict[str, Dict[str, Union[str, bool]]]:
        """
        Validate all service configurations and check connectivity
        
        Returns:
            Dict: Service validation results
            
        Raises:
            ConfigValidationError: If critical services are misconfigured
        """
        validation_results = {}
        validator = ServiceConfigValidator()
        
        # LLM Service Validation
        try:
            llm_config = Config.get("llm")
            required_llm_fields = ["url"]
            validator.validate_required_fields(llm_config, required_llm_fields, "llm")
            
            llm_url = llm_config.get("url")
            llm_reachable = await validator.validate_service_url(llm_url, "LLM")
            
            validation_results["llm"] = {
                "url": llm_url,
                "reachable": llm_reachable,
                "validated": True
            }
            
        except ConfigValidationError as e:
            logger.error("LLM service validation failed", error=str(e))
            validation_results["llm"] = {"validated": False, "error": str(e)}
        
        # STT Service Validation
        try:
            stt_config = Config.get("stt")
            required_stt_fields = ["url"]
            validator.validate_required_fields(stt_config, required_stt_fields, "stt")
            
            stt_url = stt_config.get("url")
            stt_reachable = await validator.validate_service_url(stt_url, "STT")
            
            validation_results["stt"] = {
                "url": stt_url,
                "reachable": stt_reachable,
                "validated": True
            }
            
        except ConfigValidationError as e:
            logger.error("STT service validation failed", error=str(e))
            validation_results["stt"] = {"validated": False, "error": str(e)}
        
        # TTS Service Validation
        try:
            tts_config = Config.get("tts")
            required_tts_fields = ["url"]
            validator.validate_required_fields(tts_config, required_tts_fields, "tts")
            
            tts_url = tts_config.get("url")
            tts_reachable = await validator.validate_service_url(tts_url, "TTS")
            
            validation_results["tts"] = {
                "url": tts_url,
                "reachable": tts_reachable,
                "validated": True
            }
            
        except ConfigValidationError as e:
            logger.error("TTS service validation failed", error=str(e))
            validation_results["tts"] = {"validated": False, "error": str(e)}
        
        # OpenSIPS Service Validation
        try:
            opensips_config = Config.get("opensips")
            required_opensips_fields = ["ip", "port"]
            validator.validate_required_fields(opensips_config, required_opensips_fields, "opensips")
            
            validation_results["opensips"] = {
                "ip": opensips_config.get("ip"),
                "port": opensips_config.getint("port"),
                "validated": True
            }
            
        except ConfigValidationError as e:
            logger.error("OpenSIPS service validation failed", error=str(e))
            validation_results["opensips"] = {"validated": False, "error": str(e)}
        
        # Log validation summary
        valid_services = sum(1 for result in validation_results.values() if result.get("validated", False))
        total_services = len(validation_results)
        
        logger.info("Service configuration validation completed", 
                   valid_services=valid_services, 
                   total_services=total_services,
                   results=validation_results)
        
        # Check if critical services are valid
        critical_services = ["llm", "stt", "tts", "opensips"]
        failed_critical = [name for name in critical_services 
                          if not validation_results.get(name, {}).get("validated", False)]
        
        if failed_critical:
            raise ConfigValidationError(
                f"Critical services failed validation: {', '.join(failed_critical)}"
            )
        
        return validation_results


# vim: tabstop=8 expandtab shiftwidth=4 softtabstop=4
