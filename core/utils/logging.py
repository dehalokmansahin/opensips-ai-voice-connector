"""
Logging utilities for OpenSIPS AI Voice Connector
Centralized logging configuration with enhanced development support
"""

import logging
import logging.handlers
import os
import sys
import traceback
from pathlib import Path
from typing import Optional

def setup_logging(
    level: str = "INFO",
    log_file: Optional[str] = None,
    log_format: Optional[str] = None,
    max_bytes: int = 10 * 1024 * 1024,  # 10MB
    backup_count: int = 5,
    development_mode: bool = None
):
    """
    Setup logging configuration
    
    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_file: Log file path (optional)
        log_format: Log format string (optional)
        max_bytes: Maximum log file size before rotation
        backup_count: Number of backup log files to keep
        development_mode: Enable development-friendly logging features
    """
    
    # Detect development mode
    if development_mode is None:
        development_mode = os.getenv('DEVELOPMENT_MODE', '0') == '1'
    
    # Default format - enhanced for development
    if not log_format:
        if development_mode:
            # More detailed format for development
            log_format = "%(asctime)s | %(levelname)-8s | %(name)-20s | %(funcName)-15s:%(lineno)-4d | %(message)s"
        else:
            log_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    
    # Convert string level to logging level
    numeric_level = getattr(logging, level.upper(), logging.INFO)
    
    # Create root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(numeric_level)
    
    # Clear existing handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    
    # Create formatter
    formatter = logging.Formatter(log_format)
    
    # Console handler with development enhancements
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(numeric_level)
    
    if development_mode:
        # Colored console output for development
        try:
            import colorlog
            color_formatter = colorlog.ColoredFormatter(
                '%(log_color)s%(asctime)s | %(levelname)-8s | %(name)-20s | %(funcName)-15s:%(lineno)-4d | %(message)s',
                log_colors={
                    'DEBUG': 'cyan',
                    'INFO': 'green',
                    'WARNING': 'yellow',
                    'ERROR': 'red',
                    'CRITICAL': 'bold_red',
                }
            )
            console_handler.setFormatter(color_formatter)
        except ImportError:
            # Fallback to regular formatter if colorlog not available
            console_handler.setFormatter(formatter)
    else:
        console_handler.setFormatter(formatter)
    
    root_logger.addHandler(console_handler)
    
    # File handler (optional)
    if log_file:
        try:
            # Create log directory if it doesn't exist
            log_path = Path(log_file)
            log_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Rotating file handler
            file_handler = logging.handlers.RotatingFileHandler(
                log_file,
                maxBytes=max_bytes,
                backupCount=backup_count,
                encoding='utf-8'
            )
            file_handler.setLevel(numeric_level)
            file_handler.setFormatter(formatter)
            root_logger.addHandler(file_handler)
            
            logging.info(f"Logging to file: {log_file}")
            
        except Exception as e:
            logging.error(f"Failed to setup file logging: {e}")
    
    # Configure specific loggers
    configure_third_party_loggers(development_mode)
    
    # Set up exception handler in development mode
    if development_mode:
        setup_development_exception_handler()
    
    mode_str = "DEVELOPMENT" if development_mode else "PRODUCTION"
    logging.info(f"Logging setup completed - Level: {level}, Mode: {mode_str}")

def configure_third_party_loggers(development_mode: bool = False):
    """Configure third-party library loggers"""
    
    if development_mode:
        # In development, show more details from third-parties for debugging
        logging.getLogger("grpc").setLevel(logging.INFO)
        logging.getLogger("urllib3").setLevel(logging.INFO)
        logging.getLogger("websockets").setLevel(logging.INFO)
        logging.getLogger("asyncio").setLevel(logging.INFO)
        logging.getLogger("watchdog").setLevel(logging.WARNING)  # File watcher is noisy
    else:
        # Reduce noise from third-party libraries in production
        logging.getLogger("grpc").setLevel(logging.WARNING)
        logging.getLogger("urllib3").setLevel(logging.WARNING)
        logging.getLogger("websockets").setLevel(logging.WARNING)
        logging.getLogger("asyncio").setLevel(logging.WARNING)
    
    # Keep our application loggers at appropriate levels
    app_loggers = [
        "opensips",
        "grpc_clients", 
        "bot",
        "pipeline",
        "session"
    ]
    
    for logger_name in app_loggers:
        if development_mode:
            logging.getLogger(logger_name).setLevel(logging.DEBUG)
        else:
            logging.getLogger(logger_name).setLevel(logging.INFO)

def get_logger(name: str) -> logging.Logger:
    """Get logger with standardized name"""
    return logging.getLogger(name)

class LoggerAdapter:
    """Logger adapter with context information"""
    
    def __init__(self, logger: logging.Logger, context: dict):
        self.logger = logger
        self.context = context
    
    def _format_message(self, msg: str) -> str:
        """Format message with context"""
        context_str = " ".join([f"{k}={v}" for k, v in self.context.items()])
        return f"[{context_str}] {msg}"
    
    def debug(self, msg: str, **kwargs):
        self.logger.debug(self._format_message(msg), **kwargs)
    
    def info(self, msg: str, **kwargs):
        self.logger.info(self._format_message(msg), **kwargs)
    
    def warning(self, msg: str, **kwargs):
        self.logger.warning(self._format_message(msg), **kwargs)
    
    def error(self, msg: str, **kwargs):
        self.logger.error(self._format_message(msg), **kwargs)
    
    def critical(self, msg: str, **kwargs):
        self.logger.critical(self._format_message(msg), **kwargs)

