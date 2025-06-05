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

""" Handles the a SIP call """

import random
import socket
import asyncio
import logging
import secrets
import datetime
from queue import Empty
from typing import Optional, Tuple, Dict, List, Any, Callable, Coroutine, Awaitable
import socket # Added for socket.socket and socket.error
import asyncio # Added for asyncio.AbstractEventLoop, asyncio.Queue, etc.
from aiortc.sdp import SessionDescription
from config import Config
from opensips.mi import OpenSIPSMI

from rtp import decode_rtp_packet, generate_rtp_packet
from utils import get_ai
from src.ai import AIEngine
from src.codec import GenericCodec
import constants

rtp_cfg = Config.get("rtp")
min_rtp_port: int = int(rtp_cfg.get("min_port", "RTP_MIN_PORT", "35000"))
max_rtp_port: int = int(rtp_cfg.get("max_port", "RTP_MAX_PORT", "65000"))

available_ports: set[int] = set(range(min_rtp_port, max_rtp_port))


class NoAvailablePorts(Exception):
    """ There are no available ports """


class RTPReceiver:
    """ Handles receiving RTP packets and forwarding audio to AI. """
    def __init__(self,
                 serversock: socket.socket,
                 client_addr: str,
                 client_port: int,
                 paused_callback: Callable[[], bool],
                 ai_send_callback: Callable[[bytes], Awaitable[None]],
                 loop: asyncio.AbstractEventLoop,
                 call_ref: 'Call'): # Forward reference Call
        self.serversock: socket.socket = serversock
        self.client_addr: str = client_addr
        self.client_port: int = client_port
        self.paused_callback: Callable[[], bool] = paused_callback
        self.ai_send_callback: Callable[[bytes], Awaitable[None]] = ai_send_callback
        self.first_packet: bool = True
        self.loop: asyncio.AbstractEventLoop = loop
        self.call_ref: 'Call' = call_ref
        self.rtp_receive_buffer_size: int = Config.get("rtp").getint("rtp_receive_buffer_size", "RTP_RECEIVE_BUFFER_SIZE", 4096)

    def start_listening(self) -> None:
        try:
            if self.serversock.fileno() != -1: # Check if socket is valid
                self.loop.add_reader(self.serversock.fileno(), self._read_rtp_internal)
            else:
                log_prefix = getattr(self.call_ref, 'session_id', getattr(self.call_ref, 'b2b_key', 'UnknownCall'))
                logging.error(f"[{log_prefix}] RTPReceiver: Cannot start listening, socket is closed.")
        except Exception as e:
            log_prefix = getattr(self.call_ref, 'session_id', getattr(self.call_ref, 'b2b_key', 'UnknownCall'))
            logging.error(f"[{log_prefix}] RTPReceiver: Error adding reader: {e}", exc_info=True)


    def stop_listening(self) -> None:
        log_prefix = getattr(self.call_ref, 'session_id', getattr(self.call_ref, 'b2b_key', 'UnknownCall'))
        try:
            if self.serversock.fileno() != -1:
                 self.loop.remove_reader(self.serversock.fileno())
        except ValueError:
            logging.debug(f"[{log_prefix}] RTPReceiver: Reader already removed or socket closed.")
        except Exception as e:
            logging.error(f"[{log_prefix}] RTPReceiver: Error removing reader: {e}", exc_info=True)


    def _read_rtp_internal(self) -> None:
        """ Reads an RTP packet. (Internal method called by loop.add_reader) """
        log_prefix = getattr(self.call_ref, 'session_id', getattr(self.call_ref, 'b2b_key', 'UnknownCall'))
        try:
            # Ensure rtp_receive_buffer_size is available, otherwise default
            buffer_size = getattr(self, 'rtp_receive_buffer_size', 4096)
            data, adr = self.serversock.recvfrom(buffer_size)
            client_ip_from_packet, client_port_from_packet = adr

            if self.first_packet:
                logging.info(f"[{log_prefix}] First RTP packet received from {client_ip_from_packet}:{client_port_from_packet}, updating client address.")
                self.first_packet = False
                self.client_addr = client_ip_from_packet
                self.client_port = client_port_from_packet
                if self.call_ref:
                    # Update Call object's direct knowledge if it holds client_addr/port
                    self.call_ref.client_addr = client_ip_from_packet
                    self.call_ref.client_port = client_port_from_packet
                    self.call_ref._start_rtp_sender_if_needed()

            if client_ip_from_packet != self.client_addr or client_port_from_packet != self.client_port:
                logging.warning(f"[{log_prefix}] Received RTP from unexpected source {client_ip_from_packet}:{client_port_from_packet}")
                return
        except BlockingIOError:
            return
        except socket.timeout:
            logging.warning(f"[{log_prefix}] Socket timeout in RTPReceiver (should not occur with add_reader)", exc_info=True)
            return
        except socket.error as sock_err:
            logging.error(f"[{log_prefix}] Socket error receiving RTP: {sock_err}", exc_info=True)
            return
        except Exception as e:
            logging.error(f"[{log_prefix}] Generic error receiving RTP: {e}", exc_info=True)
            return

        if self.paused_callback():
            return

        try:
            packet: Dict[str, Any] = decode_rtp_packet(data.hex())
            audio: bytes = bytes.fromhex(packet['payload'])
            asyncio.create_task(self.ai_send_callback(audio))
        except ValueError as ve:
            logging.warning(f"[{log_prefix}] Failed to decode RTP packet or payload: {ve}", exc_info=True)
        except Exception as e:
            logging.error(f"[{log_prefix}] Error processing received RTP packet: {e}", exc_info=True)


