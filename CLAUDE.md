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

## System Status - 2026-04-25 - Comprehensive Audit Complete

### Context

A comprehensive audit of the Bloodplague codebase was completed on April 25, 2026 to assess alignment with CLAUDE.md principles and identify consistency gaps between documented design intent and runtime behavior.

**Full audit report:** See [AUDIT_REPORT_20250425.md](AUDIT_REPORT_20250425.md)

### Audit Summary

**Issues Found:** 23 total  
- 3 HIGH-risk (immediate action required)
- 8 MEDIUM-risk (next sprint)
- 12 LOW-risk (monitor/document)

**Architecture Status:** STRONG  
The codebase demonstrates excellent foundational architecture:
- ✅ Event correlation and forensic enrichment (well-designed)
- ✅ Strain lineage tracking with fitness metrics (comprehensive)
- ✅ 12-stage kill chain mapping (complete)
- ✅ Defense friction framework (well-architected)
- ✅ Mutation diversity mechanisms (functional)

**Principle Alignment:** PARTIAL  
Several HIGH-risk gaps between documented principles (CLAUDE.md) and runtime enforcement:

### Critical Issues (Immediate Action)

**Issue 1: Template Fallback Budget Not Enforced** — *Violates Principle #4*  
- Location: `agents/shared/attack_planner.py`, `select_mutation()`
- Problem: Budget checked but mutation selected anyway; system can use unlimited fallback mutations
- Impact: Defeats evolutionary pressure; repetition penalty not enforced
- Fix: Add explicit rejection when fallback budget exhausted; emit FALLBACK_BUDGET_EXHAUSTED event

**Issue 2: Novelty Scoring Not Applied** — *Violates Principle #1*  
- Location: `agents/shared/attack_planner.py`, `select_mutation()`
- Problem: Recent mutation choices not passed to novelty_score_for_candidate(); function always receives empty list
- Impact: System cannot detect or penalize repeated mutation patterns
- Fix: Extract payload fingerprints from recent_mutation_choices; pass to novelty scoring

**Issue 3: Friction Decision Ignored** — *Violates Principle #5*  
- Location: `orchestrator/c2.py`, `agents/shared/defense_friction.py`
- Problem: FrictionDecision computed by defense but never applied to C2 success rates
- Impact: Defense has zero observable effect on infection success; system cannot demonstrate defensive adaptation
- Fix: Apply friction_decision.effective_block_p to modify beacon/exfil success probability

### High-Priority Issues (Next Sprint)

**Issue 4:** Strain blacklist permanent (no expiration) — blocks strains forever  
**Issue 5:** Bootstrap integrity checks deferred by default — allows corruption to accumulate  
**Issue 6:** Event ID correlation broken across agent boundaries — multi-hop chains cannot be reconstructed  
**Issue 7:** Phenotype traits never update — agents don't learn or adapt from experience  
**Issue 8:** SIEM sync blocks event loop — orchestrator starvation under load  

See [AUDIT_REPORT_20250425.md](AUDIT_REPORT_20250425.md) for full details and recommended fixes.

### Recommended Configuration Defaults

```bash
# High-risk fixes (required)
# These should be enforced in code, not config

# Medium-risk mitigations (recommended)
DEFENSE_FRICTION_BLACKLIST_TTL_S=3600    # Add: expire blacklist
TELEMETRY_BOOTSTRAP_INTEGRITY=1          # Change: enable by default (was 0)
MUTATION_CROWDING_PENALTY_CAP=0.12       # Reduce: from 0.22

# Performance optimization (recommended)
SIEM_LIVE_SYNC_ENABLED=0                 # Keep: off by default
SIEM_SYNC_LIMIT=200                      # Keep: reasonable
WORLD_AUTO_ADVANCE_INTERVAL_S=8          # Keep: reasonable
```

### Operational Notes (Current)

- Use `http://localhost:8000` on Windows Docker Desktop. `127.0.0.1:8000` can still be unreliable due to Docker loopback behavior.
- Do not put `logger.verify_integrity()`, `siem_indexer.health()`, full SIEM syncs, or full-table analytics directly in hot async routes.
- Keep `/api/health` cheap. Use `/api/telemetry/verify-index` for expensive integrity verification.
- Keep `SIEM_LIVE_SYNC_ENABLED=0` unless intentionally testing live forced sync under controlled load.
- External C2 beacon forwarding may remain enabled for demos, but it must stay off the event loop.
- If Pixel Lab hangs, first check for event-loop starvation by probing `/status`, `/api/health`, `/api/live`, and `/pixel-assets/asset-index.json` concurrently.
- If simulation diverges from expected behavior, check audit report for known gaps between principle and implementation.

