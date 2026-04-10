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