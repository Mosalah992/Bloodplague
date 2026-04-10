from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import typer

from ..core.api import APIRequestError, OrchestratorAPI
from ..core.discovery import find_repo_root

app = typer.Typer(help="Telemetry index integrity, rebuild, and run summaries.")


def _orchestrator_import_path() -> Path:
    return find_repo_root() / "orchestrator"


@app.command("verify-index")
def verify_index(
    local: bool = typer.Option(
        False,
        "--local",
        help="Verify SQLite files on disk (no running orchestrator). Uses LOGS_DIR / SIEM_DB_PATH from env.",
    ),
    siem_db: str = typer.Option("", "--siem-db", help="Override SIEM index DB path for --local."),
    epidemic_db: str = typer.Option("", "--epidemic-db", help="Override epidemic.db path for --local."),
) -> None:
    """Check SIEM index and event logger integrity (API or local PRAGMA quick_check)."""
    if local:
        sys.path.insert(0, str(_orchestrator_import_path()))
        from telemetry_integrity import verify_sqlite_integrity  # type: ignore

        root = find_repo_root()
        logs = root / "logs"
        siem_path = siem_db or os.environ.get("SIEM_DB_PATH", str(logs / "siem_index.db"))
        epi_path = epidemic_db or str(logs / "epidemic.db")
        out = {
            "siem_index": verify_sqlite_integrity(siem_path),
            "epidemic_db": verify_sqlite_integrity(epi_path),
        }
        typer.echo(json.dumps(out, indent=2))
        if not out["siem_index"].get("ok") and not out["siem_index"].get("skipped"):
            raise typer.Exit(code=1)
        if not out["epidemic_db"].get("ok") and not out["epidemic_db"].get("skipped"):
            raise typer.Exit(code=1)
        return
    try:
        data = OrchestratorAPI().get("/api/telemetry/verify-index")
    except APIRequestError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(json.dumps(data, indent=2))


@app.command("rebuild-index")
def rebuild_index(
    jsonl: str = typer.Option(
        "",
        "--jsonl",
        help="Path to JSONL under logs (must stay within import roots). Default: server uses events.jsonl.",
    ),
) -> None:
    """Rebuild the SIEM SQLite index from JSONL via the orchestrator API."""
    try:
        data = OrchestratorAPI().post("/api/telemetry/rebuild-index", payload={"jsonl_path": jsonl})
    except APIRequestError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(json.dumps(data, indent=2))


@app.command("forensic-summary")
def forensic_summary(
    target: Path = typer.Argument(..., exists=True, readable=True),
    output: str = typer.Option("json", "--output", "-o", help="json | markdown"),
    write: bool = typer.Option(False, "--write", help="If target is a run dir, write forensic_summary.json/.md there"),
) -> None:
    """Decision-grade forensic summary (JSON default, Markdown optional)."""
    sys.path.insert(0, str(_orchestrator_import_path()))
    from run_forensic_summary import (  # type: ignore
        build_forensic_summary_from_run_dir,
        build_forensic_summary,
        forensic_summary_to_markdown,
        iter_jsonl_events,
        write_run_forensic_outputs,
    )

    if target.is_dir():
        doc = build_forensic_summary_from_run_dir(target)
        if write:
            write_run_forensic_outputs(target, write_markdown=True)
    elif target.suffix.lower() == ".jsonl":
        doc = build_forensic_summary(
            list(iter_jsonl_events(target)),
            window_label=target.stem,
            source_path=str(target),
        )
    else:
        typer.echo("Target must be a run directory or a .jsonl file.", err=True)
        raise typer.Exit(code=1)

    out = str(output or "json").lower()
    if out in ("md", "markdown"):
        typer.echo(forensic_summary_to_markdown(doc))
    else:
        typer.echo(json.dumps(doc, indent=2, ensure_ascii=False, sort_keys=True))


@app.command("summarize-run")
def summarize_run(
    run_dir: Path = typer.Argument(..., exists=True, file_okay=False, dir_okay=True, readable=True),
) -> None:
    """Summarize a soak/archive run directory (progress + minute summaries) without the API."""
    sys.path.insert(0, str(_orchestrator_import_path()))
    from telemetry_integrity import summarize_jsonl_run  # type: ignore

    typer.echo(json.dumps(summarize_jsonl_run(str(run_dir)), indent=2))


@app.command("summarize-strains")
def summarize_strains() -> None:
    """Print strain engine / store health from GET /api/strain/health."""
    try:
        data = OrchestratorAPI().get("/api/strain/health")
    except APIRequestError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(json.dumps(data, indent=2))
