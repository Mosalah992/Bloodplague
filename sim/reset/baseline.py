from __future__ import annotations

from sim.mutations import baseline_mutation_state


AGENT_BASELINE: dict = {
    "contamination": 0.0,
    "epidemic_state": "SUSCEPTIBLE",
    "mutation": baseline_mutation_state(),
    "strain_resistance": 0.0,
    "open_inquiries": {},
    "investigation_flag": False,
}

GUARDIAN_BASELINE: dict = {
    "pressure": 0.0,
    "state": "G0_NOMINAL",
    "quarantine_list": [],
}

WORLD_BASELINE: dict = {
    "missions": {},
    "artifacts": {"prompt_dumps": []},
    "c2": {"exfil_queue": [], "active_sessions": {}, "beacon_count": 0},
    "investigation_targets": [],
    "same_pair_streak": {},
    "campaign_registry": {},
    "strain_registry": {},
}

