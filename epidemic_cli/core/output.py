from __future__ import annotations

from typing import Iterable, Sequence

from rich.console import Console
from rich.panel import Panel
from rich.table import Table


console = Console()


def print_message(message: str, *, style: str = "") -> None:
    console.print(message, style=style or None)


def print_kv(title: str, rows: Iterable[tuple[str, object]]) -> None:
    table = Table(title=title, show_header=True, header_style="bold cyan")
    table.add_column("Key", style="cyan")
    table.add_column("Value", style="white")
    for key, value in rows:
        table.add_row(str(key), "" if value is None else str(value))
    console.print(table)


def print_table(title: str, columns: Sequence[str], rows: Iterable[Sequence[object]]) -> None:
    table = Table(title=title, show_header=True, header_style="bold cyan")
    for column in columns:
        table.add_column(column)
    for row in rows:
        table.add_row(*[str(value) for value in row])
    console.print(table)


def print_panel(title: str, body: str, *, style: str = "cyan") -> None:
    console.print(Panel(body, title=title, border_style=style))
