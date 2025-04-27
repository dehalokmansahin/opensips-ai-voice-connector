import logging
from speech_session_vosk import VoskSTT

# Example of how to set logging level for your Vosk implementation
def set_vosk_to_info_level(vosk_instance):
    # Set to INFO level (turn off DEBUG logs)
    vosk_instance.set_log_level(logging.INFO)
    print("Set Vosk logging to INFO level (debug logs disabled)")

def set_vosk_to_debug_level(vosk_instance):
    # Set to DEBUG level (enable all logs including debug)
    vosk_instance.set_log_level(logging.DEBUG)
    print("Set Vosk logging to DEBUG level (debug logs enabled)")

# Usage examples:
# 1. When you want only INFO logs:
# set_vosk_to_info_level(your_vosk_instance)
#
# 2. When you want DEBUG logs too:
# set_vosk_to_debug_level(your_vosk_instance)

# Example in your main code:
'''
# Get your Vosk instance 
vosk_stt = your_session.vosk_stt  # or however you access it

# Initially see only errors and info (no debug)
set_vosk_to_info_level(vosk_stt)

# Later if you need detailed logs for troubleshooting:
set_vosk_to_debug_level(vosk_stt)
''' 