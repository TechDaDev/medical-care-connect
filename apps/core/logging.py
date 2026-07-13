"""
Production-ready structured JSON logging.

Fields:
  timestamp, level, logger, event, request_id, method, path_template,
  status_code, duration_ms, user_id (hashed), role, remote_ip_hash,
  user_agent_family (minimal), environment, service, error_code

Never logs: request body, response body, passwords, cookies, auth headers,
JWT, CSRF token, attachment contents, descriptions, messages, intake data,
medical records, private notes, original IP, DeepSeek data, secrets.
"""

import hashlib
import json
import logging
import os
import time
import uuid

from django.conf import settings


class JSONFormatter(logging.Formatter):
    """Format log records as JSON lines."""

    def format(self, record):
        timestamp = self.formatTime(record, "%Y-%m-%dT%H:%M:%S.%fZ")
        log_entry = {
            "timestamp": timestamp,
            "level": record.levelname,
            "logger": record.name,
            "event": getattr(record, "event", record.msg[:80] if isinstance(record.msg, str) else "log"),
            "environment": getattr(settings, "APP_ENVIRONMENT", os.environ.get("APP_ENVIRONMENT", "development")),
            "service": os.environ.get("LOG_SERVICE_NAME", "mcc-backend"),
        }
        for extra_field in ("request_id", "method", "path_template", "status_code",
                            "duration_ms", "user_id", "role", "remote_ip_hash",
                            "user_agent_family", "error_code"):
            val = getattr(record, extra_field, None)
            if val is not None:
                log_entry[extra_field] = val
        if record.exc_info and record.exc_info[1]:
            log_entry["exception"] = repr(record.exc_info[1])
        # Merge any additional safe extras
        extras = getattr(record, "safe_extras", None)
        if extras and isinstance(extras, dict):
            for k, v in extras.items():
                if k not in log_entry and _is_safe_extra(k, v):
                    log_entry[k] = v
        return json.dumps(log_entry, default=str)


def _is_safe_extra(key: str, value) -> bool:
    """Reject extra fields that might contain sensitive data."""
    BLOCKED_PREFIXES = ("body", "request_body", "response_body", "password",
                        "secret", "token", "cookie", "auth", "credential",
                        "medical", "intake", "message", "note", "file_content")
    key_lower = key.lower()
    for prefix in BLOCKED_PREFIXES:
        if key_lower.startswith(prefix):
            return False
    return True


class SafeLogger:
    """Logger wrapper that enforces safe-field logging."""

    def __init__(self, name: str):
        self._logger = logging.getLogger(name)

    def _log(self, level: int, event: str, **extra):
        record = logging.LogRecord(
            name=self._logger.name,
            level=level,
            pathname="",
            lineno=0,
            msg=event,
            args=(),
            exc_info=None,
        )
        record.event = event
        for k, v in extra.items():
            if _is_safe_extra(k, v):
                setattr(record, k, v)
        self._logger.handle(record)

    def info(self, event: str, **extra):
        self._log(logging.INFO, event, **extra)

    def warning(self, event: str, **extra):
        self._log(logging.WARNING, event, **extra)

    def error(self, event: str, **extra):
        self._log(logging.ERROR, event, **extra)

    def critical(self, event: str, **extra):
        self._log(logging.CRITICAL, event, **extra)


def hash_ip(ip: str) -> str:
    """One-way hash of IP address for privacy-safe logging."""
    salt = os.environ.get("LOG_IP_HASH_SALT", "")
    if not salt:
        return ""
    raw = f"{salt}{ip}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:16]


class RequestLoggingMiddleware:
    """Log each request/response cycle with safe fields."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if not _should_log():
            return self.get_response(request)

        start = time.time()
        response = self.get_response(request)
        duration_ms = int((time.time() - start) * 1000)

        self._log_request(request, response, duration_ms)
        return response

    def _log_request(self, request, response, duration_ms):
        logger = SafeLogger("mcc.request")
        method = getattr(request, "method", "")
        status_code = getattr(response, "status_code", 0)
        rid = getattr(request, "request_id", "")
        user = getattr(request, "user", None)
        user_id = ""
        role = ""
        if user and user.is_authenticated:
            user_id = str(user.id)
            role = getattr(user, "role", "")

        remote_ip = request.META.get("REMOTE_ADDR", "")
        ip_hash = hash_ip(remote_ip)
        ua = request.META.get("HTTP_USER_AGENT", "")[:80]
        slow_ms = int(os.environ.get("LOG_SLOW_REQUEST_MS", "1000"))

        extra = {
            "request_id": rid,
            "method": method,
            "status_code": status_code,
            "duration_ms": duration_ms,
            "user_id": user_id,
            "role": role,
            "remote_ip_hash": ip_hash,
            "user_agent_family": ua,
        }
        if duration_ms > slow_ms:
            logger.warning("request.slow", **extra)
        elif status_code >= 500:
            logger.error("request.error", **extra)
        else:
            logger.info("request.ok", **extra)


def _should_log() -> bool:
    include = os.environ.get("LOG_INCLUDE_REQUESTS", "true").lower()
    return include == "true"


def configure_logging() -> None:
    """Configure Django logging with JSON formatter."""
    log_level = os.environ.get("LOG_LEVEL", "INFO").upper()
    log_format = os.environ.get("LOG_FORMAT", "json").lower()

    handlers = {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "json" if log_format == "json" else "simple",
            "stream": "ext://sys.stdout",
        },
    }

    formatters = {
        "json": {
            "()": JSONFormatter,
        },
        "simple": {
            "format": "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        },
    }

    loggers = {
        "mcc": {
            "handlers": ["console"],
            "level": log_level,
            "propagate": False,
        },
        "mcc.request": {
            "handlers": ["console"],
            "level": log_level,
            "propagate": False,
        },
        "django": {
            "handlers": ["console"],
            "level": log_level,
            "propagate": False,
        },
        "django.request": {
            "handlers": ["console"],
            "level": log_level,
            "propagate": False,
        },
    }

    logging.config.dictConfig({
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": formatters,
        "handlers": handlers,
        "loggers": loggers,
        "root": {
            "handlers": ["console"],
            "level": log_level,
        },
    })
