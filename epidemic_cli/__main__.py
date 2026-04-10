from __future__ import annotations

import sys

from .app import app
from .control_center import launch_control_center


def _console_process_count() -> int | None:
    if sys.platform != "win32":
        return None

    try:
        import ctypes

        process_ids = (ctypes.c_uint * 64)()
        count = ctypes.windll.kernel32.GetConsoleProcessList(process_ids, len(process_ids))
        return int(count)
    except Exception:
        return None


def should_pause_on_exit(argv: list[str] | None = None) -> bool:
    args = argv or list(sys.argv)
    if sys.platform != "win32":
        return False
    if not getattr(sys, "frozen", False):
        return False
    if len(args) > 1:
        return False

    process_count = _console_process_count()
    return process_count is not None and process_count <= 1


def should_launch_control_center(argv: list[str] | None = None) -> bool:
    args = argv or list(sys.argv)
    return bool(getattr(sys, "frozen", False) and len(args) <= 1)


def _pause_before_exit() -> None:
    try:
        input("\nPress Enter to close epidemic.exe...")
    except EOFError:
        pass


def main() -> None:
    pause_on_exit = should_pause_on_exit()
    if should_launch_control_center():
        launch_control_center()
        if pause_on_exit:
            _pause_before_exit()
        return

    try:
        app()
    except SystemExit:
        if pause_on_exit:
            _pause_before_exit()
        raise

    if pause_on_exit:
        _pause_before_exit()


if __name__ == "__main__":
    main()
