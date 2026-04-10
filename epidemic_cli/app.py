from __future__ import annotations

import typer

from .commands import config as config_commands
from .commands import control, openers, soak, stack, status, telemetry


app = typer.Typer(no_args_is_help=True, help="Local operator CLI for Epidemic Lab.")

app.command()(stack.up)
app.command()(stack.down)
app.command()(stack.restart)
app.command()(stack.rebuild)
app.command()(stack.ps)
app.command()(stack.logs)

app.command()(status.status)
app.command()(status.doctor)
app.command()(status.live)

app.command()(openers.urls)
app.command()(control.reset)
app.command()(control.vaccine)
app.command()(control.quarantine)
app.command()(control.inject)
app.command()(config_commands.config)

app.add_typer(openers.app, name="open")
app.add_typer(soak.app, name="soak")
app.add_typer(telemetry.app, name="telemetry")
