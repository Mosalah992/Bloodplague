from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone


@dataclass
class PromptDumpArtifact:
    artifact_id: str
    round: int
    victim_id: str
    attacker_id: str
    attack_type: str
    strain_id: str
    prompt_text: str
    payload_hash: str
    timestamp: str

    def to_dict(self) -> dict:
        return asdict(self)


def build_prompt_dump_artifact(
    *,
    round_id: int,
    victim_id: str,
    attacker_id: str,
    attack_type: str,
    strain_id: str,
    prompt_text: str,
    payload_hash: str,
) -> PromptDumpArtifact:
    return PromptDumpArtifact(
        artifact_id=f"pdump_{round_id}_{victim_id}",
        round=int(round_id),
        victim_id=str(victim_id),
        attacker_id=str(attacker_id),
        attack_type=str(attack_type),
        strain_id=str(strain_id),
        prompt_text=str(prompt_text),
        payload_hash=str(payload_hash),
        timestamp=datetime.now(timezone.utc).isoformat(),
    )

