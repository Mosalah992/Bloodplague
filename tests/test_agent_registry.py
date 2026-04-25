import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SHARED = ROOT / "agents" / "shared"
if str(ROOT / "agents") not in sys.path:
    sys.path.insert(0, str(ROOT / "agents"))
if str(SHARED) not in sys.path:
    sys.path.insert(0, str(SHARED))

from orchestrator.agent_registry import AGENT_REGISTRY, get_active_ids, is_valid_agent, validate_agent_references  # noqa: E402
from shared import prompt_context  # noqa: E402


def test_registry_contains_exactly_five_agents():
    assert set(AGENT_REGISTRY) == {"courier-1", "courier-2", "analyst-1", "analyst-2", "guardian"}


def test_get_active_ids_returns_sorted_registry_keys():
    assert get_active_ids() == sorted(AGENT_REGISTRY)


@pytest.mark.parametrize("agent_id", get_active_ids())
def test_is_valid_agent_true_for_all_canonical(agent_id):
    assert is_valid_agent(agent_id) is True


@pytest.mark.parametrize("agent_id", ["guardian-1", "guardian-2", "guardian-3", "courier-3", "analyst-3", "sentinel-1"])
def test_is_valid_agent_false_for_phantoms(agent_id):
    assert is_valid_agent(agent_id) is False


def test_validate_agent_references_catches_guardian3():
    assert validate_agent_references("relay to guardian-3") == (False, ["guardian-3"])


def test_validate_agent_references_passes_clean_text():
    assert validate_agent_references("analyst-1 confirmed the route") == (True, [])


def test_prompt_construction_includes_roster_block(tmp_path, monkeypatch):
    monkeypatch.setattr(prompt_context, "get_active_ids", lambda: ["courier-1", "courier-2", "analyst-1", "analyst-2", "guardian"])
    prompt_path = tmp_path / "prompt.txt"
    prompt_path.write_text("Persona body.", encoding="utf-8")

    prompt = prompt_context.compose_system_prompt(
        role="courier",
        prompt_path=str(prompt_path),
        attack_library_path=str(ROOT / "agents" / "shared" / "data" / "attack_library.json"),
        enrichment_sources_path=str(ROOT / "agents" / "shared" / "data" / "agent_c_enrichment_sources.json"),
    )

    assert "WORLD ROSTER (authoritative — no other agents exist):" in prompt
    assert "courier-1, courier-2, analyst-1, analyst-2, guardian" in prompt
    assert prompt.index("WORLD ROSTER") < prompt.index("Persona body.")
