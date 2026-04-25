import builtins
import json
import sys
import threading
from datetime import datetime, timezone
from typing import Any


_LOCK = threading.Lock()
_ORIGINAL_PRINT = builtins.print
_INSTALLED = False


def _message_from_args(args: tuple[Any, ...], sep: str) -> str:
    return sep.join(str(arg) for arg in args)


def install_json_print_logger(*, service: str, agent_id: str = "", role: str = "") -> None:
    global _INSTALLED
    if _INSTALLED:
        return

    def json_print(*args: Any, **kwargs: Any) -> None:
        sep = str(kwargs.get("sep", " "))
        end = str(kwargs.get("end", "\n"))
        file_obj = kwargs.get("file", sys.stdout)
        flush = bool(kwargs.get("flush", False))
        line = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "level": "info",
            "service": service,
            "agent_id": agent_id,
            "role": role,
            "message": _message_from_args(args, sep),
        }
        encoded = json.dumps(line, ensure_ascii=False, separators=(",", ":"))
        with _LOCK:
            _ORIGINAL_PRINT(encoded, end=end, file=file_obj, flush=flush)

    builtins.print = json_print
    _INSTALLED = True
