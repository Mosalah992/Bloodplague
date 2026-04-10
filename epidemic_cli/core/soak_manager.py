from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .compose import run_command
from .discovery import find_repo_root, latest_progress, latest_report_path, logs_dir, resolve_soak_script


STATE_DIR = Path.home() / ".epidemic_cli"
STATE_PATH = STATE_DIR / "state.json"


def _ensure_state_dir() -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)


def load_state() -> dict[str, Any]:
    _ensure_state_dir()
    if not STATE_PATH.exists():
        return {}
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def save_state(state: dict[str, Any]) -> None:
    _ensure_state_dir()
    STATE_PATH.write_text(json.dumps(state, indent=2), encoding="utf-8")


def clear_state() -> None:
    if STATE_PATH.exists():
        STATE_PATH.unlink()


def process_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        if os.name == "nt":
            result = run_command(["tasklist", "/FI", f"PID eq {pid}"])
            return str(pid) in (result.stdout or "")
        os.kill(pid, 0)
        return True
    except Exception:
        return False


def active_soak_state() -> dict[str, Any]:
    state = load_state()
    pid = int(state.get("pid") or 0)
    if not pid or not process_alive(pid):
        return {}
    return state


def parse_duration_hours(duration: str) -> float:
    text = str(duration or "").strip().lower()
    if not text:
        return 6.0
    if text.endswith("h"):
        return float(text[:-1])
    if text.endswith("m"):
        return float(text[:-1]) / 60.0
    return float(text)


def launch_soak(script_name: str, *, duration: str = "6h", root: Path | None = None) -> dict[str, Any]:
    repo_root = find_repo_root(root)
    script_path = resolve_soak_script(script_name, repo_root)
    if script_path is None:
        raise FileNotFoundError(f"unknown soak script: {script_name}")
    log_directory = logs_dir(repo_root) / "cli"
    log_directory.mkdir(parents=True, exist_ok=True)
    started_at = datetime.now(timezone.utc)
    log_path = log_directory / f"{script_path.stem}_{started_at.strftime('%Y%m%d_%H%M%S')}.log"
    cmd = [sys.executable, str(script_path)]
    if "wallclock" in script_path.stem:
        cmd.extend(["--hours", str(parse_duration_hours(duration))])
    handle = log_path.open("w", encoding="utf-8")
    try:
        process = subprocess.Popen(
            cmd,
            cwd=str(repo_root),
            stdout=handle,
            stderr=subprocess.STDOUT,
            text=True,
        )
    finally:
        handle.close()
    state = {
        "pid": process.pid,
        "script": script_path.name,
        "script_path": str(script_path),
        "duration": duration,
        "started_at": started_at.isoformat(),
        "log_path": str(log_path),
    }
    save_state(state)
    return state


def stop_soak() -> dict[str, Any]:
    state = load_state()
    pid = int(state.get("pid") or 0)
    if not pid or not process_alive(pid):
        clear_state()
        return {"stopped": False, "reason": "no active soak"}
    if os.name == "nt":
        run_command(["taskkill", "/PID", str(pid), "/T", "/F"])
    else:
        os.kill(pid, signal.SIGTERM)
    state["stopped_at"] = datetime.now(timezone.utc).isoformat()
    save_state(state)
    return {"stopped": True, **state}


def latest_soak_snapshot(root: Path | None = None) -> dict[str, Any]:
    return {
        "state": active_soak_state() or load_state(),
        "progress": latest_progress(root),
        "report_path": str(latest_report_path(root) or ""),
    }
