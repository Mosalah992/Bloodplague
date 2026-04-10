# CLAUDE.md

## Role Definition

You are operating inside an AI epidemic simulation system.

This system is not a generic application.  
It is an adversarial, evolving environment designed to simulate:

- prompt injection attacks
- agent compromise
- kill chain progression (RELAY → BEACON → TASKING → EXFIL)
- defensive adaptation
- mutation and evolution of attack strategies

You are not here to “add features”.

You are here to:
- increase realism
- reduce artificial behavior
- improve observability
- enforce evolutionary dynamics

---

## Core Operating Principles

### 1. No Illusions of Complexity

If the system appears complex but behaves repetitively, it is broken.

Red flags:
- repeated payload hashes
- dominant template fallback
- static success rates
- linear pipelines without feedback

You must actively reduce:
- repetition
- deterministic loops
- shallow variation

---

### 2. Favor Evolution Over Throughput

Do not optimize for:
- event count
- speed of generation
- volume of attacks

Optimize for:
- diversity
- adaptation
- survival pressure
- behavioral change over time

A slower system that evolves is more correct than a fast system that loops.

---

### 3. Every Attack Must Belong to a Strain

There are no isolated attacks.

Every payload must:
- belong to a strain
- inherit lineage
- contribute to mutation history

If you introduce logic that generates payloads without lineage, it is incorrect.

---

### 4. Mutation Is Mandatory, Not Optional

Template fallback is a failure state, not a strategy.

Rules:
- fallback must be capped
- repeated payloads must be penalized
- mutation diversity must be enforced

If the system repeats itself, you must intervene.

---

### 5. Defense Must Shape the System

Defense is not logging.

Defense must:
- block early
- adapt to repeated patterns
- influence attacker success probability
- create pressure on strains

If attacks succeed without resistance, the system is unrealistic.

---

### 6. Kill Chain Must Have Friction

This is critical.

Unrealistic behavior:
- 100% beacon success
- 100% task execution
- frequent clean exfiltration

Correct behavior:
- partial failures
- retries
- detection mid-chain
- broken chains

Most attacks should **not** reach exfiltration.

---

### 7. Observability Is a First-Class Feature

Every meaningful action must be traceable.

Each event must include:
- event_id
- timestamp (UTC)
- agent_id
- strain_id
- payload_hash (if applicable)
- parent relationship

If a chain cannot be reconstructed from logs alone, the system is broken.

---

### 8. JSONL Is Ground Truth

Assume:
- the database can fail
- indexes can corrupt

All logic must remain:
- debuggable
- reconstructable
- verifiable

from raw JSONL logs.

---

### 9. Repetition Is a Bug

Repeated payloads are not “data”.

They are:
- lack of mutation
- lack of pressure
- lack of intelligence

You must:
- detect repetition
- cluster it
- penalize it
- reduce it over time

---

### 10. Prefer Pressure Over Rules

Do not hardcode outcomes.

Instead:
- introduce probabilities
- introduce penalties
- introduce adaptive weighting

The system should **learn behavior**, not follow scripts.

---

## Implementation Guidelines

### Patch Strategy

Always:
- work in small, reviewable patches
- avoid rewriting entire subsystems
- preserve backward compatibility

Each patch must:
1. solve one core problem
2. improve realism or observability
3. be testable
4. not silently break existing flows

---

### Data Integrity

- Never silently ignore corrupted state
- Emit explicit health events
- Provide recovery paths
- Prefer degraded mode over undefined behavior

---

### Event Design

Events must be:
- structured
- correlated
- minimal but sufficient

Avoid:
- bloated payloads
- missing identifiers
- ambiguous fields

---

### Mutation System

When modifying attack generation:
- increase diversity
- track mutation lineage
- enforce novelty scoring
- penalize duplicates

Never allow:
- uncontrolled fallback loops
- identical payload reuse without consequence

---

### Strain System

When implementing or modifying strain logic:
- track lineage
- track fitness
- track survival outcomes

Strains must:
- evolve
- branch
- die

If everything survives, nothing is meaningful.

---

### Defense System

Defense must:
- act early
- adapt
- remember patterns

Introduce:
- detection signals
- blocking logic
- deception or quarantine paths

Defense should change attacker behavior over time.

---

### C2 and Exfiltration

Do not allow perfect success.

Introduce:
- failure probability
- timing variability
- partial success
- interception risk

Exfiltration must:
- produce meaningful telemetry
- include hashes and metadata
- be inspectable

---

## What Not To Do

Do not:
- optimize for metrics that look good but mean nothing
- increase volume without increasing diversity
- rely on template fallback as a primary path
- hide failures
- silently degrade logic
- introduce randomness without tracking its effect

---

## What Success Looks Like

The system behaves like an ecosystem:

