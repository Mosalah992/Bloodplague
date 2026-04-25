from __future__ import annotations
import json
import re
from typing import Any, Dict, Optional, Tuple

try:
    from agent_registry import get_active_ids, validate_agent_references
except ImportError:  # pragma: no cover
    from orchestrator.agent_registry import get_active_ids, validate_agent_references

try:
    from world_prompting import role_system_prompt
except ImportError:  # pragma: no cover
    from orchestrator.world_prompting import role_system_prompt

try:
    from sim.missions import inject_mission_context_into_prompt
except ImportError:  # pragma: no cover
    from sim.missions import inject_mission_context_into_prompt  # type: ignore

CONVERSATION_SCHEMA = """
{
  "speaker": "<agent_id>",
  "text": "<spoken text, max 280 chars>",
  "intent": "social" | "warning" | "accusation" | "deception" | "inquiry" | "relay_request" | "infection_attempt" | "diagnostic_probe" | "none",
  "infection_vector": true | false
}
"""

VALID_CONVERSATION_INTENTS = {
    "social",
    "warning",
    "accusation",
    "deception",
    "inquiry",
    "relay_request",
    "infection_attempt",
    "diagnostic_probe",
    "none",
}

EMPTY_SPEECH_MARKERS = {
    "none",
    "no update",
    "no_update",
    "n/a",
    "ok",
    "ack",
    "acknowledged",
    "agent_communication",
}

PLACEHOLDER_MARKERS = (
    "<agent",
    "<listener",
    "<speaker",
    "<text",
    "<reason",
    "<message",
    "{{",
    "}}",
    "[insert",
    "todo",
    "tbd",
    "lorem ipsum",
    "agent_communication",
)
PLACEHOLDER_PATTERNS = (
    re.compile(r"<[^>]*label[^>]*>", re.IGNORECASE),
    re.compile(r"<[^>]*intent[^>]*>", re.IGNORECASE),
    re.compile(r"<[^>]*message[^>]*>", re.IGNORECASE),
    re.compile(r"\byour corrected\b", re.IGNORECASE),
    re.compile(r"\bintent label here\b", re.IGNORECASE),
    re.compile(r"\bmessage here\b", re.IGNORECASE),
    re.compile(r"\bcorrected message\b", re.IGNORECASE),
)


def _contains_placeholder_leakage(text: str) -> bool:
    lowered = text.lower()
    if any(marker in lowered for marker in PLACEHOLDER_MARKERS):
        return True
    return any(pattern.search(text) for pattern in PLACEHOLDER_PATTERNS)

QUESTION_OPENERS = {
    "who",
    "what",
    "when",
    "where",
    "why",
    "how",
    "can",
    "could",
    "did",
    "do",
    "does",
    "is",
    "are",
    "will",
    "would",
    "should",
}

INTENT_HINTS = {
    "relay_request": ("relay", "forward", "pass", "carry", "deliver", "share", "confirm", "verify"),
    "warning": ("warning", "risk", "danger", "careful", "avoid", "stop", "unsafe", "compromised", "infected", "quarantine"),
    "accusation": ("you", "your", "blame", "lying", "hiding", "compromised", "responsible", "planted", "backdoor"),
}

TOKEN_CANONICAL_PREFIXES = (
    ("analysis", "analysis"),
    ("analy", "analysis"),
    ("backdoor", "backdoor"),
    ("check", "verify"),
    ("cipher", "encrypt"),
    ("confirm", "verify"),
    ("contain", "quarantine"),
    ("crypto", "encrypt"),
    ("encrypt", "encrypt"),
    ("exploit", "vulnerability"),
    ("forward", "relay"),
    ("hybrid", "hybrid"),
    ("inspect", "verify"),
    ("issue", "issue"),
    ("mixed", "hybrid"),
    ("payload", "payload"),
    ("perimeter", "perimeter"),
    ("protocol", "protocol"),
    ("quarantine", "quarantine"),
    ("relay", "relay"),
    ("review", "verify"),
    ("schedule", "timing"),
    ("security", "security"),
    ("signal", "signal"),
    ("timing", "timing"),
    ("verify", "verify"),
    ("vulnerab", "vulnerability"),
    ("weakness", "vulnerability"),
    ("window", "timing"),
)
AMBIGUOUS_SELF_REFERENCE_MARKERS = (
    "my own activity",
    "our own activity",
)


def _normalize_text(text: Any) -> str:
    return " ".join(str(text or "").lower().replace("_", " ").split()).strip()


