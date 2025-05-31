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
Module that provides helper functions for SIP processing
"""
from typing import Optional, Dict, Any
import re
from sipmessage import Address


def get_header(params: Dict[str, Any], header: str) -> Optional[str]:
    """ Returns a specific line from headers """
    if 'headers' not in params or not isinstance(params['headers'], str):
        return None
    hdr_lines = [line for line in params['headers'].splitlines()
                 if re.match(f"{header}:", line, re.I)]
    if len(hdr_lines) == 0:
        return None
    return hdr_lines[0].split(":", 1)[1].strip()


def get_to(params: Dict[str, Any]) -> Optional[Address]:
    """ Returns the To line parameters """
    to_line = get_header(params, "To")
    if not to_line:
        return None
    try:
        return Address.parse(to_line)
    except Exception: # sipmessage.Address.parse can throw various errors
        return None


def indialog(params: Dict[str, Any]) -> bool:
    """ indicates whether the message is an in-dialog one """
    if 'headers' not in params or not isinstance(params['headers'], str):
        return False
    to_addr = get_to(params) # Renamed to avoid conflict with params argument
    if not to_addr:
        return False
    # Access parameters from the Address object, not the input `params` dict directly for this logic
    address_params = to_addr.parameters
    if "tag" in address_params and len(address_params["tag"]) > 0:
        return True
    return False


def get_user(params: Dict[str, Any]) -> Optional[str]:
    """ Returns the User from the SIP headers """
    to_addr = get_to(params) # Renamed to avoid conflict
    return to_addr.uri.user.lower() if to_addr and to_addr.uri else None

# vim: tabstop=8 expandtab shiftwidth=4 softtabstop=4
