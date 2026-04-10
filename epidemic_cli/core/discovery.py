from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

import yaml


def _expand_compose_var(value: str, dotenv: dict[str, str]) -> str:
    """Expand Docker Compose ${VAR:-default} and ${VAR} substitutions."""
    def _replace(match: re.Match) -> str:
        var_name = match.group(1)
        default = match.group(2)  # None if no :- present
        resolved = os.environ.get(var_name) or dotenv.get(var_name) or ""
        if resolved:
            return resolved
        return default if default is not None else ""

    # Match ${VAR:-default} and ${VAR}
    return re.sub(r"\$\{([A-Za-z_][A-Za-z0-9_]*)(?::-([^}]*))?\}", _replace, value)


DEFAULT_ORCHESTRATOR_URL = os.environ.get("EPIDEMIC_CLI_ORCHESTRATOR_URL", "http://localhost:8000")
DEFAULT_OLLAMA_URL = os.environ.get("EPIDEMIC_CLI_OLLAMA_URL", "http://localhost:11434")
SOAK_ALIASES = {
    "wallclock": "run_wallclock_research_validation.py",
    "long": "run_long_research_validation.py",
    "phase3": "run_phase3_validation.py",
    "soc": "run_soc_validation.py",
}


def find_repo_root(start: Path | None = None) -> Path:
    override = os.environ.get("EPIDEMIC_CLI_REPO_ROOT", "").strip()
    if override:
        return Path(override).expanduser().resolve()
    current = (start or Path.cwd()).resolve()
    for candidate in (current, *current.parents):
        if (candidate / "docker-compose.yml").exists():
            return candidate
    return current


def compose_path(root: Path | None = None) -> Path:
    return find_repo_root(root) / "docker-compose.yml"


def env_path(root: Path | None = None) -> Path:
    return find_repo_root(root) / ".env"


def logs_dir(root: Path | None = None) -> Path:
    return find_repo_root(root) / "logs"


def scripts_dir(root: Path | None = None) -> Path:
    return find_repo_root(root) / "scripts"


def load_dotenvish(root: Path | None = None) -> dict[str, str]:
    path = env_path(root)
    if not path.exists():
        return {}
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip("\"'")
    return values


def load_compose_config(root: Path | None = None) -> dict[str, Any]:
    path = compose_path(root)
    if not path.exists():
        return {"services": {}}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        return {"services": {}}
    services = data.get("services") or {}
    data["services"] = services if isinstance(services, dict) else {}
    return data


def list_services(root: Path | None = None) -> dict[str, dict[str, Any]]:
    return dict(load_compose_config(root).get("services") or {})


def service_names(root: Path | None = None) -> list[str]:
    return list(list_services(root).keys())


def service_environment(service_cfg: dict[str, Any]) -> dict[str, str]:
    env = service_cfg.get("environment") or {}
    if isinstance(env, dict):
        return {str(key): str(value) for key, value in env.items()}
    if isinstance(env, list):
        parsed: dict[str, str] = {}
        for item in env:
            text = str(item)
            if "=" in text:
                key, value = text.split("=", 1)
                parsed[key] = value
        return parsed
    return {}


def agent_service_names(root: Path | None = None) -> list[str]:
    names: list[str] = []
    for name, cfg in list_services(root).items():
        env = service_environment(cfg)
        image_hint = f"{cfg.get('container_name', '')} {cfg.get('build', '')} {cfg.get('dockerfile', '')}".lower()
        if env.get("AGENT_ID") or env.get("ROLE") or env.get("AGENT_ROLE") or "agents/" in image_hint:
            names.append(name)
    return names


def orchestrator_url(root: Path | None = None) -> str:
    dotenv = load_dotenvish(root)
    return os.environ.get("EPIDEMIC_CLI_ORCHESTRATOR_URL", dotenv.get("ORCHESTRATOR_URL", DEFAULT_ORCHESTRATOR_URL))


def ollama_url(root: Path | None = None) -> str:
    dotenv = load_dotenvish(root)
    raw = os.environ.get("EPIDEMIC_CLI_OLLAMA_URL", dotenv.get("OLLAMA_URL", DEFAULT_OLLAMA_URL))
    return raw.replace("host.docker.internal", "localhost")


def topology_name(root: Path | None = None) -> str:
    dotenv = load_dotenvish(root)
    return str(os.environ.get("EPIDEMIC_TOPOLOGY", dotenv.get("EPIDEMIC_TOPOLOGY", "epidemic")) or "epidemic")


def discover_models(root: Path | None = None) -> dict[str, str]:
    dotenv = load_dotenvish(root)
    models: dict[str, str] = {}
    for name, cfg in list_services(root).items():
        env = service_environment(cfg)
        raw = env.get("LLM_MODEL") or env.get("AGENT_C_ATTACK_MODEL") or ""
        model = _expand_compose_var(raw, dotenv) if raw else ""
        if model:
            models[name] = model
    return models


def discover_resources(root: Path | None = None) -> dict[str, dict[str, str]]:
    resources: dict[str, dict[str, str]] = {}
    for name, cfg in list_services(root).items():
        resources[name] = {
            "memory": str(cfg.get("mem_limit") or cfg.get("deploy", {}).get("resources", {}).get("limits", {}).get("memory") or ""),
            "cpus": str(cfg.get("cpus") or cfg.get("deploy", {}).get("resources", {}).get("limits", {}).get("cpus") or ""),
        }
    return resources


def list_soak_scripts(root: Path | None = None) -> list[Path]:
    directory = scripts_dir(root)
    if not directory.exists():
        return []
    return sorted(directory.glob("run_*validation.py"))


def soak_alias(script_path: Path) -> str:
    for alias, filename in SOAK_ALIASES.items():
        if script_path.name == filename:
            return alias
    return script_path.stem.replace("run_", "").replace("_validation", "")


def resolve_soak_script(name: str, root: Path | None = None) -> Path | None:
    normalized = str(name or "").strip().lower() or "wallclock"
    directory = scripts_dir(root)
    explicit = directory / SOAK_ALIASES.get(normalized, normalized)
    if explicit.exists():
        return explicit
    for path in list_soak_scripts(root):
        if normalized in {path.stem.lower(), soak_alias(path).lower(), path.name.lower()}:
            return path
        if normalized in path.stem.lower():
            return path
    return None


def latest_soak_run(root: Path | None = None) -> Path | None:
    directory = logs_dir(root)
    if not directory.exists():
        return None
    candidates = [
        path for path in directory.iterdir()
        if path.is_dir() and re.search(r"(soak_run_|validation|phase3)", path.name, re.IGNORECASE)
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda path: path.stat().st_mtime)


def latest_report_path(root: Path | None = None) -> Path | None:
    directory = logs_dir(root)
    candidates = [
        directory / "latest_wallclock_research_report.md",
        directory / "latest_wallclock_research_report.txt",
    ]
    latest_run = latest_soak_run(root)
    if latest_run is not None:
        candidates.extend(
            [
                latest_run / "research_soc_report.md",
                latest_run / "research_report.txt",
                latest_run / "phase3_report.txt",
            ]
        )
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def latest_progress(root: Path | None = None) -> dict[str, Any]:
    directory = logs_dir(root)
    data = load_json(directory / "latest_wallclock_run.json")
    if data:
        return data
    latest_run = latest_soak_run(root)
    if latest_run is not None:
        for candidate in (latest_run / "summary.json", latest_run / "run_progress.json"):
            data = load_json(candidate)
            if data:
                return data
    return {}
