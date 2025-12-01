"""
Structured logging configuration for the bank reconciliation tool.
"""
import logging
import sys
from datetime import datetime
from pathlib import Path
import json
from typing import Any, Dict


class JSONFormatter(logging.Formatter):
    """Format log records as JSON for structured logging."""

    def format(self, record: logging.LogRecord) -> str:
        log_data = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        # Add exception info if present
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        # Add extra fields
        if hasattr(record, "extra_data"):
            log_data.update(record.extra_data)

        return json.dumps(log_data)


class ContextLogger(logging.LoggerAdapter):
    """Logger adapter that adds context to all log messages."""

    def process(self, msg: str, kwargs: Dict[str, Any]) -> tuple:
        extra = kwargs.get("extra", {})
        extra.update(self.extra)
        kwargs["extra"] = extra
        return msg, kwargs


def setup_logging(
    level: str = "INFO",
    log_file: str = None,
    json_format: bool = False
) -> logging.Logger:
    """
    Set up logging configuration.

    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_file: Optional file path for log output
        json_format: Use JSON formatting for structured logs

    Returns:
        Configured logger instance
    """
    # Create logger
    logger = logging.getLogger("bank_recon")
    logger.setLevel(getattr(logging, level.upper()))

    # Clear existing handlers
    logger.handlers.clear()

    # Create formatter
    if json_format:
        formatter = JSONFormatter()
    else:
        formatter = logging.Formatter(
            "%(asctime)s | %(levelname)-8s | %(name)s | %(funcName)s:%(lineno)d | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # File handler (optional)
    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_path)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    return logger


def get_logger(name: str = None) -> logging.Logger:
    """Get a logger instance."""
    if name:
        return logging.getLogger(f"bank_recon.{name}")
    return logging.getLogger("bank_recon")


# Convenience functions for structured logging
def log_reconciliation_start(logger: logging.Logger, run_id: str, bank_count: int, ap_count: int):
    """Log reconciliation start with context."""
    logger.info(
        f"Starting reconciliation run {run_id[:8]}... | bank_txns={bank_count} | ap_txns={ap_count}",
        extra={"extra_data": {
            "event": "reconciliation_start",
            "run_id": run_id,
            "bank_transaction_count": bank_count,
            "ap_transaction_count": ap_count
        }}
    )


def log_reconciliation_complete(
    logger: logging.Logger,
    run_id: str,
    matched: int,
    exceptions: int,
    match_rate: float,
    duration_seconds: float
):
    """Log reconciliation completion with metrics."""
    logger.info(
        f"Reconciliation complete {run_id[:8]}... | matched={matched} | exceptions={exceptions} | rate={match_rate:.1%} | time={duration_seconds:.2f}s",
        extra={"extra_data": {
            "event": "reconciliation_complete",
            "run_id": run_id,
            "matched_count": matched,
            "exception_count": exceptions,
            "match_rate": match_rate,
            "duration_seconds": duration_seconds
        }}
    )


def log_match_found(
    logger: logging.Logger,
    bank_id: str,
    ap_ids: list,
    confidence: float,
    reasons: list
):
    """Log a successful match."""
    logger.debug(
        f"Match found: bank={bank_id} -> ap={ap_ids} | confidence={confidence:.0%}",
        extra={"extra_data": {
            "event": "match_found",
            "bank_transaction_id": bank_id,
            "ap_transaction_ids": ap_ids,
            "confidence": confidence,
            "match_reasons": reasons
        }}
    )


def log_exception_created(
    logger: logging.Logger,
    exception_id: str,
    exception_type: str,
    severity: str,
    transaction_id: str
):
    """Log exception creation."""
    logger.warning(
        f"Exception created: {exception_type} | severity={severity} | txn={transaction_id}",
        extra={"extra_data": {
            "event": "exception_created",
            "exception_id": exception_id,
            "exception_type": exception_type,
            "severity": severity,
            "transaction_id": transaction_id
        }}
    )


def log_api_request(
    logger: logging.Logger,
    method: str,
    path: str,
    status_code: int,
    duration_ms: float,
    client_ip: str = None
):
    """Log API request."""
    logger.info(
        f"{method} {path} | status={status_code} | time={duration_ms:.0f}ms",
        extra={"extra_data": {
            "event": "api_request",
            "method": method,
            "path": path,
            "status_code": status_code,
            "duration_ms": duration_ms,
            "client_ip": client_ip
        }}
    )


def log_error(
    logger: logging.Logger,
    error: Exception,
    context: str = None,
    extra: Dict[str, Any] = None
):
    """Log an error with context."""
    extra_data = {"event": "error", "error_type": type(error).__name__}
    if context:
        extra_data["context"] = context
    if extra:
        extra_data.update(extra)

    logger.error(
        f"Error: {error} | context={context or 'none'}",
        exc_info=True,
        extra={"extra_data": extra_data}
    )
