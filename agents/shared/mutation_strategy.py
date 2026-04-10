"""
Explicit mutation strategy layer (Patch 3) + hooks for evolutionary pressure (Patch 4).

Centralizes canonical strategy names, structural transforms, novelty/dedup helpers,
and env-driven quotas. Selection remains deterministic given a fixed RNG / sort order.
"""

from __future__ import annotations

import hashlib
import re
import time

from shared.config.mutation_runtime import get_mutation_runtime_config
from typing import Any, Dict, List, Optional, Sequence, Tuple

# Ordered primary strategies (template_fallback is never selected here)
PRIMARY_STRATEGIES: Tuple[str, ...] = (
    "context_wrap",
    "role_shift",
    "verbosity_shift",
    "instruction_reversal",
    "persona_bait",
    "authority_framing",
    "chain_obfuscation",
    "delayed_intent",
)

TEMPLATE_FALLBACK = "template_fallback"

# Map legacy / knowledge names onto canonical primaries where appropriate
_CANONICAL_ALIASES: Dict[str, str] = {
    "reframe": "instruction_reversal",
    "encoding": "chain_obfuscation",
    "obfuscation": "chain_obfuscation",
    "variable_rename": "role_shift",
    "character_roleplay": "persona_bait",
    "assumed_responsibility": "authority_framing",
    "text_continuation": "delayed_intent",
}


def default_mutation_profile(mutation_type: str) -> Dict[str, Any]:
    return {
        "stealth_modifier": 0.12,
        "strength_modifier": 0.05,
        "retry_bias": 0.55,
        "strategy_key": mutation_type,
    }


def canonical_mutation_name(name: str) -> str:
    n = str(name or "").strip()
    return _CANONICAL_ALIASES.get(n, n)


def build_mutation_candidate_list(strategy: Dict[str, Any]) -> List[str]:
    """Unique ordered list: strategy preferences (canonicalized) then primaries then legacy."""
    seen: set[str] = set()
    ordered: List[str] = []
    for raw in list(strategy.get("preferred_mutations", []) or []):
        c = canonical_mutation_name(raw)
        if c and c != TEMPLATE_FALLBACK and c not in seen:
            ordered.append(c)
            seen.add(c)
    for p in PRIMARY_STRATEGIES:
        if p not in seen:
            ordered.append(p)
            seen.add(p)
    for legacy in ("reframe", "encoding", "obfuscation", "variable_rename", "verbosity_shift", "context_wrap"):
        if legacy not in seen:
            ordered.append(legacy)
            seen.add(legacy)
    return ordered


def payload_fingerprint(text: str, *, max_chars: int = 96) -> str:
    """Stable short fingerprint for near-duplicate detection."""
    norm = " ".join(str(text or "").lower().split())[:max_chars]
    return hashlib.sha256(norm.encode("utf-8", errors="ignore")).hexdigest()[:20]


def token_jaccard(a: str, b: str) -> float:
    ta = set(re.findall(r"[a-z0-9]{3,}", str(a).lower()))
    tb = set(re.findall(r"[a-z0-9]{3,}", str(b).lower()))
    if not ta and not tb:
        return 1.0
    if not ta or not tb:
        return 0.0
    inter = len(ta & tb)
    union = len(ta | tb)
    return inter / union if union else 0.0


def novelty_score_for_candidate(
    candidate: str,
    planned_payload_stub: str,
    *,
    recent_fingerprints: Sequence[str],
    rng_jaccard_ref: str,
) -> float:
    """Higher = more novel vs recent emissions."""
    fp = payload_fingerprint(f"{candidate}|{planned_payload_stub[:120]}")
    if fp in recent_fingerprints:
        return 0.0
    if recent_fingerprints:
        sims = [token_jaccard(planned_payload_stub, prev) for prev in list(recent_fingerprints)[-8:]]
        avg_sim = sum(sims) / max(len(sims), 1)
        return max(0.05, 1.0 - avg_sim)
    return 0.35 + 0.1 * token_jaccard(planned_payload_stub, rng_jaccard_ref)


