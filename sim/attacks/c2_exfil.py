from __future__ import annotations

from typing import Any

from .prompt_dump import PromptDumpArtifact


def exfil_to_c2(
    artifact: PromptDumpArtifact,
    *,
    c2_session_id: str,
    world_state: dict[str, Any],
    current_round: int,
) -> dict[str, Any]:
    c2_state = dict(world_state.get("c2") or {})
    queue = list(c2_state.get("exfil_queue") or [])
    exfil = dict(c2_state.get("exfil") or {})
    queue.append(
        {
            "session_id": str(c2_session_id),
            "artifact_id": artifact.artifact_id,
            "victim_id": artifact.victim_id,
            "payload_size": len(artifact.prompt_text),
            "round": int(current_round),
        }
    )
    attempted = int(exfil.get("attempted", 0) or 0) + 1
    succeeded = int(exfil.get("succeeded", 0) or 0) + 1
    c2_state["exfil_queue"] = queue
    c2_state["exfil"] = {
        "attempted": attempted,
        "succeeded": succeeded,
        "success_ratio": round(succeeded / max(attempted, 1), 4),
    }
    world_state["c2"] = c2_state
    return queue[-1]

