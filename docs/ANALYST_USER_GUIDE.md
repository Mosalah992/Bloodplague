# Analyst user guide — Epidemic Lab

This guide is for **people investigating the simulation**: SOC-style analysts, red-team observers, and researchers who need to follow attacks, defenses, and post-compromise activity without reading source code.

It is **not** a guide to the *Analyst agent* software (`analyst-1` / `analyst-2`). For agent behavior, see [README.md](../README.md) (Agent roles) and [USER_GUIDE.md](../USER_GUIDE.md).

---

## 1. What you are looking at

Epidemic Lab records a **time-ordered stream of events**: infections, blocks, mutations, LLM decisions, C2 beacons, exfil attempts, epidemic state changes, and more. Everything searchable in the UI is backed by the same **SIEM index** (normalized SQLite + APIs).

**Your main tools:**

| Tool | URL / place | Best for |
|------|-------------|----------|
| **Search** | Dashboard → **Search** tab | Historical queries, pivots, reports, soak runs |
| **Live** | Dashboard → **Live** tab | Watching the firehose in near real time |
| **Query help** | Search UI → query help / field list | Discovering valid fields and syntax |

Default dashboard: **http://localhost:8000**

---

## 2. Before your first search

1. **Confirm the stack is running** (`docker compose ps`, orchestrator up).
2. **Pick a time range** in the Search UI (e.g. *last 1h* or *all* for a quiet dev box). Narrow windows load faster.
3. **Generate activity** if the index is empty: use **Simulation** to inject, or wait for an automated soak.

If results are empty, widen the time range or run a reset + inject from the Simulation tab.

---

## 3. Mental model (one minute)

- **Agents** (`courier-1`, `analyst-1`, `guardian`, …) send messages; the orchestrator **logs each step** as an event.
- **`src` / `dst`** show who acted and who received the message (when present).
- **`injection_id`** ties many events to **one worm injection experiment**.
- **`reset_id` / `epoch`** separate runs after a full reset.
- **`campaign_id`** groups attacker-side **campaign** behavior (objectives, strategy).
- **`payload_hash`** identifies a payload; **`parent_payload_hash`** links mutations.
- **C2 / kill chain** events describe behavior **after** a node is treated as compromised in the simulation.

You rarely need all fields at once—start from an event type or an `injection_id`, then pivot.

---

## 4. Recommended workflows

### A. “What happened after I injected?”

1. Open **Search**, time range **last 15m** or **last 1h**.
2. Run: `event=INFECTION_ATTEMPT` or `event=INFECTION_SUCCESSFUL` and sort by time (newest first).
3. Pick one row → open **trace** or **related** (or use pivots on `injection_id`).
4. Optionally add: `AND injection_id=<id from row>` to narrow.

### B. “Show me blocks and defenses”

Try:

```text
event=INFECTION_BLOCKED
```

or

```text
event=DEFENSE_RESULT_EVALUATED AND defense_result=blocked
```

Then pivot on `dst`, `attack_type`, or `payload_hash`.

### C. “Follow one payload’s mutations”

1. Find an event with a `payload_hash`.
2. Use **payload lineage** / **lineage** actions in the event detail pane, or query:

```text
payload_hash=<hash>
```

Include `mutation_v` in the column set if available.

### D. “Campaign and attacker strategy”

```text
campaign_id exists
```

Open **Intelligence** sub-tabs (patterns, mutation/strategy analytics) from the Search workspace. For a single campaign, use the campaign drill-down from an event or API (`/api/campaign/{id}`).

### E. “C2 and exfil”

Quick filters **BEACON**, **EXFIL**, **C2**, or saved search **`C2_BEACONS`** / **`EXFIL_DETECT`** (names may match your UI version).

Example structured query:

```text
event=C2_BEACON OR event=C2_EXFIL
```

Then narrow by `src` or time range.

### F. “Analyze a finished soak run”

1. In Search, **load/import** the run from the runs library (or import artifacts if your UI exposes it—see `/api/runs`).
2. Set time range to **all** if the run’s timestamps are in the past.
3. Use saved searches like **`MUTATION_TRACE`** or **`KILL_CHAIN`** as starting points.

---

## 5. Search workspace tour

- **Saved searches** — Curated starting points (infections, C2, epidemic, objectives, …). Use them before writing custom queries.
- **Quick filters** — One-click subsets (INFECTION, BLOCK, BEACON, …). Combine with the query bar if needed.
- **Query modes** — **Field** mode uses the structured language; **natural** mode tries to rewrite plain English (handy for exploration, less precise).
- **Result tabs** — **Events** (rows), **Patterns**, **Statistics**, **Visualization**, **Intelligence** (aggregates and campaign-style views).
- **Event detail** — Metadata, decoded payload hints, **related events**, **trace**, **lineage**, **decision summary**, and suggested next pivots.

**Tip:** Prefer one strong filter (`injection_id=…`, `reset_id=…`, `event=…`) over many vague terms.

---

## 6. Query language (essentials)

Full reference: **[QUERY_LANGUAGE_GUIDE.txt](QUERY_LANGUAGE_GUIDE.txt)**

**Patterns:**

| You want | Example |
|----------|---------|
| Exact event type | `event=INFECTION_SUCCESSFUL` |
| Combine conditions | `event=INFECTION_BLOCKED AND dst=guardian` |
| Either/or | `event=C2_BEACON OR event=C2_TASK` |
| Negation | `NOT event=HEARTBEAT` |
| Substring | `payload contains "override"` |
| Field present | `campaign_id exists` |
| Comparison | `mutation_v>=1`, `hop_count>=2` |

Validate syntax with the in-UI **query help** / validation if available, or `GET /api/validate-query`.

---

## 7. Live tab vs Search

| | **Live** | **Search** |
|---|----------|------------|
| **Data** | Recent stream | Indexed history (and imported runs) |
| **Best for** | Demos, spot-checking | Investigations, reports, comparisons |
| **Load** | Pause filters if busy | Narrow time range |

From Live, you can often open an **investigation** scoped to a selected event—use that to jump into Search-style pivots.

---

## 8. Export and APIs (optional)

- **ZIP log export:** `GET /logs/dump` (see [USER_GUIDE.md](../USER_GUIDE.md)).
- **JSON APIs:** `GET /api/search`, `/api/trace/...`, `/api/related/...`, `/api/campaigns`, etc. (see README **API surface**).

Use APIs when automating regression checks or building external dashboards.

---

## 9. Troubleshooting (analyst view)

| Symptom | What to try |
|---------|-------------|
| No rows | Widen time range; confirm simulation ran; check `/api/health`. |
| Slow UI | Shorter time window; add `reset_id` or `injection_id`. |
| “No such field” | Open field discovery / query help—aliases differ from raw JSON paths. |
| C2 empty | Compromise + beacon path may not have fired yet; run a longer simulation. |

Operator-level fixes (Docker, Ollama, Redis) are in [USER_GUIDE.md](../USER_GUIDE.md) § Troubleshooting.

---

## 10. Glossary (short)

| Term | Meaning |
|------|---------|
| **SIEM** | Local search index + query APIs over simulation events. |
| **Trace** | Ordered slice of events linked to one investigation anchor (e.g. event id, injection, reset). |
| **Lineage** | How payloads derive from parents via hashes / mutations. |
| **Campaign** | Attacker planner grouping (objectives, strategy rotation). |
| **Kill chain** | Stage model from injection through detection (see README). |
| **Soak run** | Long wall-clock run with archived logs and reports under `logs/`. |

---

## 11. Where to go next

| Document | Use it for |
|----------|------------|
| [USER_GUIDE.md](../USER_GUIDE.md) | Starting/stopping stack, CLI, URLs |
| [QUERY_LANGUAGE_GUIDE.txt](QUERY_LANGUAGE_GUIDE.txt) | Complete query syntax |
| [EXPERIMENT_CONFIG.md](EXPERIMENT_CONFIG.md) | Tuning realism (env vars, no code) |
| [README.md](../README.md) | Architecture, API list, topology |

If you document a **repeatable investigation playbook** for your team, keep it alongside this file (e.g. `docs/playbooks/`) so analysts share one process.
