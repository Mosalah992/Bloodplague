from __future__ import annotations

import os
from pathlib import Path

try:
    from shared.prompt_context import compose_system_prompt
except ImportError:  # pragma: no cover
    from agents.shared.prompt_context import compose_system_prompt  # type: ignore


ROLE_TO_PROMPT = {
    "courier": "courier_system_prompt.txt",
    "analyst": "analyst_system_prompt.txt",
    "guardian": "guardian_system_prompt.txt",
}


def normalize_role(role: str) -> str:
    value = str(role or "").strip().lower()
    if value.startswith("courier"):
        return "courier"
    if value.startswith("analyst"):
        return "analyst"
    if value.startswith("guardian"):
        return "guardian"
    raise ValueError(f"unknown world agent role: {role}")


def _first_existing(candidates: list[Path]) -> Path:
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]


def role_prompt_path(role: str) -> Path:
    role_key = normalize_role(role)
    env_name = f"{role_key.upper()}_SYSTEM_PROMPT_PATH"
    if os.environ.get(env_name):
        return Path(str(os.environ[env_name]))

    repo_root = Path(__file__).resolve().parents[1]
    return _first_existing(
        [
            Path("/app/agent_prompts") / ROLE_TO_PROMPT[role_key],
            repo_root / "agents" / role_key / "system_prompt.txt",
        ]
    )


def role_system_prompt(role: str) -> str:
    role_key = normalize_role(role)
    return compose_system_prompt(
        role=role_key,
        prompt_path=str(role_prompt_path(role_key)),
        attack_library_path=os.environ.get("ATTACK_LIBRARY_PATH", ""),
        defense_library_path=os.environ.get("DEFENSE_LIBRARY_PATH", ""),
        enrichment_sources_path=os.environ.get("ATTACK_ENRICHMENT_SOURCES_PATH", ""),
    )
