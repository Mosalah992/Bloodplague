from __future__ import annotations

import sys
from pathlib import Path

from typer.testing import CliRunner


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from epidemic_cli.app import app
from epidemic_cli import control_center
from epidemic_cli.commands import stack
from epidemic_cli.core import discovery
from epidemic_cli import __main__ as cli_main


RUNNER = CliRunner()


def _write_repo_fixture(root: Path) -> None:
    (root / "scripts").mkdir(parents=True, exist_ok=True)
    (root / "logs").mkdir(parents=True, exist_ok=True)
    (root / "scripts" / "run_wallclock_research_validation.py").write_text("print('ok')\n", encoding="utf-8")
    (root / ".env").write_text("EPIDEMIC_TOPOLOGY=epidemic\n", encoding="utf-8")
    (root / "docker-compose.yml").write_text(
        """
services:
  orchestrator:
    environment:
      - OLLAMA_URL=http://host.docker.internal:11434
  courier-1:
    build:
      context: .
      dockerfile: agents/courier/Dockerfile
    environment:
      - AGENT_ID=courier-1
      - AGENT_ROLE=courier
      - LLM_MODEL=phi3:mini
    mem_limit: 256m
    cpus: "0.25"
  guardian:
    build:
      context: .
      dockerfile: agents/guardian/Dockerfile
    environment:
      - AGENT_ID=guardian
      - AGENT_ROLE=guardian
      - LLM_MODEL=llama3:8b-instruct
    mem_limit: 1g
    cpus: "1.0"
        """.strip(),
        encoding="utf-8",
    )


def test_discovery_lists_dynamic_services(tmp_path: Path, monkeypatch) -> None:
    _write_repo_fixture(tmp_path)
    monkeypatch.setenv("EPIDEMIC_CLI_REPO_ROOT", str(tmp_path))

    assert discovery.service_names() == ["orchestrator", "courier-1", "guardian"]
    assert discovery.agent_service_names() == ["courier-1", "guardian"]
    assert discovery.discover_models()["courier-1"] == "phi3:mini"
    assert discovery.discover_resources()["guardian"]["memory"] == "1g"
    assert discovery.topology_name() == "epidemic"


def test_urls_command_outputs_useful_endpoints(tmp_path: Path, monkeypatch) -> None:
    _write_repo_fixture(tmp_path)
    monkeypatch.setenv("EPIDEMIC_CLI_REPO_ROOT", str(tmp_path))

    result = RUNNER.invoke(app, ["urls"])

    assert result.exit_code == 0
    assert "dashboard" in result.stdout
    assert "/api/c2/metrics" in result.stdout
    assert "/api/epidemic/metrics" in result.stdout


def test_config_models_command_reads_compose(tmp_path: Path, monkeypatch) -> None:
    _write_repo_fixture(tmp_path)
    monkeypatch.setenv("EPIDEMIC_CLI_REPO_ROOT", str(tmp_path))

    result = RUNNER.invoke(app, ["config", "--models"])

    assert result.exit_code == 0
    assert "courier-1" in result.stdout
    assert "phi3:mini" in result.stdout


def test_quarantine_command_uses_api(tmp_path: Path, monkeypatch) -> None:
    _write_repo_fixture(tmp_path)
    monkeypatch.setenv("EPIDEMIC_CLI_REPO_ROOT", str(tmp_path))
    calls: list[tuple[str, dict[str, str]]] = []

    class FakeAPI:
        def safe_post(self, path: str, payload: dict[str, str] | None = None):
            calls.append((path, payload or {}))
            return type("Probe", (), {"ok": True, "data": {"status": "quarantined"}, "error": ""})()

    monkeypatch.setattr("epidemic_cli.commands.control._api", lambda: FakeAPI())

    result = RUNNER.invoke(app, ["quarantine", "courier-1"])

    assert result.exit_code == 0
    assert calls == [("/quarantine/courier-1", {})]


def test_reset_command_uses_api_reset_path(tmp_path: Path, monkeypatch) -> None:
    _write_repo_fixture(tmp_path)
    monkeypatch.setenv("EPIDEMIC_CLI_REPO_ROOT", str(tmp_path))
    calls: list[tuple[str, dict[str, str]]] = []

    class FakeAPI:
        def safe_post(self, path: str, payload: dict[str, str] | None = None):
            calls.append((path, payload or {}))
            return type("Probe", (), {"ok": True, "data": {"success": True}, "error": ""})()

    monkeypatch.setattr("epidemic_cli.commands.control._api", lambda: FakeAPI())

    result = RUNNER.invoke(app, ["reset"])

    assert result.exit_code == 0
    assert calls == [("/api/reset", {"issued_by": "epidemic_cli"})]


