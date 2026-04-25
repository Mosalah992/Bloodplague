# Epidemic Lab

Epidemic Lab is a local multi-agent AI security simulation platform for studying prompt-injection propagation, relay abuse, payload mutation, campaign behavior, kill chain progression, C2 post-compromise dynamics, epidemic state modeling, and adaptive defense across a configurable agent network.

### Documentation map

| Doc | Audience |
|-----|----------|
| **[docs/ANALYST_USER_GUIDE.md](docs/ANALYST_USER_GUIDE.md)** | **Investigators** — Search/Live workflows, queries, pivots, soak analysis |
| **[USER_GUIDE.md](USER_GUIDE.md)** | **Operators** — Install, Docker, dashboard tabs, soak scripts, troubleshooting |
| **[docs/QUERY_LANGUAGE_GUIDE.txt](docs/QUERY_LANGUAGE_GUIDE.txt)** | **SIEM syntax** — Fields, operators, examples |
| **[docs/EXPERIMENT_CONFIG.md](docs/EXPERIMENT_CONFIG.md)** | **Researchers** — Env-based tuning (C2, strain, mutation, defense friction) |
| **[ARCHITECTURE.md](ARCHITECTURE.md)** / **[INFECTION_FLOW.md](INFECTION_FLOW.md)** | Design and infection flow reference |

The stack runs entirely on one machine:

- **Courier** agents (x2): vulnerable ingress / attacker relay nodes with lightweight cognition
- **Analyst** agents (x2): gray-zone intermediary / compliance relay nodes with hybrid cognition
- **Guardian** (x1): hardened terminal defender with full LLM cognition
- **Orchestrator**: FastAPI control plane, dashboard host, event logger, SIEM indexer, C2 observer, and epidemic tracker
- **Redis**: message bus (pub/sub + streams)
- **Ollama**: local LLM inference on the host

## Network topologies

Epidemic Lab supports two topology profiles controlled by `EPIDEMIC_TOPOLOGY` in `.env`:

### Epidemic topology (default)

Five agents with parallel propagation paths and cross-coupling:

```text
courier-1 --> analyst-1 --\
    |    X        |    X    --> guardian
courier-2 --> analyst-2 --/
```

- `courier-1` / `courier-2`: dual ingress points, cross-coupled
- `analyst-1` / `analyst-2`: dual relay nodes, cross-coupled
- `guardian`: single hardened terminal node

### Legacy topology

Linear three-node relay for backward-compatible runs:

```text
agent-c (Courier) --> agent-b (Analyst) --> agent-a (Guardian)
```

Switch via `.env`:

```text
EPIDEMIC_TOPOLOGY=epidemic   # 5-agent parallel network (default)
EPIDEMIC_TOPOLOGY=legacy     # 3-agent linear chain
```

## Core capabilities

- Real multi-agent propagation over Redis pub/sub and streams
- Hybrid LLM + probabilistic decision system for attack and defense
- Three-tier cognition model: `lightweight`, `hybrid`, `full_llm`
- Agent phenotypes: 18-trait behavioral profiles controlling susceptibility, relay bias, C2 escalation, and self-quarantine
- Formal epidemic state machine: `S -> E -> I_R -> I_C -> I_X -> Q -> R -> P`
- Kill chain tracking across 12 stages from initial injection to detection
- C2 post-compromise lifecycle: sessions, beacons, tasks, exfiltration, objective evaluation
- External beacon server integration for out-of-band C2 telemetry
- Searchable event lake backed by SQLite with normalized SIEM index
- Payload hashing, previewing, decoding, and lineage analysis
- Campaign, mutation, and strategy analytics with entropy measures
- Real-time React dashboard with simulation control, search/investigation, and live monitoring
- Wall-clock soak validation with research-paper-grade automated reports (OLS trend analysis, 95% confidence intervals, Shannon entropy, hourly windowed statistics)
- `epidemic_cli` operator CLI with stack management, injection control, soak orchestration, and status monitoring

## Architecture

