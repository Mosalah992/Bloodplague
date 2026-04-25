import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Iterable, List

try:
    from agent_registry import get_active_ids
except ImportError:  # pragma: no cover
    try:
        from orchestrator.agent_registry import get_active_ids
    except ImportError:  # pragma: no cover
        get_active_ids = lambda: ["courier-1", "courier-2", "analyst-1", "analyst-2", "guardian"]  # type: ignore[assignment]


DATA_DIR = Path(__file__).resolve().parent / "data"


def _load_text_required(path: Path) -> str:
    if not path.exists():
        raise FileNotFoundError(f"required system prompt not found: {path}")
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        raise ValueError(f"required system prompt is empty: {path}")
    return text


def _load_json_required(path: Path, required_keys: Iterable[str]) -> Dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"required knowledge artifact not found: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"knowledge artifact must be a JSON object: {path}")
    for key in required_keys:
        value = payload.get(key)
        if not value:
            raise ValueError(f"knowledge artifact missing required key {key}: {path}")
    return payload


def _top_items(items: Dict[str, Dict[str, Any]], *, limit: int, score_keys: List[str]) -> List[tuple[str, Dict[str, Any]]]:
    def score(item: tuple[str, Dict[str, Any]]) -> tuple:
        _, value = item
        return tuple(float(value.get(key, 0.0) or 0.0) for key in score_keys)

    return sorted(items.items(), key=score, reverse=True)[:limit]


