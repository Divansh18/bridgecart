import json
import logging

from bridgecart.core.logging import JsonFormatter


def test_log_record_is_structured_json() -> None:
    record = logging.LogRecord("bridgecart.test", logging.INFO, __file__, 1, "started", (), None)
    payload = json.loads(JsonFormatter().format(record))
    assert payload["level"] == "INFO"
    assert payload["logger"] == "bridgecart.test"
    assert payload["message"] == "started"
    assert payload["timestamp"].endswith("+00:00")