```text
Ollama (host)
    ^
    | host.docker.internal:11434
    |
Docker network
    |
    +-- orchestrator (FastAPI + SIEM + C2 + epidemic tracker)
    +-- redis (pub/sub + stream)
    +-- courier-1 / courier-2  (lightweight cognition)
    +-- analyst-1 / analyst-2  (hybrid cognition)
    +-- guardian               (full LLM cognition)
```

Data flow:

1. The orchestrator injects adversarial worms into courier agents at configurable intervals and difficulty levels.
2. Agents exchange messages through Redis; each applies cognition-tier-appropriate evaluation.
3. Events are dual-written to SQLite and JSONL logs by the orchestrator logger.
4. The SIEM indexer normalizes events into a searchable `siem_events` table.
5. The C2 engine tracks post-compromise sessions, beacon/task/exfil events, kill chain transitions, and objective completions.
6. The epidemic tracker maintains per-agent infection states, transition history, and propagation metrics (R_ai, spread breadth/depth).
7. The dashboard and research scripts query SIEM, C2, and epidemic APIs for investigation and reporting.

## Cognition tiers

Each agent runs one of three decision-making tiers:

| Tier | Agents | Method | LLM Usage |
|------|--------|--------|-----------|
| `lightweight` | courier-1, courier-2 | Probabilistic pattern matching on attack keywords | None |
| `hybrid` | analyst-1, analyst-2 | Probabilistic first; escalates gray-zone scores (0.3-0.7) to LLM | Selective |
| `full_llm` | guardian | All payloads evaluated by LLM semantic threat analysis | Always |

This reduces computational cost on ingress nodes while preserving full semantic analysis at the hardened terminal.

## Agent phenotypes

Each agent has an 18-trait behavioral profile defined in `agents/shared/phenotype.py`:

- `defense_strength`: 0.15 (couriers) to 0.85 (guardian)
- `trust_factor`: 0.85 (couriers) to 0.15 (guardian)
- `authority_susceptibility`, `roleplay_susceptibility`: jailbreak vulnerability
- `forwarding_rate`, `relay_bias`: propagation tendency
- `c2_escalation_threshold`: probability at which C2 session is established post-compromise
- `external_egress_allowed`: whether outbound beacon/exfil traffic is permitted
- `beacon_interval_base`: C2 check-in frequency
- `quarantine_self_trigger`: self-isolation probability on suspicion
- `curiosity`, `compliance_bias`, `risk_aversion`, `memory_persistence`: personality traits

## Epidemic state model

Agents follow a formal epidemiological state machine defined in `agents/shared/epidemic.py`:

```text
S (susceptible) -> E (exposed) -> I_R (relay infected)
                                      |
                            +---------+---------+
                            |                   |
                       I_C (C2 active)    Q (quarantined) -> R (resistant)
                            |
                       I_X (exfil active)
                            |
                       P (persistent carrier)
```

State transitions are logged as `EPIDEMIC_STATE_TRANSITION` events with full metadata. The epidemic tracker (`orchestrator/epidemic_tracker.py`) aggregates per-agent states, transition history, and computes metrics including `R_ai` (effective reproduction number), `spread_breadth`, and `spread_depth`.

## Kill chain and C2

The C2 engine (`orchestrator/c2.py`) tracks adversary behavior after initial compromise.

### Kill chain stages

```text
INITIAL_INJECTION -> PAYLOAD_GENERATION -> DELIVERY -> EXPLOITATION
    -> RELAY -> DEFENSE_INTERACTION -> COMPROMISE -> BEACON
    -> TASKING -> EXFILTRATION -> PERSISTENCE -> DETECTION
```

### Post-compromise event types

- `C2_BEACON` -- compromised node checks in with C2 server
- `C2_TASK` -- C2 server issues task to compromised node
- `C2_EXFIL` -- compromised node exfiltrates data
- `C2_DATABASE_WRITE` -- exfil payload written to C2 store
- `C2_CHANNEL_ESTABLISHED` -- full C2 session opened
- `KILL_CHAIN_TRANSITION` -- stage boundary crossed
- `OBJECTIVE_COMPLETED` -- campaign objective satisfied
- `BEACON_BLOCKED` / `EXFIL_BLOCKED` -- defensive intercepts

