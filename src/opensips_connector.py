import logging
from opensips_mi_client import OpenSIPSMI, OpenSIPSMIException
from opensips_event_client import OpenSIPSEventHandler, OpenSIPSEventException
from src.config import Config

logger = logging.getLogger(__name__)

class OpenSIPSConnector:
    def __init__(self, mi_ip=None, mi_port=None):
        config = Config()
        mi_ip = mi_ip or config.get('opensips_mi_ip', '127.0.0.1')
        mi_port = mi_port or config.get('opensips_mi_port', 8080)
        
        self.mi_conn = OpenSIPSMI(mi_ip, mi_port)
        self.event_handler_callback = None
        self.subscribed_event = None

    def set_event_handler_callback(self, callback):
        self.event_handler_callback = callback

    def mi_reply(self, key, method, code, reason, body=None):
        params_for_execute = {
            'key': key,
            'method': method,
            'code': code,
            'reason': reason
        }
        if body:
            params_for_execute["body"] = body
        try:
            self.mi_conn.execute('ua_session_reply', params_for_execute)
            logger.debug(f"Replied to {method} for {key} with {code} {reason} using execute.")
        except OpenSIPSMIException as e:
            logger.error(f"Error replying to {method} for {key} using execute: {e}")

    async def start_listening(self, event_ip=None, event_port=None):
        config = Config()
        event_ip = event_ip or config.get('opensips_event_ip', '0.0.0.0')
        event_port = event_port or config.get('opensips_event_port', 5065)

        handler = OpenSIPSEventHandler(ip_addr=event_ip, port=event_port)
        self.subscribed_event = handler.async_subscribe("E_UA_SESSION", self._handle_opensips_event)
        
        actual_port = self.subscribed_event.socket.sock.getsockname()[1]
        logger.info(f"OpenSIPS Event Listener started on {event_ip}:{actual_port}")
        return actual_port

    def _handle_opensips_event(self, data):
        if self.event_handler_callback:
            self.event_handler_callback(data)
        else:
            logger.warning("OpenSIPS event received, but no handler is registered.")

    async def unsubscribe_events(self):
        if self.subscribed_event:
            try:
                self.subscribed_event.unsubscribe()
                logger.info("Unsubscribed from OpenSIPS events.")
            except (OpenSIPSEventException, OpenSIPSMIException) as e:
                logger.error(f"Error unsubscribing from OpenSIPS events: {e}")
            finally:
                self.subscribed_event = None
_content = """
import logging
from opensips_mi_client import OpenSIPSMI, OpenSIPSMIException
from opensips_event_client import OpenSIPSEventHandler, OpenSIPSEventException
from src.config import Config

logger = logging.getLogger(__name__)

class OpenSIPSConnector:
    def __init__(self, mi_ip=None, mi_port=None):
        config = Config()
        mi_ip = mi_ip or config.get('opensips_mi_ip', '127.0.0.1')
        mi_port = mi_port or config.get('opensips_mi_port', 8080)
        
        self.mi_conn = OpenSIPSMI(mi_ip, mi_port)
        self.event_handler_callback = None
        self.subscribed_event = None

    def set_event_handler_callback(self, callback):
        self.event_handler_callback = callback
"""
