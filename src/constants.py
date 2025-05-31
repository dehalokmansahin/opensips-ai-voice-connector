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

"""
Module for fixed constants used across the application.
Values here are not intended for user configuration.
"""

# RTP Related Constants
RTP_VERSION = 2

# Codec Related Constants
DEFAULT_PTIME_MS = 20  # Default packet time in milliseconds if not otherwise specified
OPUS_DEFAULT_BITRATE_BPS = 96000  # Default Opus bitrate in bits per second
OPUS_SILENCE_FRAME = b'\xf8\xff\xfe'  # Standard Opus silent frame
PCMU_SILENCE_BYTE = b'\xFF'  # Silence pattern for PCMU (G.711 mu-law)
PCMA_SILENCE_BYTE = b'\xD5'  # Silence pattern for PCMA (G.711 A-law)
G711_STANDARD_SAMPLE_RATE = 8000 # Standard sample rate for G.711 codecs
# G711_CUSTOM_DEFAULT_SAMPLE_RATE = 16000 # Specific to G711 class's old default, might be removed.
OPUS_CONTAINER_FORMAT = "ogg" # Default container for Opus internal processing
PCMU_CODEC_NAME = "mulaw"
PCMA_CODEC_NAME = "alaw"
G711_GENERIC_NAME = "g711" # For the G711 class itself

# Speech Session Manager Related Constants
VAD_MONITOR_INTERVAL_S = 0.5  # Interval for VAD timeout monitoring loop
MIN_PARTIAL_LENGTH_FOR_FORCED_FINAL = 2 # Min length of partial transcript to promote to final on timeout