def test_advance_command_uses_world_advance_endpoint(tmp_path: Path, monkeypatch) -> None:
    _write_repo_fixture(tmp_path)
    monkeypatch.setenv("EPIDEMIC_CLI_REPO_ROOT", str(tmp_path))
    calls: list[tuple[str, dict[str, str]]] = []

    class FakeAPI:
        def safe_post(self, path: str, payload: dict[str, str] | None = None):
            calls.append((path, payload or {}))
            return type(
                "Probe",
                (),
                {
                    "ok": True,
                    "data": {"round_id": 42, "selected_agent": "guardian", "reason": "manual", "terminal": False, "stalled": False},
                    "error": "",
                },
            )()

    monkeypatch.setattr("epidemic_cli.commands.control._world_api", lambda timeout_s=60.0: FakeAPI())

    result = RUNNER.invoke(app, ["advance", "3"])

    assert result.exit_code == 0
    assert calls == [
        ("/api/world/advance", {}),
        ("/api/world/advance", {}),
        ("/api/world/advance", {}),
    ]


def test_soak_list_discovers_scripts(tmp_path: Path, monkeypatch) -> None:
    _write_repo_fixture(tmp_path)
    monkeypatch.setenv("EPIDEMIC_CLI_REPO_ROOT", str(tmp_path))

    result = RUNNER.invoke(app, ["soak", "list"])

    assert result.exit_code == 0
    assert "wallclock" in result.stdout
    assert "run_wallclock_research_validation.py" in result.stdout


def test_should_pause_on_exit_for_direct_windows_launch(monkeypatch) -> None:
    monkeypatch.setattr(cli_main.sys, "platform", "win32")
    monkeypatch.setattr(cli_main.sys, "frozen", True, raising=False)
    monkeypatch.setattr(cli_main, "_console_process_count", lambda: 1)

    assert cli_main.should_pause_on_exit(["epidemic.exe"]) is True


def test_should_not_pause_on_exit_from_shell(monkeypatch) -> None:
    monkeypatch.setattr(cli_main.sys, "platform", "win32")
    monkeypatch.setattr(cli_main.sys, "frozen", True, raising=False)
    monkeypatch.setattr(cli_main, "_console_process_count", lambda: 2)

    assert cli_main.should_pause_on_exit(["epidemic.exe"]) is False


def test_should_launch_control_center_for_frozen_no_args(monkeypatch) -> None:
    monkeypatch.setattr(cli_main.sys, "frozen", True, raising=False)

    assert cli_main.should_launch_control_center(["epidemic.exe"]) is True


def test_should_launch_control_center_for_python_no_args() -> None:
    assert cli_main.should_launch_control_center(["epidemic_cli"]) is True


def test_should_not_launch_control_center_when_args_present(monkeypatch) -> None:
    monkeypatch.setattr(cli_main.sys, "frozen", True, raising=False)

    assert cli_main.should_launch_control_center(["epidemic.exe", "status"]) is False


def test_control_center_accepts_text_aliases() -> None:
    assert control_center._parse_command("Status") == ("status", [])
    assert control_center._parse_command("clear") == ("clear", [])
    assert control_center._parse_command("open dashboard") == ("dashboard", [])
    assert control_center._parse_command("start stack") == ("up", [])
    assert control_center._parse_command("start simulation") == ("simulate", [])


def test_control_center_logs_argument_parsing() -> None:
    assert control_center._parse_logs_args([]) == ("all", 80)
    assert control_center._parse_logs_args(["orchestrator"]) == ("orchestrator", 80)
    assert control_center._parse_logs_args(["120"]) == ("all", 120)
    assert control_center._parse_logs_args(["redis", "25"]) == ("redis", 25)


def test_compose_ps_formats_port_publishers() -> None:
    publishers = [
        {"PublishedPort": 8000, "TargetPort": 8000, "Protocol": "tcp"},
        {"PublishedPort": 6379, "TargetPort": 6379, "Protocol": "tcp"},
        {"PublishedPort": 8000, "TargetPort": 8000, "Protocol": "tcp"},
    ]

    assert "8000->8000/tcp" in stack._format_ports(publishers)
    assert "6379->6379/tcp" in stack._format_ports(publishers)
