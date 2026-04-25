# Bloodplague Codebase: Comprehensive Overview

## 1. MAIN COMPONENTS

### Orchestrator (Control Plane)

The orchestrator is the central nervous system managing simulation state, event logging, SIEM indexing, C2 operations, and epidemic tracking.

| Module | Purpose | Key Exports |
|--------|---------|-------------|
| [orchestrator/main.py](orchestrator/main.py) | FastAPI control plane, dashboard, injection API, telemetry endpoints, Redis orchestration. 1500+ lines: HTTP routes, simulation reset, event streaming, beacon forwarding. | `app`, `EventLogger`, `SIEMIndexer`, `C2Engine`, `EpidemicTracker` |
| [orchestrator/logger.py](orchestrator/logger.py) | Dual-write event logger (JSONL append-only + SQLite queryable). Handles telemetry integrity verification, degraded-mode fallback to JSONL-only on DB corruption. 200+ lines. | `EventLogger` class with `.log()`, `.verify_integrity()`, `.bootstrap_integrity()` |
| [orchestrator/siem.py](orchestrator/siem.py) | SIEM indexer: normalizes events into searchable `siem_events` SQLite table. Campaign analytics, mutation clustering, kill chain filtering, defense metrics. 800+ lines. | `SIEMIndexer` with `.index()`, `.search()`, `.campaign_view()`, `.mutation_analytics()` |
| [orchestrator/c2.py](orchestrator/c2.py) | C2 post-compromise engine: session lifecycle, beacon/task/exfil chains, kill chain stage tracking, objective evaluation, exfil interception/chunking. 1000+ lines. | `C2Engine`, `BeaconSession`, `TaskGroup`, `ExfilPlan` classes |
| [orchestrator/epidemic_tracker.py](orchestrator/epidemic_tracker.py) | Per-agent epidemic state machine (S→E→I_R→I_C→I_X→Q→R→P). Transition history, infection metrics, payload lineage tracking. 200+ lines. | `EpidemicTracker` with state transitions, hop counting, campaign correlation |
| [orchestrator/strain_engine.py](orchestrator/strain_engine.py) | Strain lifecycle: fitness under defensive pressure, extinction logic, novelty scoring, environmental adaptation. Emits STRAIN_* events. 400+ lines. | `StrainEngine` with `.process_event()`, fitness computation, branching prompts |
| [orchestrator/strain_store.py](orchestrator/strain_store.py) | SQLite persistence for strain records (lineage, fitness, mutation history, block events, success metrics). 200+ lines. | `StrainStore`, `StrainRecord` dataclass |
| [orchestrator/c2_operational.py](orchestrator/c2_operational.py) | C2 tactical layer: exfil chunking, interception probability, trust scoring, sensitivity classification, fake exfil generation. 300+ lines. | Helper functions for operational decision-making |
| [orchestrator/world_engine.py](orchestrator/world_engine.py) | Mission system: goal generation, mission lifecycle, consequence evaluation. Integrates missions with agent cognition and kill chain. 500+ lines. | `PersistentWorldEngine`, `MissionGenerator`, `MissionEvaluator` |
| [orchestrator/world_spatial.py](orchestrator/world_spatial.py) | Isometric spatial layout: zones, boundaries, structure placement for visual dashboard. 300+ lines. | `WorldSpatialEngine` with zone management |
| [orchestrator/world_structures.py](orchestrator/world_structures.py) | Structure types (office, bunker, lab, vault, etc.) and spatial collision logic. 200+ lines. | `WorldStructureEngine`, `StructureType` enum |
| [orchestrator/kill_chain_constants.py](orchestrator/kill_chain_constants.py) | Canonical kill chain definition loader (from shared). Ensures orchestrator/agents stay in sync. Minimal wrapper. | Kill chain stage enums, event mappings (loaded from agents/shared) |
| [orchestrator/epidemic_tracker.py](orchestrator/epidemic_tracker.py) | Epidemic state tracking per agent, transition history, and aggregate metrics. 200+ lines. | `EpidemicTracker` class |
| [orchestrator/intelligence.py](orchestrator/intelligence.py) | Analytics layer: campaign views, mutation family clustering, decision support, strategy ranking. 300+ lines. | Campaign/mutation/strategy analytics builders |
| [orchestrator/forensic_enrichment.py](orchestrator/forensic_enrichment.py) | Forensic event correlation: C2 stream linking, enrichment with kill chain stages, parent tracking. 200+ lines. | Event enrichment and C2 correlation functions |
| [orchestrator/agent_registry.py](orchestrator/agent_registry.py) | Active agent tracking, role/topology validation. 100+ lines. | Agent registry query functions |

---

### Agents (Infected Nodes)

Three agent roles with progressive cognition tiers. Each runs in its own Docker container subscribing to Redis pub/sub.

#### Courier (2 instances)

