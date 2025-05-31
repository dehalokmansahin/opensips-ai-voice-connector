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

""" Module that implements a generic codec """

from abc import ABC, abstractmethod
from aiortc import RTCRtpCodecParameters
from aiortc.sdp import SessionDescription # For type hinting get_codecs
from opus import OggOpus
from typing import List, Optional, Tuple, Union, Any, Dict, AsyncGenerator, Type, TYPE_CHECKING
import asyncio # For asyncio.Queue
import logging # Added logging import
from . import constants

if TYPE_CHECKING: # To avoid circular import with a full AIEngine import if response type is more specific
    from ..ai import AIEngine # For process_response's 'response' type hint, if it's an AIEngine method


class UnsupportedCodec(Exception):
    """ Raised when there is a codec mismatch """


    """ Raised when there is a codec mismatch """


class GenericCodec(ABC):
    """ Generic Abstract class for a codec """

    def __init__(self, params: RTCRtpCodecParameters, ptime: int = constants.DEFAULT_PTIME_MS) -> None:
        self.params: RTCRtpCodecParameters = params
        self.ptime: int = ptime
        self.payload_type: int = params.payloadType
        self.sample_rate: int = params.clockRate
        # Ensure ptime is not zero to avoid ZeroDivisionError
        effective_ptime = ptime if ptime > 0 else constants.DEFAULT_PTIME_MS
        self.ts_increment: int = int(self.sample_rate * (effective_ptime / 1000.0))

    @abstractmethod
    async def process_response(self, response: Any, queue: asyncio.Queue[bytes]) -> None:
        """ Processes the response from speech engine """
        pass

    @abstractmethod
    def get_silence(self) -> bytes:
        """ Returns a silence packet """
        pass

    @abstractmethod
    def parse(self, data: Optional[bytes], leftovers: Optional[bytes]) -> Union[List[bytes], Tuple[List[bytes], bytes], bytes, None]:
        """ Parses codec packets """
        pass


class Opus(GenericCodec):
    """ Opus codec handling """

    def __init__(self, params: RTCRtpCodecParameters) -> None:
        super().__init__(params)
        if 'sprop-maxcapturerate' in params.parameters:
            try:
                self.sample_rate = int(params.parameters['sprop-maxcapturerate'])
                # Recalculate ts_increment if sample_rate changed
                effective_ptime = self.ptime if self.ptime > 0 else constants.DEFAULT_PTIME_MS
                self.ts_increment = int(self.sample_rate * (effective_ptime / 1000.0))
                logging.info(f"Opus: Updated sample rate to {self.sample_rate} from sprop-maxcapturerate.")
            except ValueError:
                logging.warning(f"Opus: Could not parse sprop-maxcapturerate value: {params.parameters['sprop-maxcapturerate']}")
        self.name: str = 'opus' # Should this be constants.OPUS_CODEC_NAME ?
        self.bitrate: int = constants.OPUS_DEFAULT_BITRATE_BPS
        self.container: str = constants.OPUS_CONTAINER_FORMAT

    async def process_response(self, response: Any, queue: asyncio.Queue[bytes]) -> None:
        try:
            # Assuming response is an HTTP response object with a content attribute that is an AsyncGenerator[bytes, None]
            async for data_chunk in response.content.iter_any(): # Adjust based on actual response object
                if not data_chunk: continue # Skip empty chunks
                parsed_packets = self.parse(data_chunk, None)
                if parsed_packets:
                    for packet in parsed_packets:
                        queue.put_nowait(packet)
        except Exception as e:
            logging.error(f"Opus process_response error: {e}", exc_info=True)


    def parse(self, data: Optional[bytes], leftovers: Optional[bytes] = None) -> List[bytes]:
        if data is None:
            return []
        try:
            # OggOpus constructor and packets() method might raise errors on malformed data.
            return OggOpus(data).packets()
        except Exception as e:
            logging.error(f"Error parsing Opus data with OggOpus: {e}", exc_info=True)
            return []


    def get_silence(self) -> bytes:
        return constants.OPUS_SILENCE_FRAME


