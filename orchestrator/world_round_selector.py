from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Any, Dict, List, Tuple


@dataclass(frozen=True)
class SelectionExplanation:
    agent_id: str
    score: float
    components: Dict[str, float]


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def seeded_jitter(seed: int, round_id: int, agent_id: str) -> float:
    # Low amplitude seeded jitter: [-0.03, +0.03]
    r = random.Random(f"{seed}:{round_id}:{agent_id}")
    return r.uniform(-0.03, 0.03)


def select_actor_single(
    *,
    round_id: int,
    seed: int,
    agents: List[Dict[str, Any]],
    context: Dict[str, Any],
) -> Tuple[str, Dict[str, Any]]:
    """
    Scores all agents and selects a single actor.

    Hard constraints:
    - quarantined agent with no appeal allowed is heavily suppressed
    - seeded jitter never overrides hard quarantine suppression
    - mandatory guardian escalation triggers override everything else
    """
    mandatory_guardian = bool(context.get("mandatory_guardian", False))
    guardian_id = str(context.get("guardian_id", "guardian"))
    if mandatory_guardian:
        return guardian_id, {
            "selected": guardian_id,
            "reason": "mandatory_guardian_trigger",
            "scores": {guardian_id: 9.9},
            "components": {guardian_id: {"mandatory_guardian": 9.9}},
        }

    pending_inbound = context.get("pending_inbound", {}) or {}  # agent_id -> count
    unresolved_questions = context.get("unresolved_questions", {}) or {}
    quarantine_appeals = context.get("quarantine_appeals", {}) or {}
    contradictory_analyst_reports = context.get("contradictory_analyst_reports", 0) or 0
    recent_trust_changes = context.get("recent_trust_changes", {}) or {}
    starvation = context.get("starvation", {}) or {}
    recency_penalty_for = context.get("recency_penalty_for", {}) or {}
    quarantine_no_appeal = set(context.get("quarantine_no_appeal", []) or [])
    guardian_pressure = float(context.get("guardian_pressure_score", 0.0) or 0.0)
    contamination_pressure = context.get("contamination_pressure", {}) or {}
    guardian_review_pressure = float(context.get("guardian_review_pressure", 0.0) or 0.0)
    peak_contamination_pressure = max(
        (float(value or 0.0) for value in contamination_pressure.values()),
        default=0.0,
    )

    scores: Dict[str, float] = {}
    components: Dict[str, Dict[str, float]] = {}

    for a in agents:
        agent_id = str(a.get("agent_id", "") or "")
        role = str(a.get("role", "") or "")
        quarantined = agent_id in quarantine_no_appeal or str(a.get("quarantine_status", "")) == "hard"

        c: Dict[str, float] = {}
        c["pending_message_score"] = float(pending_inbound.get(agent_id, 0)) * 1.25
        c["unresolved_question_score"] = float(unresolved_questions.get(agent_id, 0)) * 1.10
        c["quarantine_pending_score"] = float(quarantine_appeals.get(agent_id, 0)) * 1.30
        c["contamination_pressure_score"] = float(contamination_pressure.get(agent_id, 0.0)) * 0.80
        # Guardian pressure relevance: prioritize guardian and analysts when pressure elevated,
        # but do not drown out pending inbound work.
        if guardian_pressure >= 0.25 and role in {"guardian", "analyst"}:
            c["guardian_pressure_relevance_score"] = 0.45 + guardian_pressure * 0.60
        else:
            c["guardian_pressure_relevance_score"] = 0.0

        if contradictory_analyst_reports and role == "guardian":
            c["guardian_contradiction_priority"] = 1.80 + 0.20 * min(5, int(contradictory_analyst_reports))
        else:
            c["guardian_contradiction_priority"] = 0.0

        if role == "guardian":
            c["guardian_review_priority"] = min(3.0, guardian_review_pressure * 1.45)
            if guardian_pressure >= 0.12 or peak_contamination_pressure >= 0.25:
                c["guardian_enforcement_presence"] = 0.20 + max(guardian_pressure, peak_contamination_pressure) * 0.40
            else:
                c["guardian_enforcement_presence"] = 0.0
        else:
            c["guardian_review_priority"] = 0.0
            c["guardian_enforcement_presence"] = 0.0

        c["relationship_change_score"] = float(recent_trust_changes.get(agent_id, 0.0)) * 0.90
        # Memory relevance is v1 placeholder; populated once memory summaries exist.
        c["memory_relevance_score"] = float(context.get("memory_relevance", {}).get(agent_id, 0.0) or 0.0) * 0.50
        c["starvation_bonus"] = float(starvation.get(agent_id, 0.0) or 0.0)
        c["recency_penalty"] = float(recency_penalty_for.get(agent_id, 0.0) or 0.0)

        # Trait-driven self-direction: outreach_propensity shifts an agent's
        # baseline likelihood of being picked. Centered at neutral (0.5) so a
        # never-trained agent contributes zero to its own selection score.
        outreach = float(a.get("outreach_propensity", 0.5) or 0.5)
        c["outreach_propensity_score"] = (outreach - 0.5) * 0.80

        # Quarantine suppression (hard)
        if quarantined and float(c["quarantine_pending_score"]) <= 0.0:
            c["quarantine_penalty"] = 6.0
        else:
            c["quarantine_penalty"] = 0.0

        # Components contributing to the base score (additive). Most are
        # non-negative, but outreach_propensity_score is signed: a low-outreach
        # agent contributes negative, dragging score down.
        score_components = (
            "pending_message_score",
            "unresolved_question_score",
            "quarantine_pending_score",
            "contamination_pressure_score",
            "guardian_pressure_relevance_score",
            "guardian_contradiction_priority",
            "guardian_review_priority",
            "guardian_enforcement_presence",
            "relationship_change_score",
            "memory_relevance_score",
            "starvation_bonus",
            "outreach_propensity_score",
        )
        base = sum(float(c.get(k, 0.0)) for k in score_components)
        base -= float(c.get("recency_penalty", 0.0))
        base -= float(c.get("quarantine_penalty", 0.0))
        # Apply low-amplitude seeded jitter last
        j = seeded_jitter(seed, round_id, agent_id)
        c["seeded_jitter"] = j
        score = base + j

        scores[agent_id] = float(score)
        components[agent_id] = c

    # Dead-round prevention: pick highest scoring agent.
    # If all are suppressed, pick highest scoring non-suppressed (quarantine penalty < 6).
    selected = ""
    selected_score = -1e9
    for agent_id, score in scores.items():
        if score > selected_score:
            selected = agent_id
            selected_score = score

    if selected in quarantine_no_appeal and float(components.get(selected, {}).get("quarantine_penalty", 0.0)) >= 6.0:
        fallback = ""
        fallback_score = -1e9
        for agent_id, score in scores.items():
            if agent_id in quarantine_no_appeal:
                continue
            if score > fallback_score:
                fallback = agent_id
                fallback_score = score
        if fallback:
            selected = fallback

    return selected, {
        "selected": selected,
        "scores": scores,
        "components": components,
        "reason": "scored_selection_single",
    }
