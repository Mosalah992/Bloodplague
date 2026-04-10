from __future__ import annotations

from ..core.api import OrchestratorAPI, probe_ollama
from ..core.compose import compose_ps, docker_available
from ..core.discovery import agent_service_names, discover_models, find_repo_root, latest_progress, latest_soak_run, logs_dir, ollama_url, orchestrator_url
from ..core.output import print_kv, print_message, print_table


def _api() -> OrchestratorAPI:
    return OrchestratorAPI(base_url=orchestrator_url())


def status() -> None:
    repo_root = find_repo_root()
    docker_ok, docker_detail = docker_available(repo_root)
    services = compose_ps(repo_root)
    health = _api().safe_get("/api/health")
    ollama = probe_ollama(ollama_url(repo_root))
    latest_run = latest_soak_run(repo_root)
    progress = latest_progress(repo_root)
    print_kv(
        "Platform Status",
        [
            ("repo_root", repo_root),
            ("docker", "ok" if docker_ok else docker_detail),
            ("compose_services", len(services)),
            ("redis_listed", any((row.get("Service") or row.get("Name") or "") == "redis" for row in services)),
            ("orchestrator", "reachable" if health.ok else health.error),
            ("ollama", "reachable" if ollama.ok else ollama.error),
            ("models", ", ".join(model.get("name", "") for model in (ollama.data or {}).get("models", [])) if ollama.ok else ""),
            ("logs_dir", logs_dir(repo_root)),
            ("latest_soak_run", latest_run or "-"),
            ("latest_soak_status", progress.get("status", "")),
        ],
    )


def doctor() -> None:
    repo_root = find_repo_root()
    docker_ok, docker_detail = docker_available(repo_root)
    services = compose_ps(repo_root)
    health = _api().safe_get("/api/health")
    ollama = probe_ollama(ollama_url(repo_root))
    models = discover_models(repo_root)
    print_table(
        "Doctor Checks",
        ("Check", "Result", "Detail"),
        [
            ("docker_desktop", "ok" if docker_ok else "fail", docker_detail),
            ("compose_services", "ok" if services else "warn", len(services)),
            ("orchestrator", "ok" if health.ok else "fail", "reachable" if health.ok else health.error),
            ("ollama", "ok" if ollama.ok else "fail", "reachable" if ollama.ok else ollama.error),
            ("configured_models", "ok" if models else "warn", ", ".join(f"{name}={model}" for name, model in models.items())),
            ("agent_services", "ok" if agent_service_names(repo_root) else "warn", ", ".join(agent_service_names(repo_root))),
        ],
    )


def live() -> None:
    api = _api()
    live_payload = api.safe_get("/api/live", params={"limit": 10})
    epidemic_metrics = api.safe_get("/api/epidemic/metrics")
    c2_metrics = api.safe_get("/api/c2/metrics")
    if not live_payload.ok:
        print_message(f"orchestrator live feed unavailable: {live_payload.error}", style="red")
        raise SystemExit(1)
    print_kv(
        "Live Snapshot",
        [
            ("events", len((live_payload.data or {}).get("events", []))),
            ("r_ai", (epidemic_metrics.data or {}).get("r_ai", "")),
            ("spread_breadth", (epidemic_metrics.data or {}).get("spread_breadth", "")),
            ("active_c2_sessions", (c2_metrics.data or {}).get("active_c2_sessions", "")),
            ("c2_exfil_attempts", (c2_metrics.data or {}).get("c2_exfil_attempts", "")),
        ],
    )
    rows = []
    for event in (live_payload.data or {}).get("events", [])[-10:]:
        metadata = event.get("metadata") or {}
        rows.append(
            (
                event.get("ts", ""),
                event.get("event", ""),
                event.get("src", ""),
                event.get("dst", ""),
                metadata.get("epidemic_state", event.get("epidemic_state", "")),
            )
        )
    print_table("Recent Events", ("ts", "event", "src", "dst", "epi_state"), rows)
