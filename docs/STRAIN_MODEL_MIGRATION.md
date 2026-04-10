# Strain model (Patch 2 migration notes)

## Overview

Payloads with a **`payload_hash`** are assigned a durable **`strain_id`**. Strains form a **lineage** when `metadata.parent_payload_hash` resolves to an existing strain (e.g. after mutation). State is stored primarily in **`STRAIN_DB_PATH`** (default: `{LOGS_DIR}/strains.db`); if SQLite fails integrity checks or writes, the store switches to **degraded JSONL** at **`STRAIN_JSONL_FALLBACK`** (default: `{LOGS_DIR}/strains_fallback.jsonl`) and logs at **ERROR** severity.

## Orchestrator pipeline

1. `enrich_forensic_event` (Patch 1) runs as before.
2. **`StrainEngine.observe_enriched`** runs next, mutating the same dict: sets top-level and `metadata.strain_id`, refreshes SIEM mirror keys via `merge_metadata_search_keys`.
3. `logger.log_event` persists the enriched row (JSONL carries full strain context).

`STRAIN_*` telemetry events are re-published to the Redis `events_stream` (same path as C2). They are **ignored** by the strain engine to avoid recursion.

## New event types

| Event | When |
|-------|------|
| `STRAIN_CREATED` | New root strain (no resolved parent payload hash). |
| `STRAIN_MUTATED` | New strain row linked via `parent_payload_hash` to a known strain. |
| `STRAIN_FITNESS_UPDATED` | Fitness changed by at least `STRAIN_FITNESS_EMIT_DELTA` (default `0.05`) since last emit. |
| `STRAIN_EXTINCT` | Optional; see extinction env vars. |

Each carries `parent_event_id` = triggering forensic `event_id`, plus `metadata` with counters and lineage.

## Strain record fields

Persisted per strain: `strain_id`, `parent_strain_id`, `payload_hash`, `creation_ts`, `originating_attack_type`, `mutation_lineage`, `generation`, `novelty_score`, `fitness_score`, `success_count`, `block_count`, `exfil_success_count`, `beacon_success_count`, `quarantine_count`, `last_seen_ts`, `extinct`, `last_emitted_fitness`.

Fitness is a **v0 heuristic** (success/block ratio plus small exfil/beacon bonuses and quarantine penalty); Patch 4 will deepen evolutionary pressure.

## Outcome mapping (increments)

- `INFECTION_SUCCESSFUL` → `success_count`
- `INFECTION_BLOCKED`, `BEACON_BLOCKED`, `TASK_BLOCKED`, `EXFIL_BLOCKED` → `block_count`
- `C2_EXFIL` → `exfil_success_count`
- `C2_BEACON` (when `metadata.beacon_success` is truthy) → `beacon_success_count`
- `QUARANTINE_ISSUED`, `QUARANTINE_ENFORCED` → `quarantine_count`

Events with only **`strain_id`** (no `payload_hash`) can still update counts if the strain exists and is not extinct.

## Environment variables

| Variable | Default | Purpose |
|--------|---------|---------|
| `STRAIN_ENGINE_ENABLED` | `1` | Disable all strain logic when `0`. |
| `STRAIN_DB_PATH` | `{LOGS_DIR}/strains.db` | SQLite database path. |
| `STRAIN_JSONL_FALLBACK` | `{LOGS_DIR}/strains_fallback.jsonl` | Append-only degraded store. |
| `STRAIN_EXTINCTION_ENABLED` | `0` | Enable automatic extinction. |
| `STRAIN_EXTINCTION_BLOCK_MIN` | `12` | Minimum blocks before extinction check. |
| `STRAIN_EXTINCTION_SUCCESS_MAX` | `0` | Extinct if `success_count` ≤ this while blocks ≥ min. |
| `STRAIN_FITNESS_EMIT_DELTA` | `0.05` | Min fitness delta to emit `STRAIN_FITNESS_UPDATED`. |

## Recovery

- Degraded JSONL uses **last line wins** per `strain_id` when scanning.
- `StrainStore.load_all_from_jsonl()` returns a dict suitable for rebuild tooling (future `rebuild-strains` CLI).

## Operator endpoint

- `GET /api/strain/health` — JSON with `enabled`, `degraded`, `reason`, `db_path`, `jsonl_fallback_path`.

## Backward compatibility

Events without `payload_hash` and without `strain_id` behave as before. Existing SIEM **`strain_id`** metadata alias (Patch 1) continues to apply.