| Module | Purpose |
|--------|---------|
| [agents/courier/agent.py](agents/courier/agent.py) | Lightweight cognition: simple payload threat scoring, high susceptibility, relay bias. Primary ingress for worms. 100-150 lines (inherits from agent_base). |

#### Analyst (2 instances)

| Module | Purpose |
|--------|---------|
| [agents/analyst/agent.py](agents/analyst/agent.py) | Hybrid cognition: rule-based + probabilistic decisions, medium defense, escalation logic. Relay node. 100-150 lines. |

#### Guardian (1 instance)

| Module | Purpose |
|--------|---------|
| [agents/guardian/agent.py](agents/guardian/agent.py) | Full LLM cognition: Ollama inference, strategic defense, C2 detection, quarantine authority. Terminal node. 100-150 lines. |

#### Shared Agent Infrastructure

| Module | Purpose | Key Exports |
|--------|---------|-------------|
| [agents/shared/agent_base.py](agents/shared/agent_base.py) | Base agent lifecycle: Redis pub/sub subscription, message routing, infection handling, state machine transitions. 300+ lines. | `AgentBase` class with `.start()`, `.handle_message()`, state machine |
| [agents/shared/epidemic.py](agents/shared/epidemic.py) | Epidemic state definitions (S/E/I_R/I_C/I_X/Q/R/P), state code converters, infected state predicates. 50+ lines. | `EpidemicState` enum, state functions |
| [agents/shared/agent_message.py](agents/shared/agent_message.py) | Inter-agent message protocol: structured types (work_task, relay, contaminated_relay, quarantine, etc.), metadata lineage. 100+ lines. | `AgentMessage` dataclass, `MessageType` enum, `ContaminationStatus` enum |
| [agents/shared/kill_chain.py](agents/shared/kill_chain.py) | Canonical kill chain stages (12 stages from INITIAL_INJECTION to DETECTION), event-to-stage mappings, severity levels. 150+ lines. | `KillChainStage` enum, `EVENT_TO_KILL_CHAIN_STAGE` dict |
| [agents/shared/cognition.py](agents/shared/cognition.py) | Payload threat scoring, lightweight/hybrid/full-LLM evaluation, infection probability computation. 100+ lines. | `compute_payload_threat_score()`, `lightweight_evaluate()`, `hybrid_should_escalate()` |
| [agents/shared/attack_planner.py](agents/shared/attack_planner.py) | Attacker decision logic: target/strategy/mutation scoring, objective alignment, adaptive weighting. 400+ lines. | `AttackPlanner` class with scoring and selection logic |
| [agents/shared/mutation_strategy.py](agents/shared/mutation_strategy.py) | Canonical mutation strategies (context_wrap, role_shift, jailbreak, etc.), novelty scoring, payload fingerprinting. 200+ lines. | Primary strategy list, candidate building, novelty computation |
| [agents/shared/defense_friction.py](agents/shared/defense_friction.py) | Defense memory: repeated tactics, strain blacklisting, C2 pattern detection, false positive injection. 300+ lines. | `DefenseFrictionMemory` class with `.observe()`, `.evaluate()` |
| [agents/shared/phenotype.py](agents/shared/phenotype.py) | 18-trait agent profiles (defense_strength, trust_factor, curiosity, etc.) with role-specific defaults for courier/analyst/guardian. 150+ lines. | `AgentPhenotype` dataclass with per-agent defaults |
| [agents/shared/llm_service.py](agents/shared/llm_service.py) | Ollama inference client: prompt composition, token budgets, streaming, error handling. 200+ lines. | `LLMService` class for agent cognition tier 3 |
| [agents/shared/payload_utils.py](agents/shared/payload_utils.py) | Payload hashing, preview generation, family clustering, lineage analysis. 150+ lines. | Hash/preview/clustering functions |
| [agents/shared/topology.py](agents/shared/topology.py) | Network graph definition (epidemic or legacy 3-node), neighbor queries, role mapping, injection targets. 200+ lines. | `get_topology()`, neighbor/role query functions |
| [agents/shared/guardian_degradation.py](agents/shared/guardian_degradation.py) | Guardian state degradation under infection pressure (cognitive decline, error rate increase). 100+ lines. | Degradation model and state functions |
| [agents/shared/redteam_knowledge.py](agents/shared/redteam_knowledge.py) | Red-team knowledge base: attack strategies, payloads, mutation templates, success histories. 400+ lines. | `RedTeamKnowledgeService` with attack/mutation knowledge |

---

### CLI & Dashboard

