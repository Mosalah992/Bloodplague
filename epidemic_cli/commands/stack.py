from __future__ import annotations

from typing import Any

from . import status as status_commands
from ..core.compose import compose_ps, run_compose
from ..core.output import console, print_message, print_table


def _format_ports(value: Any) -> str:
    if not value:
        return "-"
    if isinstance(value, str):
        return value or "-"
    if isinstance(value, list):
        formatted: list[str] = []
        seen: set[str] = set()
        for item in value:
            if not isinstance(item, dict):
                text = str(item)
            else:
                published = item.get("PublishedPort")
                target = item.get("TargetPort")
                protocol = item.get("Protocol") or "tcp"
                if published and target:
                    text = f"{published}->{target}/{protocol}"
                elif target:
                    text = f"{target}/{protocol}"
                else:
                    text = str(item)
            if text not in seen:
                seen.add(text)
                formatted.append(text)
        return ", ".join(formatted) or "-"
    return str(value)


def up() -> None:
    result = run_compose(["up", "-d"], capture_output=True)
    if result.returncode != 0:
        print_message(f"docker compose up failed\n{result.stderr or result.stdout}", style="red")
        raise SystemExit(1)
    print_message("stack started", style="green")
    status_commands.status()


def down() -> None:
    result = run_compose(["down"], capture_output=True)
    if result.returncode != 0:
        print_message(f"docker compose down failed\n{result.stderr or result.stdout}", style="red")
        raise SystemExit(1)
    print_message("stack stopped", style="green")


def restart() -> None:
    down()
    up()


def rebuild() -> None:
    build = run_compose(["build"], capture_output=True)
    if build.returncode != 0:
        print_message(f"docker compose build failed\n{build.stderr or build.stdout}", style="red")
        raise SystemExit(1)
    up()


def ps() -> None:
    rows = compose_ps()
    if rows:
        print_table(
            "Compose Services",
            ("Service", "State", "Health", "Ports"),
            [
                (
                    row.get("Service") or row.get("Name") or "",
                    row.get("State") or row.get("Status") or "",
                    row.get("Health") or "-",
                    _format_ports(row.get("Publishers") or row.get("Ports")),
                )
                for row in rows
            ],
        )
        return
    result = run_compose(["ps"], capture_output=True)
    console.print(result.stdout or result.stderr or "no services")


def logs(service: str = "all", lines: int = 200) -> None:
    args = ["logs", "--no-color", "--tail", str(lines)]
    if service and service != "all":
        args.append(service)
    result = run_compose(args, capture_output=True)
    console.print(result.stdout or result.stderr or "")