def get_contextual_logger(name: str, **context) -> LoggerAdapter:
    """Get logger with context information"""
    logger = get_logger(name)
    return LoggerAdapter(logger, context)

class PerformanceLogger:
    """Performance logging utilities"""
    
    def __init__(self, logger: logging.Logger):
        self.logger = logger
    
    def log_timing(self, operation: str, duration_ms: float, **context):
        """Log operation timing"""
        context_str = " ".join([f"{k}={v}" for k, v in context.items()])
        self.logger.info(f"PERF: {operation} took {duration_ms:.2f}ms [{context_str}]")
    
    def log_counter(self, metric: str, value: int, **context):
        """Log counter metric"""
        context_str = " ".join([f"{k}={v}" for k, v in context.items()])
        self.logger.info(f"METRIC: {metric}={value} [{context_str}]")
    
    def log_gauge(self, metric: str, value: float, **context):
        """Log gauge metric"""
        context_str = " ".join([f"{k}={v}" for k, v in context.items()])
        self.logger.info(f"GAUGE: {metric}={value:.2f} [{context_str}]")

def get_performance_logger(name: str) -> PerformanceLogger:
    """Get performance logger"""
    logger = get_logger(f"{name}.perf")
    return PerformanceLogger(logger)

def setup_development_exception_handler():
    """Setup enhanced exception handling for development"""
    
    def development_exception_handler(exc_type, exc_value, exc_traceback):
        """Enhanced exception handler for development"""
        if issubclass(exc_type, KeyboardInterrupt):
            # Allow KeyboardInterrupt to proceed normally
            sys.__excepthook__(exc_type, exc_value, exc_traceback)
            return
        
        logger = logging.getLogger("exception_handler")
        
        # Enhanced exception logging with stack trace
        logger.critical("=" * 80)
        logger.critical("UNHANDLED EXCEPTION DETECTED")
        logger.critical("=" * 80)
        logger.critical(f"Exception Type: {exc_type.__name__}")
        logger.critical(f"Exception Message: {str(exc_value)}")
        logger.critical("-" * 80)
        logger.critical("Full Stack Trace:")
        
        # Log full traceback with line numbers and context
        tb_lines = traceback.format_exception(exc_type, exc_value, exc_traceback)
        for line in tb_lines:
            for sub_line in line.rstrip().split('\n'):
                if sub_line.strip():
                    logger.critical(sub_line)
        
        logger.critical("=" * 80)
        
        # Try to extract and log local variables in development
        try:
            frame = exc_traceback.tb_frame
            logger.critical("Local Variables at Exception:")
            for key, value in frame.f_locals.items():
                try:
                    logger.critical(f"  {key} = {repr(value)[:200]}")
                except:
                    logger.critical(f"  {key} = <unable to represent>")
        except Exception as e:
            logger.critical(f"Could not extract local variables: {e}")
        
        logger.critical("=" * 80)
    
    # Install the enhanced exception handler
    sys.excepthook = development_exception_handler

class DevelopmentLogger:
    """Enhanced logger for development with additional debugging features"""
    
    def __init__(self, name: str):
        self.logger = get_logger(name)
        self.development_mode = os.getenv('DEVELOPMENT_MODE', '0') == '1'
    
    def debug_state(self, obj, message: str = ""):
        """Log object state for debugging"""
        if not self.development_mode:
            return
            
        try:
            state_info = {
                'type': type(obj).__name__,
                'id': id(obj),
                'attributes': {}
            }
            
            # Get public attributes
            for attr in dir(obj):
                if not attr.startswith('_'):
                    try:
                        value = getattr(obj, attr)
                        if not callable(value):
                            state_info['attributes'][attr] = repr(value)[:100]
                    except:
                        state_info['attributes'][attr] = '<error accessing>'
            
            prefix = f"STATE: {message}" if message else "STATE:"
            self.logger.debug(f"{prefix} {state_info}")
            
        except Exception as e:
            self.logger.debug(f"Failed to log state: {e}")
    
    def debug_function_call(self, func_name: str, args=None, kwargs=None):
        """Log function call details"""
        if not self.development_mode:
            return
            
        args_str = f"args={args}" if args else ""
        kwargs_str = f"kwargs={kwargs}" if kwargs else ""
        call_info = " ".join(filter(None, [args_str, kwargs_str]))
        
        self.logger.debug(f"CALL: {func_name}({call_info})")
    
    def debug_performance(self, operation: str, start_time: float, end_time: float):
        """Log performance timing in development"""
        if not self.development_mode:
            return
            
        duration_ms = (end_time - start_time) * 1000
        self.logger.debug(f"PERF: {operation} took {duration_ms:.2f}ms")
    
    def debug_data_flow(self, stage: str, data_type: str, data_size: int = None):
        """Log data flow through pipeline stages"""
        if not self.development_mode:
            return
            
        size_info = f" ({data_size} bytes)" if data_size else ""
        self.logger.debug(f"FLOW: {stage} -> {data_type}{size_info}")

def get_development_logger(name: str) -> DevelopmentLogger:
    """Get enhanced development logger"""
    return DevelopmentLogger(name)