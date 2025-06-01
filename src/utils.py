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
Module that provides helper functions for AI
"""
from typing import Callable, Any, Dict, Optional
import re
from src.ai import AIEngine # For type hinting get_ai return
# from deepgram_api import Deepgram
# from openai_api import OpenAI
# from deepgram_native_api import DeepgramNative
# from speech_session_vosk import SmartSpeech # Replaced by SpeechSessionManager
from src.speech_processing.speech_session_manager import SpeechSessionManager
from src.speech_processing.vosk_stt_engine import VoskSTTEngine
from src.speech_processing.piper_tts_engine import PiperTTSEngine
# Try to import Azure, but don't fail if not available
# try:
#     from azure_api import AzureAI
#     has_azure = True
# except ImportError:
#     has_azure = False
#     print("Azure module not available, Azure STT provider will be disabled")
from config import Config

# Initialize FLAVORS dictionary
# For SmartSpeech replacement, we'll define a helper or lambda
# to correctly instantiate SpeechSessionManager with its required engines.

def _create_speech_session_manager(call, cfg):
    """
    Creates and returns a SpeechSessionManager instance with initialized STT and TTS engines.
    
    Args:
        call: The call object that contains the RTP queue and other call-specific data.
        cfg: A ConfigSection object containing configuration for the SmartSpeech flavor.
             This should contain settings like "url", "host", "port", "TTS_VOICE", etc.
    
    Returns:
        A configured SpeechSessionManager instance ready to handle speech interactions.
    """
    # cfg here is the session-specific config section for "SmartSpeech" flavor
    # Global Config is accessible via from config import Config

    # STT Engine (Vosk)
    # These settings should come from the 'SmartSpeech' (or new name) section of the config
    vosk_url = cfg.get("url", "ws://localhost:2700")
    # Determine Vosk timeout as float (cfg may be plain dict)
    try:
        vosk_timeout = float(cfg.get("websocket_timeout", "5.0"))
    except (TypeError, ValueError):
        vosk_timeout = 5.0
    stt_engine = VoskSTTEngine(server_url=vosk_url, timeout=vosk_timeout)

    # TTS Engine (Piper)
    piper_host = cfg.get("host", "localhost")
    # Determine Piper port as int (cfg may be plain dict)
    try:
        piper_port = int(cfg.get("port", "8000"))
    except (TypeError, ValueError):
        piper_port = 8000 # default port
    # session_id for piper engine can be derived if needed, or passed if available
    # For now, PiperTTSEngine in TTSProcessor was using self.session_id from TTSProcessor
    # Let's assume PiperTTSEngine can get session_id from SpeechSessionManager if needed, or generate its own.
    # The PiperTTSEngine created in speech_session_manager.py's _init_components doesn't pass session_id explicitly.
    # Here, we are creating it before SpeechSessionManager, so it won't have SSM's session_id yet.
    # For now, let PiperTTSEngine use its default or an empty session_id.
    tts_engine = PiperTTSEngine(server_host=piper_host, server_port=piper_port)

    tts_voice_id = cfg.get("TTS_VOICE", "tr_TR-fahrettin-medium") # Default from original SmartSpeech
    tts_input_rate = 22050 # Piper's default output rate is fixed, not from config

    # Note: SpeechSessionManager expects the *global* Config object,
    # from which it then extracts its own "SpeechSessionManager" or "SmartSpeech" section.
    # The `cfg` passed to this helper is already that specific section.
    # So, we pass the global `Config` to SpeechSessionManager.
    from config import Config as GlobalConfig # type: ignore[no-redef]
    # Assuming 'call' is of a type that SpeechSessionManager expects, possibly src.call.Call
    return SpeechSessionManager(
        call=call,
        cfg=GlobalConfig,
        stt_engine=stt_engine,
        tts_engine=tts_engine,
        tts_voice_id=tts_voice_id,
        tts_input_rate=tts_input_rate
    )

class UnknownSIPUser(Exception):
    """ User is not known """


def _dialplan_match(regex: str, string_to_match: str) -> Optional[re.Match[str]]:
    """ Checks if a regex matches the string """
    pattern = re.compile(regex)
    return pattern.match(string_to_match)

from src import sip_utils

# Define a more specific callable type for flavor factories
FlavorFactoryType = Callable[[Any, Config], AIEngine] # (call, cfg) -> AIEngine instance

class FlavorRegistry:
    """ Manages AI flavors """

    _FLAVORS: Dict[str, FlavorFactoryType] = { # Type hint for _FLAVORS
        "SmartSpeech": _create_speech_session_manager
    }

    def __init__(self, config: Config) -> None:
        self.config: Config = config

    def _get_default_flavor(self, user: str) -> str:
        """ Returns the default algorithm for AI choosing """
        keys = [k for k, _ in self._FLAVORS.items() if
                not self.config.get(k).getboolean("disabled",
                                             f"{k.upper()}_DISABLE", # type: ignore[str-format]
                                             False)]
        if not keys:
            raise ValueError("No AI flavors available/enabled.")
        if user in keys:
            return user
        # Ensure keys is not empty before modulo, though previous check should cover it.
        if not keys: # Should be unreachable due to the check above
             raise ValueError("Internal error: No keys available for default flavor selection after filtering.")
        hash_index = hash(user) % len(keys)
        return keys[hash_index]

    def determine_flavor(self, params: Dict[str, Any]) -> str:
        """ Returns the AI flavor to be used """
        user = sip_utils.get_user(params)
        if not user:
            # Consider logging here or ensuring UnknownSIPUser is handled upstream
            raise UnknownSIPUser("Cannot parse username from SIP parameters for flavor determination.")

        for flavor_name in self.config.sections():
            if flavor_name not in self._FLAVORS:
                continue
            if self.config.get(flavor_name).getboolean("disabled",
                                             f"{flavor_name.upper()}_DISABLE", # type: ignore[str-format]
                                             False):
                continue
            dialplans = self.config.get(flavor_name).get("match")
            if not dialplans:
                continue

            current_user: str = user # Ensure type for _dialplan_match
            if isinstance(dialplans, list):
                for dialplan_regex in dialplans:
                    if _dialplan_match(str(dialplan_regex), current_user): # Ensure regex is str
                        return flavor_name
            elif isinstance(dialplans, str): # Ensure regex is str for single match
                if _dialplan_match(dialplans, current_user):
                    return flavor_name
            # else: dialplans is of an unexpected type, could log warning
        return self._get_default_flavor(user)

    def get_flavor_factory(self, flavor_name: str) -> Optional[FlavorFactoryType]:
        """ Returns the factory function for a given flavor name """
        return self._FLAVORS.get(flavor_name)

# Instantiate the FlavorRegistry
flavor_registry: FlavorRegistry = FlavorRegistry(Config)

def get_ai(flavor_name: str, call: Any, cfg: Config) -> AIEngine: # Return type is AIEngine
    """ Returns an AI object """
    factory = flavor_registry.get_flavor_factory(flavor_name)
    if factory:
        # Assuming the factory returns an instance compatible with AIEngine
        return factory(call, cfg)
    raise ValueError(f"Unknown AI flavor or factory not found: {flavor_name}")

# vim: tabstop=8 expandtab shiftwidth=4 softtabstop=4