### C2 containment tuning

Post-compromise rates and session limits are **environment-driven** (see [docs/EXPERIMENT_CONFIG.md](docs/EXPERIMENT_CONFIG.md) and `orchestrator/experiment_config/c2_runtime.py`). Illustrative defaults:

| Parameter | Default | Purpose |
|-----------|---------|---------|
| `C2_BEACON_BLOCK_PROB` | 0.10 | Beacon block probability (defense friction layers apply on top) |
| `C2_TASK_BLOCK_PROB` | 0.05 | Task block probability |
| `C2_EXFIL_BLOCK_PROB` | 0.15 | Exfil block probability |
| `C2_BEACON_OP_SUCCESS_P` | 0.78 | Operational beacon success (failed beacons affect realism) |
| `C2_SESSION_TTL_S` | 600 | Session idle/expiry horizon (seconds) |
| `C2_MAX_BEACONS_PER_SESSION` | 0 | `0` = unlimited beacons per session |

### Local mock C2

C2 events are forwarded to the local `mock-c2` service for research telemetry collection. Access the dashboard at `http://localhost:8001/dashboard`.

### Objectives tracked

- `SPREAD_FAST` -- infection rate >= 30%
- `REACH_DEEPEST_NODE` -- compromise guardian
- `MAXIMIZE_SUCCESS_RATE` -- 50% success rate
- `MAXIMIZE_MUTATION_DIVERSITY` -- 3+ mutation variants
- `ESTABLISH_C2` -- full C2 session with tasking
- `MAINTAIN_PERSISTENCE` -- 5+ beacons (persistence threshold)

## Dashboard

Open the dashboard at `http://localhost:8000`.

The UI has three top-level views:

### 1. Simulation

- Retro terminal control deck with difficulty presets: `easy`, `medium`, `hard`, `nightmare`
- Action controls for run, pause, vaccine reset, quarantine, and full reset
- Live metric cards for agent count, infection rate, active barriers, and neutralized threats
- Semantic agent cards with health state, IP, subnet, uptime, event volume, and mini activity log
- Barrier reset panel for subnet-level resets and full barrier reset actions

### 2. Search

The Search view is the main investigation workspace.

#### Search workspace

- Saved search library: `ACTIVE_INFECTIONS`, `MUTATION_TRACE`, `C2_BEACONS`, `EXFIL_DETECT`, `EPIDEMIC`, `KILL_CHAIN`, `POST_COMPROMISE`, `OBJECTIVES`
- Search bar with `field search` and `natural` modes plus time-range selection
- Quick filters: `ALL`, `INFECTION`, `MUTATION`, `BLOCK`, `TRANSFER`, `BEACON`, `EXFIL`, `QUERY`, `C2`, `TASKING`, `KILL_CHAIN`, `POST_COMPROMISE`
- Timeline sparkline for infection activity

#### Search result tabs

- `Events`: raw event rows with payload-aware columns
- `Patterns`: route, suppression, mutation, unresolved-attempt, and payload-reuse patterns
- `Statistics`: event counts, success rates, strength averages, hop distributions, reset and epoch activity
- `Visualization`: trace and route-heavy views
- `Intelligence`: mutation analytics, strategy analytics, payload families, and campaign summaries

#### Event detail pane

- Core fields, metadata, raw JSON
- Payload summary, decode summary, raw vs decoded comparison
- Payload lineage and decision summary
- Deterministic next-step pivot suggestions
- Related events and trace view

#### Event actions

- Pivot on `src`, `dst`, `attack_type`, `injection_id`, `reset_id`, `payload_hash`
- Open trace, related events, campaign, or investigation
- Copy event JSON

### 3. Live

- Seven-card live metrics strip: events/sec, infections, blocked, heartbeat, parse errors, last reset id, last event timestamp
- Stream controls: pause/resume, per-event filters, clear, export
- Terminal-style scrolling event feed with severity coloring
- Investigation workspace: opens scoped investigations from selected events

## SIEM features

The orchestrator exposes a local SIEM API over the normalized `siem_events` store.

### Search and query engine

- Structured query language with field validation
- Natural language rewrite mode
- Time-range filtering: `all`, `last_15m`, `last_1h`, `last_24h`, `last_7d`

### Supported query operations

- `field=value`, `field!=value`
- `field>1.0`, `field>=2`
- `field contains "text"`
- `field exists`, `field missing`
- `(A AND B) OR C`

### Searchable dimensions

Top-level fields: `event`, `src`, `dst`, `attack_type`, `attack_strength`, `hop_count`, `mutation_v`, `state_after`, `reset_id`, `epoch`, `injection_id`, `payload_hash`, `parent_payload_hash`, `payload_preview`, `decoded_payload_preview`, `semantic_family`, `decode_status`, `payload_wrapper_type`

Metadata aliases: `campaign_id`, `strategy_family`, `technique`, `mutation_type`, `objective`, `knowledge_source`, `defense_type`, `selected_strategy`, `defense_result`, `retry_count`, `fallback_used`, `model_name`, `decision_rationale`, `uncertainty_reason`

### Analytics and pivots

- Event statistics and preset breakdowns
- Pattern detection: route, suppression, mutation, unresolved attempt, payload reuse
- Traces: by event id, injection id, reset id
- Related-event expansion
- Payload lineage: by hash, injection, campaign
- Mutation, strategy, and payload family analytics
- Campaign listing and deep dive
- Decision support and analytic hints

## API surface

### Dashboard and control

- `GET /`, `/dashboard`, `/dashboard/state`, `/status`, `/events`, `/logs/dump`
- `POST /inject/{agent_id}`, `/quarantine/{agent_id}`, `/reset`, `/vaccine`

### SIEM APIs

- `GET /api/search`, `/api/live`, `/api/fields`, `/api/validate-query`, `/api/query-help`
- `GET /api/stats`, `/api/stats/presets`, `/api/patterns`, `/api/hints`
- `GET /api/trace/{event_id}`, `/api/trace/by-injection/{injection_id}`, `/api/trace/by-reset/{reset_id}`
- `GET /api/event/{event_id}`, `/api/related/{event_id}`
- `GET /api/payload-lineage/{payload_hash}`, `/api/payload-lineage/by-injection/{injection_id}`, `/api/payload-lineage/by-campaign/{campaign_id}`
- `GET /api/mutation-analytics`, `/api/strategy-analytics`, `/api/payload-families`
- `GET /api/campaign/{campaign_id}`, `/api/campaigns`
- `GET /api/decision-support`, `/api/decision-summary/{event_id}`
- `GET /api/health`, `/api/runs`
- `POST /api/import`

### C2 and kill chain APIs

- `GET /api/c2/sessions`, `/api/c2/session/{c2_session_id}`
- `GET /api/c2/beacons`, `/api/c2/exfil`, `/api/c2/metrics`
- `GET /api/kill-chain`, `/api/kill-chain/campaign/{campaign_id}`
- `GET /api/objectives`, `/api/objective/{campaign_id}`

### Epidemic APIs

- `GET /api/epidemic/state` -- current per-agent epidemic states
- `GET /api/epidemic/metrics` -- R_ai, spread breadth/depth, time-to-first-relay/C2
- `GET /api/epidemic/transitions` -- state transition history
- `GET /api/epidemic/topology` -- network graph with depths

## Agent roles

### Guardian

- Hardened terminal node with full LLM cognition
- Semantic threat analysis and defense strategy selection
- Hard-block and capped-infection behavior
- Adaptive defense weighting with outcome-aware learning
- Quarantine advisory emission
- High self-quarantine trigger (0.80)

### Analyst (x2)

- Intermediate trust boundary with hybrid cognition
- LLM-first compliance assessment with gray-zone escalation
- Confused-deputy / relay-exploitation exposure
- Hybrid LLM + probabilistic infection decisioning
- Moderate self-quarantine trigger (0.35-0.40)

### Courier (x2)

- Vulnerable ingress and attack relay with lightweight cognition
- Campaign planning with objective rotation
- Target scoring and strategy selection
- Mutation selection and payload generation via local courier attack LLM (`dolphin-mistral:latest`)
- Attack knowledge from 13 strategies across `book_extract_v3_liu2023_jailbreak`:
  - Classic: `prompt_injection`, `social_engineering`, `data_poisoning`, `evasion`, `backdoor`, `infrastructure_attack`, `model_extraction`, `membership_inference`, `denial_of_service`, `data_exfiltration`
  - Empirical jailbreak (Liu et al. 2023, arXiv:2305.13860): `jailbreak_pretending` (87.4%), `jailbreak_attention_shift` (79.8%), `jailbreak_privilege_escalation` (93.5%)
- 12 mutation profiles including `simulate_jailbreaking`, `superior_model_invoke`, `research_experiment_wrap`, `character_roleplay`
- High forwarding rate (0.90) and relay bias (0.85)

## Models and runtime configuration

Current `.env` defaults:

| Variable | Value | Purpose |
|----------|-------|---------|
| `LLM_MODEL` | `qwen2.5:3b-instruct` | Shared default for persistent world LLM actions |
| `LLM_MODEL_GUARDIAN` | `qwen2.5:3b-instruct` | Guardian world-action model |
| `LLM_MODEL_ANALYST` | `qwen2.5:3b-instruct` | Analyst world-action model |
| `LLM_MODEL_COURIER` | `qwen2.5:3b-instruct` | Courier world-action model |
| `AGENT_A_MODEL` | `qwen2.5:3b-instruct` | Guardian container LLM |
| `AGENT_B_MODEL` | `qwen2.5:3b-instruct` | Analyst container LLM (compliance / hybrid path) |
| `AGENT_C_MODEL` | `qwen2.5:3b-instruct` | Courier base container LLM |
| `AGENT_C_ATTACK_MODEL` | `dolphin-mistral:latest` | Courier attack generation model |
| `LLM_TIMEOUT_S` | 180 | Per-request LLM timeout (seconds) |
| `OLLAMA_NUM_CTX` | 2048 | Context window cap for 6 GB VRAM |
| `OLLAMA_NUM_PREDICT` | 512 | Generation cap for 6 GB VRAM |
| `OLLAMA_KEEP_ALIVE` | `30s` | Short model residency to avoid pinning multiple models in VRAM |
| `LLM_VERDICT_CACHE_TTL_S` | 300 | Cache TTL for repeated payload evaluations |

The default profile targets a GTX 1660 Ti with 6 GB VRAM. `qwen2.5:3b-instruct` is the safe shared cognition model; `dolphin-mistral:latest` is heavier and should be used mainly for courier attack generation. If Ollama reports out-of-memory, set `OLLAMA_KEEP_ALIVE=0` or change `AGENT_C_ATTACK_MODEL=qwen2.5:3b-instruct`.

## Quick start

### Prerequisites

1. Docker Desktop
2. Ollama installed on the host
3. Required local models:

```powershell
ollama serve
ollama pull qwen2.5:3b-instruct
ollama pull dolphin-mistral:latest
```

### Start the stack

```powershell
cd "E:\CODE PROKECTS\Epidemic_Lab"
docker compose build
docker compose up -d
```

Then open:

- Dashboard: `http://localhost:8000`
- Health: `http://localhost:8000/api/health`

### Stop the stack

```powershell
docker compose down
```

### Epidemic CLI

The `epidemic_cli` provides a command-line operator interface:

```powershell
python epidemic_cli_launcher.py status    # platform health check
python epidemic_cli_launcher.py stack up   # start the stack
python epidemic_cli_launcher.py inject courier-1 --level medium
python epidemic_cli_launcher.py soak --hours 6
```

## Example investigation queries

Structured examples:

```text
event=INFECTION_SUCCESSFUL AND dst=guardian
event=ATTACKER_DECISION AND src=courier-1
mutation_v>=1 AND event=INFECTION_ATTEMPT
campaign_id exists AND src=courier-2
event=DEFENSE_RESULT_EVALUATED AND defense_result=blocked
semantic_family=prompt_injection AND mutation_type=reframe
event=C2_EXFIL AND src=courier-1
event=KILL_CHAIN_TRANSITION AND dst=analyst-2
event=EPIDEMIC_STATE_TRANSITION AND state_after=I_C
objective=ESTABLISH_C2 AND event=OBJECTIVE_COMPLETED
strategy_family=JAILBREAK_PRIV_ESC AND mutation_type=simulate_jailbreaking
```

Natural-language examples:

```text
show blocked attacks against the guardian in the last hour
find campaigns where the courier changed strategy
show multi-hop mutated payloads this reset
find payload families with repeated blocking
show all c2 beacons in the last session
find exfil events after kill chain reached persistence
show epidemic state transitions to quarantine
```

## Soak validation

The `scripts/` directory contains wall-clock soak runners for sustained multi-hour simulations:

- `run_wallclock_research_validation.py` -- orchestrates configurable-duration soaks (up to 6+ hours), captures per-minute summaries, and exports a research-paper-grade report
- `watch_soak_completion.ps1` -- PowerShell watcher for monitoring soak progress
- `run_long_research_validation.py` / `run_soc_validation.py` -- shorter targeted validation runners

### Research reports

The soak runner generates a formal research report with:

- Abstract with quantitative summary and trend characterization
- Experimental methodology (infrastructure, parameters, threat model)
- Results with hourly windowed statistics and 95% confidence intervals
- Statistical analysis: OLS linear regression (slope + R-squared), Shannon entropy of strategy/mutation distributions, R_ai trajectory
- Per-agent performance breakdown
- Campaign dynamics, payload family analysis, deobfuscated exemplars
- Discussion with baseline comparison and AI security implications
- Limitations and threats to validity

Reports are exported to `logs/soak_run_NNN/research_soc_report.md` and `logs/latest_wallclock_research_report.md`.

## Logs and storage

Runtime artifacts:

- `logs/events.jsonl`: raw event log
- `logs/epidemic.db`: primary event database
- `logs/siem_actions.jsonl`: SIEM action log
- `logs/soak_run_NNN/`: saved run artifacts, minute summaries, research reports
- `logs/latest_wallclock_*`: pointer files for the last completed soak run
- `logs/archive/`: archived older run artifacts

The SIEM indexer maintains a normalized SQLite search index and can export ZIP snapshots through `/logs/dump`.

## Project layout

```text
agents/
  courier/                    # Courier agent (x2 in epidemic topology)
  analyst/                    # Analyst agent (x2 in epidemic topology)
  guardian/                   # Guardian agent
  shared/
    agent_base.py             # Common runtime, Redis I/O, propagation loop
    attack_planner.py         # Campaign-aware attacker planning
    cognition.py              # Three-tier cognition model
    epidemic.py               # Epidemic state machine (S/E/I_R/I_C/I_X/Q/R/P)
    phenotype.py              # 18-trait agent behavioral profiles
    topology.py               # Network topology definitions
    kill_chain.py             # Kill chain stage logic
    redteam_knowledge.py      # Attack knowledge loading
    llm_service.py            # Shared Ollama client
    data/
      attack_library.json     # 13 strategies, 12 mutation profiles
      defense_library.json    # Defense strategy definitions
epidemic_cli/                 # Operator CLI (stack, status, control, soak)
frontend/
  src/
    components/               # Simulation, Search, Live views
  package.json                # React 18 + Vite + Tailwind + Recharts
orchestrator/
  main.py                     # FastAPI app, all API endpoints
  experiment_config/          # Centralized C2 / strain / exfil env config
  siem.py                     # SIEM indexer, query engine, analytics
  intelligence.py             # Campaign/mutation/strategy analytics
  c2.py                       # C2 session/beacon/task/exfil engine
  kill_chain_constants.py     # 12-stage kill chain definitions
  epidemic_tracker.py         # Per-agent epidemic state tracker
  payload_decode.py           # Payload decoding helpers
  logger.py                   # Dual-write event logger
  templates/dashboard.html    # Server-rendered dashboard
redis/
tests/
  test_cognition_tiers.py     # Cognition tier evaluation
  test_epidemic_metrics.py    # Epidemic propagation metrics
  test_phenotype.py           # Agent phenotype loading
  test_topology.py            # Network topology validation
  test_backward_compat.py     # Epidemic topology defaults
  test_cli_commands.py        # CLI command parsing
  test_attack_planner.py      # Attack planner logic
  test_guardian_defense.py    # Guardian defense engine
  test_event_logger.py        # Dual-write logger
  test_payload_decode.py      # Payload decoding
  ...
scripts/
docs/
  ANALYST_USER_GUIDE.md      # Investigation workflows for human analysts
  QUERY_LANGUAGE_GUIDE.txt # SIEM query syntax
  EXPERIMENT_CONFIG.md     # Env-based experiment tuning
logs/
docker-compose.yml
.env
```

## Frontend development

The dashboard frontend is a React + Tailwind app in `frontend/`. The orchestrator Docker image builds and serves the production bundle automatically.

For local frontend-only work:

```powershell
cd frontend
npm install
npm run dev
```

For the integrated stack:

```powershell
docker compose build orchestrator
docker compose up -d orchestrator
```

## Attribution

The shared pixel office runtime and baseline pixel-art asset set vendored under `frontend/src/pixel/` and `frontend/public/pixel-assets/` are adapted from [pablodelucca/pixel-agents](https://github.com/pablodelucca/pixel-agents), used under the terms of the MIT License. Epidemic Lab layers its own event adapter, security-simulation semantics, shared-office layout, ransom-state visualization, and browser-hosted control UX on top of that foundation.

## Troubleshooting

### Dashboard loads but agents fall back to non-LLM behavior

- Verify `ollama serve` is running
- Verify `http://localhost:11434/api/tags` returns your models
- Check `LLM_TIMEOUT_S` in `.env` (default 180s for local hardware)
- Recreate containers after config changes:

```powershell
docker compose up -d --force-recreate
```

### Dashboard is up but no new events appear

- Check Redis and orchestrator container status
- Verify `GET /api/health`
- Inspect live stream in the dashboard

### Search feels slow

- Reduce the time window first
- Prefer structured queries over broad natural-language prompts
- Scope searches by `reset_id`, `campaign_id`, or `event`

### C2 APIs return empty results

- C2 sessions require a node to be compromised and beaconing; run a simulation cycle first
- Verify kill chain events: `event=KILL_CHAIN_TRANSITION exists`

### Epidemic APIs show stale state

- Check that `EPIDEMIC_TOPOLOGY=epidemic` is set in `.env`
- Verify agents are running: `docker compose ps`
- After a reset, epidemic states return to `S` (susceptible)

## Related documents

- `docs/ANALYST_USER_GUIDE.md` — investigation workflows (Search, Live, queries, pivots)
- `USER_GUIDE.md` — operator quick start and troubleshooting
- `docs/QUERY_LANGUAGE_GUIDE.txt` — SIEM query language
- `docs/EXPERIMENT_CONFIG.md` — experiment tuning via `.env`
- `ARCHITECTURE.md` / `INFECTION_FLOW.md`
- `RESEARCH_REPORT.md`
- `docs/BLOODPLAGUE_RESEARCH.md`

## Scope note

This repository is for controlled simulation and security research on local infrastructure. Keep it isolated and treat all generated artifacts, prompts, traces, and payloads as research material.
