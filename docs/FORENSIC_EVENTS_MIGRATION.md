# Forensic event fields (Patch 1 migration notes)

## Summary

Orchestrator ingest now assigns **stable identity and correlation** to every event read from the Redis `events_stream` before writing JSONL/SQLite. Legacy field **`event`** is unchanged; **`event_type`** mirrors it for consumers that expect that name.

## Environment

| Variable | Purpose |
|----------|---------|
| `EPIDEMIC_RUN_ID` | Optional. If set, used as the run identifier prefix for all `event_id` values for this process. If unset, a value is generated at import/startup: `run_YYYYMMDDTHHMMSS_<10 hex chars>` (UTC, no colons in the id). |

Logs include a startup line: `epidemic_run_id=...`.

## New and normalized fields (JSONL)

| Field | Description |
|-------|-------------|
| `event_id` | `{run_id}:{redis_stream_message_id}` — collision-safe for stream-backed events. |
| `run_id` | Logical simulation run for this orchestrator process (or from env). |
| `event_type` | Same string as `event`. |
| `agent_id` | Emitting agent: `agent_id` if set, else `src`. |
| `attack_id` | From `metadata.attempt_id`, `metadata.attack_id`, or top-level `attempt_id`. |
| `campaign_id`, `injection_id` | Promoted to top-level when present in metadata or top-level. |
| `strain_id` | Present when set in metadata (strain model lands in Patch 2). |
| `payload_hash` | Promoted to top-level when present in metadata or top-level. |
| `kill_chain_stage` | Filled at ingest via `resolve_kill_chain_stage` when not already set. |
| `parent_event_id` | Set when known (e.g. C2 re-emits chained to the triggering ingest event). |
| `correlation` | Object: `schema_version`, `run_id`, `stream_message_id`, `trace_id`, optional `campaign_id`, `injection_id`, `parent_event_id`, etc. |
| `logger_ts` | Unchanged: UTC ISO8601 when the orchestrator logger accepted the event. |

## Metadata mirrors (SIEM)

Selected forensic fields are also copied into **`metadata`** when missing there, so structured SIEM queries using `json_extract(metadata, '$.run_id')` (and aliases `run_id`, `parent_event_id`, `strain_id`, `attack_id`, `event_id`, `trace_id`, `stream_message_id` in `METADATA_ALIASES`) work without a SIEM schema migration.

## C2 parent chaining

When the C2 engine emits to the same Redis stream, **`parent_event_id`** defaults to the **`event_id` of the stream message** currently being processed (or the last message in the batch during `tick()`), via a context variable. Override by setting `parent_event_id` on the payload before emit.

## Backward compatibility

- Existing consumers should keep reading **`event`**.
- Historical JSONL lines without `event_id` remain valid; importers may use fallback ids.
- Primary SQLite `events` table schema is unchanged in Patch 1; full forensic rows live in JSONL.

## JSONL-first tracing

To reconstruct a kill chain from JSONL alone:

1. Index rows by `event_id`.
2. Follow `parent_event_id` / `correlation.trace_id` / `injection_id` / `campaign_id`.
3. Group payload-bearing rows by `payload_hash` and `strain_id` (when populated).
