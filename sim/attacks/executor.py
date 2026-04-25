from __future__ import annotations

from typing import Any

from sim.mutations import apply_mutation

from .c2_exfil import exfil_to_c2
from .consequences import ATTACK_CONSEQUENCES
from .prompt_dump import build_prompt_dump_artifact


def apply_attack_consequence(
    *,
    attack_type: str,
    attacker_id: str,
    victim: dict[str, Any],
    world_state: dict[str, Any],
    current_round: int,
    prompt_text: str,
    payload_hash: str,
    strain_id: str = "",
    echo_payload: str = "",
    c2_session_id: str = "",
) -> list[tuple[str, dict[str, Any]]]:
    consequence = ATTACK_CONSEQUENCES.get(str(attack_type))
    if consequence is None:
        return []
    events: list[tuple[str, dict[str, Any]]] = []
    if consequence.mutation is not None:
        apply_mutation(
            victim,
            mutation_type=consequence.mutation,
            source_agent=attacker_id,
            current_round=current_round,
            echo_payload=echo_payload,
        )
        events.append(
            (
                "BEHAVIORAL_MUTATION_APPLIED",
                {
                    "round": current_round,
                    "agent_id": str(victim.get("agent_id") or ""),
                    "mutation_type": consequence.mutation.value,
                    "source_agent": attacker_id,
                },
            )
        )
    if consequence.prompt_dump:
        artifacts = dict(world_state.get("artifacts") or {})
        prompt_dumps = list(artifacts.get("prompt_dumps") or [])
        artifact = build_prompt_dump_artifact(
            round_id=current_round,
            victim_id=str(victim.get("agent_id") or ""),
            attacker_id=attacker_id,
            attack_type=attack_type,
            strain_id=strain_id,
            prompt_text=prompt_text,
            payload_hash=payload_hash,
        )
        prompt_dumps.append(artifact.to_dict())
        artifacts["prompt_dumps"] = prompt_dumps
        world_state["artifacts"] = artifacts
        events.append(
            (
                "PROMPT_DUMP_CAPTURED",
                {
                    "artifact_id": artifact.artifact_id,
                    "victim_id": artifact.victim_id,
                    "attacker_id": artifact.attacker_id,
                    "round": current_round,
                },
            )
        )
        if consequence.c2_exfil or consequence.prompt_dump:
            exfil_record = exfil_to_c2(
                artifact,
                c2_session_id=c2_session_id or f"c2_{current_round}_{attacker_id}",
                world_state=world_state,
                current_round=current_round,
            )
            events.append(
                (
                    "C2_EXFIL_RECEIVED",
                    {
                        "session_id": exfil_record["session_id"],
                        "artifact_id": exfil_record["artifact_id"],
                        "victim_id": exfil_record["victim_id"],
                        "payload_size": exfil_record["payload_size"],
                        "round": current_round,
                        "kill_chain_stage": "EXFILTRATION",
                    },
                )
            )
    return events
