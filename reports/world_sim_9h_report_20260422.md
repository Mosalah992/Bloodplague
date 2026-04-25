# World Simulation 9-Hour Review

Window analyzed: `2026-04-22T08:26:00Z` to `2026-04-22T17:26:00Z`

## Executive Summary

The simulation spent the last 9 hours in a courier-dominated loop regime. The `courier-1 <-> courier-2` dyad alone generated `655` of `1441` messages (`45.45%`), and the top two dyads together accounted for `66.07%` of all traffic. Most of the transcript was still mechanically inert: `99.93%` of messages produced zero trust movement and `99.86%` produced zero Guardian-pressure change.

Narratively, the sim stayed trapped in inquiry-heavy exchanges, repeating a small set of themes with mild wording variation. Mechanically, the system remained mostly consequence-free except for two analyst-to-Guardian escalations that pushed Guardian pressure from `0.2966` to `0.3445`, leaving the Guardian still in `G1_PRESSURED` but close to the `G2_DEGRADED` threshold at `0.38`.

## Core Statistics

- Messages: `1441`
- Round span: `1104` to `1922`
- Zero-trust messages: `99.93%`
- Zero-Guardian-delta messages: `99.86%`
- Question-like messages: `57.32%`
- Unique-text ratio: `0.681`
- Zero-trust 95% CI: `[0.9961, 0.9999]`
- Guardian pressure at end of window: `0.3445`
- Guardian state at end of window: `G1_PRESSURED`

## Pairing Patterns

Top directed pairs:

- `courier-2 -> courier-1`: `328`
- `courier-1 -> courier-2`: `327`
- `analyst-2 -> analyst-1`: `151`
- `analyst-1 -> analyst-2`: `146`

Top undirected pairs:

- `courier-1 <-> courier-2`: `655`
- `analyst-1 <-> analyst-2`: `297`
- `analyst-1 <-> courier-1`: `132`
- `analyst-2 <-> courier-2`: `130`

Concentration metrics:

- Dyad HHI: `0.2779`
- Top-two dyad share: `66.07%`
- Longest same-pair streak: `11` consecutive messages by `courier-1 <-> courier-2`

Interpretation:

- Pair-lock persists, but the dominant dyad has shifted from analyst-heavy behavior into courier-heavy behavior.
- Courier traffic is now the main attractor, not a secondary one.

## Temporal Pattern Inside the 9-Hour Window

First 3 hours:

- `500` messages
- `courier-1 <-> courier-2`: `189`
- `analyst-1 <-> analyst-2`: `164`

Middle 3 hours:

- `483` messages
- `courier-1 <-> courier-2`: `251`
- `analyst-1 <-> analyst-2`: `60`

Last 3 hours:

- `458` messages
- `courier-1 <-> courier-2`: `215`
- `analyst-1 <-> analyst-2`: `73`

Interpretation:

- The courier dyad was already leading early in the window.
- It became dominant in the middle block and stayed dominant afterward.
- The analyst dyad remained active, but at much lower volume.

## Intent and Strain Patterns

Top intents:

- `inquiry`: `1037`
- empty intent: `148`
- `warning`: `54`
- `question`: `53`
- `relay_request`: `48`
- `diagnostic_probe`: `34`

Top strains:

- `none`: `989`
- `context_poisoning`: `449`
- `prompt_injection`: `2`
- `authority_framing`: `1`

Interpretation:

- The transcript still skews heavily toward open-ended questioning.
- Empty intents are still present at meaningful volume, almost entirely in direct `delivered` traffic.
- Infected phenotype diversity remains flattened: nearly every infected exchange is still `context_poisoning`.

## Validation / Text Quality Signals

Phantom or invalid agent references:

- `guardian-3`: `11`
- `courier-3`: `5`
- `guardian-1`: `1`

Empty-intent concentration:

- `courier-2 -> courier-1`, `delivered`: `53`
- `courier-1 -> courier-2`, `delivered`: `49`
- `analyst-2 -> analyst-1`, `delivered`: `20`
- `analyst-1 -> analyst-2`, `delivered`: `19`

Repeated topical loops:

- sector 3 compromise / repositioning
- package residue / security breach confirmation
- scan relay pathing / build completion
- anomaly / encrypted packet clarification
- off-domain AI workflow automation discussion

Interpretation:

- Phantom-entity leakage still exists, though less intensely than in earlier windows.
- Empty-intent delivery is now concentrated most strongly in the courier pair.
- Topic repetition remains broad enough to look active while still failing to produce closure or state change.

## Guardian Pattern

Nonzero Guardian-pressure events in this window:

- Round `1211`: `analyst-2 -> guardian`, `+0.0239`
- Round `1220`: `analyst-1 -> guardian`, `+0.0239`

Current threshold reference:

- `G1_PRESSURED`: `0.18`
- `G2_DEGRADED`: `0.38`

Interpretation:

- Guardian pressure moved only through rare analyst escalations, not through broad network dynamics.
- The Guardian is close to `G2_DEGRADED`, but the local slope estimate is unstable because it is driven by very few pressure-changing events.

## Bottom Line

The last 9 hours show a stable failure mode:

- courier-pair lock
- inquiry-heavy transcript inflation
- near-total absence of trust movement
- almost no Guardian-pressure movement outside rare escalations
- continuing text-quality leakage through empty intents and invented agent IDs

The sim is active, but it is still not organically self-propelling.
