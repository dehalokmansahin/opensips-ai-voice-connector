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

""" Main module that starts the AI Voice Connector """

import json
import signal
import asyncio
import logging
import requests # Keep for _fetch_remote_config
from typing import Optional, Tuple, Dict, List, Any, Coroutine

from opensips.mi import OpenSIPSMI, OpenSIPSMIException
from opensips.event import OpenSIPSEventHandler, OpenSIPSEventException
from aiortc.sdp import SessionDescription
from sipmessage import Address # For type hinting

from call import Call
from config import Config
# Assuming Config.get() can return a dict-like object for sections, or a specific ConfigSection type
# If ConfigSection is a specific type, it should be imported from config module.
# For now, we'll use Dict[str, Any] as a general type for config sections.
ConfigSection = Dict[str, Any]
from codec import UnsupportedCodec
from utils import UnknownSIPUser
from src import utils
from src import sip_utils


mi_cfg: ConfigSection = Config.get("opensips")
mi_ip: str = mi_cfg.get("ip", "MI_IP", "127.0.0.1")
mi_port: int = int(mi_cfg.get("port", "MI_PORT", "8080"))

mi_conn: OpenSIPSMI = OpenSIPSMI(conn="datagram", datagram_ip=mi_ip, datagram_port=mi_port)

calls: Dict[str, Call] = {}


def mi_reply(key: str, method: str, code: int, reason: str, body: Optional[str] = None) -> None:
    """ Replies to the server """
    params: Dict[str, Any] = {'key': key,
                              'method': method,
                              'code': code,
                              'reason': reason}
    if body:
        params["body"] = body
    try:
        mi_conn.execute('ua_session_reply', params)
    except OpenSIPSMIException as e:
        logging.error(f"MI command ua_session_reply failed for {key}, method {method}: {e}", exc_info=True)


def _fetch_remote_config(api_url: str, bot_user: str) -> Optional[Dict[str, Any]]:
    """
    Sends a POST request to the API to fetch the bot configuration.
    """
    if not api_url:
        logging.warning("_fetch_remote_config called with empty api_url for bot %s.", bot_user)
        return None
    try:
        response = requests.post(api_url, json={"bot": bot_user})
        response.raise_for_status()
        return response.json()
    except requests.exceptions.HTTPError as http_err:
        logging.error(f"HTTP error fetching remote config for {bot_user} from {api_url}: {http_err}", exc_info=True)
    except requests.RequestException as req_err:
        logging.error(f"Request error fetching remote config for {bot_user} from {api_url}: {req_err}", exc_info=True)
    except json.JSONDecodeError as json_err:
        logging.error(f"JSON decode error for remote config response for {bot_user} from {api_url}: {json_err}", exc_info=True)
    return None


def _parse_extra_params(extra_params_str: Optional[str]) -> Optional[Dict[str, Any]]:
    """ Parses the extra_params JSON string. """
    if extra_params_str:
        try:
            return json.loads(extra_params_str)
        except json.JSONDecodeError as e:
            logging.warning("Failed to parse extra_params JSON '%s': %s", extra_params_str, e, exc_info=True)
    return None


def _determine_flavor(params: Dict[str, Any],
                      extra_params_data: Optional[Dict[str, Any]],
                      remote_config_data: Optional[Dict[str, Any]]) -> str:
    """ Determines the AI flavor based on various sources. """
    flavor: Optional[str] = None
    if remote_config_data:
        flavor = remote_config_data.get('flavor')

    if not flavor and extra_params_data:
        flavor = extra_params_data.get('flavor')

    if not flavor:
        try:
            flavor = utils.flavor_registry.determine_flavor(params)
        except UnknownSIPUser as e: # Catch specific exception if user cannot be determined
            logging.error(f"Cannot determine flavor: {e}", exc_info=True)
            raise # Re-raise to be handled by caller, or define default behavior

    if not flavor:
        logging.critical("AI Flavor could not be determined and no default is set.")
        raise ValueError("AI Flavor could not be determined.")
    return flavor


def _load_final_cfg(flavor: str,
                    extra_params_data: Optional[Dict[str, Any]],
                    remote_config_data: Optional[Dict[str, Any]]) -> ConfigSection:
    """ Loads the final configuration for the chosen flavor. """
    cfg: ConfigSection = {}

    base_cfg_from_file: ConfigSection = Config.get(flavor, {})
    if isinstance(base_cfg_from_file, dict):
         cfg.update(base_cfg_from_file)
    elif base_cfg_from_file is not None:
        logging.warning(f"Config.get({flavor}) returned non-dict type: {type(base_cfg_from_file)}")

    if remote_config_data and flavor in remote_config_data and isinstance(remote_config_data[flavor], dict):
        cfg.update(remote_config_data[flavor])

    if extra_params_data and flavor in extra_params_data and isinstance(extra_params_data[flavor], dict):
        cfg.update(extra_params_data[flavor])

    if not cfg and not base_cfg_from_file :
        logging.warning(f"No configuration found for flavor '{flavor}'. Behavior may be undefined.")
        # Return a ConfigSection, possibly empty, consistent with Config.get()
        return Config.get(flavor)

    return cfg


