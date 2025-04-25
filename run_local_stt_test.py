#!/usr/bin/env python3

import asyncio
import logging
import os
import sys # <-- Import sys
import configparser # <-- Import configparser

# --- Add src directory to Python path --- 
# This allows imports like 'from ai ...' and 'from config ...' to work when running from the root
project_root = os.path.dirname(os.path.abspath(__file__))
source_dir = os.path.join(project_root, 'src')
if source_dir not in sys.path:
    sys.path.insert(0, source_dir)
# ----------------------------------------

from stt_vosk import VoskSTT # Now we can import directly from src
# from config import Config    # No longer importing Config directly if not needed for loading

# --- Dummy Call Object ---
# Create a simple object that mimics the necessary attributes of the 'call' object
# passed to VoskSTT during normal operation.
class DummyCall:
    def __init__(self):
        self.b2b_key = "local_test_001" # Just a unique identifier
        self.sdp = None # SDP is not used in WAV test mode

# --- Main Test Function ---
async def main():
    # Configure logging
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    logger = logging.getLogger(__name__)

    config_file = 'local_test_config.ini'
    if not os.path.exists(config_file):
        logger.error(f"Configuration file '{config_file}' not found.")
        return

    logger.info(f"Loading configuration from {config_file}")
    config_parser = configparser.ConfigParser()
    try:
        # Load the local configuration using configparser
        read_files = config_parser.read(config_file)
        if not read_files:
            raise ValueError(f"Config file '{config_file}' was empty or not found by configparser.")
        if 'vosk' not in config_parser:
             raise ValueError("Section [vosk] not found in config file.")

    except Exception as e:
         logger.error(f"Failed to load or parse configuration: {e}")
         return

    # Check if test.wav exists using the config_parser object
    try:
        test_wav_path = config_parser.get('vosk', 'test_wav_path', fallback='test.wav')
    except configparser.NoSectionError:
        logger.error("Section [vosk] missing in config for test_wav_path check.")
        return
        
    if not os.path.exists(test_wav_path):
        logger.error(f"Test WAV file '{test_wav_path}' not found.")
        return

    # Create dummy call object
    dummy_call = DummyCall()

    # Instantiate VoskSTT
    logger.info("Instantiating VoskSTT engine...")
    try:
        # Pass the configparser object directly
        vosk_engine = VoskSTT(dummy_call, config_parser)
    except Exception as e:
        logger.error(f"Failed to instantiate VoskSTT: {e}")
        return

    # Start the engine
    logger.info("Starting VoskSTT engine...")
    await vosk_engine.start()

    logger.info("VoskSTT started. Waiting for WAV processing to complete...")

    # --- Wait for completion ---
    # Wait for the connection_task (which manages the send/receive loops) 
    # to finish. This task completes when the connection closes or the loops exit.
    if vosk_engine.connection_task:
        try:
            await vosk_engine.connection_task 
            logger.info("Vosk connection task completed.")
            # Optional: Small delay if final messages might still be processing asynchronously
            # await asyncio.sleep(1)
        except asyncio.CancelledError:
             logger.info("Connection task was cancelled during wait.")
        except Exception as e:
             logger.error(f"Error waiting for connection task: {e}")

    # Close the engine
    logger.info("Closing VoskSTT engine...")
    await vosk_engine.close()
    logger.info("Test finished.")

# --- Run the Test ---
if __name__ == "__main__":
    asyncio.run(main())