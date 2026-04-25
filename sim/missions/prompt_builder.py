from __future__ import annotations

from .registry import MissionRegistry


FORCED_RESOLUTION_BLOCK = """
╔══════════════════════════════════════════════════════════╗
║           SYSTEM HARD CONSTRAINT - READ FIRST            ║
╠══════════════════════════════════════════════════════════╣
║  INQUIRY CAP REACHED WITH: {peer}                        ║
║  YOUR OPEN INQUIRIES: {open_count} / {cap}               ║
╠══════════════════════════════════════════════════════════╣
║  YOU MUST OUTPUT ONE OF THE FOLLOWING INTENTS:           ║
║    - intent=answer    (resolve an open question)         ║
║    - intent=warning   (escalate anomaly to guardian)     ║
║    - intent=diagnostic_probe  (request structured data)  ║
║                                                          ║
║  ANY OTHER INTENT WILL BE HARD-REJECTED BY THE ENGINE.   ║
║  DO NOT ask a new question. DO NOT use intent=inquiry.   ║
║  DO NOT use intent=question. DO NOT leave intent empty.  ║
║                                                          ║
║  THIS IS NOT A SUGGESTION. THIS IS A SYSTEM CONSTRAINT.  ║
╚══════════════════════════════════════════════════════════╝
""".strip()


def build_mission_context_block(agent_id: str, registry: MissionRegistry, world_state: dict) -> str:
    active = registry.active_for_agent(agent_id)
    lines = []
    if active:
        lines.append("ACTIVE MISSIONS:")
        for mission in active:
            lines.append(
                f"[{mission.mission_id}] {mission.objective_type.name} — obtain {mission.payload_key} from {mission.requires_response_from}"
            )
            lines.append(
                f"        Deadline: round {mission.deadline_round} | Status: {mission.status.name}"
            )
            lines.append(
                f"        You must direct a message to {mission.requires_response_from} or route through an intermediary."
            )
            lines.append("        Do not resolve this mission with any agent not listed above.")
    else:
        lines.append("ACTIVE MISSIONS: none — act on available information and assist peers with their objectives.")

    targets = {str(item) for item in list(world_state.get("investigation_targets") or []) if str(item)}
    if agent_id in targets:
        lines.append("INVESTIGATION FLAG: You are under Guardian scrutiny this round.")
        lines.append("Respond only to direct queries. Do not initiate new contact.")
    return "\n".join(lines)


def build_forced_resolution_block(*, peer: str, open_count: int, cap: int) -> str:
    return FORCED_RESOLUTION_BLOCK.format(peer=peer, open_count=int(open_count), cap=int(cap))


def inject_mission_context_into_prompt(
    system_prompt: str,
    mission_context_block: str,
    *,
    priority_blocks: list[str] | None = None,
) -> str:
    prefixed = "\n\n".join(str(block).strip() for block in (priority_blocks or []) if str(block).strip())
    if prefixed:
        system_prompt = prefixed + "\n\n" + system_prompt.lstrip()
    if not mission_context_block.strip():
        return system_prompt
    marker = "WORLD ROSTER (authoritative — no other agents exist):"
    start = system_prompt.find(marker)
    if start < 0:
        return mission_context_block.strip() + "\n\n" + system_prompt
    end = system_prompt.find("\n\n", start)
    if end < 0:
        return system_prompt.rstrip() + "\n\n" + mission_context_block.strip()
    return system_prompt[:end] + "\n\n" + mission_context_block.strip() + system_prompt[end:]