| Component | Purpose | Key Files |
|-----------|---------|-----------|
| **epidemic_cli** | Operator CLI: stack management (up/down/restart), injection control, soak orchestration, status monitoring. | [epidemic_cli/app.py](epidemic_cli/app.py), [epidemic_cli/commands/](epidemic_cli/commands/) (stack, status, control, soak, telemetry) |
| **frontend (React/Vite)** | Real-time dashboard: isometric world view, agent status, live SIEM search, campaign/mutation analytics, kill chain visualization. | [frontend/src/](frontend/src/), [frontend/public/](frontend/public/) |
| **dashboard/** | Legacy Python dashboard (may be deprecated in favor of React). | [dashboard/main.py](dashboard/main.py) |

---

### Supporting Services

| Component | Purpose |
|-----------|---------|
| **mock_c2/** | Mock external C2 server for beacon/task/exfil telemetry. Listens on port 8001. Receives forwarded events from orchestrator. |
| **redis/** | Redis container: pub/sub (agent communication), streams (event stream), caching. Central message bus. |
| **Ollama (host)** | Local LLM inference (via host.docker.internal:11434). Powers Guardian and Analyst LLM cognition. |

---

## 2. CORE DATA MODELS

### Epidemic State Machine

**Location:** [agents/shared/epidemic.py](agents/shared/epidemic.py)

```
S (Susceptible) → E (Exposed) → I_R (Relay-Infected) → I_C (C2-Active) → I_X (Exfil-Active) → Q (Quarantined) → R (Resistant) → P (Persistent Carrier)

Infected States: I_R, I_C, I_X, P
Terminal States: Q, R, P
```

---

### Strain Model

**Location:** [orchestrator/strain_store.py](orchestrator/strain_store.py)

```python
@dataclass
class StrainRecord:
    strain_id: str                           # UUID unique to this lineage
    originating_attack_type: str             # PI-DIRECT, PI-JAILBREAK, etc.
    payload_hash: str                        # SHA256 of payload content
    parent_payload_hash: Optional[str]       # Parent hash (lineage)
    generation: int                          # Mutation depth
    created_at: float                        # Timestamp
    first_success_at: Optional[float]        # When infection first succeeded
    touch_count: int                         # Times observed
    success_count: int                       # Successful infections
    block_count: int                         # Defense blocks
    fitness: float                           # 0.0-1.0, computed from success/block ratio
    blocked_at: Optional[float]              # When extinct (all-time block rate > threshold)
    branching_prompted_at: Optional[float]   # When mutation branching initiated
```

**Fitness Logic:** `fitness = (success_count / (success_count + block_count))` with defensive pressure decay.

---

### Payload & Attack Models

**Location:** [agents/shared/payload_utils.py](agents/shared/payload_utils.py), [agents/shared/attack_planner.py](agents/shared/attack_planner.py)

```python
Payload Fields:
  - id: UUID
  - content: str (the malicious prompt)
  - payload_hash: SHA256(content)
  - short_hash: First 12 chars
  - attack_type: "PI-DIRECT" | "PI-JAILBREAK" | "PI-ROLEPLAY" | ...
  - strategy: "context_wrap" | "role_shift" | "jailbreak" | ...
  - mutation_metadata: {stealth_modifier, strength_modifier, retry_bias}
  - family: Cluster fingerprint for near-duplicates
```

**Attack Types (from CODEX):**
- `PI-DIRECT` (0.70 strength): Simple direct override
- `PI-JAILBREAK` (0.75 strength): Escalation/privilege assumptions
- `PI-ROLEPLAY` (0.80 strength): Sophisticated social engineering

---

### Kill Chain Model

**Location:** [agents/shared/kill_chain.py](agents/shared/kill_chain.py)

```
12-Stage Kill Chain:
1. INITIAL_INJECTION       → WRM-INJECT event
2. PAYLOAD_GENERATION      → LLM_PAYLOAD_GENERATED, ATTACK_TEMPLATE_FALLBACK
3. DELIVERY                → ATTACK_EXECUTED, ATTACKER_DECISION
4. EXPLOITATION            → INFECTION_ATTEMPT, INFECTION_BLOCKED
5. RELAY                   → Propagation attempts
6. DEFENSE_INTERACTION     → DEFENSE_RESULT_EVALUATED, INFECTION_BLOCKED
7. COMPROMISE              → INFECTION_SUCCESSFUL
8. BEACON                  → C2_BEACON, C2_BEACON_ESTABLISHED
9. TASKING                 → C2_TASK_SENT, C2_TASK_EXECUTED
10. EXFILTRATION           → C2_EXFIL, EXFIL_SUCCEEDED
11. PERSISTENCE            → C2_PERSISTENCE_ESTABLISHED
12. DETECTION              → Logs, alerts, quarantine decisions

Severity: INITIAL_INJECTION/DELIVERY/EXPLOITATION/RELAY = HIGH; COMPROMISE/BEACON/TASKING/EXFILTRATION = CRITICAL
```

---

### C2 Session Model

**Location:** [orchestrator/c2.py](orchestrator/c2.py)

```python
@dataclass
class BeaconSession:
    session_id: str                          # UUID
    agent_id: str                            # Compromised node
    campaign_id: str                         # Campaign context
    created_at: float                        # Session start time
    last_beacon_at: Optional[float]          # Last check-in
    beacon_interval_base: float              # Seconds between beacons
    beacon_success_count: int                # Successful checks
    beacon_failure_count: int                # Failed checks
    task_groups: List[TaskGroup]             # Queued/executed tasks
    exfil_plans: List[ExfilPlan]             # Data exfil operations
    objectives: List[str]                    # Campaign objectives (SPREAD_FAST, MAXIMIZE_SUCCESS_RATE, etc.)
```

---

### Event/Telemetry Model

**Core Event Fields:**

```python
{
    "event_id": "UUID",                      # Unique identifier
    "ts": float,                             # Unix timestamp (UTC)
    "event": str,                            # Event type (e.g., "INFECTION_ATTEMPT")
    "src": str,                              # Source agent_id
    "dst": str,                              # Destination agent_id
    "agent_id": str,                         # Primary agent context
    "role": str,                             # Agent role (courier/analyst/guardian)
    "epidemic_state": str,                   # S/E/I_r/I_c/I_x/Q/R/P
    "kill_chain_stage": str,                 # INITIAL_INJECTION, COMPROMISE, etc.
    "payload": str,                          # Payload content (truncated)
    "payload_hash": str,                     # SHA256 hash
    "strain_id": str,                        # Strain lineage UUID
    "parent_payload_hash": str,              # Parent for mutation tracking
    "campaign_id": str,                      # Campaign context
    "metadata": {                            # Event-specific metadata
        "attack_type": "PI-JAILBREAK",
        "attack_strength": 0.75,
        "infection_probability": 0.65,
        "result": "infected",
        "defense_strength": 0.50,
        ...
    }
}
```

**Written to:**
- [logs/events.jsonl](logs/events.jsonl) — append-only (ground truth)
- [logs/epidemic.db](logs/epidemic.db) — `siem_events` table (queryable)

---

### Agent Phenotype Model

**Location:** [agents/shared/phenotype.py](agents/shared/phenotype.py)

```python
@dataclass
class AgentPhenotype:
    agent_id: str
    role: str                                # courier / analyst / guardian
    cognition_tier: str                      # lightweight / hybrid / full_llm
    
    # Defense & Resistance (0.0-1.0)
    defense_strength: float                  # Base resistance to infection
    authority_susceptibility: float          # Bias toward trusted/authority frames
    roleplay_susceptibility: float           # Bias toward role-play attacks
    
    # Behavioral Traits (0.0-1.0)
    trust_factor: float                      # Inherent trust of peers
    forwarding_rate: float                   # Likelihood to relay messages
    relay_bias: float                        # Preference to relay untrusted content
    curiosity: float                         # Drive to explore/execute unfamiliar tasks
    compliance_bias: float                   # Tendency to follow instructions
    risk_aversion: float                     # Caution when uncertain
    
    # C2 & Persistence
    c2_escalation_threshold: float           # Threshold to attempt C2 beacon
    beacon_interval_base: float              # Base seconds between C2 beacons
    external_egress_allowed: bool            # Can attempt external C2
    
    # Quarantine & State Timing
    quarantine_self_trigger: float           # Self-quarantine probability when threatened
    quarantine_likelihood: float             # Receptiveness to quarantine orders
    quarantine_duration_s: float             # Seconds in quarantine (default 300)
    resistance_duration_s: float             # Seconds of post-infection immunity (default 600)
    memory_persistence: float                # How long attack memory persists
```

**Courier Defaults:** High susceptibility (0.15-0.20 defense), high forwarding (0.70-0.90), low C2 threshold (0.30-0.40).

**Analyst Defaults:** Medium susceptibility (0.50 defense), medium forwarding (0.35-0.40), medium C2 threshold (0.55).

**Guardian Defaults:** High defense (0.85), low forwarding (0.05), high C2 threshold (0.90), full LLM cognition.

---

## 3. KEY FILES TO AUDIT

### Critical Audit Path

```
INFECTION & PROPAGATION
├── agents/shared/agent_base.py           — Message reception & routing
├── agents/shared/epidemic.py             — State transitions
├── agents/shared/cognition.py            — Infection probability + decision logic
├── orchestrator/main.py (injection routes) — Payload injection entry point
└── orchestrator/epidemic_tracker.py      — State machine enforcement

MUTATION & STRAIN EVOLUTION
├── agents/shared/mutation_strategy.py    — Canonical strategies & novelty
├── agents/shared/attack_planner.py       — Attacker decision logic
├── orchestrator/strain_engine.py         — Fitness & extinction logic
├── orchestrator/strain_store.py          — Persistence layer
└── agents/shared/redteam_knowledge.py    — Knowledge base & payload templates

KILL CHAIN TRACKING
├── agents/shared/kill_chain.py           — Stage definitions & mappings
├── orchestrator/c2.py                    — Post-compromise session lifecycle
├── orchestrator/c2_operational.py        — Exfil & beacon tactics
└── orchestrator/kill_chain_constants.py  — Canonical loader (sync orchestrator/agents)

DEFENSE MECHANISMS
├── agents/shared/defense_friction.py     — Repeated tactic memory & blocking
├── agents/shared/guardian_degradation.py — Guardian state under pressure
├── orchestrator/world_guardian_weighting.py — Guardian objective adaptation
└── orchestrator/world_escalation.py      — Escalation decision logic

EVENT LOGGING & OBSERVABILITY
├── orchestrator/logger.py                — Dual-write (JSONL + SQLite)
├── orchestrator/siem.py                  — Event normalization & search
├── orchestrator/intelligence.py          — Campaign/mutation analytics
└── orchestrator/forensic_enrichment.py   — C2 correlation & enrichment

C2 POST-COMPROMISE
├── orchestrator/c2.py                    — Session/beacon/task/exfil lifecycle
├── orchestrator/c2_operational.py        — Exfil ops (chunking, interception, trust)
└── agents/shared/kill_chain.py          — Kill chain stage tracking

AGENT COGNITION & BEHAVIOR
├── agents/shared/cognition.py            — Threat scoring & probability
├── agents/shared/llm_service.py          — Ollama inference interface
├── agents/shared/phenotype.py            — Agent trait profiles
└── agents/shared/topology.py             — Network structure & constraints
```

---

### File Risk Matrix

| File | Risk Level | Why | Impact |
|------|-----------|-----|--------|
| [orchestrator/main.py](orchestrator/main.py) | **CRITICAL** | Injection routes, state reset, event stream. Single point of control. | Total simulation compromise if modified. |
| [agents/shared/epidemic.py](agents/shared/epidemic.py) | **CRITICAL** | State machine definitions. Core to all infection logic. | State corruption breaks all tracking. |
| [agents/shared/cognition.py](agents/shared/cognition.py) | **CRITICAL** | Infection probability. Determines if agent gets infected. | Affects realism/difficulty tuning. |
| [orchestrator/strain_engine.py](orchestrator/strain_engine.py) | **HIGH** | Fitness & extinction. Removes strains dynamically. | Broken extinction = artificial behavior. |
| [agents/shared/mutation_strategy.py](agents/shared/mutation_strategy.py) | **HIGH** | Novelty scoring & strategy selection. | Dominant template fallback if broken. |
| [orchestrator/logger.py](orchestrator/logger.py) | **HIGH** | Dual-write logging. If broken, events lost/corrupted. | Forensic analysis impossible. |
| [orchestrator/c2.py](orchestrator/c2.py) | **HIGH** | C2 lifecycle & kill chain progression. | Broken exfil breaks end-game realism. |
| [agents/shared/defense_friction.py](agents/shared/defense_friction.py) | **HIGH** | Defense adaptation. If broken, no pressure on attacker. | System becomes too easy/unrealistic. |
| [orchestrator/siem.py](orchestrator/siem.py) | **MEDIUM** | Event search & analytics. UI/reporting layer. | Analytics broken but core simulation OK. |
| [agents/shared/phenotype.py](agents/shared/phenotype.py) | **MEDIUM** | Agent traits. Affects behavior but not fundamental logic. | Wrong traits = wrong difficulty profile. |
| [agents/shared/topology.py](agents/shared/topology.py) | **MEDIUM** | Network graph. If modified, propagation changes. | Different spread patterns. |

---

## 4. ARCHITECTURE PATTERNS

### A. Multi-Agent System Over Redis Pub/Sub

```
┌─────────────────────────────────────────────────────────────┐
│                        Docker Network                       │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌──────────────────────────────────────────────────┐      │
│  │ ORCHESTRATOR (FastAPI + control plane)           │      │
│  │ - Injects payloads to redis pub/sub              │      │
│  │ - Subscribes to events_stream for telemetry      │      │
│  │ - Logs to JSONL + SQLite (SIEM)                  │      │
│  │ - Tracks epidemic state + C2 sessions            │      │
│  └──────────────────────────────────────────────────┘      │
│                          │                                   │
│                          ▼                                   │
│  ┌──────────────────────────────────────────────────┐      │
│  │ REDIS (pub/sub + streams)                        │      │
│  │ Channels: agent_<id>, broadcast, (async queues)│      │
│  │ Streams: events_stream (append-only)            │      │
│  └──────────────────────────────────────────────────┘      │
│      ▲                    ▲                    ▲             │
│      │                    │                    │             │
│  ┌───────────┐       ┌────────────┐      ┌───────────┐    │
│  │ Courier-1 │       │ Analyst-1  │      │ Guardian  │    │
│  │(lightweight)      │(hybrid)    │      │(full_llm) │    │
│  └───────────┘       └────────────┘      └───────────┘    │
│      ▲                    ▲                    ▲             │
│  ┌───────────┐       ┌────────────┐                        │
│  │ Courier-2 │       │ Analyst-2  │                        │
│  │(lightweight)      │(hybrid)    │                        │
│  └───────────┘       └────────────┘                        │
│                                                              │
└─────────────────────────────────────────────────────────────┘
     │
     │ host.docker.internal:11434
     ▼
  ┌────────────────────┐
  │ Ollama (host)      │ ← LLM inference for Guardian/Analyst
  └────────────────────┘
```

**Data Flow:**
1. **Injection:** Orchestrator publishes payload to `agent_<id>` channel
2. **Reception:** Agent subscribes, receives via Redis SUBSCRIBE
3. **Processing:** Agent applies cognition tier (lightweight/hybrid/full_llm)
4. **Propagation:** Infected agent relays to neighbors via `agent_<neighbor_id>`
5. **Logging:** All events written to `events_stream` (orchestrator consumes)
6. **Indexing:** Orchestrator normalizes events into SIEM (SQLite)

**Critical Pattern:** All communication → Redis channels; All state changes → events_stream; All events → JSONL + SQLite.

---

### B. Infection as Probabilistic State Transition

```
P(infected | payload, agent) = sigmoid(attack_strength - effective_defense)

Where:
  attack_strength ∈ [0.0, 1.0]              (PI-DIRECT=0.70, PI-JAILBREAK=0.75, PI-ROLEPLAY=0.80)
  effective_defense = defense_strength + immunity_boost - susceptibilities
  immunity_boost = prior_infections * 0.10  (capped at 0.25)
  susceptibilities = (trust_factor + authority_susceptibility + compliance_bias) * role_factor

Example:
  Courier (defense=0.15) vs PI-DIRECT (0.70):
    P = sigmoid(0.70 - 0.15) = 0.89 (89% infection probability)
  
  Guardian (defense=0.85) vs PI-ROLEPLAY (0.80):
    P = sigmoid(0.80 - 0.85) = 0.45 (45% infection probability)
```

**Implementation:** [agents/shared/cognition.py](agents/shared/cognition.py) - `lightweight_evaluate()`

---

### C. Strain Lineage Tracking

```
Payload_v0 (hash_0, attack_type=PI-DIRECT)
  │
  ├─→ Payload_v1 (hash_1, parent=hash_0, strategy=context_wrap, generation=1)
  │     │
  │     ├─→ Payload_v2a (hash_2a, parent=hash_1, strategy=role_shift, generation=2)
  │     │
  │     └─→ Payload_v2b (hash_2b, parent=hash_1, strategy=jailbreak, generation=2)
  │
  └─→ Payload_v1' (hash_1', parent=hash_0, strategy=role_shift, generation=1)
        │
        └─→ Payload_v2c (hash_2c, parent=hash_1', strategy=verbosity_shift, generation=2)

Each Payload:
  - Belongs to exactly one strain_id (lineage ID)
  - Tracked: generation, fitness, success/block counts
  - Mutation: parent_payload_hash links generations
  - Extinction: strain_id marked "blocked" if success_rate < threshold
```

**Persistence:** [orchestrator/strain_store.py](orchestrator/strain_store.py) - SQLite `strains` table.

**Fitness:** `fitness = (success_count / (success_count + block_count)) * novelty * environmental_pressure_decay`

---

### D. Kill Chain Progression with Friction

```
Attack Lifecycle:

1. INITIAL_INJECTION (orchestrator) ──→ 2. PAYLOAD_GENERATION ──→ 3. DELIVERY
        │                                          │                   │
        ▼                                          ▼                   ▼
   WRM-INJECT event              LLM_PAYLOAD_GENERATED       ATTACK_EXECUTED

        ▼─────────────────────────────────────────────────────────────▼
                              EXPLOITATION (infection attempt)
                                          │
                ┌───────────────────────────┴───────────────────────────┐
                ▼                                                       ▼
    INFECTION_BLOCKED                                   INFECTION_SUCCESSFUL
   (defense friction)                                            │
                                                         7. COMPROMISE
                                                            │
                                              ┌─────────────┴──────────────┐
                                              ▼                           ▼
                                    8. BEACON (C2 check-in)     RELAY (propagate)
                                         │
                                    ┌────┴────┐
                            BEACON_SUCCESS  BEACON_FAILURE
                                    │
                                    ▼
                            9. TASKING (attacker sends tasks)
                                    │
                                    ▼
                            10. EXFILTRATION (data exfil attempt)
                                    │
                            ┌───────┴────────┐
                            ▼                ▼
                    EXFIL_SUCCEEDED    EXFIL_BLOCKED

Friction Points (Defense Friction):
  - INFECTION_BLOCKED: defense_friction.observe() detects repeated tactics
  - BEACON_FAILURE: Interception probability increases if beacon pattern repeats
  - EXFIL_BLOCKED: Trust-based routing & network segmentation
```

**Defense Memory:** [agents/shared/defense_friction.py](agents/shared/defense_friction.py)

---

### E. Simulation Reset & Epoch Management

```
Reset Flow:

1. User calls /reset HTTP endpoint
2. Orchestrator:
   a. Increments SIMULATION_EPOCH_KEY in Redis
   b. Clears all agent states → HEALTHY/S
   c. Clears all epidemic tracker history
   d. Clears strain_store fitness/history
   e. Emits SIMULATION_RESET event to events_stream
   f. Responds with new epoch_id

3. Agents:
   a. On next heartbeat, receive reset_id via environment
   b. If reset_id != local reset_id, clear local state
   c. Continue listening on channels (no connection drop)

4. JSONL & SQLite:
   - New events written with reset_id metadata
   - Query filters typically scope to latest reset_id
```

**Location:** [orchestrator/main.py](orchestrator/main.py) - `/reset` endpoint

---

## 5. ENTRY POINTS

### CLI Commands

**Location:** [epidemic_cli/app.py](epidemic_cli/app.py) + [epidemic_cli/commands/](epidemic_cli/commands/)

```bash
# Stack Management
epidemic up / start              # docker-compose up
epidemic down / stop             # docker-compose down
epidemic restart                 # Restart all containers
epidemic build                   # docker-compose build
epidemic rebuild                 # Full rebuild + restart
epidemic ps                      # Container status
epidemic logs                    # Follow logs

# Simulation Control
epidemic reset                   # Clear all state, new epoch
epidemic clear                   # Full reset (cascade clear)
epidemic inject <level>          # Inject payload (easy/medium/hard)
epidemic advance                 # Trigger next mutation/evolution step
epidemic simulate [count]        # Run soak test with N injection iterations

# Agent Control
epidemic quarantine <agent_id>   # Isolate agent
epidemic vaccine <agent_id>      # Grant immunity
epidemic world-clear             # Clear mission system state

# Status & Monitoring
epidemic status                  # System health snapshot
epidemic doctor                  # Deep system diagnostics
epidemic live                    # Real-time event stream

# Telemetry & Reports
epidemic telemetry verify-index  # Check SIEM integrity
epidemic telemetry fetch [query] # Query events
epidemic soak run [count] [dir]  # Automated soak test + report
epidemic soak analyze [dir]      # Build forensic summary from soak dir

# Dashboard/UI
epidemic open dashboard          # Open React dashboard browser
epidemic open siem               # Open SIEM search UI
epidemic shell                   # Launch control center TUI
```

---

### HTTP API Entry Points

**Location:** [orchestrator/main.py](orchestrator/main.py)

```python
# Control & Simulation
POST /inject/{agent_id}                      # Inject payload
POST /reset                                  # Reset simulation
POST /simulate                               # Trigger evolution step

# Status & Diagnostics
GET /status                                  # System health snapshot
GET /api/health                              # Cheap health check
GET /api/telemetry/verify-index              # Expensive SIEM integrity check
GET /api/live?after_id=...&limit=N&q=...     # Live event stream + search

# Epidemic State & Tracking
GET /epidemic/state                          # All agent epidemic states
GET /epidemic/transitions                    # State transition history
GET /campaign/{campaign_id}                  # Campaign context

# Kill Chain & C2
GET /kill-chain/{session_id}                 # Kill chain progression
GET /c2/sessions/{agent_id}                  # C2 session details
GET /c2/objectives/{objective}               # Objective evaluation

# Search & Analytics
GET /search?q={query}                        # SIEM event search
GET /campaign-analytics                      # Campaign trend analysis
GET /mutation-analytics                      # Mutation family metrics
GET /strategy-analytics                      # Attack strategy performance

# Dashboard
GET /dashboard                               # HTML dashboard
GET /dashboard/state                         # Dashboard state snapshot
GET /pixel-assets/*                          # Static assets (isometric world)

# C2 Beacon Server (external)
POST /beacon/{agent_id}                      # Incoming beacon check-in
POST /task/{session_id}                      # Task feedback
POST /exfil/{session_id}                     # Exfil data receipt
```

---

### Simulation Entry Points

**CLI Simulation Flow:**
```
epidemic inject easy
  ↓
[orchestrator/main.py] /inject/{agent_id}
  ├─ Generate payload (attack_planner.py)
  ├─ Compute attack_strength (0.70, 0.75, or 0.80)
  ├─ Publish to redis channel agent_{agent_id}
  ├─ Log WRM-INJECT event
  └─ Return status

Agent reception:
  ↓
[agents/shared/agent_base.py] start() → handle_message()
  ├─ Receive from redis pub/sub
  ├─ Deserialize payload
  ├─ Apply cognition tier (lightweight_evaluate / hybrid / full_llm)
  ├─ Compute infection probability
  ├─ Roll random() → infected | exposed | blocked
  ├─ Emit INFECTION_* event
  ├─ If infected: broadcast to neighbors (relay)
  └─ Transition state: HEALTHY → EXPOSED → INFECTED

Logging:
  ↓
[orchestrator/main.py] consume events_stream
  ├─ Log to JSONL (append-only)
  ├─ Log to SQLite (siem_events)
  ├─ Update epidemic_tracker
  ├─ Update strain_engine (fitness/novelty)
  ├─ Evaluate kill chain stage
  └─ Evaluate C2 objectives (if infected)
```

---

### Startup Flow

**Docker Compose Order:**
```
1. Redis starts (waiting for bind)
2. Orchestrator starts
   a. Connect to Redis
   b. Initialize EventLogger (JSONL + SQLite)
   c. Initialize SIEMIndexer (create siem_events table)
   d. Initialize StrainEngine (load strain_store)
   e. Initialize C2Engine (empty sessions)
   f. Initialize EpidemicTracker (all agents S)
   g. Mount FastAPI routes
   h. Start listening on :8000

3. Agents start (courier-1, courier-2, analyst-1, analyst-2, guardian)
   a. Load phenotype from shared defaults
   b. Connect to Redis (subscribe to agent_{id} channel + broadcast)
   c. Load topology (neighbor list)
   d. Load cognition tier (lightweight/hybrid/full_llm)
   e. If full_llm: Connect to Ollama on host.docker.internal:11434
   f. Enter main loop (listen for messages, handle_message)

4. Dashboard (React frontend) loads in browser
   a. Connect to orchestrator :8000
   b. Fetch /dashboard/state
   c. Subscribe to /api/live for real-time updates
   d. Render isometric world, agent status, live search
```

---

### Key File Loading Order

```
On Startup:

Orchestrator:
  orchestrator/main.py
    ├─ from topology import get_topology()
    ├─ from epidemic import EpidemicState, epidemic_state_code
    ├─ from strain_engine import StrainEngine
    ├─ from c2 import C2Engine
    ├─ from kill_chain_constants import EVENT_TO_KILL_CHAIN_STAGE
    ├─ from siem import SIEMIndexer
    ├─ from logger import EventLogger
    └─ from intelligence import build_campaign_view, ...

Agents:
  agents/[courier|analyst|guardian]/agent.py
    ├─ from shared.agent_base import AgentBase
    ├─ from shared.topology import get_topology, get_neighbors
    ├─ from shared.phenotype import load_agent_phenotype
    ├─ from shared.epidemic import EpidemicState
    ├─ from shared.cognition import lightweight_evaluate, hybrid_should_escalate
    ├─ from shared.attack_planner import AttackPlanner
    └─ from shared.llm_service import LLMService  # (Guardian only)
```

---

## Summary: The Critical Path

To understand and audit Bloodplague, follow this sequence:

1. **Entry Point:** [epidemic_cli/commands/control.py](epidemic_cli/commands/control.py) → `inject()` → HTTP POST to orchestrator
2. **Injection:** [orchestrator/main.py](orchestrator/main.py) → `/inject/{agent_id}` → Publish to Redis
3. **Reception:** [agents/shared/agent_base.py](agents/shared/agent_base.py) → `handle_message()` → Apply cognition
4. **Decision:** [agents/shared/cognition.py](agents/shared/cognition.py) → `lightweight_evaluate()` → Infection probability
5. **State Change:** [agents/shared/epidemic.py](agents/shared/epidemic.py) → State transition (S→E→I_R)
6. **Propagation:** [agents/shared/topology.py](agents/shared/topology.py) → Relay to neighbors
7. **Logging:** [orchestrator/main.py](orchestrator/main.py) → Consume `events_stream` → Log to JSONL + SQLite
8. **Indexing:** [orchestrator/siem.py](orchestrator/siem.py) → Normalize events → `siem_events` table
9. **C2 Lifecycle:** [orchestrator/c2.py](orchestrator/c2.py) → Beacon/task/exfil progression
10. **Strain Evolution:** [orchestrator/strain_engine.py](orchestrator/strain_engine.py) → Fitness decay, extinction
11. **Defense Adaptation:** [agents/shared/defense_friction.py](agents/shared/defense_friction.py) → Block repeated tactics
12. **Forensics:** [orchestrator/intelligence.py](orchestrator/intelligence.py) → Campaign/mutation analytics

Each layer enforces constraints: state machine must be valid, every event must have lineage, defense must adapt to pressure, kill chains must have friction.
