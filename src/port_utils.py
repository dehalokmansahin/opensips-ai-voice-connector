import socket
import structlog

logger = structlog.get_logger()

def find_available_port(bind_ip: str, min_port: int, max_port: int) -> int:
    """Find an available UDP port in the given range."""
    for port in range(min_port, max_port + 1):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as test_sock:
                test_sock.bind((bind_ip, port))
            logger.info("Found available RTP port", port=port)
            return port
        except OSError:
            continue
    logger.warning("No available ports in range, using auto-assign")
    return 0
