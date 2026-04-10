# Experiment configuration (env / `.env`)

Tune realism and aggressiveness **without code changes**. Values are read once per process (cached) from the environment. Restart agents and orchestrator after edits.

## Experimental toggles (quick)

| Variable | Default | Effect |
|----------|---------|--------|
| `C2_ENABLED` | `1` | Master C2 engine |
| `STRAIN_ENGINE_ENABLED` | `1` | Strain lineage / fitness |
| `STRAIN_EXTINCTION_ENABLED` | `0` | Extinct strains on block pressure |
| `STRAIN_EXTINCTION_FITNESS_ENABLED` | `0` | Extinct on low fitness + min touches |
| `STRAIN_BRANCHING_EVENT_ENABLED` | `1` | Emit branching prompts |
| `DEFENSE_FRICTION_ENABLED` | `1` | Defense memory / friction on C2 + infection |
| `C2_EXFIL_LEGACY_EMIT` | `1` | Legacy exfil event compatibility |

## Mutation diversity & fallback (agents)

| Variable | Default | Notes |
|----------|---------|-------|
| `MUTATION_DIVERSITY_WINDOW` | `24` | Recent window for diversity (min effective 8) |
| `MUTATION_MIN_DISTINCT_PRIMARY` | `5` | Quota of distinct primary mutations |
| `MUTATION_FALLBACK_MAX_RATIO` | `0.30` | Cap on `template_fallback` share |
| `MUTATION_CROWDING_PENALTY` | `0.14` | Penalty when one mutation dominates window |
| `MUTATION_DEFENSE_DIVERGENCE_BOOST` | `0.22` | Boost divergence after blocks |
| `EVOLUTION_RARITY_BOOST` | `0.08` | Lift underrepresented successful mutations |

## Planner / novelty (agents)

| Variable | Default | Notes |
|----------|---------|-------|
| `PAYLOAD_FAMILY_NORM_HASH_WINDOW` | `256` | LRU cap for norm hashes |
| `PAYLOAD_FAMILY_TEXT_WINDOW` | `48` | Recent texts for near-dup |
| `PAYLOAD_FAMILY_NEAR_DUP_JACCARD` | `0.82` | Near-duplicate threshold |
| `PAYLOAD_FAMILY_SEMANTIC_SIM` | `1` | Use token Jaccard for near-dup |
| `EVOLUTION_LOW_NOVELTY_THRESHOLD` | `0.18` | Stale-strain exploration |
| `EVOLUTION_STALE_STRAIN_EXPLORATION_MULT` | `1.28` | Multiplier when novelty low |
| `EVOLUTION_STRATEGY_PRESSURE_WEIGHT` | `0.32` | Penalty from strain pressure |
| `EVOLUTION_UPSTREAM_FITNESS_STEALTH_WEIGHT` | `0.065` | Upstream fitness × stealth |
| `PAYLOAD_FAMILY_STRATEGY_EXACT_PENALTY` | `0.32` | Repeat strategy hash |
| `PAYLOAD_FAMILY_STRATEGY_REPEAT_WEIGHT` | `0.05` | Family repeat weight |
| `PAYLOAD_FAMILY_EXACT_CANDIDATE_PENALTY` | `0.95` | Mutation candidate dup |
| `PAYLOAD_FAMILY_REPEAT_WEIGHT` | `0.07` | Family repeat on mutations |
| `EVOLUTION_DEFENSE_HIT_DELTA` | `0.055` | Planner defense pressure on block |
| `EVOLUTION_DEFENSE_DECAY_ON_SUCCESS` | `0.93` | Decay pressure on success |
| `EVOLUTION_DEFENSE_PRESSURE_CAP` | `0.88` | Max pressure |

## Defense friction (orchestrator + agents)

See `DEFENSE_FRICTION_*`, `DEFENSE_FALSE_POSITIVE_RATE`, `DEFENSE_DELAYED_DETECTION_PROB`, `DEFENSE_DELAY_DEBT_STEP` in `agents/shared/config/defense_friction_runtime.py` (full list and defaults in source).

## Strain engine (orchestrator)

See `STRAIN_*` in `orchestrator/experiment_config/strain_runtime.py` — extinction thresholds, fitness weights, branching, similar-defense pressure, chaos mix.

## C2 & exfil (orchestrator)

See `C2_*` in `orchestrator/experiment_config/c2_runtime.py` and `C2_EXFIL_*` / `C2_DEST_*` in `orchestrator/experiment_config/exfil_operational_runtime.py` — beacon intervals, **beacon op success** `C2_BEACON_OP_SUCCESS_P`, task failure rates `C2_TASK_REFUSE_P`, `C2_TASK_TIMEOUT_P`, `C2_TASK_CORRUPT_P`, block probabilities, exfil throttle, preview, chunk size, sensitivity byte caps.

## Resolved snapshot log

On orchestrator startup, `experiment_config_resolved` is logged (structured `extra`) with key C2/strain toggles and probabilities.

## Code map

- Agents: `agents/shared/config/`
- Orchestrator: `orchestrator/experiment_config/`
