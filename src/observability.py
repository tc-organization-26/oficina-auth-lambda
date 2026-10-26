"""Structured invocation logs. Datadog's Lambda layer supplies the active trace."""
import contextvars
import functools
import json
import logging
import os
import re
import time
import uuid
from datetime import datetime, timezone

_request_id = contextvars.ContextVar("request_id", default=None)


class JsonFormatter(logging.Formatter):
    def format(self, record):
        payload = {
            "@timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "message": record.getMessage(),
            "service": os.getenv("DD_SERVICE", "oficina-auth"),
            "env": os.getenv("DD_ENV", "local"),
            "version": os.getenv("DD_VERSION", "local"),
            "request_id": _request_id.get(),
        }
        # Import only when deployed with the Datadog layer; local tests need no SDK.
        try:
            from ddtrace import tracer
            correlation = tracer.get_log_correlation_context()
            for key in ("trace_id", "span_id"):
                value = correlation.get(key)
                if value and str(value) != "0":
                    payload["dd." + key] = str(value)
        except ImportError:
            pass
        payload.update(getattr(record, "fields", {}))
        return json.dumps(payload, ensure_ascii=False)


LOGGER = logging.getLogger("oficina.observability")
LOGGER.setLevel(logging.INFO)
LOGGER.propagate = False
if not LOGGER.handlers:
    stream = logging.StreamHandler()
    stream.setFormatter(JsonFormatter())
    LOGGER.addHandler(stream)


def emit(level, event, message, **fields):
    LOGGER.log(level, message, extra={"fields": {"event": event, **fields}})


def integration(name):
    """Emit one integration failure at the boundary, without secrets or CPF."""
    def decorate(function):
        @functools.wraps(function)
        def wrapped(*args, **kwargs):
            try:
                return function(*args, **kwargs)
            except Exception as failure:
                emit(logging.ERROR, "integration.failed", "Falha na integracao",
                     integracao=name, operacao=function.__name__, error_type=type(failure).__name__)
                raise
        return wrapped
    return decorate


def observe(operation, route=None):
    def decorate(function):
        @functools.wraps(function)
        def wrapped(event, context):
            headers = {key.lower(): value for key, value in (event.get("headers") or {}).items()}
            supplied = headers.get("x-request-id", "")
            request_id = supplied if isinstance(supplied, str) and re.fullmatch(r"[A-Za-z0-9._-]{1,64}", supplied) else str(uuid.uuid4())
            token = _request_id.set(request_id)
            started = time.perf_counter()
            status = 500
            try:
                result = function(event, context)
                status = result.get("statusCode", 200 if result.get("isAuthorized") else 403)
                if "statusCode" in result:
                    result.setdefault("headers", {})["X-Request-ID"] = request_id
                return result
            finally:
                try:
                    emit(logging.ERROR if status >= 500 else logging.INFO,
                         "http.request" if route else "lambda.request", "Invocacao concluida",
                         operacao=operation, http_route=route, http_method="POST" if route else None,
                         http_status=status, duracao_ms=(time.perf_counter() - started) * 1000,
                         aws_request_id=getattr(context, "aws_request_id", None))
                    # Caught exceptions returned as HTTP 500 must also mark the span.
                    if status >= 500:
                        try:
                            from ddtrace import tracer
                            span = tracer.current_span()
                            if span:
                                span.error = 1
                        except ImportError:
                            pass
                finally:
                    _request_id.reset(token)
        return wrapped
    return decorate
