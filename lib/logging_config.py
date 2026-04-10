"""
Centralized logging configuration for the trading system.

Usage:
    from lib.logging_config import setup_logging
    setup_logging()  # call once at module entry point
    log = logging.getLogger(__name__)

In Cloud Run (K_SERVICE env var set): outputs structured JSON for Cloud Logging.
Locally: outputs human-readable format with timestamps.
"""

import logging
import os
import uuid


def setup_logging(level: int = logging.INFO) -> None:
    """Configure the root logger with the appropriate format.

    Detects Cloud Run via K_SERVICE env var and uses JSON format for
    structured logging in Cloud Logging. Falls back to human-readable
    format for local development.

    Safe to call multiple times — subsequent calls are no-ops.
    """
    root = logging.getLogger()
    if root.handlers:
        return  # already configured

    is_cloud_run = bool(os.environ.get('K_SERVICE'))

    if is_cloud_run:
        _setup_json_logging(root, level)
    else:
        _setup_local_logging(root, level)


def _setup_local_logging(root: logging.Logger, level: int) -> None:
    """Human-readable format for local development."""
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter(
        '%(asctime)s  %(levelname)-7s  %(message)s',
        datefmt='%H:%M:%S',
    ))
    root.addHandler(handler)
    root.setLevel(level)


def _setup_json_logging(root: logging.Logger, level: int) -> None:
    """Structured JSON format for Cloud Logging integration.

    Cloud Logging automatically parses JSON log entries and extracts
    'severity', 'message', and custom fields into the log entry metadata.
    """
    import json
    import time

    correlation_id = os.environ.get('CORRELATION_ID', uuid.uuid4().hex[:12])

    class JsonFormatter(logging.Formatter):
        def format(self, record: logging.LogRecord) -> str:
            entry = {
                'severity': record.levelname,
                'message': record.getMessage(),
                'timestamp': self.formatTime(record, '%Y-%m-%dT%H:%M:%S.') + f'{record.msecs:03.0f}Z',
                'module': record.module,
                'correlation_id': correlation_id,
                'service': os.environ.get('K_SERVICE', 'unknown'),
            }
            if record.exc_info and record.exc_info[0]:
                entry['exception'] = self.formatException(record.exc_info)
            return json.dumps(entry)

    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root.addHandler(handler)
    root.setLevel(level)
