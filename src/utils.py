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
Utilities and configuration for OpenSIPS AI Voice Connector
"""

import re
import configparser
from pathlib import Path
import logging
from sipmessage import Address
from config import get as get_config_section, sections as get_config_sections

logger = logging.getLogger(__name__)

# Pipecat AI Engine import
try:
    from pipeline.ai_engine import PipelineAI
    PIPECAT_AVAILABLE = True
    logger.info("Pipecat AI engine available")
except ImportError as e:
    PipelineAI = None
    PIPECAT_AVAILABLE = False
    logger.warning(f"Pipecat AI engine not available: {e}")

# AI Engine flavors mapping - Sadece Pipecat
FLAVORS = {}

# Register Pipecat AI engine
if PipelineAI:
    FLAVORS['pipecat'] = PipelineAI

# Log available flavors
logger.info(f"Available AI flavors: {list(FLAVORS.keys())}")

class UnknownSIPUser(Exception):
    """ User is not known """


def get_header(params, header):
    """ Returns a specific line from headers """
    if 'headers' not in params:
        return None
    
    # Debug: Check the type of headers field
    headers = params['headers']
    logger.debug(f"get_header: headers type: {type(headers)}, content: {headers}")
    
    # Handle both string and dict types
    if isinstance(headers, dict):
        # If headers is a dict, look for the header directly
        for key, value in headers.items():
            if key.lower() == header.lower():
                return value
        return None
    elif isinstance(headers, str):
        # Original string processing
        hdr_lines = [line for line in headers.splitlines()
                     if re.match(f"{header}:", line, re.I)]
        if len(hdr_lines) == 0:
            return None
        return hdr_lines[0].split(":", 1)[1].strip()
    else:
        logger.error(f"get_header: Unexpected headers type: {type(headers)}")
        return None


def get_to(params):
    """ Returns the To line parameters """
    to_line = get_header(params, "To")
    if not to_line:
        return None
    return Address.parse(to_line)


def indialog(params):
    """ indicates whether the message is an in-dialog one """
    if 'headers' not in params:
        return False
    to = get_to(params)
    if not to:
        return False
    params = to.parameters
    if "tag" in params and len(params["tag"]) > 0:
        return True
    return False


def get_user(params):
    """ Returns the User from the SIP headers """
    to = get_to(params)
    return to.uri.user.lower() if to.uri else None


def _dialplan_match(regex, string):
    """ Checks if a regex matches the string """
    pattern = re.compile(regex)
    return pattern.match(string)


def get_ai_flavor_default(user):
    """ Returns the default algorithm for AI choosing """
    # remove disabled engines
    keys = [k for k, _ in FLAVORS.items() if
            not get_config_section(k).getboolean("disabled",
                                         f"{k.upper()}_DISABLE",
                                         False)]
    if user in keys:
        return user
    if keys:
        hash_index = hash(user) % len(keys)
        return keys[hash_index]
    else:
        # Default to pipecat if available
        return 'pipecat' if 'pipecat' in FLAVORS else None


def get_ai_flavor(params):
    """ Returns the AI flavor to be used """

    user = get_user(params)
    if not user:
        raise UnknownSIPUser("cannot parse username")

    # first, get the sections in order and check if they have a dialplan
    flavor = None
    for flavor in get_config_sections():
        if flavor not in FLAVORS:
            continue
        if get_config_section(flavor).getboolean("disabled",
                                         f"{flavor.upper()}_DISABLE",
                                         False):
            continue
        dialplans = get_config_section(flavor).get("match")
        if not dialplans:
            continue
        if isinstance(dialplans, list):
            for dialplan in dialplans:
                if _dialplan_match(dialplan, user):
                    return flavor
        elif _dialplan_match(dialplans, user):
            return flavor
    
    # If no specific flavor found, use default
    default_flavor = get_ai_flavor_default(user)
    if default_flavor:
        return default_flavor
    else:
        # Fallback to pipecat
        return 'pipecat'


def get_ai(flavor, call, cfg):
    """ Returns an AI object """
    if flavor not in FLAVORS:
        logger.warning(f"AI flavor '{flavor}' not available, using pipecat")
        flavor = 'pipecat'
    
    if flavor not in FLAVORS:
        raise ValueError(f"No AI flavors available! Available: {list(FLAVORS.keys())}")
        
    return FLAVORS[flavor](call, cfg)


def load_config(config_path: str):
    """Config dosyasını yükle"""
    config = configparser.ConfigParser()
    config.read(config_path)
    
    # Config objesi oluştur
    class ConfigWrapper:
        def __init__(self, config_parser):
            self.config = config_parser
            
            # Default values
            self.ai_flavor = self.config.get('ai', 'flavor', fallback='pipecat')
            self.ai_model = self.config.get('ai', 'model', fallback='default')
            self.sample_rate = self.config.getint('audio', 'sample_rate', fallback=16000)
            self.chunk_size = self.config.getint('audio', 'chunk_size', fallback=160)
            
            # OpenSIPS settings
            self.opensips_host = self.config.get('opensips', 'host', fallback='localhost')
            self.opensips_port = self.config.getint('opensips', 'port', fallback=5060)
            
            # Vosk settings
            self.vosk_url = self.config.get('vosk', 'url', fallback='ws://localhost:2700')
            
            # Validate AI flavor
            if self.ai_flavor not in FLAVORS:
                logger.warning(f"AI flavor '{self.ai_flavor}' not available, using fallback")
                # Fallback to pipecat
                self.ai_flavor = 'pipecat'
                logger.info(f"Using fallback AI flavor: {self.ai_flavor}")
    
    return ConfigWrapper(config)

def get_ai_engine_class(flavor: str):
    """AI flavor'ına göre engine class'ını döndür"""
    if flavor not in FLAVORS:
        available = list(FLAVORS.keys())
        raise ValueError(f"AI flavor '{flavor}' not available. Available: {available}")
    
    return FLAVORS[flavor]

def list_available_flavors():
    """Mevcut AI flavor'larını listele"""
    return list(FLAVORS.keys())

# Backward compatibility
def create_ai_engine(flavor: str, call, cfg):
    """AI engine oluştur"""
    engine_class = get_ai_engine_class(flavor)
    return engine_class(call, cfg)

# Debug info
if __name__ == "__main__":
    print("🔧 OpenSIPS AI Voice Connector Utils")
    print("=" * 40)
    print(f"Available AI Flavors: {list_available_flavors()}")
    print(f"Pipecat Available: {PIPECAT_AVAILABLE}")
    
    for flavor, engine_class in FLAVORS.items():
        print(f"  - {flavor}: {engine_class.__name__ if engine_class else 'None'}")

# vim: tabstop=8 expandtab shiftwidth=4 softtabstop=4
