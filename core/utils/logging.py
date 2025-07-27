"""
Logging utilities for OpenSIPS AI Voice Connector
Centralized logging configuration
"""

import logging
import logging.handlers
import sys
from pathlib import Path
from typing import Optional

def setup_logging(
    level: str = "INFO",
    log_file: Optional[str] = None,
    log_format: Optional[str] = None,
    max_bytes: int = 10 * 1024 * 1024,  # 10MB
    backup_count: int = 5
):
    """
    Setup logging configuration
    
    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_file: Log file path (optional)
        log_format: Log format string (optional)
        max_bytes: Maximum log file size before rotation
        backup_count: Number of backup log files to keep
    """
    
    # Default format
    if not log_format:
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
    
    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(numeric_level)
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
    configure_third_party_loggers()
    
    logging.info(f"Logging setup completed - Level: {level}")

def configure_third_party_loggers():
    """Configure third-party library loggers"""
    
    # Reduce noise from third-party libraries
    logging.getLogger("grpc").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("websockets").setLevel(logging.WARNING)
    logging.getLogger("asyncio").setLevel(logging.WARNING)
    
    # Keep our application loggers at INFO or above
    app_loggers = [
        "opensips",
        "grpc_clients", 
        "bot",
        "pipeline",
        "session"
    ]
    
    for logger_name in app_loggers:
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