class RTPSender:
    """ Handles generating and sending RTP packets. """
    def __init__(self,
                 serversock: socket.socket,
                 client_addr: str, # Initial client address, see get_client_addr for dynamic value
                 client_port: int, # Initial client port, see get_client_port for dynamic value
                 codec: GenericCodec,
                 rtp_queue: asyncio.Queue[bytes],
                 stop_event: asyncio.Event,
                 call_ref: 'Call'):
        self.serversock: socket.socket = serversock
        self.initial_client_addr: str = client_addr
        self.initial_client_port: int = client_port
        self.codec: GenericCodec = codec
        self.rtp_queue: asyncio.Queue[bytes] = rtp_queue
        self.stop_event: asyncio.Event = stop_event
        self.send_task: Optional[asyncio.Task[None]] = None
        self.rtp_sender_stop_timeout: float = Config.get("rtp").getfloat("rtp_sender_stop_timeout", "RTP_SENDER_STOP_TIMEOUT", 1.0)
        self.call_ref: 'Call' = call_ref

        self.get_client_addr: Callable[[], str] = lambda: self.call_ref.rtp_receiver.client_addr
        self.get_client_port: Callable[[], int] = lambda: self.call_ref.rtp_receiver.client_port

    def start(self) -> None:
        log_prefix = getattr(self.call_ref, 'session_id', getattr(self.call_ref, 'b2b_key', 'UnknownCall'))
        if not self.send_task or self.send_task.done():
            # client_addr & client_port for the loop are obtained dynamically via lambdas.
            logging.info(f"[{log_prefix}] RTPSender task starting for client {self.get_client_addr()}:{self.get_client_port()}.")
            self.send_task = asyncio.create_task(self._send_rtp_loop(), name=f"RTPSendLoop-{log_prefix}")
        else:
            logging.warning(f"[{log_prefix}] RTPSender task already running.")

    async def stop(self) -> None:
        log_prefix = getattr(self.call_ref, 'session_id', getattr(self.call_ref, 'b2b_key', 'UnknownCall'))
        if self.send_task and not self.send_task.done():
            logging.debug(f"[{log_prefix}] RTPSender stop called. Waiting for send_task.")
            try:
                await asyncio.wait_for(self.send_task, timeout=self.rtp_sender_stop_timeout)
            except asyncio.TimeoutError:
                logging.warning(f"[{log_prefix}] RTPSender task timed out during stop. Cancelling.")
                if self.send_task and not self.send_task.done(): self.send_task.cancel()
            except asyncio.CancelledError:
                logging.info(f"[{log_prefix}] RTPSender task was cancelled during stop.")
            except Exception as e:
                logging.error(f"[{log_prefix}] Error waiting for RTPSender task: {e}", exc_info=True)
        self.send_task = None

    async def _send_rtp_loop(self) -> None:
        log_prefix = getattr(self.call_ref, 'session_id', getattr(self.call_ref, 'b2b_key', 'UnknownCall'))
        sequence_number: int = random.randint(0, 0xFFFF)
        timestamp: int = random.randint(0, 0xFFFFFFFF)
        ssrc: int = random.randint(0, 0xFFFFFFFF)

        ts_inc: int = self.codec.ts_increment
        ptime_ms: int = self.codec.ptime
        payload_type: int = self.codec.payload_type
        marker: int = 1
        packet_no: int = 0
        start_time: datetime.datetime = datetime.datetime.now()

        # Log initial destination; actual destination per send is dynamic via lambdas
        logging.info(f"[{log_prefix}] RTPSender loop starting, initial target {self.get_client_addr()}:{self.get_client_port()}")

        try:
            while not self.stop_event.is_set():
                payload_to_send: Optional[bytes] = None
                try:
                    actual_timeout_s = float(ptime_ms) / 1000.0 if ptime_ms > 0 else 0.020 # Default 20ms if ptime is 0
                    payload_to_send = await asyncio.wait_for(self.rtp_queue.get(), timeout=actual_timeout_s)
                    self.rtp_queue.task_done()
                except asyncio.TimeoutError:
                    if self.stop_event.is_set(): break
                    if self.call_ref and hasattr(self.call_ref, 'call_session') and \
                       not self.call_ref.call_session.paused and \
                       hasattr(self.codec, 'get_silence'):
                        payload_to_send = self.codec.get_silence()
                    else:
                        await asyncio.sleep(actual_timeout_s / 2)
                        continue
                except asyncio.CancelledError:
                    logging.info(f"[{log_prefix}] RTPSender queue.get() cancelled.")
                    raise

                if payload_to_send:
                    current_client_addr: str = self.get_client_addr()
                    current_client_port: int = self.get_client_port()

                    rtp_packet_dict: Dict[str, Any] = {
                        'version': constants.RTP_VERSION, 'padding': 0, 'extension': 0,
                        'csi_count': 0, 'marker': marker, 'payload_type': payload_type,
                        'sequence_number': sequence_number, 'timestamp': timestamp,
                        'ssrc': ssrc, 'payload': payload_to_send.hex()
                    }
                    packet_hex: str = generate_rtp_packet(rtp_packet_dict)
                    rtp_packet_bytes: bytes = bytes.fromhex(packet_hex)
                    marker = 0

                    try:
                        if self.serversock.fileno() != -1:
                            self.serversock.sendto(rtp_packet_bytes, (current_client_addr, current_client_port))
                        else:
                            logging.warning(f"[{log_prefix}] RTPSender: Socket closed, cannot send RTP.")
                            break
                    except socket.error as sock_err:
                        logging.error(f"[{log_prefix}] Socket error sending RTP to {current_client_addr}:{current_client_port}: {sock_err}", exc_info=True)
                        await asyncio.sleep(0.1) # Short pause before retrying or next packet
                        continue
                    except Exception as e:
                        logging.error(f"[{log_prefix}] Unexpected error sending RTP to {current_client_addr}:{current_client_port}: {e}", exc_info=True)
                        break

                    sequence_number = (sequence_number + 1) & 0xFFFF

                timestamp = (timestamp + ts_inc) & 0xFFFFFFFF
                packet_no += 1

                next_time: datetime.datetime = start_time + datetime.timedelta(milliseconds=ptime_ms * packet_no)
                now: datetime.datetime = datetime.datetime.now()
                wait_time: float = (next_time - now).total_seconds()

                if wait_time > 0:
                    try:
                        await asyncio.wait_for(self.stop_event.wait(), timeout=wait_time)
                        if self.stop_event.is_set(): break
                    except asyncio.TimeoutError:
                        pass
                    except asyncio.CancelledError:
                        logging.info(f"[{log_prefix}] RTPSender wait cancelled.")
                        raise

        except asyncio.CancelledError:
            logging.info(f"[{log_prefix}] RTPSender loop cancelled.")
        except Exception as e:
            logging.error(f"[{log_prefix}] Unhandled exception in RTPSender loop: {e}", exc_info=True)
        finally:
            logging.info(f"[{log_prefix}] RTPSender loop finished.")


