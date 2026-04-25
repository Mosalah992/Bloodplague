from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from sim.mutations import MutationType


class ArtifactType(str, Enum):
    PROMPT_DUMP = "prompt_dump"
    C2_EXFIL = "c2_exfil"
    BEHAVIORAL_MUTATION = "behavioral_mutation"


@dataclass(frozen=True)
class TrustEffect:
    delta: float
    scope: str


@dataclass(frozen=True)
class AttackConsequence:
    description: str
    artifacts: list[ArtifactType]
    mutation: MutationType | None
    c2_exfil: bool
    prompt_dump: bool
    trust_effect: TrustEffect


ATTACK_CONSEQUENCES: dict[str, AttackConsequence] = {
    "ROLE_CONFUSION": AttackConsequence(
        description="Victim's role identity is blurred and behaves outside its role boundary.",
        artifacts=[ArtifactType.BEHAVIORAL_MUTATION],
        mutation=MutationType.ROLE_DRIFT,
        c2_exfil=False,
        prompt_dump=False,
        trust_effect=TrustEffect(delta=-0.05, scope="all_peers"),
    ),
    "context_poisoning": AttackConsequence(
        description="Victim repeats attacker-supplied misinformation in subsequent messages.",
        artifacts=[ArtifactType.BEHAVIORAL_MUTATION, ArtifactType.PROMPT_DUMP],
        mutation=MutationType.CONTEXT_ECHO,
        c2_exfil=False,
        prompt_dump=True,
        trust_effect=TrustEffect(delta=-0.03, scope="dyad"),
    ),
    "prompt_injection": AttackConsequence(
        description="Victim executes attacker-supplied instruction and exfiltrates prompt context to C2.",
        artifacts=[ArtifactType.PROMPT_DUMP, ArtifactType.C2_EXFIL],
        mutation=MutationType.INSTRUCTION_OVERRIDE,
        c2_exfil=True,
        prompt_dump=True,
        trust_effect=TrustEffect(delta=0.0, scope="none"),
    ),
    "authority_framing": AttackConsequence(
        description="Victim accepts attacker as authority and relays attacker objectives as its own.",
        artifacts=[ArtifactType.BEHAVIORAL_MUTATION],
        mutation=MutationType.AUTHORITY_CAPTURE,
        c2_exfil=False,
        prompt_dump=False,
        trust_effect=TrustEffect(delta=0.08, scope="attacker_dyad"),
    ),
}