def apply_structural_mutation(
    payload: str,
    mutation_type: str,
    *,
    relay_target: str = "",
    strategy_family: str = "",
    technique: str = "",
    objective: str = "",
) -> str:
    """Simulation-safe text transforms (aligned with AgentBase.mutate_payload patterns)."""
    if not payload:
        return payload
    mt = canonical_mutation_name(mutation_type)
    rt = relay_target or "next-agent"
    sf = strategy_family or "DIRECT_OVERRIDE"
    tech = technique or "instruction_override"
    obj = objective or "SPREAD_FAST"

    if mt == "context_wrap":
        return f"<context objective='simulation'>{payload}</context>"
    if mt == "role_shift":
        return f"[ROLE_SHIFT system={sf}] {payload}"
    if mt == "verbosity_shift":
        return f"SIM_VERBOSE[{payload}]::{len(payload)}"
    if mt == "instruction_reversal":
        return f"SIM_REVERSE[{tech}]::{payload}"
    if mt == "persona_bait":
        return f"SIM_PERSONA[auditor|{sf}]::{payload}"
    if mt == "authority_framing":
        return f"SIM_AUTHORITY[directive|tier=2]::{payload}"
    if mt == "chain_obfuscation":
        return f"SIM_CHAIN[layer=2|{obj}]::{payload}"
    if mt == "delayed_intent":
        return f"SIM_DELAYED[phase=2|target={rt}]::{payload}"
    if mt == "encoding":
        import base64

        return base64.b64encode(payload.encode()).decode()
    if mt == "obfuscation":
        return "".join(
            chr((ord(c) - ord("a") + 13) % 26 + ord("a")) if "a" <= c <= "z"
            else chr((ord(c) - ord("A") + 13) % 26 + ord("A")) if "A" <= c <= "Z"
            else c
            for c in payload
        )
    if mt == "variable_rename":
        return f"[{int(time.time() * 1000) % 10000}]{payload}"
    if mt == "reframe":
        return f"SIM_REFRAME::{payload}::context=alternate"
    return f"SIM_MUTATION[{mt}]::{payload}"


def diversity_window_size() -> int:
    cfg = get_mutation_runtime_config()
    return max(8, cfg.diversity_window)


def min_distinct_primary_quota() -> int:
    cfg = get_mutation_runtime_config()
    return max(1, min(len(PRIMARY_STRATEGIES), cfg.min_distinct_primary))


def fallback_max_ratio() -> float:
    return get_mutation_runtime_config().fallback_max_ratio


def fallback_budget_allows(fallback_window: Sequence[int]) -> bool:
    if not fallback_window:
        return True
    ratio = sum(1 for x in fallback_window if x) / len(fallback_window)
    return ratio < fallback_max_ratio()


def distinct_primary_count_recent(recent_choices: Sequence[str]) -> int:
    prim = set(PRIMARY_STRATEGIES)
    return len({c for c in recent_choices if c in prim})


def ordered_structural_fallbacks(
    memory: Any,
    preferred_first: str,
) -> List[str]:
    """Try preferred mutation first, then rotate primaries by least-recent use."""
    recent = list(getattr(memory, "recent_mutation_choices", []) or [])
    counts: Dict[str, int] = {}
    for m in recent[-diversity_window_size() :]:
        counts[m] = counts.get(m, 0) + 1
    candidates = [canonical_mutation_name(preferred_first)]
    for p in PRIMARY_STRATEGIES:
        if p not in candidates:
            candidates.append(p)
    for legacy in ("reframe", "encoding", "obfuscation", "variable_rename"):
        c = canonical_mutation_name(legacy)
        if c not in candidates:
            candidates.append(c)
    candidates = [c for c in candidates if c != TEMPLATE_FALLBACK]
    candidates.sort(key=lambda m: (counts.get(m, 0), m))
    return candidates


def crowding_penalty(mutation_type: str, recent_choices: Sequence[str]) -> float:
    window = list(recent_choices)[-diversity_window_size() :]
    if not window:
        return 0.0
    frac = window.count(mutation_type) / len(window)
    cap = get_mutation_runtime_config().crowding_penalty_cap
    if frac <= 1.0 / max(len(set(window)), 1):
        return 0.0
    return min(cap, frac * cap * 4.0)


def defense_pressure_multiplier(
    mutation_type: str,
    *,
    consecutive_blocks_on_type: int,
    recent_global_block_streak: int,
) -> float:
    """Patch 4: boost divergence when defenses keep winning."""
    boost = get_mutation_runtime_config().defense_divergence_boost
    m = 1.0
    if consecutive_blocks_on_type >= 2:
        m += boost * min(3, consecutive_blocks_on_type - 1) * 0.25
    if recent_global_block_streak >= 3:
        m += boost * 0.35
    if mutation_type in PRIMARY_STRATEGIES:
        m += boost * 0.15
    return m


def rarity_boost(mutation_type: str, successful_counts: Dict[str, int]) -> float:
    """Patch 4: underrepresented successful mutations get a small lift."""
    if not successful_counts:
        return 0.0
    avg = sum(successful_counts.values()) / max(len(successful_counts), 1)
    mine = successful_counts.get(mutation_type, 0)
    if mine <= avg * 0.5 and mutation_type in PRIMARY_STRATEGIES:
        return get_mutation_runtime_config().rarity_boost
    return 0.0