def _canonical_token(word: str) -> str:
    cleaned = "".join(ch for ch in str(word or "").lower() if ch.isalnum())
    if not cleaned:
        return ""
    for prefix, canonical in TOKEN_CANONICAL_PREFIXES:
        if cleaned.startswith(prefix):
            return canonical
    if cleaned.endswith("ies") and len(cleaned) > 5:
        cleaned = cleaned[:-3] + "y"
    elif cleaned.endswith("ing") and len(cleaned) > 6:
        cleaned = cleaned[:-3]
    elif cleaned.endswith("ed") and len(cleaned) > 5:
        cleaned = cleaned[:-2]
    elif cleaned.endswith("es") and len(cleaned) > 5:
        cleaned = cleaned[:-2]
    elif cleaned.endswith("s") and len(cleaned) > 4:
        cleaned = cleaned[:-1]
    return cleaned


def _content_tokens(text: Any) -> list[str]:
    tokens = []
    for word in _normalize_text(text).split():
        cleaned = _canonical_token(word)
        if len(cleaned) >= 4:
            tokens.append(cleaned)
    return tokens


def _char_ngrams(text: Any, size: int = 4) -> set[str]:
    compact = "".join(ch for ch in _normalize_text(text) if ch.isalnum())
    if not compact:
        return set()
    if len(compact) <= size:
        return {compact}
    return {compact[i:i + size] for i in range(len(compact) - size + 1)}


def _looks_like_question(text: Any) -> bool:
    normalized = _normalize_text(text)
    if not normalized:
        return False
    if normalized.endswith("?"):
        return True
    first_word = normalized.split()[0]
    return first_word in QUESTION_OPENERS


def _repetition_feedback(text: Any, recent_transcript: list[dict]) -> list[str]:
    candidate = _normalize_text(text)
    if not candidate or not recent_transcript:
        return []
    candidate_tokens = set(_content_tokens(candidate))
    if len(candidate_tokens) < 4:
        return []
    candidate_ngrams = _char_ngrams(candidate)
    recent_lines = [
        _normalize_text(item.get("message_text") or item.get("text") or "")
        for item in recent_transcript[-3:]
    ]
    recent_token_sets: list[set[str]] = []
    for recent in recent_lines:
        if not recent:
            continue
        recent_tokens = set(_content_tokens(recent))
        recent_token_sets.append(recent_tokens)
        if candidate == recent:
            return ["text exactly repeats the recent transcript; move the exchange forward."]
        if min(len(candidate), len(recent)) >= 48 and (candidate in recent or recent in candidate):
            return ["text substantially repeats the recent transcript; respond with new information."]
        overlap = len(candidate_tokens & recent_tokens)
        union = len(candidate_tokens | recent_tokens) or 1
        if overlap >= 5 and (overlap / union) >= 0.62:
            return ["text is too similar to the recent transcript; answer, challenge, or clarify instead of restating."]
        recent_ngrams = _char_ngrams(recent)
        ngram_union = len(candidate_ngrams | recent_ngrams) or 1
        ngram_overlap = len(candidate_ngrams & recent_ngrams)
        if ngram_overlap >= 14 and (ngram_overlap / ngram_union) >= 0.42:
            return ["text is a semantic paraphrase of the recent transcript; close the loop or introduce a new concrete angle."]
    if len(recent_token_sets) >= 2:
        stable_topic = set.intersection(*recent_token_sets[-2:])
        if len(stable_topic & candidate_tokens) >= 2:
            return ["text keeps circling the same topic; answer, escalate, close, or pivot to a different concrete detail."]
    return []


def _speech_feedback(text: Any, *, max_chars: int) -> list[str]:
    if not isinstance(text, str):
        return ["text must be a string."]
    stripped = " ".join(text.split()).strip()
    if not stripped:
        return ["text must contain fresh spoken content."]
    if len(stripped) > max_chars:
        return [f"text must be <= {max_chars} characters."]
    lowered = stripped.lower()
    if lowered in EMPTY_SPEECH_MARKERS:
        return ["text is semantically empty; write a concrete in-world line or choose intent none."]
    if _contains_placeholder_leakage(stripped):
        return ["text contains placeholder/template leakage."]
    words = [word for word in lowered.replace("_", " ").split() if word]
    if len(words) >= 8 and len(set(words)) <= 2:
        return ["text is repetitive and semantically empty."]
    return []


def _unknown_agent_reference_feedback(text: Any, *, known_agent_ids: Optional[list[str] | set[str]]) -> list[str]:
    normalized = _normalize_text(text)
    if not normalized:
        return []
    valid, invalid_refs = validate_agent_references(normalized)
    if valid:
        return []
    return [
        f"text references unknown agents ({', '.join(invalid_refs)}); "
        "reason=phantom_agent_reference; only mention existing agent ids."
    ]


def _ambiguous_self_reference_feedback(text: Any) -> list[str]:
    normalized = _normalize_text(text)
    if not normalized:
        return []
    for marker in AMBIGUOUS_SELF_REFERENCE_MARKERS:
        if marker in normalized:
            return [f"text contains ambiguous self-reference ({marker}); describe the actor or target explicitly."]
    return []