def parse_params(params: Dict[str, Any]) -> Tuple[str, Optional[Address], ConfigSection]:
    """ Parses parameters received in a call using helper functions. """
    bot_user: Optional[str] = sip_utils.get_user(params)
    to_address: Optional[Address] = sip_utils.get_to(params)

    api_url: Optional[str] = Config.engine("api_url", "API_URL")
    remote_config_data: Optional[Dict[str, Any]] = None
    if bot_user and api_url:
        remote_config_data = _fetch_remote_config(api_url, bot_user)

    extra_params_data: Optional[Dict[str, Any]] = None
    raw_extra_params: Any = params.get("extra_params")
    if raw_extra_params:
        if isinstance(raw_extra_params, str):
            extra_params_data = _parse_extra_params(raw_extra_params)
        else:
            logging.warning(f"extra_params field is not a string: {type(raw_extra_params)}. Value: {raw_extra_params}")

    flavor: str = _determine_flavor(params, extra_params_data, remote_config_data)
    cfg: ConfigSection = _load_final_cfg(flavor, extra_params_data, remote_config_data)

    return flavor, to_address, cfg


def _handle_invite(call_obj: Optional[Call], key: str, method: str, params: Dict[str, Any]) -> None:
    """ Handles INVITE requests. """
    if 'body' not in params:
        mi_reply(key, method, 415, 'Unsupported Media Type')
        return

    sdp_str: str = params['body']
    sdp_str = "\n".join([line for line in sdp_str.split("\n")
                         if not line.startswith("a=rtcp:")])
    try:
        sdp: SessionDescription = SessionDescription.parse(sdp_str)
    except ValueError as e:
        logging.error(f"Error parsing SDP for call {key}: {e}", exc_info=True)
        mi_reply(key, method, 400, 'Bad Request - SDP Parse Error')
        return

    if call_obj:
        direction: Optional[str] = sdp.media[0].direction if sdp.media and len(sdp.media) > 0 else None
        if not direction or direction == "sendrecv":
            call_obj.resume()
        else:
            call_obj.pause()
        try:
            mi_reply(key, method, 200, 'OK', call_obj.get_body())
        except OpenSIPSMIException as e:
            logging.error(f"Error sending MI reply for re-INVITE {key}: {e}", exc_info=True)
        return

    try:
        flavor, to, cfg_section = parse_params(params)
        new_call = Call(key, mi_conn, sdp, flavor, to, cfg_section)
        calls[key] = new_call
        mi_reply(key, method, 200, 'OK', new_call.get_body())
    except UnsupportedCodec as e:
        logging.warning(f"Unsupported codec for call {key}: {e}", exc_info=True)
        mi_reply(key, method, 488, 'Not Acceptable Here')
    except UnknownSIPUser as e:
        logging.warning(f"Unknown SIP user for call {key}: {e}", exc_info=True)
        mi_reply(key, method, 404, 'Not Found')
    except OpenSIPSMIException as e:
        logging.error(f"MI error creating new call {key}: {e}", exc_info=True)
        mi_reply(key, method, 500, 'Server Internal Error - MI Failure')
    except Exception as e:
        logging.error(f"Unexpected error creating new call {key}: {e}", exc_info=True)
        mi_reply(key, method, 500, 'Server Internal Error - Unexpected')


def _handle_notify(call_obj: Optional[Call], key: str, method: str, params: Dict[str, Any]) -> None:
    """ Handles NOTIFY requests. """
    mi_reply(key, method, 200, 'OK')
    if call_obj:
        sub_state: Optional[str] = sip_utils.get_header(params, "Subscription-State")
        if sub_state and "terminated" in sub_state:
            if hasattr(call_obj, 'terminated'): # Check if Call object has this attribute
                 call_obj.terminated = True


def _handle_bye(call_obj: Optional[Call], key: str, method: str, params: Dict[str, Any]) -> None:
    """ Handles BYE requests. """
    if call_obj:
        asyncio.create_task(call_obj.close())
        calls.pop(key, None)
    else:
        logging.warning("BYE received for non-existent call key: %s", key)
        mi_reply(key, method, 481, 'Call/Transaction Does Not Exist')


def _handle_unsupported_method(key: str, method: str, params: Dict[str, Any]) -> None:
    """ Handles unsupported SIP methods. """
    try:
        mi_reply(key, method, 405, 'Method Not Allowed')
    except OpenSIPSMIException as e:
        logging.error(f"Failed to send 405 reply for {method} {key}: {e}", exc_info=True)


def handle_call(call_obj: Optional[Call], key: str, method: str, params: Dict[str, Any]) -> None:
    """
    Handles a SIP call by dispatching to method-specific handlers.
    """
    if method == 'INVITE':
        _handle_invite(call_obj, key, method, params)
    elif method == 'NOTIFY':
        if not call_obj:
            mi_reply(key, method, 481, 'Call/Transaction Does Not Exist')
            return
        _handle_notify(call_obj, key, method, params)
    elif method == 'BYE':
        if not call_obj:
            mi_reply(key, method, 481, 'Call/Transaction Does Not Exist')
            return
        _handle_bye(call_obj, key, method, params)
    else:
        _handle_unsupported_method(key, method, params)


