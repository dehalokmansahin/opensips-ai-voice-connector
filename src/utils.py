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

import re
from sipmessage import Address
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
    vosk_timeout = cfg.getfloat("websocket_timeout", "5.0") # Pass as string to avoid os.getenv TypeError
    stt_engine = VoskSTTEngine(server_url=vosk_url, timeout=vosk_timeout)

    # TTS Engine (Piper)
    piper_host = cfg.get("host", "localhost")
    piper_port = cfg.getint("port", "8000") # Pass as string to avoid os.getenv TypeError
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
    from config import Config as GlobalConfig
    return SpeechSessionManager(
        call=call,
        cfg=GlobalConfig, # Pass the global Config object
        stt_engine=stt_engine,
        tts_engine=tts_engine,
        tts_voice_id=tts_voice_id,
        tts_input_rate=tts_input_rate
    )

FLAVORS = {
    "SmartSpeech": _create_speech_session_manager
}

# Add Azure if available
# if has_azure:
#     FLAVORS["azure"] = AzureAI

class UnknownSIPUser(Exception):
    """ User is not known """


def get_header(params, header):
    """ Returns a specific line from headers """
    if 'headers' not in params:
        return None
    hdr_lines = [line for line in params['headers'].splitlines()
                 if re.match(f"{header}:", line, re.I)]
    if len(hdr_lines) == 0:
        return None
    return hdr_lines[0].split(":", 1)[1].strip()


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
            not Config.get(k).getboolean("disabled",
                                         f"{k.upper()}_DISABLE",
                                         False)]
    if user in keys:
        return user
    hash_index = hash(user) % len(keys)
    return keys[hash_index]


def get_ai_flavor(params):
    """ Returns the AI flavor to be used """

    user = get_user(params)
    if not user:
        raise UnknownSIPUser("cannot parse username")

    # first, get the sections in order and check if they have a dialplan
    flavor = None
    for flavor in Config.sections():
        if flavor not in FLAVORS:
            continue
        if Config.get(flavor).getboolean("disabled",
                                         f"{flavor.upper()}_DISABLE",
                                         False):
            continue
        dialplans = Config.get(flavor).get("match")
        if not dialplans:
            continue
        if isinstance(dialplans, list):
            for dialplan in dialplans:
                if _dialplan_match(dialplan, user):
                    return flavor
        elif _dialplan_match(dialplans, user):
            return flavor
    return get_ai_flavor_default(user)


def get_ai(flavor, call, cfg):
    """ Returns an AI object """
    return FLAVORS[flavor](call, cfg)

# vim: tabstop=8 expandtab shiftwidth=4 softtabstop=4
