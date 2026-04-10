from __future__ import annotations

import webbrowser

import typer

from ..core.discovery import latest_report_path, latest_soak_run, list_soak_scripts, soak_alias
from ..core.output import print_kv, print_message, print_table
from ..core.soak_manager import active_soak_state, latest_soak_snapshot, launch_soak, stop_soak


app = typer.Typer(help="Manage soak and validation runs.")


@app.command("list")
def list_command() -> None:
    scripts = list_soak_scripts()
    print_table("Soak Scripts", ("Alias", "Script"), [(soak_alias(path), path.name) for path in scripts])


@app.command("start")
def start(script: str = "wallclock", duration: str = "6h") -> None:
    active = active_soak_state()
    if active:
        print_message(f"soak already running :: pid={active.get('pid')} script={active.get('script')}", style="yellow")
        raise SystemExit(1)
    state = launch_soak(script, duration=duration)
    print_kv(
        "Soak Started",
        [
            ("pid", state.get("pid")),
            ("script", state.get("script")),
            ("duration", state.get("duration")),
            ("log_path", state.get("log_path")),
        ],
    )


@app.command("watch")
def watch() -> None:
    snapshot = latest_soak_snapshot()
    print_kv(
        "Soak Watch",
        [
            ("pid", snapshot.get("state", {}).get("pid", "")),
            ("script", snapshot.get("state", {}).get("script", "")),
            ("status", snapshot.get("progress", {}).get("status", "")),
            ("completed_minutes", snapshot.get("progress", {}).get("completed_minutes", "")),
            ("total_minutes", snapshot.get("progress", {}).get("total_minutes", "")),
            ("note", snapshot.get("progress", {}).get("note", "")),
            ("report_path", snapshot.get("report_path", "")),
        ],
    )


@app.command("latest")
def latest() -> None:
    latest_run = latest_soak_run()
    snapshot = latest_soak_snapshot()
    print_kv(
        "Latest Soak",
        [
            ("run_dir", latest_run or ""),
            ("status", snapshot.get("progress", {}).get("status", "")),
            ("latest_report", snapshot.get("report_path", "")),
        ],
    )


@app.command("stop")
def stop() -> None:
    result = stop_soak()
    if not result.get("stopped"):
        print_message(result.get("reason", "no active soak"), style="yellow")
        return
    print_message(f"stopped soak pid={result.get('pid')}", style="green")


@app.command("open-report")
def open_report() -> None:
    report = latest_report_path()
    if report is None:
        print_message("no report found", style="yellow")
        raise SystemExit(1)
    webbrowser.open(report.resolve().as_uri())
