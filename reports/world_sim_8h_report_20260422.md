# World Simulation 8-Hour Review

Window analyzed: `2026-04-21T23:17:59Z` to `2026-04-22T07:17:59Z`

## Executive Summary

The simulation is still dominated by local conversational loops rather than system-driving interaction. Over the last 8 hours, the top two dyads accounted for `70.41%` of all transcript traffic, `99.70%` of messages produced zero trust movement, and `99.54%` produced zero Guardian-pressure change. That combination points to a sim that is verbose but mechanically weak.

The immediate trajectory, if nothing changed, would be continued high-volume inquiry loops with almost no relationship movement and a slow continued Guardian-pressure climb. Using a simple linear projection on observed throughput and Guardian-pressure slope, the next 2 hours would likely add about `329.5` messages, of which roughly `328.5` would still carry zero trust delta, while Guardian pressure would continue drifting from `0.2487` toward the `G2` threshold at `0.38` in about `7.71` hours.

## Core Statistics

- Messages in window: `1318`
- Zero-trust messages: `99.70%`
- Zero-Guardian-delta messages: `99.54%`
- Question-like messages: `57.66%`
- Unique-text ratio: `0.660`
- Zero-trust 95% CI: `[0.9922, 0.9988]`
- Guardian state at end of window: `G1_PRESSURED`
- Guardian pressure at end of window: `0.2487`
- Estimated Guardian-pressure slope: `0.0170` per hour

## Interaction Concentration

Top directed pairs:

- `analyst-1 -> analyst-2`: `342`
- `analyst-2 -> analyst-1`: `327`
- `courier-1 -> courier-2`: `130`
- `courier-2 -> courier-1`: `129`

Top undirected pairs:

- `analyst-1 <-> analyst-2`: `669`
- `courier-1 <-> courier-2`: `259`
- `analyst-1 <-> courier-1`: `99`
- `analyst-2 <-> courier-1`: `98`

Concentration metrics:

- Dyad HHI: `0.3175`
- Share of traffic held by top two dyads: `70.41%`

Interpretation:

- The sim is still pair-locked.
- Analyst traffic dominates the graph.
- Courier-to-courier loops remain a secondary but still strong attractor.

## Semantic and Mechanical Patterns

Intent distribution:

- `inquiry`: `1024`
- empty intent: `166`
- `warning`: `27`
- `question`: `26`
- `relay_request`: `24`
- `answer`: `15`

Strain distribution:

- `none`: `915`
- `context_poisoning`: `395`
- `authority_framing`: `4`
- `prompt_injection`: `4`

Observed patterns:

- Most of the transcript is inquiry-shaped, which keeps conversations open but rarely resolves or escalates them.
- Empty intent labels are still concentrated in direct `delivered` messages, not proximity chat.
- Infection phenotype diversity remains compressed; almost every infected line is still `context_poisoning`.
- The log still contains repeated nonexistent entity references: `guardian-2` (`52` mentions), `courier-3` (`27`), and `guardian-1` (`10`).
- Ambiguous identity drift also appears in lines such as `my own activity`, which suggests text-generation instability rather than grounded world-state.

## Projection

Simple throughput extrapolation from the last 8 hours:

- Expected messages in next 2 hours: `329.5`
- Expected zero-trust messages in next 2 hours: `328.5`
- Expected zero-Guardian-delta messages in next 2 hours: `328.0`

Behavioral projection if unchanged:

- The sim continues to produce mostly analyst-pair and courier-pair loops.
- Relationship state remains nearly frozen because direct and proximity messages rarely move trust.
- Guardian pressure keeps rising slowly from analyst escalations, but not because the broader graph is becoming more interactive or informative.
- Narrative quality degrades further as empty intents and phantom-agent mentions accumulate.

## Fixes Started

The following fixes were implemented after this review:

- Direct message validation now requires a non-empty intent.
- Direct and proximity text now reject nonexistent numbered-agent references such as `courier-3` and `guardian-2`.
- Direct and proximity text now reject ambiguous self-reference patterns such as `my own activity`.
- Ordinary direct messages now apply small semantic trust deltas by intent, so `inquiry`, `answer`, `warning`, and similar exchanges stop recording as mechanically inert by default.
- Proximity prompts now include the allowed roster and explicitly forbid invented agents.

## Verification

- `python3 -m pytest tests/test_world_conversation.py tests/test_persistent_world_mechanics.py -q`
- `python3 -m pytest tests/test_world_spatial.py tests/test_world_structures.py tests/test_world_conversation.py tests/test_persistent_world_mechanics.py -q`

Both passed after the fixes. The `.pytest_cache` warning is environmental and comes from a root-owned cache directory, not from the code changes.