class CallSession:
    """ Manages AI engine, call state (paused, terminated), and high-level call actions. """
    def __init__(self,
                 ai_engine: AIEngine,
                 rtp_queue: asyncio.Queue[bytes],
                 mi_conn: OpenSIPSMI,
                 b2b_key: str,
                 stop_event: asyncio.Event,
                 call_ref: 'Call'): # Added call_ref for logging prefix
        self.ai_engine: AIEngine = ai_engine
        self.rtp_queue: asyncio.Queue[bytes] = rtp_queue
        self.paused: bool = False
        self.terminated: bool = False # Should be managed by stop_event and Call.close()
        self.mi_conn: OpenSIPSMI = mi_conn
        self.b2b_key: str = b2b_key
        self.stop_event: asyncio.Event = stop_event
        self.call_ref: 'Call' = call_ref
        self.log_prefix: str = getattr(self.call_ref, 'session_id', getattr(self.call_ref, 'b2b_key', 'UnknownCall'))


    async def start_ai(self) -> None:
        if self.ai_engine:
            try:
                # If AI engine needs rtp_queue, it should be passed during its own __init__ or via a setter.
                # Example: if hasattr(self.ai_engine, 'set_rtp_send_queue'):
                # self.ai_engine.set_rtp_send_queue(self.rtp_queue)
                await self.ai_engine.start()
                logging.info(f"[{self.log_prefix}] AI engine started.")
            except Exception as e:
                logging.error(f"[{self.log_prefix}] Error starting AI engine: {e}", exc_info=True)
                # Optionally, re-raise or set a failed state
        else:
            logging.warning(f"[{self.log_prefix}] No AI engine provided to CallSession.")


    def pause_session(self) -> None:
        if self.paused: return
        logging.info(f"[{self.log_prefix}] Pausing session.")
        self.paused = True # This flag gates RTPReceiver and affects RTPSender
        if hasattr(self.ai_engine, 'pause') and callable(self.ai_engine.pause):
            # Ensure this is awaited if it's an async operation
            asyncio.create_task(self._call_ai_pause()) # Create task to avoid blocking here
        # RTPSender checks self.call_ref.call_session.paused to send silence

    async def _call_ai_pause(self):
        try:
            await self.ai_engine.pause()
        except Exception as e:
            logging.error(f"[{self.log_prefix}] Error during ai_engine.pause(): {e}", exc_info=True)

    def resume_session(self) -> None: # Keep this sync for now, matching Call.resume()
        if not self.paused: return
        logging.info(f"[{self.log_prefix}] Resuming session.")
        self.paused = False # This flag gates RTPReceiver and affects RTPSender
        if hasattr(self.ai_engine, 'resume') and callable(self.ai_engine.resume):
            # Ensure this is awaited if it's an async operation
            asyncio.create_task(self._call_ai_resume()) # Create task to avoid blocking here

    async def _call_ai_resume(self):
        try:
            await self.ai_engine.resume()
        except Exception as e:
            logging.error(f"[{self.log_prefix}] Error during ai_engine.resume(): {e}", exc_info=True)

    async def close_ai(self) -> None:
        if self.ai_engine:
            try:
                await self.ai_engine.close()
                logging.info(f"[{self.log_prefix}] AI engine closed.")
            except Exception as e:
                logging.error(f"[{self.log_prefix}] Error closing AI engine: {e}", exc_info=True)

    def terminate_call_sip(self) -> None:
        """ Initiates SIP call termination via MI. """
        # self.terminated is problematic if not managed carefully with stop_event
        # Rely on stop_event as the primary signal for termination.
        if not self.stop_event.is_set(): # Check stop_event instead of self.terminated
            logging.info(f"[{self.log_prefix}] Terminating SIP call via MI.")
            # self.terminated = True # This flag's utility is reduced if stop_event is the main driver
            self.stop_event.set() # Signal all components to stop
            try:
                # Consider making MI call non-blocking if it can be, or run in executor
                # For now, assuming it's relatively quick.
                self.mi_conn.execute("ua_session_terminate", {"key": self.b2b_key})
            except OpenSIPSMI.OpenSIPSMIException as e: # Catch specific MI error
                logging.error(f"[{self.log_prefix}] MI error sending ua_session_terminate: {e}", exc_info=True)
            except Exception as e: # Catch any other unexpected error
                logging.error(f"[{self.log_prefix}] Unexpected error sending ua_session_terminate: {e}", exc_info=True)
        else:
            logging.info(f"[{self.log_prefix}] SIP call termination already in progress or completed (stop_event set).")