---

## Immediate Action Items

The three HIGH-risk issues must be fixed to restore alignment with CLAUDE.md principles. Each fix is isolated and can be implemented independently but should be tested in sequence.

### Fix #1: Template Fallback Budget Enforcement (agents/shared/attack_planner.py)

**Timeline:** This week  
**Risk Level:** HIGH  
**Principle:** #4 - Mutation Is Mandatory, Not Optional

```python
# Current: budget checked but mutation still selected
# Fix: Add explicit rejection
if not fallback_budget_allows(fallback_window):
    emit_event("FALLBACK_BUDGET_EXHAUSTED", {
        "strain_id": self.strain_id,
        "fallback_ratio": current_ratio,
        "action": "reject_mutation"
    })
    # Choose non-fallback mutation or fail gracefully
    return None
```

**Test:** `test_fallback_budget_enforcement()` in tests/test_mutation_strategy.py

---

### Fix #2: Novelty Scoring from Mutation History (agents/shared/attack_planner.py)

**Timeline:** This week  
**Risk Level:** HIGH  
**Principle:** #1 - Repetition Is a Bug

```python
# Current: recent_fingerprints always empty
# Fix: Extract from recent_mutation_choices
recent_fingerprints = [
    self.extract_payload_fingerprint(mut)
    for mut in self.memory.recent_mutation_choices[-20:]
]
novelty_score = novelty_score_for_candidate(
    candidate,
    planned_payload_stub,
    recent_fingerprints=recent_fingerprints  # ← Pass actual data
)
```

**Test:** `test_novelty_score_from_mutation_history()` in tests/test_mutation_strategy.py

---

### Fix #3: Friction Decision to C2 Success (orchestrator/c2.py)

**Timeline:** This week  
**Risk Level:** HIGH  
**Principle:** #5 - Defense Must Shape the System

```python
# Current: FrictionDecision computed but not used
friction_decision = friction_memory.decide_c2(...)
# ✗ Not applied to success rates

# Fix: Apply decision to success probability
effective_block_p = friction_decision.effective_block_p
beacon_success_p = base_beacon_success * (1.0 - effective_block_p)

emit_event("DEFENSE_FRICTION_APPLIED", {
    "stage": "BEACON",
    "friction_multiplier": effective_block_p,
    "adjusted_success_p": beacon_success_p
})
```

**Test:** `test_friction_decision_affects_c2_success()` in tests/test_c2.py

---

## Development Workflow Going Forward

Before making any changes to the following critical components:

**Always run impact analysis:**
- `agents/shared/attack_planner.py` (mutation selection)
- `agents/shared/defense_friction.py` (friction memory)
- `orchestrator/c2.py` (C2 operations)
- `orchestrator/strain_engine.py` (strain fitness)
- `orchestrator/main.py` (event consumption loop)

**After implementing fixes:**
1. Run full test suite: `pytest tests/ -v`
2. Run audit test pack: `pytest tests/test_mutation_strategy.py tests/test_attack_planner.py tests/test_c2.py`
3. Run soak test: `python -m pytest tests/test_siem_soak_resilience.py` (verify no regressions)
4. Verify audit report still reflects reality: `grep -r "TODO\|FIXME\|HACK" orchestrator/ agents/` (none should exist)

---


# GitNexus — Code Intelligence

This project is indexed by GitNexus as **Bloodplague-main** (52818 symbols, 84037 relationships, 300 execution flows). Use the GitNexus MCP tools to understand code, assess impact, and navigate safely.

> If any GitNexus tool warns the index is stale, run `npx gitnexus analyze` in terminal first.

## Always Do

- **MUST run impact analysis before editing any symbol.** Before modifying a function, class, or method, run `gitnexus_impact({target: "symbolName", direction: "upstream"})` and report the blast radius (direct callers, affected processes, risk level) to the user.
- **MUST run `gitnexus_detect_changes()` before committing** to verify your changes only affect expected symbols and execution flows.
- **MUST warn the user** if impact analysis returns HIGH or CRITICAL risk before proceeding with edits.
- When exploring unfamiliar code, use `gitnexus_query({query: "concept"})` to find execution flows instead of grepping. It returns process-grouped results ranked by relevance.
- When you need full context on a specific symbol — callers, callees, which execution flows it participates in — use `gitnexus_context({name: "symbolName"})`.

