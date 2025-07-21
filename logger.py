import logging
import sys
from typing import Optional
from config import LogConfig

class StructuredLogger:
    """Centralized logging utility with structured format."""
    
    _loggers = {}
    _config = LogConfig()
    
    @classmethod
    def setup_logging(cls, config: Optional[LogConfig] = None) -> None:
        """Setup global logging configuration."""
        if config:
            cls._config = config
        
        # Configure root logger
        root_logger = logging.getLogger()
        root_logger.setLevel(getattr(logging, cls._config.level.upper()))
        
        # Clear existing handlers
        root_logger.handlers.clear()
        
        formatter = logging.Formatter(cls._config.format)
        
        # Console handler
        if cls._config.enable_console:
            console_handler = logging.StreamHandler(sys.stdout)
            console_handler.setFormatter(formatter)
            root_logger.addHandler(console_handler)
        
        # File handler
        if cls._config.enable_file:
            file_handler = logging.FileHandler(cls._config.file_path)
            file_handler.setFormatter(formatter)
            root_logger.addHandler(file_handler)
    
    @classmethod
    def get_logger(cls, name: str) -> logging.Logger:
        """Get or create a logger for the given name."""
        if name not in cls._loggers:
            cls._loggers[name] = logging.getLogger(name)
        return cls._loggers[name]