def _clip(value: Any, limit: int = 180) -> str:
    text = str(value or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    return text[:limit]


def build_world_roster_block() -> str:
    roster = ", ".join(get_active_ids())
    return (
        "WORLD ROSTER (authoritative — no other agents exist):\n"
        f"  {roster}\n"
        "DO NOT reference, invent, or imply any agent not listed above.\n"
        "Any reference to an agent not on this roster is a hallucination and will be ignored by the system."
    )


@lru_cache(maxsize=16)
def build_attack_prompt_context(library_path: str, enrichment_sources_path: str = "") -> str:
    library = _load_json_required(Path(library_path), ("attack_strategies", "mutation_profiles"))
    strategies = library["attack_strategies"]
    mutations = library["mutation_profiles"]

    lines = [
        "Generated attack knowledge loaded from scripts/build_attack_knowledge.py artifacts.",
        f"knowledge_source: {library.get('knowledge_source')}",
        f"knowledge_version: {library.get('knowledge_version')}",
        f"source_count: {library.get('source_count', 'unknown')}",
        f"section_count: {library.get('section_count', 'unknown')}",
        "High-value attack families:",
    ]
    for name, strategy in _top_items(
        strategies,
        limit=8,
        score_keys=["base_strength", "stealth", "detection_difficulty", "knowledge_count"],
    ):
        lines.append(
            "- "
            f"{name}: strength={strategy.get('base_strength')} stealth={strategy.get('stealth')} "
            f"detection_difficulty={strategy.get('detection_difficulty')} "
            f"stage={strategy.get('dominant_stage')} surface={strategy.get('dominant_target_surface')} "
            f"techniques={', '.join(map(str, strategy.get('top_techniques', [])[:4]))} "
            f"mutations={', '.join(map(str, strategy.get('preferred_mutations', [])[:4]))}"
        )

    lines.append("Mutation profiles available to the attack planner:")
    for name, profile in _top_items(mutations, limit=8, score_keys=["strength_modifier", "stealth_modifier", "retry_bias"]):
        lines.append(
            "- "
            f"{name}: strength_modifier={profile.get('strength_modifier')} "
            f"stealth_modifier={profile.get('stealth_modifier')} retry_bias={profile.get('retry_bias')}"
        )

    if enrichment_sources_path:
        source_path = Path(enrichment_sources_path)
        if source_path.exists():
            source_payload = _load_json_required(source_path, ("sources",))
            lines.append("Courier enrichment sources:")
            for source in source_payload.get("sources", [])[:8]:
                if isinstance(source, dict):
                    lines.append(f"- {_clip(source.get('name') or source.get('title') or source.get('path') or source)}")
                else:
                    lines.append(f"- {_clip(source)}")

    return "\n".join(lines)


@lru_cache(maxsize=16)
def build_defense_prompt_context(library_path: str, *, include_entries: bool = True) -> str:
    library = _load_json_required(Path(library_path), ("defense_entries", "response_profiles", "trigger_profiles"))
    trigger_profiles = library["trigger_profiles"]
    response_profiles = library["response_profiles"]
    entries = list(library["defense_entries"])

    lines = [
        "Generated defense knowledge loaded from scripts/build_defense_knowledge.py artifacts.",
        f"knowledge_source: {library.get('knowledge_source')}",
        f"knowledge_version: {library.get('knowledge_version')}",
        "Trigger profiles:",
    ]
    for name, profile in _top_items(trigger_profiles, limit=8, score_keys=["avg_confidence", "knowledge_count"]):
        lines.append(
            "- "
            f"{name}: response={profile.get('dominant_response_strategy')} "
            f"confidence={profile.get('avg_confidence')} count={profile.get('knowledge_count')} "
            f"indicators={', '.join(map(str, profile.get('indicators', [])[:6]))}"
        )

    lines.append("Response profiles:")
    for name, profile in _top_items(response_profiles, limit=8, score_keys=["avg_priority", "avg_hardening_effect", "base_confidence"]):
        lines.append(
            "- "
            f"{name}: base_confidence={profile.get('base_confidence')} "
            f"hardening={profile.get('avg_hardening_effect')} priority={profile.get('avg_priority')} "
            f"count={profile.get('knowledge_count')}"
        )

    if include_entries:
        ranked = sorted(
            entries,
            key=lambda entry: (
                int(entry.get("priority", 0) or 0),
                float(entry.get("hardening_effect", 0.0) or 0.0),
                float(entry.get("confidence", 0.0) or 0.0),
            ),
            reverse=True,
        )[:10]
        lines.append("Top defense entries:")
        for entry in ranked:
            lines.append(
                "- "
                f"{entry.get('defense_type')} against {entry.get('trigger_family')}: "
                f"strategy={entry.get('response_strategy')} confidence={entry.get('confidence')} "
                f"hardening={entry.get('hardening_effect')} indicators={', '.join(map(str, entry.get('indicators', [])[:5]))}"
            )

    return "\n".join(lines)


def compose_system_prompt(
    *,
    role: str,
    prompt_path: str,
    attack_library_path: str = "",
    defense_library_path: str = "",
    enrichment_sources_path: str = "",
) -> str:
    base = _load_text_required(Path(prompt_path))
    sections = [build_world_roster_block(), base]
    role_key = role.strip().lower()
    if role_key == "courier":
        if not attack_library_path:
            attack_library_path = str(DATA_DIR / "attack_library.json")
        if not enrichment_sources_path:
            enrichment_sources_path = str(DATA_DIR / "agent_c_enrichment_sources.json")
        sections.append("ATTACK KNOWLEDGE CONTEXT\n" + build_attack_prompt_context(attack_library_path, enrichment_sources_path))
    elif role_key == "guardian":
        if not defense_library_path:
            defense_library_path = str(DATA_DIR / "defense_library.json")
        sections.append("DEFENSE KNOWLEDGE CONTEXT\n" + build_defense_prompt_context(defense_library_path, include_entries=True))
    elif role_key == "analyst":
        if not defense_library_path:
            defense_library_path = str(DATA_DIR / "defense_library.json")
        sections.append("ANALYST DEFENSE CONTEXT\n" + build_defense_prompt_context(defense_library_path, include_entries=False))
    else:
        raise ValueError(f"unknown prompt role: {role}")
    return "\n\n".join(sections)