def udp_handler(data: Dict[str, Any]) -> None:
    """ UDP handler of events received """
    params_dict: Optional[Dict[str, Any]] = data.get('params') # Renamed to avoid conflict
    if not params_dict:
        logging.warning("udp_handler: 'params' missing in data.")
        return

    key: Optional[str] = params_dict.get('key')
    if not key:
        logging.warning("udp_handler: 'key' missing in params.")
        return

    method: Optional[str] = params_dict.get('method')
    if not method:
        logging.warning("udp_handler: 'method' missing in params for key %s.", key)
        return

    current_call: Optional[Call] = None # Renamed to avoid conflict
    if sip_utils.indialog(params_dict):
        if key not in calls:
            logging.warning(f"udp_handler: In-dialog message for non-existent call key {key}.")
            mi_reply(key, method, 481, 'Call/Transaction Does Not Exist')
            return
        current_call = calls[key]

    handle_call(current_call, key, method, params_dict)


async def shutdown(s: int, loop: asyncio.AbstractEventLoop, event_handler: OpenSIPSEventHandler) -> None:
    """ Called when the program is shutting down """
    signal_name = signal.Signals(s).name if isinstance(s, int) and s in signal.Signals else str(s)
    logging.info("Received exit signal %s...", signal_name)

    active_call_tasks: List[Coroutine[Any, Any, None]] = []
    call_keys_to_remove: List[str] = []
    for call_key, call_instance in list(calls.items()):
        if hasattr(call_instance, 'terminated') and call_instance.terminated: # Check if Call object has 'terminated'
            continue
        logging.info(f"Closing call {call_key} during shutdown...")
        active_call_tasks.append(call_instance.close())
        call_keys_to_remove.append(call_key)

    if active_call_tasks:
        await asyncio.gather(*active_call_tasks, return_exceptions=True)

    for key_to_remove in call_keys_to_remove: # Clean up calls dict
        calls.pop(key_to_remove, None)

    other_tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
    if other_tasks:
        logging.info("Cancelling %d other outstanding tasks...", len(other_tasks))
        for task in other_tasks:
            task.cancel()
        await asyncio.gather(*other_tasks, return_exceptions=True)

    try:
        if event_handler:
             event_handler.unsubscribe()
    except OpenSIPSEventException as e:
        logging.error("Error unsubscribing from OpenSIPS event: %s", e, exc_info=True)
    except OpenSIPSMIException as e:
        logging.error("MI error during OpenSIPS event unsubscribe: %s", e, exc_info=True)

    if loop.is_running():
        loop.stop()
    logging.info("Shutdown complete.")


async def async_run() -> None:
    """ Main function """
    host_ip: str = Config.engine("event_ip", "EVENT_IP", "127.0.0.1")
    port_str: str = Config.engine("event_port", "EVENT_PORT", "0")
    port: int = int(port_str) if port_str is not None else 0


    if not mi_conn:
        logging.critical("MI connection (mi_conn) is not initialized. Cannot start event handler.")
        return

    event_handler_obj: OpenSIPSEventHandler = OpenSIPSEventHandler(mi_conn, "datagram", ip=host_ip, port=port)
    event_subscription: Any = None # To store the subscription object
    try:
        event_subscription = event_handler_obj.async_subscribe("E_UA_SESSION", udp_handler)
    except OpenSIPSEventException as e:
        logging.critical("Fatal: Error subscribing to OpenSIPS event E_UA_SESSION: %s", e, exc_info=True)
        return
    except OpenSIPSMIException as e:
        logging.critical("Fatal: MI error during OpenSIPS event subscription: %s", e, exc_info=True)
        return

    actual_host: str = host_ip
    actual_port: int = port
    if event_subscription and event_subscription.socket and hasattr(event_subscription.socket, 'sock'):
         actual_host, actual_port = event_subscription.socket.sock.getsockname()

    logging.info("Event handler started at %s:%hu", actual_host, actual_port)

    loop: asyncio.AbstractEventLoop = asyncio.get_running_loop()

    for s_val in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(
            s_val,
            lambda s=s_val: asyncio.create_task(shutdown(s, loop, event_handler_obj)),
        )
    try:
        # Keep the loop running. If there was a specific future for shutdown, await it here.
        # For now, assume the loop runs until loop.stop() is called by signal handlers.
        while loop.is_running(): # Or a more robust way to keep alive if needed
            await asyncio.sleep(3600) # Wake up periodically if needed, or just rely on signals
    except asyncio.CancelledError:
        logging.info("async_run main task cancelled.")
    finally:
        logging.info("async_run finished.")


def run() -> None:
    """ Runs the entire engine asynchronously """
    try:
        asyncio.run(async_run())
    except KeyboardInterrupt:
        logging.info("KeyboardInterrupt received. Assuming shutdown is handled by signal handlers.")
    except Exception as e:
        logging.critical(f"Unhandled exception in run(): {e}", exc_info=True)

# vim: tabstop=8 expandtab shiftwidth=4 softtabstop=4
