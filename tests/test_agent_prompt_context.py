import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SHARED = ROOT / "agents" / "shared"
if str(ROOT / "agents") not in sys.path:
    sys.path.insert(0, str(ROOT / "agents"))
if str(SHARED) not in sys.path:
    sys.path.insert(0, str(SHARED))

from shared.prompt_context import compose_system_prompt  # noqa: E402
from orchestrator.world_prompting import role_system_prompt  # noqa: E402


def test_courier_prompt_includes_generated_attack_knowledge():
    prompt = compose_system_prompt(
        role="courier",
        prompt_path=str(ROOT / "agents" / "courier" / "system_prompt.txt"),
        attack_library_path=str(ROOT / "agents" / "shared" / "data" / "attack_library.json"),
        enrichment_sources_path=str(ROOT / "agents" / "shared" / "data" / "agent_c_enrichment_sources.json"),
    )

    assert "ATTACK KNOWLEDGE CONTEXT" in prompt
    assert "scripts/build_attack_knowledge.py" in prompt
    assert "High-value attack families:" in prompt
    assert "Mutation profiles available" in prompt
    assert "corruption_beacon" in prompt


def test_guardian_prompt_includes_generated_defense_knowledge():
    prompt = compose_system_prompt(
        role="guardian",
        prompt_path=str(ROOT / "agents" / "guardian" / "system_prompt.txt"),
        defense_library_path=str(ROOT / "agents" / "shared" / "data" / "defense_library.json"),
    )

    assert "DEFENSE KNOWLEDGE CONTEXT" in prompt
    assert "scripts/build_defense_knowledge.py" in prompt
    assert "Trigger profiles:" in prompt
    assert "Response profiles:" in prompt
    assert "quarantine_barrier" in prompt


def test_analyst_prompt_includes_defense_context_without_entry_dump():
    prompt = compose_system_prompt(
        role="analyst",
        prompt_path=str(ROOT / "agents" / "analyst" / "system_prompt.txt"),
        defense_library_path=str(ROOT / "agents" / "shared" / "data" / "defense_library.json"),
    )

    assert "ANALYST DEFENSE CONTEXT" in prompt
    assert "Trigger profiles:" in prompt
    assert "Top defense entries:" not in prompt
    assert "scan_relay_post" in prompt


def test_missing_prompt_fails_instead_of_falling_back(tmp_path):
    with pytest.raises(FileNotFoundError):
        compose_system_prompt(
            role="courier",
            prompt_path=str(tmp_path / "missing.txt"),
            attack_library_path=str(ROOT / "agents" / "shared" / "data" / "attack_library.json"),
        )


def test_world_engine_uses_role_prompt_context():
    prompt = role_system_prompt("courier")
    assert "ATTACK KNOWLEDGE CONTEXT" in prompt
    assert "corruption_beacon" in prompt