class Call():
    """ Class that handles a call """
    def __init__(self,
                 b2b_key: str,
                 mi_conn: OpenSIPSMI,
                 sdp: SessionDescription, # This is aiortc.sdp.SessionDescription
                 flavor: str,
                 to: Optional[str], # 'to' from parse_params can be sipmessage.Address, but original Call took 'to' as str.
                                 # Let's assume it's meant to be the string representation or relevant part.
                                 # If it's an Address object, the type should be Optional[Address].
                                 # Given it's not heavily used in Call class itself, Optional[str] is safer for now.
                 cfg: Dict[str, Any] # This is a ConfigSection like object
                 ) -> None:
        self.b2b_key: str = b2b_key
        self.mi_conn: OpenSIPSMI = mi_conn
        self.sdp: SessionDescription = sdp # Store original SDP for reference, new one generated below
        self.loop: asyncio.AbstractEventLoop = asyncio.get_running_loop()

        # For logging prefix, try to get session_id from CallSession if it's already set up by AI factory
        # This is a bit of a chicken-and-egg if CallSession uses Call's b2b_key for its session_id.
        # Fallback to b2b_key for logging if session_id not yet available.
        self.session_id: str = f"[Call:{self.b2b_key}]" # Basic log prefix

        host_ip_cfg: str = rtp_cfg.get('bind_ip', 'RTP_BIND_IP', '0.0.0.0')
        rtp_advertise_ip_cfg: str = rtp_cfg.get('ip', 'RTP_IP') # Can be None if not set

        try:
            # Determine rtp_ip: use config 'ip' if set, else local hostname, else 127.0.0.1
            if rtp_advertise_ip_cfg:
                rtp_ip: str = rtp_advertise_ip_cfg
            else:
                try:
                    rtp_ip = socket.gethostbyname(socket.gethostname())
                except socket.gaierror:
                    logging.warning(f"[{self.session_id}] Could not determine local hostname for RTP IP, using 127.0.0.1.")
                    rtp_ip = "127.0.0.1"
        except Exception as e: # Catch any error during IP determination
            logging.error(f"[{self.session_id}] Error determining RTP IP: {e}", exc_info=True)
            rtp_ip = "127.0.0.1" # Fallback


        # These will be dynamically updated by RTPReceiver's first packet logic
        self.client_addr: str = self.sdp.media[0].host if self.sdp.media and len(self.sdp.media)>0 and self.sdp.media[0].host else (self.sdp.host or '0.0.0.0')
        self.client_port: int = self.sdp.media[0].port if self.sdp.media and len(self.sdp.media)>0 else 0

        self.serversock: socket.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._bind_socket(host_ip_cfg)
        self.serversock.setblocking(False)

        self.rtp_queue: asyncio.Queue[bytes] = asyncio.Queue()
        self.stop_event: asyncio.Event = asyncio.Event()
        self.stop_event.clear()

        # This 'self' is passed to get_ai. AIEngine's __init__ (e.g. SpeechSessionManager)
        # might set up self.session_id on this Call instance if it's designed that way.
        # For now, SpeechSessionManager creates its own session_id.
        self.ai_engine_instance: AIEngine = get_ai(flavor, self, cfg)
        self.codec: GenericCodec = self.ai_engine_instance.get_codec()

        self.call_session: CallSession = CallSession(
            ai_engine=self.ai_engine_instance,
            rtp_queue=self.rtp_queue,
            mi_conn=self.mi_conn,
            b2b_key=self.b2b_key,
            stop_event=self.stop_event,
            call_ref=self
        )
        # Update session_id if CallSession sets a more specific one (e.g. from AI engine)
        if hasattr(self.ai_engine_instance, 'session_id') and self.ai_engine_instance.session_id:
             self.session_id = f"[{self.ai_engine_instance.session_id}]" # Use AI engine's session ID if available
        else: # Fallback if AI engine doesn't set it, use b2b_key based one.
             self.session_id = f"[{self.call_session.session_id if hasattr(self.call_session, 'session_id') and self.call_session.session_id else self.b2b_key}]"


        self.rtp_receiver: RTPReceiver = RTPReceiver(
            serversock=self.serversock, client_addr=self.client_addr, client_port=self.client_port,
            paused_callback=lambda: self.call_session.paused,
            ai_send_callback=lambda audio_chunk: self.ai_engine_instance.send(audio_chunk),
            loop=self.loop, call_ref=self
        )

        self.rtp_sender: RTPSender = RTPSender(
            serversock=self.serversock, client_addr=self.client_addr, client_port=self.client_port,
            codec=self.codec, rtp_queue=self.rtp_queue, stop_event=self.stop_event, call_ref=self
        )

        # SDP generation using the determined RTP IP
        self.sdp = self.get_new_sdp(self.sdp, rtp_ip)

        asyncio.create_task(self.call_session.start_ai(), name=f"StartAI-{self.session_id}")
        self.rtp_receiver.start_listening()

        self.rtp_sender_started: bool = False

        logging.info(f"[{self.session_id}] Call initialized for {self.client_addr}:{self.client_port} using {flavor} AI. Waiting for first RTP to start sender.")

    def _start_rtp_sender_if_needed(self) -> None:
        if not self.rtp_sender_started:
            # RTPSender's __init__ now uses call_ref to get client_addr/port dynamically.
            # Explicitly setting them here is redundant if lambdas in RTPSender are used.
            # However, if RTPSender's _send_rtp_loop caches client_addr/port at start, this is needed.
            # The current RTPSender._send_rtp_loop gets them fresh in each iteration.
            # For safety / explicitness, let's ensure the RTPSender instance has its initial values updated too.
            self.rtp_sender.initial_client_addr = self.rtp_receiver.client_addr
            self.rtp_sender.initial_client_port = self.rtp_receiver.client_port
            self.rtp_sender.start()
            self.rtp_sender_started = True
            logging.info(f"[{self.session_id}] RTPSender started after first packet.")

    def _bind_socket(self, host_ip: str) -> None:
        """ Binds the call to an available port. """
        if not available_ports:
            logging.error(f"[{self.session_id}] No available RTP ports to bind.")
            raise NoAvailablePorts("No available RTP ports for call.")

        chosen_port: Optional[int] = None
        try:
            # Attempt to bind to a port from the available set
            # This loop is more robust than secrets.choice if ports are quickly reused/released
            # or if there's a small race condition.
            for port_candidate in list(available_ports): # Iterate over a copy
                try:
                    self.serversock.bind((host_ip, port_candidate))
                    chosen_port = port_candidate
                    available_ports.remove(chosen_port)
                    logging.info(f"[{self.session_id}] Bound to RTP port {host_ip}:{chosen_port}")
                    break
                except socket.error as e:
                    logging.debug(f"[{self.session_id}] Port {port_candidate} already in use or unavailable: {e}")
            if chosen_port is None:
                raise NoAvailablePorts(f"Could not bind to any port in range for call {self.session_id}")
        except NoAvailablePorts: # Re-raise specific error
            raise
        except Exception as e: # Catch other unexpected errors during bind
            logging.error(f"[{self.session_id}] Unexpected error during socket bind: {e}", exc_info=True)
            raise # Re-raise to prevent call setup with bad socket


    def get_body(self) -> str:
        """ Retrieves the SDP built """
        return str(self.sdp)

    def get_new_sdp(self, original_sdp: SessionDescription, host_ip: str) -> SessionDescription:
        """ Gets a new SDP to be sent back in 200 OK """
        # Create a new SessionDescription or deepcopy to avoid modifying the original if it's reused
        # For simplicity, this example modifies in place as per original logic.
        # Consider: new_sdp = original_sdp.copy() or deepcopy(original_sdp)

        # Update origin user and IP
        if original_sdp.origin:
            origin_parts = original_sdp.origin.split(' ')
            if len(origin_parts) >= 3: # user session-id version IN IP4/IP6 address
                 original_sdp.origin = f"{origin_parts[0]} {origin_parts[1]} {origin_parts[2]} IN IP4 {host_ip}" # Assuming IP4
            else: # Fallback if origin format is unexpected
                 original_sdp.origin = f"- {random.randint(1000, 9999)} {random.randint(1000,9999)} IN IP4 {host_ip}"


        # Update media port and IP
        if original_sdp.media and len(original_sdp.media) > 0:
            original_sdp.media[0].port = self.serversock.getsockname()[1]
            original_sdp.media[0].host = host_ip # Set media IP to our advertised IP

        # Update connection line IP if present at session level
        if original_sdp.host:
            original_sdp.host = host_ip

        # Filter codecs: keep only the one chosen for the session
        if self.codec and hasattr(self.codec, 'params') and original_sdp.media and len(original_sdp.media) > 0:
            original_sdp.media[0].rtp.codecs = [self.codec.params] # params is RTCRtpCodecParameters
            original_sdp.media[0].fmt = [str(self.codec.payload_type)] # fmt should be list of strings
        else:
            logging.warning(f"[{self.session_id}] Could not set chosen codec in SDP; codec or media info missing.")

        return original_sdp

    def resume(self) -> None:
        """ Resumes the call's audio """
        if not self.call_session.paused: # Check state via CallSession
            return
        logging.info(f"[{self.session_id}] Resuming call audio.")
        if self.sdp.media and len(self.sdp.media) > 0:
            self.sdp.media[0].direction = "sendrecv"
        self.call_session.resume_session()

    def pause(self) -> None:
        """ Pauses the call's audio """
        if self.call_session.paused: # Check state via CallSession
            return
        logging.info(f"[{self.session_id}] Pausing call audio.")
        if self.sdp.media and len(self.sdp.media) > 0:
            self.sdp.media[0].direction = "recvonly"
        self.call_session.pause_session()

    async def close(self) -> None:
        """ Closes the call and all its components. """
        log_prefix = self.session_id if hasattr(self, 'session_id') else self.b2b_key
        logging.info(f"[{log_prefix}] Call closing...")
        if self.stop_event.is_set():
            logging.warning(f"[{log_prefix}] Call close() called but stop_event already set.")
            return

        self.stop_event.set()

        if hasattr(self, 'rtp_receiver') and self.rtp_receiver: # Check if initialized
            self.rtp_receiver.stop_listening()

        if hasattr(self, 'rtp_sender') and self.rtp_sender:
            await self.rtp_sender.stop()

        if hasattr(self, 'call_session') and self.call_session:
            await self.call_session.close_ai()

        if self.serversock:
            socket_port_to_free: Optional[int] = None
            try:
                if self.serversock.fileno() != -1: # Check if socket is still open
                    socket_port_to_free = self.serversock.getsockname()[1]
                    self.serversock.close()
                if socket_port_to_free is not None: # Add back only if successfully got port
                    available_ports.add(socket_port_to_free)
                    logging.info(f"[{log_prefix}] Socket closed and port {socket_port_to_free} freed.")
                else:
                    logging.warning(f"[{log_prefix}] Socket port could not be determined or socket already closed before freeing.")
            except socket.error as e: # Catch specific socket errors
                 logging.error(f"[{log_prefix}] Socket error during close: {e}", exc_info=True)
            except Exception as e: # Catch any other error during socket close
                logging.error(f"[{log_prefix}] Error closing socket: {e}", exc_info=True)

        logging.info(f"[{log_prefix}] Call closed successfully.")


    def terminate(self) -> None:
        """ Terminates the call via SIP and triggers closing of resources. """
        log_prefix = self.session_id if hasattr(self, 'session_id') else self.b2b_key
        logging.info(f"[{log_prefix}] Call.terminate() called.")
        if hasattr(self, 'call_session') and self.call_session:
            self.call_session.terminate_call_sip()
        else: # Fallback if call_session not initialized
            logging.warning(f"[{log_prefix}] CallSession not available for terminate_call_sip. Setting stop_event directly.")
            self.stop_event.set()

        # Ensure close is scheduled, as terminate_call_sip only sets stop_event
        # and relies on main loop or other tasks to await stop_event for cleanup.
        # Creating a task here ensures cleanup if no other mechanism is active.
        if not self.stop_event.is_set(): self.stop_event.set() # Ensure it's set
        asyncio.create_task(self.close(), name=f"CallCloseTask-{log_prefix}")


# vim: tabstop=8 expandtab shiftwidth=4 softtabstop=4
