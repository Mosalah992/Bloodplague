# Mutation engine (Patch 3) and evolutionary pressure (Patch 4)

## Patch 3 — Mutation strategy layer

### Canonical strategies

Primary mutation strategies (used in planner scoring and structural recovery), in order:

`context_wrap`, `role_shift`, `verbosity_shift`, `instruction_reversal`, `persona_bait`, `authority_framing`, `chain_obfuscation`, `delayed_intent`

`template_fallback` is **never** chosen by the planner; it remains the Courier **last resort** after LLM failure when structural recovery cannot produce a novel payload.

Legacy knowledge names are **canonicalized** (e.g. `reframe` → `instruction_reversal`, `encoding` → `chain_obfuscation`). Unknown types receive a default profile from `RedTeamKnowledgeService.get_mutation_profile` (no `KeyError`).

### Selection (`KnowledgeAwareAttackPlanner.choose_mutation`)

Scores each candidate using:

- Existing knowledge / runtime weights and cooldowns  
- **Novelty** vs recent payload fingerprints  
- **Diversity quota**: boost primaries when distinct primary usage in the sliding window is below `MUTATION_MIN_DISTINCT_PRIMARY`  
- **Duplicate penalty** when `(mutation_type|planned_stub)` fingerprint matches recent hashes  
- **Crowding penalty** for over-represented types in the window (`MUTATION_CROWDING_PENALTY`)  
- **Defense pressure** multipliers when the same mutation type or global run is blocked repeatedly  

Telemetry is attached under `PlannedAttack.score_breakdown["mutation_telemetry"]`:

- `mutation_attempted`, `mutation_selected`, `mutation_rejected_duplicate`, `mutation_selection_reason`

### Courier LLM failure path

Before `template_fallback`, the Courier tries **structural recovery**: ordered strategies from `ordered_structural_fallbacks` (least-used first), emitting:

- `MUTATION_ATTEMPTED`, `MUTATION_REJECTED_DUPLICATE` (near-duplicate fingerprint), `MUTATION_SELECTED`  
- `ATTACK_PAYLOAD_VALIDATED` with `validation_tags` including `structural_mutation`  

`fallback_usage_window` tracks recent true fallbacks; `MUTATION_FALLBACK_MAX_RATIO` caps how often template fallback may dominate.

### Environment variables (Patch 3)

| Variable | Default | Role |
|---------|---------|------|
| `MUTATION_DIVERSITY_WINDOW` | `24` | Sliding window for diversity / crowding |
| `MUTATION_MIN_DISTINCT_PRIMARY` | `5` | Target distinct primaries in window |
| `MUTATION_FALLBACK_MAX_RATIO` | `0.30` | Max share of recent steps using template fallback |
| `MUTATION_CROWDING_PENALTY` | `0.14` | Strength of overuse penalty |
| `MUTATION_DEFENSE_DIVERGENCE_BOOST` | `0.22` | Extra weight under block pressure |
| `EVOLUTION_RARITY_BOOST` | `0.08` | Boost for underrepresented successful mutations |

## Patch 4 — Strain fitness and targeting pressure

### Strain fitness (`orchestrator/strain_engine.py`)

Fitness now subtracts **detectability** (block rate), **generation repetition**, optional **fast time-to-block** (`STRAIN_TTD_*`), and optional **`STRAIN_CROWDING_PENALTY`**. Weights are tunable via env (see below).

`STRAIN_*` telemetry metadata includes **`detectability_score`** and **`branching_recommended`** when a strain is both successful and noisy (heuristic for future branching / mutation pressure).

### Attacker memory

- `mutation_consecutive_blocks`, `recent_block_streak`, `successful_mutation_counts` drive defense-aware mutation multipliers and rarity boost.  
- Target scoring adds a small **mutation diversity reward** when recent mutation types are varied.

### Environment variables (Patch 4 — strain)

| Variable | Default | Role |
|---------|---------|------|
| `STRAIN_FITNESS_BASE_WEIGHT` | `0.62` | Weight on success ratio |
| `STRAIN_FITNESS_EXFIL_WEIGHT` | `0.11` | Exfil bonus |
| `STRAIN_FITNESS_BEACON_WEIGHT` | `0.018` | Beacon bonus |
| `STRAIN_FITNESS_QUARANTINE_WEIGHT` | `0.038` | Quarantine penalty |
| `STRAIN_DETECTABILITY_MULT` | `0.22` | Block-rate penalty scale |
| `STRAIN_DETECTABILITY_CAP` | `0.18` | Cap on detectability penalty |
| `STRAIN_REPETITION_GEN_PEN` | `0.025` | Penalty per generation above 2 |
| `STRAIN_TTD_FAST_DETECT_S` | `12` | “Fast detection” window (seconds) |
| `STRAIN_TTD_PENALTY` | `0.055` | Penalty if blocked quickly |
| `STRAIN_CROWDING_PENALTY` | `0` | Optional global subtraction |

## Backward compatibility

- `mutation_type` on events remains the primary field; new telemetry is additive.  
- LLM-validated payloads still use `mutation_type=llm_generated`.  
- Template fallback behavior is unchanged when structural recovery is exhausted or over budget.
