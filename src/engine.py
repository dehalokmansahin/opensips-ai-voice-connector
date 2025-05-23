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

""" Main module that starts the Deepgram AI integration """

import signal
import asyncio
import logging

# Removed json, requests, OpenSIPSMI, OpenSIPSEventHandler, OpenSIPSMIException, OpenSIPSEventException, SessionDescription
from src.config import Config
from src.opensips_connector import OpenSIPSConnector
from src.call_manager import CallManager

# Global mi_conn and calls are removed.
# Imports for Call, UnsupportedCodec, UnknownSIPUser, utils, json, requests,
# OpenSIPSMIException, OpenSIPSEventException, SessionDescription are removed as they are no longer directly used in this file.
# Functions mi_reply, fetch_bot_config, parse_params, handle_call, udp_handler are removed.


async def shutdown(s, loop, stop_future, opensips_connector: OpenSIPSConnector, call_manager: CallManager):
    """ Called when the program is shutting down """
    logging.info("Received exit signal %s...", s)
    tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
    for task in tasks:
        task.cancel()
    logging.info("Cancelling %d outstanding tasks", len(tasks))
    
    # Iterate over active calls using CallManager
    active_calls = call_manager.get_active_calls()
    logging.info(f"Closing {len(active_calls)} active calls.")
    for call in active_calls:
        if hasattr(call, 'terminated') and call.terminated: # Check if call has 'terminated' attr
            continue
        if hasattr(call, 'close') and asyncio.iscoroutinefunction(call.close):
            await call.close()
        elif hasattr(call, 'close'):
            call.close() # If not async
        else:
            logging.warning(f"Call object of type {type(call)} does not have a close method or is already processed.")

    # Unsubscribe from events using OpenSIPSConnector
    if opensips_connector:
        await opensips_connector.unsubscribe_events()
    
    await asyncio.gather(*tasks, return_exceptions=True)
    if not stop_future.done():
        stop_future.set_result(True) # Signal the main loop to stop
    loop.stop()
    logging.info("Shutdown complete.")


async def async_run():
    """ Main function """
    # Config.engine calls might still be used for engine-specific settings, not OpenSIPS related.
    # For example, log levels or other application parameters.
    # The OpenSIPSConnector and CallManager will fetch their own configs via Config().
    
    logging.info("Starting OpenSIPS AI Voice Connector...")

    opensips_connector = OpenSIPSConnector()
    call_manager = CallManager(opensips_connector)

    opensips_connector.set_event_handler_callback(call_manager.handle_sip_event)
    
    # The OpenSIPSConnector's start_listening method should use Config internally
    # to get event_ip and event_port.
    try:
        actual_event_port = await opensips_connector.start_listening()
        # The IP is determined by OpenSIPSConnector, can be logged there or fetched if needed.
        # For now, we log the port as returned.
        # If OpenSIPSConnector.start_listening doesn't return the IP, we can assume it logged it.
        logging.info(f"Successfully started listening for OpenSIPS events on port {actual_event_port}.")
    except Exception as e:
        logging.error(f"Failed to start OpenSIPS event listener: {e}", exc_info=True)
        return # Cannot proceed if listener fails

    loop = asyncio.get_running_loop()
    stop_future = loop.create_future() # Renamed from 'stop' to 'stop_future'

    shutdown_handler = lambda s: asyncio.create_task(
        shutdown(s, loop, stop_future, opensips_connector, call_manager)
    )

    loop.add_signal_handler(signal.SIGTERM, shutdown_handler, signal.SIGTERM)
    loop.add_signal_handler(signal.SIGINT, shutdown_handler, signal.SIGINT)

    logging.info("OpenSIPS AI Voice Connector running. Press Ctrl+C to exit.")

    try:
        await stop_future # Wait until shutdown is complete
    except asyncio.CancelledError:
        logging.info("Main task cancelled.")
    finally:
        if not loop.is_closed(): # Ensure loop is stopped if not already
            loop.stop()
        logging.info("Application event loop stopped.")


def run():
    """ Runs the entire engine asynchronously """
    # Basic logging setup, if not already handled by Config or a dedicated logging module
    # This is a good place for it if engine.py is the main entry point.
    # For now, assume logging is configured elsewhere or by default.
    asyncio.run(async_run())

# vim: tabstop=8 expandtab shiftwidth=4 softtabstop=4
