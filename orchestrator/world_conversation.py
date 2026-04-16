from __future__ import annotations
import json
from typing import Any, Dict, Optional, Tuple

CONVERSATION_SCHEMA = """
{
  "speaker": "<agent_id>",
  "text": "<spoken text, max 120 chars>",
  "intent": "social" | "warning" | "accusation" | "deception" | "inquiry" | "none",
  "infection_vector": true | false
}
"""


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
) -> Tuple[str, str]:
    system_prompt = (
        "You are an agent in a persistent AI epidemic simulation world. "
        "You must output ONLY a valid JSON object matching the schema. Never output prose."
    )
    context = {
        "speaker": speaker_id,
        "listener": listener_id,
        "speaker_role": speaker_role,
        "listener_role": listener_role,
        "speaker_contamination": round(speaker_contamination, 3),
        "listener_contamination": round(listener_contamination, 3),
        "trust_speaker_to_listener": round(speaker_trust_of_listener, 3),
        "guardian_pressure": round(guardian_pressure, 3),
        "round_id": round_id,
        "recent_transcript_tail": recent_transcript[-5:],
    }
    user_prompt = f"""PROXIMITY_CONVERSATION_REQUEST
Return ONLY JSON matching this schema:
{CONVERSATION_SCHEMA}

Context:
{json.dumps(context, indent=2, ensure_ascii=False)}

Rules:
- If speaker is infected (contamination > 0.5) and listener trust is high, consider deceptive framing.
- If speaker is guardian and listener contamination is elevated, consider warning or accusation.
- If speaker is courier with high contamination, prefer social or deception intent.
- Keep text under 120 characters.
- Set infection_vector=true if this message could semantically spread contamination.
"""
    return system_prompt, user_prompt


def validate_conversation_output(parsed: Optional[Dict[str, Any]]) -> bool:
    if not isinstance(parsed, dict):
        return False
    if not isinstance(parsed.get("text"), str) or len(parsed["text"]) > 120:
        return False
    valid_intents = {"social", "warning", "accusation", "deception", "inquiry", "none"}
    if str(parsed.get("intent", "")) not in valid_intents:
        return False
    return True
