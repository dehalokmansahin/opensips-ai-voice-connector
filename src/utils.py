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
from deepgram_api import Deepgram
from openai_api import OpenAI
from deepgram_native_api import DeepgramNative
from speech_session_vosk import VoskSTT
# Try to import Azure, but don't fail if not available
try:
    from azure_api import AzureAI
    has_azure = True
except ImportError:
    has_azure = False
    print("Azure module not available, Azure STT provider will be disabled")
from config import Config

# Initialize FLAVORS dictionary
FLAVORS = {"deepgram": Deepgram,
           "openai": OpenAI,
           "deepgram_native": DeepgramNative,
           "vosk":VoskSTT}

# Add Azure if available
if has_azure:
    FLAVORS["azure"] = AzureAI

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
def get_ai(flavor, call, cfg):
    """ Returns an AI object """
    return FLAVORS[flavor](call, cfg)

# vim: tabstop=8 expandtab shiftwidth=4 softtabstop=4