class G711Base(GenericCodec):
    """ Base class for G.711 family codecs (PCMU, PCMA). """
    def __init__(self, params: RTCRtpCodecParameters) -> None:
        super().__init__(params)
        if self.sample_rate != constants.G711_STANDARD_SAMPLE_RATE:
            logging.warning(f"G711 codec ({getattr(self, 'name', 'G711Base')}) initialized with non-standard sample rate {self.sample_rate} from SDP. Standard is {constants.G711_STANDARD_SAMPLE_RATE}.")
        self.bitrate: Optional[int] = None
        self.container: str = 'none'
        # self.name is set by concrete subclasses

    async def process_response(self, response: Any, queue: asyncio.Queue[bytes]) -> None:
        leftovers: bytes = b''
        try:
            async for data_chunk in response.content.iter_any(): # Adjust based on actual response object
                if data_chunk:
                    parsed_output = self.parse(data_chunk, leftovers)
                    if isinstance(parsed_output, tuple) and len(parsed_output) == 2:
                        packets, new_leftovers = parsed_output
                        for packet in packets:
                            queue.put_nowait(packet)
                        leftovers = new_leftovers
                    elif isinstance(parsed_output, bytes):
                        queue.put_nowait(parsed_output)
                        leftovers = b''

            if leftovers:
                final_packet_output = self.parse(None, leftovers)
                if isinstance(final_packet_output, bytes):
                     queue.put_nowait(final_packet_output)
                elif isinstance(final_packet_output, tuple) and final_packet_output[0]:
                    for p in final_packet_output[0]: queue.put_nowait(p)
        except Exception as e:
            logging.error(f"G711Base process_response error: {e}", exc_info=True)

    def parse(self, data: Optional[bytes], leftovers: Optional[bytes]) -> Union[Tuple[List[bytes], bytes], bytes, None]:
        chunk_size: int = self.get_payload_len()
        if chunk_size <= 0: # Avoid division by zero or negative chunk sizes if ptime/sample_rate is misconfigured
            logging.error(f"G711 parse: Invalid chunk size ({chunk_size}). ptime: {self.ptime}, sample_rate: {self.sample_rate}")
            return ([], b'') if data is not None else None # Return empty if cannot process

        current_leftovers: bytes = leftovers if leftovers is not None else b''

        if not data: # Only leftovers to process
            if not current_leftovers: return None
            if len(current_leftovers) < chunk_size :
                try:
                    silence_byte = self.get_silence_byte()
                    padding = silence_byte * (chunk_size - len(current_leftovers))
                    padded_leftovers: bytes = current_leftovers + padding
                    return padded_leftovers
                except Exception as e: # Catch error from get_silence_byte
                    logging.error(f"Error generating padding for G711 parse: {e}", exc_info=True)
                    return current_leftovers # Return unpadded if error
            else:
                return current_leftovers # Already a full chunk or more (should ideally be handled by loop)

        current_data: bytes = current_leftovers + data
        chunks: List[bytes] = []

        i = 0
        while (i + chunk_size) <= len(current_data):
            chunks.append(current_data[i:i + chunk_size])
            i += chunk_size

        new_leftovers: bytes = current_data[i:]
        return chunks, new_leftovers

    def get_silence(self) -> bytes:
        return self.get_silence_byte() * self.get_payload_len()

    @abstractmethod
    def get_silence_byte(self) -> bytes:
        pass

    def get_payload_len(self) -> int:
        if self.ptime <= 0: return 0 # Avoid issues with invalid ptime
        return int(self.sample_rate * self.ptime / 1000)


class G711(G711Base):
    """ Generic G711 Codec (defaults to PCMU silence if used directly). """
    def __init__(self, params: RTCRtpCodecParameters) -> None:
        super().__init__(params)
        self.name: str = constants.G711_GENERIC_NAME

    def get_silence_byte(self) -> bytes:
        return constants.PCMU_SILENCE_BYTE


class PCMU(G711Base):
    """ PCMU (G.711 mu-law) codec handling. """
    def __init__(self, params: RTCRtpCodecParameters) -> None:
        super().__init__(params)
        self.name: str = constants.PCMU_CODEC_NAME
        if self.sample_rate != constants.G711_STANDARD_SAMPLE_RATE:
            logging.warning(f"PCMU codec '{self.name}' initialized with non-standard sample rate {self.sample_rate} from SDP. Standard is {constants.G711_STANDARD_SAMPLE_RATE}.")

    def get_silence_byte(self) -> bytes:
        return constants.PCMU_SILENCE_BYTE


class PCMA(G711Base):
    """ PCMA (G.711 A-law) codec handling. """
    def __init__(self, params: RTCRtpCodecParameters) -> None:
        super().__init__(params)
        self.name: str = constants.PCMA_CODEC_NAME
        if self.sample_rate != constants.G711_STANDARD_SAMPLE_RATE:
            logging.warning(f"PCMA codec '{self.name}' initialized with non-standard sample rate {self.sample_rate} from SDP. Standard is {constants.G711_STANDARD_SAMPLE_RATE}.")

    def get_silence_byte(self) -> bytes:
        return constants.PCMA_SILENCE_BYTE


STATIC_PAYLOAD_TYPE_MAP: Dict[int, Dict[str, Any]] = {
    0: {"mimeType": "audio/PCMU", "clockRate": constants.G711_STANDARD_SAMPLE_RATE, "name": constants.PCMU_CODEC_NAME},
    8: {"mimeType": "audio/PCMA", "clockRate": constants.G711_STANDARD_SAMPLE_RATE, "name": constants.PCMA_CODEC_NAME},
}

def get_codecs(sdp: SessionDescription) -> List[RTCRtpCodecParameters]:
    """
    Returns the codecs list from SDP, adding known static payload types
    if they are listed in sdp.media[0].fmt but not fully described in rtp.codecs.
    """
    if not sdp or not sdp.media or len(sdp.media) == 0 or not hasattr(sdp.media[0].rtp, 'codecs') or not hasattr(sdp.media[0], 'fmt'):
        logging.warning("get_codecs: SDP object or required attributes are missing/invalid. Returning empty list.")
        return []

    existing_codecs: List[RTCRtpCodecParameters] = list(sdp.media[0].rtp.codecs)
    payload_types_in_existing_codecs: set[int] = {codec.payloadType for codec in existing_codecs}

    for pt_str in sdp.media[0].fmt:
        try:
            pt: int = int(pt_str)
        except ValueError:
            logging.warning(f"Could not parse payload type string '{pt_str}' to int in get_codecs.")
            continue

        if pt in STATIC_PAYLOAD_TYPE_MAP:
            if pt not in payload_types_in_existing_codecs:
                map_entry = STATIC_PAYLOAD_TYPE_MAP[pt]
                codec = RTCRtpCodecParameters(
                    mimeType=map_entry["mimeType"],
                    clockRate=map_entry["clockRate"],
                    payloadType=pt
                )
                existing_codecs.append(codec)
                payload_types_in_existing_codecs.add(pt)
                logging.debug(f"Added known static codec: {map_entry['name']} (PT: {pt}) from fmt list.")

    return existing_codecs


CODECS: Dict[str, Type[GenericCodec]] = { # Type hint for CODECS dictionary
    "opus": Opus,
    "pcma": PCMA,
    "pcmu": PCMU,
}

# vim: tabstop=8 expandtab shiftwidth=4 softtabstop=4
