from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any

from .discovery import find_repo_root


def run_command(
    args: list[str],
    *,
    root: Path | None = None,
    capture_output: bool = True,
    check: bool = False,
) -> subprocess.CompletedProcess[str]:
    cwd = str(find_repo_root(root))
    if os.name == "nt":
        command = subprocess.list2cmdline(args)
        return subprocess.run(command, cwd=cwd, shell=True, capture_output=capture_output, text=True, check=check)
    return subprocess.run(args, cwd=cwd, shell=False, capture_output=capture_output, text=True, check=check)


def run_compose(
    args: list[str],
    *,
    root: Path | None = None,
    capture_output: bool = True,
    check: bool = False,
) -> subprocess.CompletedProcess[str]:
    return run_command(["docker", "compose", *args], root=root, capture_output=capture_output, check=check)


def docker_available(root: Path | None = None) -> tuple[bool, str]:
    result = run_command(["docker", "info"], root=root, capture_output=True)
    if result.returncode == 0:
        return True, "ok"
    error = (result.stderr or result.stdout or "").strip() or "docker info failed"
    return False, error


def compose_ps(root: Path | None = None) -> list[dict[str, Any]]:
    result = run_compose(["ps", "--format", "json"], root=root, capture_output=True)
    if result.returncode != 0:
        return []
    output = (result.stdout or "").strip()
    if not output:
        return []
    try:
        parsed = json.loads(output)
        if isinstance(parsed, list):
            return [dict(item) for item in parsed if isinstance(item, dict)]
    except json.JSONDecodeError:
        pass
    rows: list[dict[str, Any]] = []
    for line in output.splitlines():
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows
