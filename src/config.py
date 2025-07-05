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
Parses the configuration file.
This is a simplified, functional approach to configuration management.
"""

import configparser
import os
import structlog
from configparser import SectionProxy
from typing import Optional

logger = structlog.get_logger()

_config: Optional[configparser.ConfigParser] = None

class ConfigValidationError(Exception):
    """Custom exception for configuration validation errors."""
    pass

def initialize(config_file: str):
    """
    Initializes the config parser with a configuration file.
    This must be called once at application startup.
    """
    global _config
    if _config:
        logger.warning("Configuration has already been initialized.")
        return

    _config = configparser.ConfigParser()
    if not os.path.exists(config_file):
        raise ConfigValidationError(f"Configuration file not found: {config_file}")
    
    try:
        _config.read(config_file)
        logger.info("Configuration file loaded successfully", file=config_file)
    except configparser.Error as e:
        raise ConfigValidationError(f"Error parsing configuration file {config_file}: {e}")

def get_section(section: str) -> Optional[SectionProxy]:
    """
    Get a whole configuration section.
    Returns a SectionProxy object, which is dict-like.
    Returns None if the config is not initialized or the section does not exist.
    """
    if not _config or not _config.has_section(section):
        return None
    return _config[section]

def get_env(key: str, default: str = "") -> str:
    """
    Get environment variable with fallback to default value.
    Helper function for configuration.
    """
    return os.environ.get(key, default)

# vim: tabstop=8 expandtab shiftwidth=4 softtabstop=4
