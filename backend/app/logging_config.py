"""JSON logs with per-request context (request ID, user, organization).

Each request gets one mutable context dict. Dependencies running in worker threads
update that same dict, so their fields reach every later log line of the request.
"""
import contextvars
import json
import logging
import os
import re
import sys
import time
import uuid
from datetime import datetime, timezone

from fastapi import Request

from .error_tracking import tag_request

_request_context: contextvars.ContextVar[dict | None] = contextvars.ContextVar("request_context", default=None)

# Accept a caller's X-Request-ID only if it can't smuggle anything into the logs
_SAFE_REQUEST_ID = re.compile(r"^[A-Za-z0-9._-]{1,64}$")

request_logger = logging.getLogger("app.request")


def bind_log_context(**fields) -> None:
    """Attach fields (e.g. user_id) to every log line for the rest of the current request."""
    context = _request_context.get()
    if context is not None:
        context.update({key: value for key, value in fields.items() if value is not None})
    tag_request(**fields)  # the same ids on error reports


def current_request_id() -> str | None:
    context = _request_context.get()
    return context.get("request_id") if context else None


def internal_error_detail() -> str:
    """Message for unexpected 500s: no internals, but a reference support can find in the logs."""
    return f"Something went wrong on our side. Reference: {current_request_id() or 'unknown'}"


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        entry = {
            "time": datetime.fromtimestamp(record.created, timezone.utc).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        entry.update(_request_context.get() or {})
        entry.update(getattr(record, "fields", None) or {})
        if record.exc_info:
            entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(entry, default=str, ensure_ascii=False)


def configure_logging() -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())

    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(os.getenv("LOG_LEVEL", "INFO").upper())

    # Our middleware logs every request, so uvicorn's own access log would duplicate it
    logging.getLogger("uvicorn.access").disabled = True
    for name in ("uvicorn", "uvicorn.error"):
        uvicorn_logger = logging.getLogger(name)
        uvicorn_logger.handlers = []
        uvicorn_logger.propagate = True


async def request_logging_middleware(request: Request, call_next):
    incoming = request.headers.get("x-request-id", "")
    request_id = incoming if _SAFE_REQUEST_ID.match(incoming) else uuid.uuid4().hex
    token = _request_context.set({"request_id": request_id})
    started = time.perf_counter()
    status_code = 500
    try:
        response = await call_next(request)
        status_code = response.status_code
        response.headers["X-Request-ID"] = request_id
        return response
    except Exception:
        request_logger.exception("Unhandled error")
        raise
    finally:
        request_logger.info(
            "request",
            extra={"fields": {
                "method": request.method,
                "path": request.url.path,
                "status": status_code,
                "duration_ms": round((time.perf_counter() - started) * 1000, 1),
            }},
        )
        _request_context.reset(token)
