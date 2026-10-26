import io
import json
import logging
import os
import sys
import types
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import observability
from handler import authorizer, login


class ObservabilityTest(unittest.TestCase):
    def setUp(self):
        self.stream = io.StringIO()
        self.handler = logging.StreamHandler(self.stream)
        self.handler.setFormatter(observability.JsonFormatter())
        observability.LOGGER.addHandler(self.handler)

    def tearDown(self):
        observability.LOGGER.removeHandler(self.handler)

    def logs(self):
        return [json.loads(line) for line in self.stream.getvalue().splitlines()]

    def test_login_preserves_request_id_and_injects_active_trace(self):
        tracer = types.SimpleNamespace(get_log_correlation_context=lambda: {"trace_id": "123", "span_id": "456"})
        with patch.dict(sys.modules, {"ddtrace": types.SimpleNamespace(tracer=tracer)}):
            response = login({"headers": {"X-Request-ID": "teste-123"}, "body": '{"cpf":"invalido"}'}, None)
        self.assertEqual("teste-123", response["headers"]["X-Request-ID"])
        entry = self.logs()[-1]
        self.assertEqual("123", entry["dd.trace_id"])
        self.assertEqual("456", entry["dd.span_id"])
        self.assertEqual(400, entry["http_status"])
        self.assertIsNone(observability._request_id.get())

    def test_request_context_does_not_leak_between_warm_invocations(self):
        one = login({"headers": {"X-Request-ID": "first"}, "body": '{}'}, None)
        two = login({"headers": {"X-Request-ID": "bad\nheader"}, "body": '{}'}, None)
        self.assertEqual("first", one["headers"]["X-Request-ID"])
        self.assertNotEqual("first", two["headers"]["X-Request-ID"])
        self.assertNotIn("\n", two["headers"]["X-Request-ID"])
        self.assertIsNone(observability._request_id.get())

    def test_integration_failure_does_not_log_secrets(self):
        @observability.integration("postgresql")
        def broken():
            raise OSError("password=secret cpf=00361937040")
        with self.assertRaises(OSError):
            broken()
        entry = self.logs()[-1]
        self.assertEqual("integration.failed", entry["event"])
        self.assertEqual("postgresql", entry["integracao"])
        self.assertNotIn("password", self.stream.getvalue())
        self.assertNotIn("00361937040", self.stream.getvalue())

    def test_handled_500_marks_trace_as_error(self):
        span = types.SimpleNamespace(error=0)
        tracer = types.SimpleNamespace(get_log_correlation_context=lambda: {}, current_span=lambda: span)
        with (patch.dict(sys.modules, {"ddtrace": types.SimpleNamespace(tracer=tracer)}),
              patch("handler._find_client", side_effect=OSError("database unavailable"))):
            response = login({"body": '{"cpf":"00361937040"}'}, None)
        self.assertEqual(500, response["statusCode"])
        self.assertEqual(1, span.error)
        self.assertEqual("ERROR", self.logs()[-1]["level"])

    def test_denied_authorizer_is_not_a_technical_failure(self):
        response = authorizer({"headers": {}}, None)
        self.assertFalse(response["isAuthorized"])
        self.assertEqual("lambda.request", self.logs()[-1]["event"])
        self.assertEqual(403, self.logs()[-1]["http_status"])
