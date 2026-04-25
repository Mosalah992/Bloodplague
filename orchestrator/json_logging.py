import json
import logging
from datetime import datetime, timezone
from typing import Any


def _json_safe(value: Any) -> Any:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    try:
        json.dumps(value)
        return value
    except TypeError:
        return str(value)


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        data: dict[str, Any] = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname.lower(),
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            data["exception"] = self.formatException(record.exc_info)
        if record.stack_info:
            data["stack"] = self.formatStack(record.stack_info)
        return json.dumps(data, ensure_ascii=False, separators=(",", ":"))


class UvicornAccessJsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        data: dict[str, Any] = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname.lower(),
            "logger": record.name,
            "event": "http_access",
            "message": record.getMessage(),
        }
        if isinstance(record.args, tuple) and len(record.args) >= 5:
            client_addr, method, path, http_version, status_code = record.args[:5]
            data.update(
                {
                    "client": _json_safe(client_addr),
                    "method": _json_safe(method),
                    "path": _json_safe(path),
                    "http_version": _json_safe(http_version),
                    "status": _json_safe(status_code),
                }
            )
        return json.dumps(data, ensure_ascii=False, separators=(",", ":"))
