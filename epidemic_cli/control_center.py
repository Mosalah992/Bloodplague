from __future__ import annotations

import os
from typing import Callable

from .commands import control, openers, stack, status as status_commands
from .core.compose import compose_ps
from .core.discovery import orchestrator_url, topology_name
from .core.output import console, print_message, print_panel


CommandHandler = Callable[[list[str]], None]


HELP_BODY = """\
Core:
  up | down | start | stop | restart | build | rebuild
  status | doctor | ps | logs [service] [lines] | live
World:
  advance [rounds] | simulate [rounds] | reset | world-clear
Openers:
  dashboard | health | urls
Control:
  vaccine | quarantine <agent_id> | inject <agent_id> [worm_level]
Shell:
  help | clear | exit

Shortcuts:
  1=up  2=down  3=restart  4=status  5=ps  6=logs  7=live  8=dashboard  9=health  10=urls
Examples:
  start stack
  build
  advance 5
  simulate 20
  logs orchestrator 100
  quarantine courier-1
  inject courier-1 high"""


ALIASES = {
    "1": "up",
    "2": "down",
    "3": "restart",
    "4": "status",
    "5": "ps",
    "6": "logs",
    "7": "live",
    "8": "dashboard",
    "9": "health",
    "10": "urls",
    "start": "up",
    "stop": "down",
    "build": "build",
    "advance round": "advance",
    "start simulation": "simulate",
    "start sim": "simulate",
    "run simulation": "simulate",
    "world reset": "world-clear",
    "clear world": "world-clear",
    "start stack": "up",
    "stop stack": "down",
    "take down stack": "down",
    "services": "ps",
    "service": "ps",
    "menu": "help",
    "?": "help",
    "q": "exit",
    "quit": "exit",
    "cls": "clear",
}


def _service_summary() -> tuple[int, int]:
    services = compose_ps()
    running = 0
    for row in services:
        state = str(row.get("State") or row.get("Status") or "").lower()
        if "running" in state:
            running += 1
    return running, len(services)


def _render_header() -> None:
    running, total = _service_summary()
    body = (
        f"Topology: {topology_name()}\n"
        f"Orchestrator: {orchestrator_url()}\n"
        f"Running services: {running}/{total}\n\n"
        f"Type help for commands."
    )
    print_panel("Epidemic Control Center", body, style="green")


def _render_help() -> None:
    print_panel("Commands", HELP_BODY, style="cyan")


def render_help() -> None:
    _render_help()


def _parse_command(raw: str) -> tuple[str, list[str]]:
    text = (raw or "").strip()
    if not text:
        return "status", []
    lowered = text.lower()
    if lowered in ALIASES:
        return ALIASES[lowered], []
    parts = text.split()
    command = ALIASES.get(parts[0].lower(), parts[0].lower())
    args = parts[1:]
    if command == "open" and args:
        command = ALIASES.get(args[0].lower(), args[0].lower())
        args = args[1:]
    return command, args


def _parse_logs_args(args: list[str]) -> tuple[str, int]:
    service = "all"
    lines = 80
    if not args:
        return service, lines
    if len(args) == 1:
        if args[0].isdigit():
            return service, int(args[0])
        return args[0], lines
    service = args[0]
    if args[1].isdigit():
        lines = int(args[1])
    return service, lines


def _handle_up(_: list[str]) -> None:
    stack.up()


def _handle_down(_: list[str]) -> None:
    stack.down()


def _handle_restart(_: list[str]) -> None:
    stack.restart()


def _handle_rebuild(_: list[str]) -> None:
    stack.rebuild()


def _handle_build(_: list[str]) -> None:
    stack.build()


def _handle_status(_: list[str]) -> None:
    status_commands.status()


def _handle_doctor(_: list[str]) -> None:
    status_commands.doctor()


def _handle_ps(_: list[str]) -> None:
    stack.ps()


def _handle_logs(args: list[str]) -> None:
    service, lines = _parse_logs_args(args)
    stack.logs(service=service, lines=lines)


def _handle_live(_: list[str]) -> None:
    status_commands.live()


def _handle_dashboard(_: list[str]) -> None:
    openers.open_dashboard()
    print_message(f"opened {orchestrator_url()}/dashboard", style="green")


def _handle_health(_: list[str]) -> None:
    openers.open_health()
    print_message(f"opened {orchestrator_url()}/api/health", style="green")


def _handle_urls(_: list[str]) -> None:
    openers.urls()


def _handle_reset(_: list[str]) -> None:
    control.reset()


def _handle_world_clear(_: list[str]) -> None:
    control.world_clear()


def _handle_vaccine(_: list[str]) -> None:
    control.vaccine()


def _handle_quarantine(args: list[str]) -> None:
    if not args:
        print_message("usage: quarantine <agent_id>", style="yellow")
        return
    control.quarantine(args[0])


def _handle_inject(args: list[str]) -> None:
    if not args:
        print_message("usage: inject <agent_id> [worm_level]", style="yellow")
        return
    worm_level = args[1] if len(args) > 1 else "medium"
    control.inject(args[0], worm_level=worm_level)


def _handle_advance(args: list[str]) -> None:
    rounds = 1
    if args and args[0].isdigit():
        rounds = int(args[0])
    control.advance(rounds=rounds)


def _handle_simulate(args: list[str]) -> None:
    rounds = 10
    if args and args[0].isdigit():
        rounds = int(args[0])
    control.simulate(rounds=rounds)


HANDLERS: dict[str, CommandHandler] = {
    "up": _handle_up,
    "down": _handle_down,
    "restart": _handle_restart,
    "build": _handle_build,
    "rebuild": _handle_rebuild,
    "status": _handle_status,
    "doctor": _handle_doctor,
    "ps": _handle_ps,
    "logs": _handle_logs,
    "live": _handle_live,
    "dashboard": _handle_dashboard,
    "health": _handle_health,
    "urls": _handle_urls,
    "reset": _handle_reset,
    "world-clear": _handle_world_clear,
    "vaccine": _handle_vaccine,
    "quarantine": _handle_quarantine,
    "inject": _handle_inject,
    "advance": _handle_advance,
    "simulate": _handle_simulate,
}


def launch_control_center() -> None:
    if os.name == "nt":
        os.system("title Epidemic Control Center")

    console.clear()
    _render_header()
    _render_help()

    while True:
        try:
            raw = console.input("[bold cyan]epidemic> [/]")
        except (EOFError, KeyboardInterrupt):
            print()
            break

        command, args = _parse_command(raw)
        if command == "exit":
            break
        if command == "clear":
            console.clear()
            _render_header()
            continue
        if command == "help":
            _render_help()
            continue

        handler = HANDLERS.get(command)
        if handler is None:
            print_message(f"unknown command: {command}. type help.", style="red")
            continue

        try:
            handler(args)
        except SystemExit:
            pass
