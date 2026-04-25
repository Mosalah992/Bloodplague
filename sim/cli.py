from __future__ import annotations

import typer
import httpx


app = typer.Typer(help="Simulation utilities.")


@app.command()
def reset(
    confirm: bool = typer.Option(False, "--confirm", "-y", help="Skip confirmation prompt"),
    base_url: str = typer.Option("http://localhost:8000", help="Orchestrator base URL."),
) -> None:
    """
    Reset the simulation to epoch-start baseline.
    Clears all infection state, mutations, artifacts, C2 sessions, and Guardian pressure.
    """
    if not confirm:
        typer.confirm(
            "This will clear ALL infection state, mutations, and artifacts. Continue?",
            abort=True,
        )
    response = httpx.post(f"{base_url.rstrip('/')}/api/reset", params={"issued_by": "cli"}, timeout=30.0)
    response.raise_for_status()
    result = response.json()
    typer.echo(f"[RESET COMPLETE] Round {result.get('round', 0)}")
    typer.echo(f"  Agents cleared:    {len(result.get('agents_cleared', []))}")
    typer.echo(f"  Missions cleared:  {result.get('missions_cleared', 0)}")
    typer.echo(f"  Artifacts cleared: {result.get('artifacts_cleared', 0)}")
    typer.echo(f"  C2 sessions closed: {result.get('c2_sessions_cleared', 0)}")


if __name__ == "__main__":
    app()
