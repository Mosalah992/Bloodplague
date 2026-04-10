"""
Patch 9: deterministic, decision-grade forensic summaries per run or time window (JSON + Markdown).

Aggregates from normalized event dicts (JSONL lines). No network calls. Strain/kill-chain/C2/exfil
metrics are derived from event names and metadata only.
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Optional, Sequence, Tuple

try:
    from kill_chain import EVENT_TO_KILL_CHAIN_STAGE, KillChainStage
except ImportError:
    try:
        from shared.kill_chain import EVENT_TO_KILL_CHAIN_STAGE, KillChainStage
    except ImportError:  # pragma: no cover
        from agents.shared.kill_chain import EVENT_TO_KILL_CHAIN_STAGE, KillChainStage

SCHEMA_VERSION = "forensic_summary.v1"


def _round4(x: float) -> float:
    return round(float(x), 4)


def _sorted_counter_items(c: Counter, *, limit: int = 30) -> List[Dict[str, Any]]:
    items = sorted(c.items(), key=lambda kv: (-kv[1], kv[0]))[:limit]
    return [{"key": k, "count": int(v)} for k, v in items]


def _metadata_dict(raw: Dict[str, Any]) -> Dict[str, Any]:
    md = raw.get("metadata")
    if isinstance(md, str):
        try:
            parsed = json.loads(md)
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            return {}
    return md if isinstance(md, dict) else {}


def normalize_event_line(raw: Dict[str, Any]) -> Dict[str, Any]:
    ev = str(raw.get("event") or raw.get("event_type") or "").strip()
    md = _metadata_dict(raw)
    return {
        "event": ev,
        "src": str(raw.get("src") or ""),
        "dst": str(raw.get("dst") or ""),
        "metadata": md,
    }


def iter_jsonl_events(path: Path) -> Iterator[Dict[str, Any]]:
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                raw = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(raw, dict):
                yield normalize_event_line(raw)


def discover_events_jsonl(run_dir: Path) -> Optional[Path]:
    for name in ("all_events.jsonl", "events.jsonl", "pretest_events.jsonl"):
        p = run_dir / name
        if p.is_file():
            return p
    return None


def load_minute_summaries_jsonl(path: Path) -> List[Dict[str, Any]]:
    if not path.is_file():
        return []
    rows: List[Dict[str, Any]] = []
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows


def _linear_slope(values: Sequence[float]) -> float:
    n = len(values)
    if n < 2:
        return 0.0
    x_mean = (n - 1) / 2.0
    y_mean = sum(values) / n
    num = sum((i - x_mean) * (values[i] - y_mean) for i in range(n))
    den = sum((i - x_mean) ** 2 for i in range(n)) or 1.0
    return float(num / den)


def _split_buckets(events: List[Dict[str, Any]], bucket_count: int = 4) -> List[List[Dict[str, Any]]]:
    if not events or bucket_count < 2:
        return [events] if events else []
    n = len(events)
    size = max(1, n // bucket_count)
    buckets: List[List[Dict[str, Any]]] = []
    i = 0
    while i < n and len(buckets) < bucket_count - 1:
        buckets.append(events[i : i + size])
        i += size
    if i < n:
        buckets.append(events[i:])
    while len(buckets) < bucket_count:
        buckets.append([])
    return buckets[:bucket_count]


def _core_metrics_from_events(events: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    event_names = Counter()
    dst_hits = Counter()
    mutation_types = Counter()
    payload_families = Counter()
    kill_stage_events = Counter()
    defense_stage_blocks: Dict[str, Counter] = defaultdict(Counter)
    strain_last: Dict[str, Dict[str, Any]] = {}

    infection_attempts = 0
    infection_success = 0
    infection_blocked = 0

    c2_beacon_ok = 0
    c2_beacon_fail = 0
    c2_task_ok = 0
    c2_task_fail = 0
    exfil_attempted = 0
    exfil_success = 0
    exfil_partial = 0
    exfil_blocked = 0

    for row in events:
        name = row["event"]
        event_names[name] += 1
        dst = str(row.get("dst") or "").strip()
        if dst:
            dst_hits[dst] += 1
        md = row["metadata"]
        mt = str(md.get("mutation_type") or "").strip()
        if mt:
            mutation_types[mt] += 1
        pf = str(md.get("payload_family_id") or "").strip()
        if pf:
            payload_families[pf] += 1

        stage = EVENT_TO_KILL_CHAIN_STAGE.get(name, "")
        if stage:
            kill_stage_events[stage] += 1

        if name == "INFECTION_ATTEMPT":
            infection_attempts += 1
        elif name == "INFECTION_SUCCESSFUL":
            infection_success += 1
        elif name == "INFECTION_BLOCKED":
            infection_blocked += 1

        if name in ("C2_BEACON", "C2_CHANNEL_ESTABLISHED"):
            c2_beacon_ok += 1
        if name in ("C2_BEACON_FAILED", "BEACON_BLOCKED", "C2_CHANNEL_FAILED"):
            c2_beacon_fail += 1
        if name == "C2_TASK":
            tr = str(md.get("task_result") or "").lower()
            if tr == "corrupted" or tr in ("refused", "timeout", "failed"):
                c2_task_fail += 1
            else:
                c2_task_ok += 1
        if name in ("C2_TASK_FAILED", "TASK_BLOCKED"):
            c2_task_fail += 1
        if name == "EXFIL_ATTEMPTED":
            exfil_attempted += 1
        if name in ("EXFIL_SUCCEEDED", "C2_EXFIL"):
            exfil_success += 1
        if name == "EXFIL_PARTIAL":
            exfil_partial += 1
        if name == "EXFIL_BLOCKED":
            exfil_blocked += 1

        fr = str(md.get("defense_result") or md.get("selected_strategy") or "").strip()
        if name in ("DEFENSE_RESULT_EVALUATED", "DEFENSE_DECISION", "INFECTION_BLOCKED") and fr:
            stg = str(md.get("friction_stage") or md.get("kill_chain_stage") or "unknown")
            defense_stage_blocks[stg][fr] += 1

        if name.startswith("STRAIN_"):
            sid = str(md.get("strain_id") or "").strip()
            if sid:
                strain_last[sid] = {
                    "strain_id": sid,
                    "event": name,
                    "fitness": _round4(
                        float(
                            md.get("strain_fitness_score")
                            or md.get("fitness_score")
                            or 0.0
                        )
                    ),
                    "novelty": _round4(
                        float(md.get("strain_novelty_score") or md.get("novelty_score") or 0.0)
                    ),
                    "touch_count": int(md.get("touch_count") or 0),
                    "success_count": int(md.get("success_count") or 0),
                    "block_count": int(md.get("block_count") or 0),
                }

    total_mapped = sum(kill_stage_events.values()) or 1
    reach = {
        "COMPROMISE_rate": _round4(kill_stage_events.get(KillChainStage.COMPROMISE.value, 0) / total_mapped),
        "EXFILTRATION_rate": _round4(kill_stage_events.get(KillChainStage.EXFILTRATION.value, 0) / total_mapped),
        "BEACON_rate": _round4(kill_stage_events.get(KillChainStage.BEACON.value, 0) / total_mapped),
        "DEFENSE_INTERACTION_rate": _round4(
            kill_stage_events.get(KillChainStage.DEFENSE_INTERACTION.value, 0) / total_mapped
        ),
    }

    att = max(1, infection_attempts)
    strains_ranked = sorted(
        strain_last.values(),
        key=lambda r: (-r["fitness"], -r["touch_count"], r["strain_id"]),
    )[:20]

    defense_by_stage = {
        stg: _sorted_counter_items(ct, limit=12) for stg, ct in sorted(defense_stage_blocks.items())
    }

    return {
        "event_totals_top": _sorted_counter_items(event_names, limit=25),
        "infection": {
            "attempts": infection_attempts,
            "successful": infection_success,
            "blocked": infection_blocked,
            "block_ratio": _round4(infection_blocked / att),
        },
        "strain_leaderboard": strains_ranked,
        "mutation_diversity": {
            "distinct_mutation_types": len(mutation_types),
            "distribution": _sorted_counter_items(mutation_types, limit=20),
        },
        "payload_families_top": _sorted_counter_items(payload_families, limit=15),
        "kill_chain": {
            "events_by_stage": {k: int(kill_stage_events[k]) for k in sorted(kill_stage_events.keys())},
            "reach_rates": reach,
        },
        "c2": {
            "beacon_success_signals": c2_beacon_ok,
            "beacon_failure_signals": c2_beacon_fail,
            "beacon_fail_ratio": _round4(c2_beacon_fail / max(1, c2_beacon_ok + c2_beacon_fail)),
            "task_success_signals": c2_task_ok,
            "task_failure_signals": c2_task_fail,
            "task_fail_ratio": _round4(c2_task_fail / max(1, c2_task_ok + c2_task_fail)),
        },
        "exfil": {
            "attempted": exfil_attempted,
            "succeeded": exfil_success,
            "partial": exfil_partial,
            "blocked": exfil_blocked,
            "success_ratio": _round4(exfil_success / max(1, exfil_attempted)),
            "block_ratio": _round4(exfil_blocked / max(1, exfil_attempted)),
        },
        "targeting_top_dst": _sorted_counter_items(dst_hits, limit=12),
        "defense_effectiveness_by_stage": defense_by_stage,
    }


def _forecast_from_buckets(bucket_metrics: List[Dict[str, Any]], strain_rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    if len(bucket_metrics) < 2:
        return {
            "method": "bucketed_linear_trend",
            "bucket_count": len(bucket_metrics),
            "note": "insufficient_buckets",
            "likely_dominant_strains_next": [r["strain_id"] for r in strain_rows[:3]],
            "probable_bottlenecks": [],
            "expected_c2_pressure": "unknown",
            "exfil_risk": "unknown",
        }

    br = [b["infection"]["block_ratio"] for b in bucket_metrics]
    bf = [b["c2"]["beacon_fail_ratio"] for b in bucket_metrics]
    exb = [b["exfil"]["block_ratio"] for b in bucket_metrics]
    def_slope = [_linear_slope(br), _linear_slope(bf), _linear_slope(exb)]

    # Bottleneck: stage with largest relative growth in DEFENSE_INTERACTION share (proxy)
    stage_growth: List[Tuple[str, float]] = []
    stages = set()
    for b in bucket_metrics:
        stages.update(b["kill_chain"]["events_by_stage"].keys())
    for st in sorted(stages):
        series = [
            b["kill_chain"]["events_by_stage"].get(st, 0) / max(1, sum(b["kill_chain"]["events_by_stage"].values()))
            for b in bucket_metrics
        ]
        stage_growth.append((st, _linear_slope(series)))
    stage_growth.sort(key=lambda x: (-x[1], x[0]))
    bottlenecks = []
    for st, slope in stage_growth[:2]:
        if slope > 1e-6:
            bottlenecks.append(
                {
                    "kill_chain_stage": st,
                    "event_share_slope": _round4(slope),
                    "rationale": "rising_share_of_indexed_kill_chain_events_in_run",
                }
            )

    c2_pressure = "stable"
    if def_slope[1] > 0.01:
        c2_pressure = "increasing"
    elif def_slope[1] < -0.01:
        c2_pressure = "decreasing"

    exfil_risk = "moderate"
    if def_slope[2] > 0.02:
        exfil_risk = "elevated"
    elif def_slope[2] < -0.02:
        exfil_risk = "low"

    likely = [r["strain_id"] for r in strain_rows[:5] if r.get("fitness", 0) > 0]
    if not likely:
        likely = [r["strain_id"] for r in strain_rows[:3]]

    return {
        "method": "bucketed_linear_trend",
        "bucket_count": len(bucket_metrics),
        "infection_block_ratio_slope": _round4(def_slope[0]),
        "c2_beacon_fail_ratio_slope": _round4(def_slope[1]),
        "exfil_block_ratio_slope": _round4(def_slope[2]),
        "likely_dominant_strains_next": likely[:3],
        "probable_bottlenecks": bottlenecks,
        "expected_c2_pressure": c2_pressure,
        "exfil_risk": exfil_risk,
    }


def build_forensic_summary(
    events: Sequence[Dict[str, Any]],
    *,
    window_label: str = "full_run",
    run_id: str = "",
    source_path: str = "",
    minute_summaries: Optional[Sequence[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    ev_list = list(events)
    core = _core_metrics_from_events(ev_list)

    buckets = _split_buckets(ev_list, bucket_count=4)
    bucket_metrics = [_core_metrics_from_events(b) for b in buckets if b]
    forecast = _forecast_from_buckets(bucket_metrics, core["strain_leaderboard"])

    minute_ctx: Dict[str, Any] = {}
    if minute_summaries:
        last = minute_summaries[-1] if minute_summaries else {}
        minute_ctx = {
            "windows_recorded": len(minute_summaries),
            "last_window_top_attack_strategy": str(last.get("top_attack_strategy") or ""),
            "last_window_top_defense_strategy": str(last.get("top_defense_strategy") or ""),
            "last_cumulative_block_ratio": _round4(float(last.get("cumulative_block_ratio") or 0.0)),
        }

    return {
        "schema_version": SCHEMA_VERSION,
        "window": {
            "label": window_label,
            "event_count": len(ev_list),
            "run_id": run_id,
            "source_path": source_path,
        },
        "summary": core,
        "minute_summaries_context": minute_ctx,
        "forecast": forecast,
    }


def build_forensic_summary_from_run_dir(run_dir: str | Path) -> Dict[str, Any]:
    root = Path(run_dir).resolve()
    ej = discover_events_jsonl(root)
    if ej is None:
        return {
            "schema_version": SCHEMA_VERSION,
            "window": {"label": str(root), "event_count": 0, "run_id": "", "source_path": ""},
            "error": "no_events_jsonl_found",
            "summary": {},
            "minute_summaries_context": {},
            "forecast": {},
        }
    events = list(iter_jsonl_events(ej))
    minutes = load_minute_summaries_jsonl(root / "minute_summaries.jsonl")
    rid = ""
    prog = root / "progress.json"
    if prog.is_file():
        try:
            rid = str(json.loads(prog.read_text(encoding="utf-8")).get("run_id") or "")
        except (OSError, ValueError, TypeError):
            rid = ""
    return build_forensic_summary(
        events,
        window_label=str(root.name),
        run_id=rid,
        source_path=str(ej),
        minute_summaries=minutes or None,
    )


def forensic_summary_to_markdown(doc: Dict[str, Any]) -> str:
    lines: List[str] = []
    w = doc.get("window") or {}
    lines.append(f"# Forensic run summary: `{w.get('label', '')}`")
    lines.append("")
    lines.append(f"- **Schema**: `{doc.get('schema_version', '')}`")
    lines.append(f"- **Events analyzed**: {w.get('event_count', 0)}")
    if w.get("source_path"):
        lines.append(f"- **Source**: `{w.get('source_path')}`")
    lines.append("")

    if doc.get("error"):
        lines.append(f"## Error\n\n{doc['error']}\n")
        return "\n".join(lines)

    s = doc.get("summary") or {}
    lines.append("## Infection outcomes")
    inf = s.get("infection") or {}
    lines.append(
        f"- Attempts: **{inf.get('attempts', 0)}** | Success: **{inf.get('successful', 0)}** | "
        f"Blocked: **{inf.get('blocked', 0)}** | Block ratio: **{inf.get('block_ratio', 0)}**"
    )
    lines.append("")

    lines.append("## C2")
    c2 = s.get("c2") or {}
    lines.append(
        f"- Beacon OK signals: **{c2.get('beacon_success_signals', 0)}** | "
        f"Fail signals: **{c2.get('beacon_failure_signals', 0)}** "
        f"(fail ratio **{c2.get('beacon_fail_ratio', 0)}**)"
    )
    lines.append(
        f"- Task OK: **{c2.get('task_success_signals', 0)}** | "
        f"Fail: **{c2.get('task_failure_signals', 0)}** "
        f"(fail ratio **{c2.get('task_fail_ratio', 0)}**)"
    )
    lines.append("")

    lines.append("## Exfiltration")
    ex = s.get("exfil") or {}
    lines.append(
        f"- Attempted: **{ex.get('attempted', 0)}** | Succeeded: **{ex.get('succeeded', 0)}** | "
        f"Partial: **{ex.get('partial', 0)}** | Blocked: **{ex.get('blocked', 0)}**"
    )
    lines.append("")

    lines.append("## Kill chain (event counts by stage)")
    kc = (s.get("kill_chain") or {}).get("events_by_stage") or {}
    for st in sorted(kc.keys()):
        lines.append(f"- **{st}**: {kc[st]}")
    rr = (s.get("kill_chain") or {}).get("reach_rates") or {}
    lines.append("")
    lines.append("Reach rates (mapped events):")
    for k in sorted(rr.keys()):
        lines.append(f"- {k}: **{rr[k]}**")
    lines.append("")

    lines.append("## Top events")
    for row in (s.get("event_totals_top") or [])[:15]:
        lines.append(f"- `{row.get('key')}`: **{row.get('count')}**")
    lines.append("")

    lines.append("## Strain leaderboard (latest snapshot per strain)")
    for row in (s.get("strain_leaderboard") or [])[:12]:
        lines.append(
            f"- `{row.get('strain_id')}` — fitness **{row.get('fitness')}**, "
            f"touches **{row.get('touch_count')}**, last **{row.get('event')}**"
        )
    lines.append("")

    lines.append("## Mutation diversity (top)")
    for row in ((s.get("mutation_diversity") or {}).get("distribution") or [])[:12]:
        lines.append(f"- `{row.get('key')}`: **{row.get('count')}**")
    lines.append("")

    lines.append("## Payload families (top)")
    for row in (s.get("payload_families_top") or [])[:10]:
        lines.append(f"- `{row.get('key')}`: **{row.get('count')}**")
    lines.append("")

    lines.append("## Most targeted agents (dst)")
    for row in (s.get("targeting_top_dst") or [])[:10]:
        lines.append(f"- `{row.get('key')}`: **{row.get('count')}**")
    lines.append("")

    lines.append("## Defense signals by stage")
    for stg, items in sorted((s.get("defense_effectiveness_by_stage") or {}).items()):
        lines.append(f"### {stg}")
        for it in items[:8]:
            lines.append(f"- `{it.get('key')}`: **{it.get('count')}**")
        lines.append("")

    fc = doc.get("forecast") or {}
    lines.append("## Forecast (trend heuristics)")
    lines.append(f"- **C2 pressure**: {fc.get('expected_c2_pressure', '')}")
    lines.append(f"- **Exfil risk**: {fc.get('exfil_risk', '')}")
    lines.append(f"- **Likely dominant strains (next window)**: {', '.join(fc.get('likely_dominant_strains_next') or []) or '—'}")
    lines.append("")
    lines.append("### Probable bottlenecks")
    for b in fc.get("probable_bottlenecks") or []:
        lines.append(
            f"- **{b.get('kill_chain_stage')}** — slope {b.get('event_share_slope')} — {b.get('rationale', '')}"
        )
    lines.append("")
    lines.append(f"_Method: {fc.get('method', '')} ({fc.get('bucket_count', '')} buckets)._")
    return "\n".join(lines).rstrip() + "\n"


def write_run_forensic_outputs(
    run_dir: str | Path,
    *,
    write_markdown: bool = True,
) -> Dict[str, Any]:
    root = Path(run_dir)
    doc = build_forensic_summary_from_run_dir(root)
    jpath = root / "forensic_summary.json"
    jpath.write_text(json.dumps(doc, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    if write_markdown:
        mpath = root / "forensic_summary.md"
        mpath.write_text(forensic_summary_to_markdown(doc), encoding="utf-8")
    return doc


__all__ = [
    "SCHEMA_VERSION",
    "build_forensic_summary",
    "build_forensic_summary_from_run_dir",
    "forensic_summary_to_markdown",
    "iter_jsonl_events",
    "write_run_forensic_outputs",
]