## When Debugging

1. `gitnexus_query({query: "<error or symptom>"})` — find execution flows related to the issue
2. `gitnexus_context({name: "<suspect function>"})` — see all callers, callees, and process participation
3. `READ gitnexus://repo/Bloodplague-main/process/{processName}` — trace the full execution flow step by step
4. For regressions: `gitnexus_detect_changes({scope: "compare", base_ref: "main"})` — see what your branch changed

## When Refactoring

- **Renaming**: MUST use `gitnexus_rename({symbol_name: "old", new_name: "new", dry_run: true})` first. Review the preview — graph edits are safe, text_search edits need manual review. Then run with `dry_run: false`.
- **Extracting/Splitting**: MUST run `gitnexus_context({name: "target"})` to see all incoming/outgoing refs, then `gitnexus_impact({target: "target", direction: "upstream"})` to find all external callers before moving code.
- After any refactor: run `gitnexus_detect_changes({scope: "all"})` to verify only expected files changed.

## Never Do

- NEVER edit a function, class, or method without first running `gitnexus_impact` on it.
- NEVER ignore HIGH or CRITICAL risk warnings from impact analysis.
- NEVER rename symbols with find-and-replace — use `gitnexus_rename` which understands the call graph.
- NEVER commit changes without running `gitnexus_detect_changes()` to check affected scope.

## Tools Quick Reference

| Tool | When to use | Command |
|------|-------------|---------|
| `query` | Find code by concept | `gitnexus_query({query: "auth validation"})` |
| `context` | 360-degree view of one symbol | `gitnexus_context({name: "validateUser"})` |
| `impact` | Blast radius before editing | `gitnexus_impact({target: "X", direction: "upstream"})` |
| `detect_changes` | Pre-commit scope check | `gitnexus_detect_changes({scope: "staged"})` |
| `rename` | Safe multi-file rename | `gitnexus_rename({symbol_name: "old", new_name: "new", dry_run: true})` |
| `cypher` | Custom graph queries | `gitnexus_cypher({query: "MATCH ..."})` |

## Impact Risk Levels

| Depth | Meaning | Action |
|-------|---------|--------|
| d=1 | WILL BREAK — direct callers/importers | MUST update these |
| d=2 | LIKELY AFFECTED — indirect deps | Should test |
| d=3 | MAY NEED TESTING — transitive | Test if critical path |

## Resources

| Resource | Use for |
|----------|---------|
| `gitnexus://repo/Bloodplague-main/context` | Codebase overview, check index freshness |
| `gitnexus://repo/Bloodplague-main/clusters` | All functional areas |
| `gitnexus://repo/Bloodplague-main/processes` | All execution flows |
| `gitnexus://repo/Bloodplague-main/process/{name}` | Step-by-step execution trace |

## Self-Check Before Finishing

Before completing any code modification task, verify:
1. `gitnexus_impact` was run for all modified symbols
2. No HIGH/CRITICAL risk warnings were ignored
3. `gitnexus_detect_changes()` confirms changes match expected scope
4. All d=1 (WILL BREAK) dependents were updated

## Keeping the Index Fresh

After committing code changes, the GitNexus index becomes stale. Re-run analyze to update it:

```bash
npx gitnexus analyze
```

If the index previously included embeddings, preserve them by adding `--embeddings`:

```bash
npx gitnexus analyze --embeddings
```

To check whether embeddings exist, inspect `.gitnexus/meta.json` — the `stats.embeddings` field shows the count (0 means no embeddings). **Running analyze without `--embeddings` will delete any previously generated embeddings.**

> Claude Code users: A PostToolUse hook handles this automatically after `git commit` and `git merge`.

## CLI

| Task | Read this skill file |
|------|---------------------|
| Understand architecture / "How does X work?" | `.claude/skills/gitnexus/gitnexus-exploring/SKILL.md` |
| Blast radius / "What breaks if I change X?" | `.claude/skills/gitnexus/gitnexus-impact-analysis/SKILL.md` |
| Trace bugs / "Why is X failing?" | `.claude/skills/gitnexus/gitnexus-debugging/SKILL.md` |
| Rename / extract / split / refactor | `.claude/skills/gitnexus/gitnexus-refactoring/SKILL.md` |
| Tools, resources, schema reference | `.claude/skills/gitnexus/gitnexus-guide/SKILL.md` |
| Index, status, clean, wiki CLI commands | `.claude/skills/gitnexus/gitnexus-cli/SKILL.md` |

<!-- gitnexus:end -->
