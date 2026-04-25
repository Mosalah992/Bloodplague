from __future__ import annotations

import typer

from .commands import config as config_commands
from .commands import control, openers, soak, stack, status, telemetry
from .control_center import launch_control_center, render_help


app = typer.Typer(no_args_is_help=True, help="Local operator CLI for Epidemic Lab.")

app.command()(stack.up)
app.command(name="start")(stack.up)
app.command()(stack.down)
app.command(name="stop")(stack.down)
app.command()(stack.restart)
app.command()(stack.build)
app.command(name="build-stack")(stack.build)
app.command()(stack.rebuild)
app.command()(stack.ps)
app.command()(stack.logs)

app.command()(status.status)
app.command()(status.doctor)
app.command()(status.live)

app.command()(openers.urls)
app.command()(control.reset)
app.command()(control.clear)
app.command(name="world-clear")(control.world_clear)
app.command()(control.vaccine)
app.command()(control.quarantine)
app.command()(control.inject)
app.command()(control.advance)
app.command()(control.simulate)
app.command()(config_commands.config)


@app.command()
def shell() -> None:
    launch_control_center()


@app.command()
def help() -> None:
    render_help()

app.add_typer(openers.app, name="open")
app.add_typer(soak.app, name="soak")
app.add_typer(telemetry.app, name="telemetry")
