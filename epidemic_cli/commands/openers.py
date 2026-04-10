from __future__ import annotations

import webbrowser

import typer

from ..core.discovery import orchestrator_url
from ..core.output import print_kv


app = typer.Typer(help="Open platform URLs.")


@app.command("dashboard")
def open_dashboard() -> None:
    webbrowser.open(f"{orchestrator_url()}/dashboard")


@app.command("health")
def open_health() -> None:
    webbrowser.open(f"{orchestrator_url()}/api/health")


def urls() -> None:
    base = orchestrator_url()
    print_kv(
        "Useful URLs",
        [
            ("dashboard", f"{base}/dashboard"),
            ("health", f"{base}/api/health"),
            ("search", f"{base}/api/search"),
            ("c2_metrics", f"{base}/api/c2/metrics"),
            ("epidemic_metrics", f"{base}/api/epidemic/metrics"),
        ],
    )
