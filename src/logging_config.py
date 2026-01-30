"""
Logging Configuration - Structured logging with JSON support
"""
import sys
import json
from datetime import datetime
from typing import Optional
from loguru import logger


def json_serializer(record: dict) -> str:
    """Serialize log record to JSON format"""
    subset = {
        "timestamp": record["time"].strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z",
        "level": record["level"].name,
        "message": record["message"],
        "module": record["name"],
        "function": record["function"],
        "line": record["line"],
    }

    # Add exception info if present
    if record["exception"]:
        subset["exception"] = {
            "type": record["exception"].type.__name__ if record["exception"].type else None,
            "value": str(record["exception"].value) if record["exception"].value else None,
        }

    # Add extra fields if present
    if record["extra"]:
        subset["extra"] = record["extra"]

    return json.dumps(subset, ensure_ascii=False)


def json_sink(message):
    """Sink for JSON formatted logs"""
    record = message.record
    print(json_serializer(record), file=sys.stderr)


def configure_logging(
    level: str = "INFO",
    json_format: bool = False,
    log_file: Optional[str] = None,
) -> None:
    """
    Configure logging with optional JSON format.

    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR)
        json_format: If True, output logs in JSON format
        log_file: Optional file path to write logs
    """
    # Remove default handler
    logger.remove()

    if json_format:
        # JSON format for production/structured logging
        logger.add(
            json_sink,
            level=level,
            format="{message}",
            colorize=False,
        )
    else:
        # Human-readable format for development
        logger.add(
            sys.stderr,
            format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - {message}",
            level=level,
            colorize=True,
        )

    # Add file handler if specified
    if log_file:
        if json_format:
            logger.add(
                log_file,
                format=lambda m: json_serializer(m.record) + "\n",
                level=level,
                rotation="10 MB",
                retention="7 days",
            )
        else:
            logger.add(
                log_file,
                format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
                level=level,
                rotation="10 MB",
                retention="7 days",
            )


def get_logger(name: str = None):
    """Get a logger instance with optional name binding"""
    if name:
        return logger.bind(name=name)
    return logger


# Convenience functions for structured logging
def log_request(url: str, method: str = "GET", **kwargs):
    """Log an HTTP request"""
    logger.info(
        f"Request: {method} {url}",
        method=method,
        url=url,
        **kwargs
    )


def log_response(url: str, status: int, duration: float, **kwargs):
    """Log an HTTP response"""
    logger.info(
        f"Response: {status} {url} ({duration:.2f}s)",
        url=url,
        status=status,
        duration=duration,
        **kwargs
    )


def log_error(error: str, error_type: str = None, **kwargs):
    """Log an error with structured data"""
    logger.error(
        f"Error: {error}",
        error=error,
        error_type=error_type,
        **kwargs
    )


def log_task(task_id: str, action: str, **kwargs):
    """Log a task event"""
    logger.info(
        f"Task {task_id}: {action}",
        task_id=task_id,
        action=action,
        **kwargs
    )