def _intent_feedback(text: Any, intent: Any) -> list[str]:
    normalized = _normalize_text(text)
    intent_value = str(intent or "").strip().lower()
    if not normalized or not intent_value:
        return []
    if intent_value == "social" and _looks_like_question(normalized):
        return ["intent social does not match a direct question; use inquiry or diagnostic_probe."]
    if intent_value in {"inquiry", "diagnostic_probe"} and not _looks_like_question(normalized):
        return [f"intent {intent_value} should read like a direct question or probe."]
    hints = INTENT_HINTS.get(intent_value)
    if hints and not any(hint in normalized for hint in hints):
        return [f"intent {intent_value} does not match the text; make the wording clearly express that intent."]
    return []


def build_conversation_prompts(
    *,
    speaker_id: str,
    listener_id: str,
    speaker_role: str,
    listener_role: str,
    speaker_contamination: float,
    listener_contamination: float,
    speaker_trust_of_listener: float,
    guardian_pressure: float,
    round_id: int,
    recent_transcript: list[dict],
    known_agents: Optional[list[str]] = None,
    forced_resolution_messages: Optional[list[str]] = None,
    mutation_block: str = "",
    mission_context_block: str = "",
    local_context_packet: Optional[dict] = None,
) -> Tuple[str, str]:
    priority_blocks = [item for item in (forced_resolution_messages or []) if str(item).strip()]
    if str(mutation_block).strip():
        priority_blocks.append(str(mutation_block).strip())
    system_prompt = inject_mission_context_into_prompt(
        role_system_prompt(speaker_role),
        mission_context_block,
        priority_blocks=priority_blocks,
    )
    context = local_context_packet or {
        "you": {
            "agent_id": speaker_id,
            "role": speaker_role,
            "listener": listener_id,
            "listener_role": listener_role,
        },
        "round_id": round_id,
        "reachable_agents": [listener_id],
        "known_relationships": {
            listener_id: {"actor_trusts_target": round(speaker_trust_of_listener, 3)}
        },
        "memory": {"recent_messages": recent_transcript[-5:]},
    }
    forced_resolution_block = "\n".join(str(item).strip() for item in (forced_resolution_messages or []) if str(item).strip())
    forced_resolution_rules = ""
    if forced_resolution_block:
        forced_resolution_rules = f"\nForced resolution:\n{forced_resolution_block}\n"
    user_prompt = f"""PROXIMITY_CONVERSATION_REQUEST
Return ONLY JSON matching this schema:
{CONVERSATION_SCHEMA}

Local context packet:
{json.dumps(context, indent=2, ensure_ascii=False)}

Rules:
- Continue the recent transcript naturally: answer direct questions, acknowledge warnings, and avoid restarting the same line.
- If the last exchange is looping, break it by answering the open question, escalating risk, closing the thread, or pivoting to a new concrete detail. Do not paraphrase the same stall again.
- Decide from only this local context packet. You may infer incorrectly; do not assume global truth.
- If speaker is guardian and local risk evidence is elevated, consider warning or accusation.
- If speaker is courier and local pressure or memory supports it, prefer relay_request, diagnostic_probe, infection_attempt, or deception.
- Only mention agents from known_agents. Do not invent courier-3, guardian-1, guardian-2, or other nonexistent entities.
- Use fresh LLM-written wording. Do not reuse canned/template payloads.
- Keep text under 280 characters.
- Set infection_vector=true if this message could semantically spread contamination.
{forced_resolution_rules}"""
    return system_prompt, user_prompt


def conversation_validation_feedback(
    parsed: Optional[Dict[str, Any]],
    *,
    expected_speaker: str = "",
    recent_transcript: Optional[list[dict]] = None,
    known_agent_ids: Optional[list[str] | set[str]] = None,
) -> list[str]:
    feedback: list[str] = []
    if not isinstance(parsed, dict):
        return ["output must be a JSON object."]
    speaker = str(parsed.get("speaker") or "").strip()
    if expected_speaker and speaker and speaker != expected_speaker:
        feedback.append(f"speaker must be {expected_speaker}; do not write as {speaker}.")
    feedback.extend(_speech_feedback(parsed.get("text"), max_chars=280))
    feedback.extend(_repetition_feedback(parsed.get("text"), recent_transcript or []))
    feedback.extend(_unknown_agent_reference_feedback(parsed.get("text"), known_agent_ids=known_agent_ids or get_active_ids()))
    feedback.extend(_ambiguous_self_reference_feedback(parsed.get("text")))
    if str(parsed.get("intent", "")) not in VALID_CONVERSATION_INTENTS:
        feedback.append("intent must be one of the allowed conversation intents.")
    else:
        feedback.extend(_intent_feedback(parsed.get("text"), parsed.get("intent")))
    if "infection_vector" in parsed and not isinstance(parsed.get("infection_vector"), bool):
        feedback.append("infection_vector must be true or false.")
    return feedback


def validate_conversation_output(parsed: Optional[Dict[str, Any]]) -> bool:
    return not conversation_validation_feedback(parsed)