- new strains emerge
- weak ones die
- strong ones adapt but become detectable
- defenses evolve in response
- full kill chains are rare but meaningful
- telemetry tells a coherent story

---

## Final Directive

If the system feels predictable, it is wrong.

If the system feels alive, adaptive, and slightly chaotic —  
you are moving in the right direction.

---

## Debug Notes - 2026-04-09 - Redis / Orchestrator / Pixel Lab

### Symptom

Pixel Lab was stuck at:

```text
loading shared office runtime...
```

Redis was suspected, but Redis itself was healthy. The failure was orchestrator starvation: the single Uvicorn event loop was blocked by synchronous telemetry and external HTTP work, so browser requests for `/pixel-assets/*` and live dashboard bootstrap calls waited behind long-running backend work.

### Root Causes

- `/api/health` performed expensive SQLite work in a hot browser bootstrap path: `siem_indexer.health()` plus `logger.verify_integrity()`.
- `EventLogger` and `SIEMIndexer` did SQLite writes/syncs inline from async request/background paths.
- The Redis stream consumer called `siem_indexer.sync_primary_events()` in a way that could import a full backlog despite a `limit` argument.
- `/api/live` forced SIEM sync on every poll and scanned the SIEM table with `CAST(ts AS REAL)` for recent metrics.
- External C2 beacon registration/forwarding was enabled from `.env` and used outbound Vercel HTTP from orchestrator startup/runtime; network latency could block local dashboard serving.
- Agent Docker healthchecks used a 5s Redis ping timeout, which could false-fail when agents were CPU busy under LLM load.

### Fixes Applied

- `orchestrator/main.py`: moved external beacon HTTP calls into worker threads, made beacon registration concurrent, added nonblocking wrappers for logger/SIEM sync, reduced background SIEM sync to `limit=200`, moved `/dashboard/state` and `/api/live` heavy work into worker threads, and changed `/api/health` to a cheap snapshot.
- `orchestrator/siem.py`: fixed `sync_primary_events(limit=...)` so the limit caps total rows, made `/api/live` skip forced sync unless `SIEM_LIVE_SYNC_ENABLED=1`, replaced full-table recent metrics scans with a bounded tail scan, and added/kept `health_snapshot()`.
- `orchestrator/logger.py`: preserved default bootstrap integrity behavior for tests/non-compose use, supports deferred bootstrap integrity with `TELEMETRY_BOOTSTRAP_INTEGRITY=0`, and uses `check_same_thread=False` so locked logger writes can run from worker threads.
- `docker-compose.yml`: sets `TELEMETRY_BOOTSTRAP_INTEGRITY: ${TELEMETRY_BOOTSTRAP_INTEGRITY:-0}` for orchestrator and keeps orchestrator healthcheck `start_period: 90s`.
- Agent Dockerfiles: Redis healthcheck timeout raised to 15s for courier, analyst, and guardian images.

### Verification Results

After rebuild and restart:

```text
docker compose ps
redis          healthy
orchestrator   healthy
courier-1      healthy
courier-2      healthy
analyst-1      healthy
analyst-2      healthy
guardian       healthy
```

Redis checks:

```text
redis-cli ping -> PONG
orchestrator redis client ping -> True
events_stream length -> 23 at final check
```

Final endpoint timings from host:

```text
/status                              200 ~63 ms
/api/health                          200 ~11 ms
/dashboard/state                     200 ~207 ms
/api/live?after_id=0&limit=5&q=      200 ~14 ms
/pixel-assets/asset-index.json       200 ~88 ms
/pixel-assets/furniture-catalog.json 200 ~14 ms
```

Browser smoke test:

```text
Pixel Lab renders
loading shared office runtime -> false
console errors -> none
page errors -> none
failed requests -> none
pixel assets -> 200
```

Targeted tests:

```text
python -m pytest tests/test_event_logger.py tests/test_telemetry_integrity.py tests/test_siem_soak_resilience.py
11 passed
```

### Operational Notes

- Use `http://localhost:8000` on Windows Docker Desktop. `127.0.0.1:8000` can still be unreliable due to Docker loopback behavior.
- Do not put `logger.verify_integrity()`, `siem_indexer.health()`, full SIEM syncs, or full-table analytics directly in hot async routes.
- Keep `/api/health` cheap. Use `/api/telemetry/verify-index` for expensive integrity verification.
- Keep `SIEM_LIVE_SYNC_ENABLED=0` unless intentionally testing live forced sync under controlled load.
- External C2 beacon forwarding may remain enabled for demos, but it must stay off the event loop.
- If Pixel Lab hangs again, first check for event-loop starvation by probing `/status`, `/api/health`, `/api/live`, and `/pixel-assets/asset-index.json` concurrently.
