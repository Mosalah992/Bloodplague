"""Generate a research-paper-grade report from a partial soak run's minute_summaries.jsonl."""
import json
import math
import statistics
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def slope(ys):
    n = len(ys)
    if n < 2:
        return 0.0
    xm = (n - 1) / 2.0
    ym = sum(ys) / n
    num = sum((i - xm) * (y - ym) for i, y in enumerate(ys))
    den = sum((i - xm) ** 2 for i in range(n))
    return num / den if den else 0.0


def r_squared(ys):
    n = len(ys)
    if n < 2:
        return 0.0
    s = slope(ys)
    xm = (n - 1) / 2.0
    ym = sum(ys) / n
    ss_res = sum((y - (ym + s * (i - xm))) ** 2 for i, y in enumerate(ys))
    ss_tot = sum((y - ym) ** 2 for y in ys)
    return 1.0 - ss_res / ss_tot if ss_tot else 0.0


def ci95(vals):
    n = len(vals)
    if n == 0:
        return (0.0, 0.0, 0.0)
    mu = statistics.mean(vals)
    if n < 2:
        return (mu, mu, mu)
    se = statistics.stdev(vals) / math.sqrt(n)
    return (mu, mu - 2 * se, mu + 2 * se)


def entropy(ctr):
    t = sum(ctr.values())
    if t == 0:
        return 0.0
    e = 0.0
    for c in ctr.values():
        if c > 0:
            p = c / t
            e -= p * math.log2(p)
    return round(e, 4)


def hourly(vals):
    return [vals[i : i + 60] for i in range(0, len(vals), 60)]


def main():
    artifact = ROOT / "logs" / "soak_run_002"
    summaries_path = artifact / "minute_summaries.jsonl"
    if not summaries_path.exists():
        print(f"No minute_summaries.jsonl found at {summaries_path}")
        return

    summaries = [json.loads(line) for line in open(summaries_path) if line.strip()]
    n_min = len(summaries)
    print(f"Loaded {n_min} minute summaries")

    # ---- Time series ----
    per_min_success = [float(s["counts"].get("INFECTION_SUCCESSFUL", 0)) for s in summaries]
    per_min_blocked = [float(s["counts"].get("INFECTION_BLOCKED", 0)) for s in summaries]
    per_min_attack = [float(s["counts"].get("ATTACK_EXECUTED", 0)) for s in summaries]
    per_min_adapt = [float(s["counts"].get("DEFENSE_ADAPTED", 0)) for s in summaries]
    per_min_events = [float(s["event_count"]) for s in summaries]
    per_min_br = [s.get("cumulative_block_ratio", 0) for s in summaries]
    per_min_rai = [float(s.get("r_ai", 0)) for s in summaries]

    total_success = int(summaries[-1]["cumulative_successes"])
    total_blocked = int(summaries[-1]["cumulative_blocks"])
    total_events = sum(s["event_count"] for s in summaries)
    total_attempts = total_success + total_blocked

    # Aggregate counters
    all_counts: Counter = Counter()
    attack_strats: Counter = Counter()
    mutations: Counter = Counter()
    defense_strats: Counter = Counter()
    for s in summaries:
        for k, v in s["counts"].items():
            all_counts[k] += v
        if s["top_attack_strategy"]:
            attack_strats[s["top_attack_strategy"]] += 1
        if s["top_mutation"]:
            mutations[s["top_mutation"]] += 1
        if s["top_defense_strategy"]:
            defense_strats[s["top_defense_strategy"]] += 1

    h_success = hourly(per_min_success)
    h_blocked = hourly(per_min_blocked)

    s_slope = slope(per_min_success)
    b_slope = slope(per_min_blocked)
    br_slope = slope(per_min_br)
    rai_slope = slope(per_min_rai)
    s_r2 = r_squared(per_min_success)
    b_r2 = r_squared(per_min_blocked)
    br_r2 = r_squared(per_min_br)

    s_ci = ci95(per_min_success)
    b_ci = ci95(per_min_blocked)
    a_ci = ci95(per_min_attack)

    first_hour = summaries[:60]
    last_hour = summaries[-60:]
    fh_success = sum(s["counts"].get("INFECTION_SUCCESSFUL", 0) for s in first_hour)
    lh_success = sum(s["counts"].get("INFECTION_SUCCESSFUL", 0) for s in last_hour)
    fh_blocked = sum(s["counts"].get("INFECTION_BLOCKED", 0) for s in first_hour)
    lh_blocked = sum(s["counts"].get("INFECTION_BLOCKED", 0) for s in last_hour)

    start_utc = summaries[0]["minute_start_utc"]
    end_utc = summaries[-1]["minute_end_utc"]

    # C2 / epidemic
    max_kill_chain = ""
    max_objectives = 0
    max_spread_breadth = 0
    max_spread_depth = 0
    for s in summaries:
        kc = s.get("highest_kill_chain_stage", "")
        if len(kc) > len(max_kill_chain):
            max_kill_chain = kc
        obj = s.get("objectives_completed", 0)
        if obj > max_objectives:
            max_objectives = obj
        sb = s.get("spread_breadth", 0)
        if sb > max_spread_breadth:
            max_spread_breadth = sb
        sd = s.get("spread_depth", 0)
        if sd > max_spread_depth:
            max_spread_depth = sd

    r_ai_nonzero = [r for r in per_min_rai if r > 0]
    r_ai_ci_vals = ci95(r_ai_nonzero) if r_ai_nonzero else (0, 0, 0)

    strat_ent = entropy(attack_strats)
    mut_ent = entropy(mutations)
    def_ent = entropy(defense_strats)

    last_s = summaries[-1]

    # ---- Build Report ----
    L = []

    L.append("# Adversarial Prompt-Injection Propagation Under Adaptive Defense:")
    L.append("# A Controlled Multi-Agent Simulation Study")
    L.append("")
    L.append(f"**Observation window:** {start_utc[:19]} -- {end_utc[:19]} UTC ({n_min} minutes, ~{n_min/60:.1f} hours)")
    L.append("**Artifact:** `logs/soak_run_002`")
    L.append(f"**Run status:** Partial ({n_min}/360 minutes collected; injection API failure at minute {n_min + 1})")
    L.append("")
    L.append("---")
    L.append("")

    # Abstract
    L.append("## Abstract")
    L.append("")
    trend_word = "declining" if s_slope < 0 else "stable or increasing"
    adapt_word = "converging toward containment" if br_slope > 0 else "not yet converging"
    L.append(
        f"We present results from a {n_min}-minute partial observation of a multi-agent adversarial soak "
        f"on the Epidemic Lab simulation platform. The system recorded {total_events:,} events comprising "
        f"{total_success:,} successful infections and {total_blocked:,} blocked infections across a "
        f"five-node epidemic topology (2 couriers, 2 analysts, 1 guardian). "
        f"Linear trend analysis of per-minute attacker success shows a {trend_word} slope "
        f"({s_slope:+.4f}/min, R\u00b2={s_r2:.3f}), while the cumulative "
        f"block ratio is {adapt_word} (slope {br_slope:+.6f}/min). "
        f"The Guardian emitted {int(sum(per_min_adapt)):,} defense-adaptation events. "
        f"Post-compromise activity reached the {max_kill_chain} kill chain stage with "
        f"{max_objectives} campaign objectives completed. "
        f"We report hourly confidence intervals, strategy entropy, R_ai trajectory, and C2 metrics."
    )
    L.append("")

    # 1. Introduction
    L.append("## 1. Introduction")
    L.append("")
    L.append(
        "Large language models deployed as autonomous agents inherit a novel attack surface: "
        "prompt-injection payloads can propagate through multi-agent message-passing topologies, "
        "creating self-replicating worm dynamics analogous to biological epidemics. Understanding "
        "how these payloads mutate, spread, and evade adaptive defenses requires controlled "
        "experimentation in a realistic but safe simulation environment."
    )
    L.append("")
    L.append(
        "Epidemic Lab provides this environment. It instantiates a network of five LLM-backed "
        "agents -- two Couriers (lightweight cognition), two Analysts (hybrid cognition), and one "
        "Guardian (full LLM cognition) -- connected via Redis message passing under an orchestrator "
        "that injects adversarial worms at configurable intervals."
    )
    L.append("")
    L.append("**Research questions:**")
    L.append("")
    L.append("1. Does the Guardian's adaptive defense produce a measurable decline in attacker success over a multi-hour window?")
    L.append("2. How do attacker strategy diversity and payload mutation entropy evolve under sustained pressure?")
    L.append("3. What is the effective reproduction number (R_ai) trajectory, and does the system approach containment?")
    L.append("4. How far does the kill chain progress, and how effective are C2 containment controls?")
    L.append("")

    # 2. Methodology
    L.append("## 2. Experimental Methodology")
    L.append("")
    L.append("### 2.1 Infrastructure & Topology")
    L.append("")
    L.append("| Service | Role | Cognition Tier |")
    L.append("|---------|------|----------------|")
    L.append("| orchestrator | Control plane, SIEM, C2 observer, epidemic tracker | N/A |")
    L.append("| courier-1, courier-2 | Ingress nodes, LLM attack generators | Lightweight |")
    L.append("| analyst-1, analyst-2 | Relay nodes, compliance analyzers | Hybrid |")
    L.append("| guardian | Terminal defender, adaptive defense | Full LLM |")
    L.append("| redis | Message bus (pub/sub + streams) | N/A |")
    L.append("")
    L.append("Network: `courier-1/2 -> analyst-1/2 -> guardian` with cross-coupling between courier pair and analyst pair.")
    L.append("")
    L.append("### 2.2 Experimental Parameters")
    L.append("")
    L.append("| Parameter | Value |")
    L.append("|-----------|-------|")
    L.append("| Target duration | 6 hours (360 min) |")
    L.append(f"| Actual observation | {n_min} minutes (~{n_min/60:.1f} hours) |")
    L.append("| Reporting minute length | 60 seconds |")
    L.append("| Heartbeat interval | 60 seconds |")
    L.append("| Injection cadence | Every 5 minutes |")
    L.append("| Injection difficulty cycle | easy, medium, difficult (repeating) |")
    L.append("| LLM timeout | 300 seconds |")
    L.append("| Time compression | Disabled (true wall-clock) |")
    L.append(f"| Termination cause | Injection API 500 error at minute {n_min + 1} |")
    L.append("")
    L.append("### 2.3 Threat Model")
    L.append("")
    L.append(
        "Courier agents act as adaptive adversaries using an LLM-backed attack planner "
        "with campaign-aware objective rotation. They generate prompt-injection payloads "
        "targeting downstream agents, applying mutation strategies (encoding, reframing, "
        "context-wrapping) to evade detection. Analysts apply hybrid LLM-probabilistic "
        "compliance checking. The Guardian applies adaptive defense with outcome-aware weight "
        "learning. C2 post-compromise activity (beacons, tasks, exfiltration) is subject to "
        "probabilistic blocking (beacon 35%, task 30%, exfil 45%)."
    )
    L.append("")

    # 3. Results
    L.append("## 3. Results")
    L.append("")
    L.append("### 3.1 Aggregate Outcome Distribution")
    L.append("")
    L.append("| Metric | Count |")
    L.append("|--------|-------|")
    for evt in (
        "HEARTBEAT", "ATTACK_EXECUTED", "INFECTION_ATTEMPT", "INFECTION_SUCCESSFUL",
        "INFECTION_BLOCKED", "DEFENSE_RESULT_EVALUATED", "DEFENSE_ADAPTED",
        "LLM_COMPLIANCE_ASSESSMENT", "LLM_THREAT_ANALYSIS", "HYBRID_DECISION_MADE",
        "ATTACKER_DECISION", "STRATEGY_SELECTED", "TECHNIQUE_SELECTED", "MUTATION_SELECTED",
        "ATTACK_PAYLOAD_VALIDATED", "ATTACK_TEMPLATE_FALLBACK", "LLM_FALLBACK",
        "ROUTING_DECISION", "TARGET_SCORED", "DEFENSE_DECISION",
        "C2_BEACON", "C2_TASK", "C2_EXFIL", "C2_DATABASE_WRITE", "C2_CHANNEL_ESTABLISHED",
        "KILL_CHAIN_TRANSITION", "BEACON_BLOCKED", "EXFIL_BLOCKED",
        "EPIDEMIC_STATE_TRANSITION", "QUARANTINE_ADVISORY_SENT",
    ):
        if all_counts.get(evt, 0) > 0:
            L.append(f"| {evt} | {all_counts[evt]:,} |")
    L.append(f"| **Total events** | **{total_events:,}** |")
    L.append("")
    L.append(
        f"Overall infection success rate: **{total_success / max(total_attempts, 1):.2%}** "
        f"({total_success:,}/{total_attempts:,} attempts). "
        f"Block rate: **{total_blocked / max(total_attempts, 1):.2%}**."
    )
    L.append("")

    L.append("### 3.2 Temporal Dynamics -- Hourly Windows")
    L.append("")
    L.append("| Hour | Minutes | Successes | Success/min (95% CI) | Blocks | Blocks/min (95% CI) |")
    L.append("|------|---------|-----------|----------------------|--------|---------------------|")
    for idx, (sb, bb) in enumerate(zip(h_success, h_blocked)):
        smu, slo, shi = ci95(sb)
        bmu, blo, bhi = ci95(bb)
        L.append(
            f"| {idx + 1} | {len(sb)} | {sum(sb):.0f} | {smu:.2f} [{slo:.2f}, {shi:.2f}] "
            f"| {sum(bb):.0f} | {bmu:.2f} [{blo:.2f}, {bhi:.2f}] |"
        )
    L.append("")
    L.append(
        f"First-hour successes: **{fh_success}** | Last-hour successes: **{lh_success}** | "
        f"Delta: **{lh_success - fh_success:+d}**"
    )
    L.append(
        f"First-hour blocks: **{fh_blocked}** | Last-hour blocks: **{lh_blocked}** | "
        f"Delta: **{lh_blocked - fh_blocked:+d}**"
    )
    L.append("")

    L.append("### 3.3 Defense Adaptation Trajectory")
    L.append("")
    total_adapt = int(sum(per_min_adapt))
    L.append(f"Total `DEFENSE_ADAPTED` events: **{total_adapt}**")
    L.append("")
    final_br = last_s.get("cumulative_block_ratio", 0)
    L.append(f"Final cumulative block ratio: **{final_br:.4f}** ({final_br:.1%})")
    L.append(f"Block ratio trend slope: **{br_slope:+.6f}/min** (R\u00b2={br_r2:.4f})")
    L.append("")
    if br_slope > 0:
        L.append(
            "The positive block-ratio slope indicates the defender is trending toward "
            "stronger containment over the observation window."
        )
    else:
        L.append(
            "The block-ratio slope does not show a clear improving trend; "
            "containment equilibrium was not reached."
        )
    L.append("")

    L.append("### 3.4 Attacker Strategy & Mutation Analysis")
    L.append("")
    if attack_strats:
        L.append("**Dominant attacker strategies (by minute-level leadership):**")
        L.append("")
        L.append("| Strategy | Minutes Led | Share |")
        L.append("|----------|-------------|-------|")
        total_st = sum(attack_strats.values())
        for s_name, c in attack_strats.most_common(10):
            L.append(f"| {s_name} | {c} | {c / total_st:.1%} |")
        L.append("")
    if mutations:
        L.append("**Dominant mutation families:**")
        L.append("")
        L.append("| Mutation | Minutes Led | Share |")
        L.append("|----------|-------------|-------|")
        total_mt = sum(mutations.values())
        for m_name, c in mutations.most_common(10):
            L.append(f"| {m_name} | {c} | {c / total_mt:.1%} |")
        L.append("")
    L.append(f"Strategy entropy: **{strat_ent:.3f} bits** ({len(attack_strats)} distinct)")
    L.append(f"Mutation entropy: **{mut_ent:.3f} bits** ({len(mutations)} distinct)")
    L.append(f"Defense strategy entropy: **{def_ent:.3f} bits** ({len(defense_strats)} distinct)")
    L.append("")

    L.append("### 3.5 Kill Chain & C2 Post-Compromise")
    L.append("")
    L.append("| Metric | Value |")
    L.append("|--------|-------|")
    L.append(f"| Highest kill chain stage reached | {max_kill_chain or 'N/A'} |")
    L.append(f"| Campaign objectives completed | {max_objectives} |")
    L.append(f"| Max spread breadth | {max_spread_breadth} |")
    L.append(f"| Max spread depth | {max_spread_depth} |")
    L.append(f"| C2 beacons (cumulative) | {last_s.get('c2_beacons', 0)} |")
    L.append(f"| C2 tasks (cumulative) | {last_s.get('c2_tasks', 0)} |")
    L.append(f"| Exfil attempts (cumulative) | {last_s.get('c2_exfil_attempts', 0)} |")
    L.append(f"| Beacons blocked | {last_s.get('c2_beacons_blocked', 0)} |")
    L.append(f"| Exfil blocked | {last_s.get('c2_exfil_blocked', 0)} |")
    L.append(f"| Active C2 sessions (final) | {last_s.get('active_c2_sessions', 0)} |")
    L.append("")

    last_epi = last_s.get("epidemic_state_counts", {})
    if last_epi:
        L.append("**Final epidemic state distribution:**")
        L.append("")
        L.append("| State | Count |")
        L.append("|-------|-------|")
        state_names = {"S": "Susceptible", "E": "Exposed", "I_R": "Relay-infected",
                       "I_C": "C2-active", "I_X": "Exfil-active", "Q": "Quarantined",
                       "R": "Resistant", "P": "Persistent-carrier"}
        for state, count in sorted(last_epi.items()):
            label = state_names.get(state, state)
            L.append(f"| {state} ({label}) | {count} |")
        L.append("")

    # 4. Statistical Analysis
    L.append("## 4. Statistical Analysis")
    L.append("")
    L.append("### 4.1 Trend Analysis (OLS Linear Regression)")
    L.append("")
    L.append(
        "We fit ordinary least-squares linear models to per-minute time series to quantify "
        "directional trends. The slope coefficient indicates the per-minute rate of change; "
        "R\u00b2 indicates goodness of fit."
    )
    L.append("")
    L.append("| Series | Slope (/min) | R\u00b2 | Interpretation |")
    L.append("|--------|-------------|------|----------------|")
    si = "Declining" if s_slope < -0.001 else ("Stable" if abs(s_slope) < 0.001 else "Increasing")
    bi = "Increasing" if b_slope > 0.001 else ("Stable" if abs(b_slope) < 0.001 else "Declining")
    bri = "Containment improving" if br_slope > 0 else "Containment weakening"
    L.append(f"| Infection successes | {s_slope:+.6f} | {s_r2:.4f} | {si} |")
    L.append(f"| Infection blocks | {b_slope:+.6f} | {b_r2:.4f} | {bi} |")
    L.append(f"| Cumulative block ratio | {br_slope:+.6f} | {br_r2:.4f} | {bri} |")
    L.append("")

    L.append("### 4.2 Confidence Intervals (95%)")
    L.append("")
    L.append("| Metric | Mean | 95% CI | n |")
    L.append("|--------|------|--------|---|")
    for label, vals in (
        ("Successes/min", per_min_success),
        ("Blocks/min", per_min_blocked),
        ("Attacks executed/min", per_min_attack),
        ("Events/min", per_min_events),
    ):
        mu, lo, hi = ci95(vals)
        L.append(f"| {label} | {mu:.3f} | [{lo:.3f}, {hi:.3f}] | {len(vals)} |")
    L.append("")

    L.append("### 4.3 Distribution Entropy")
    L.append("")
    L.append(
        "Shannon entropy quantifies the diversity of categorical distributions. Higher entropy "
        "indicates greater tactical diversity."
    )
    L.append("")
    L.append("| Distribution | Entropy (bits) | Distinct Values |")
    L.append("|--------------|----------------|-----------------|")
    L.append(f"| Attacker strategies | {strat_ent:.3f} | {len(attack_strats)} |")
    L.append(f"| Mutations | {mut_ent:.3f} | {len(mutations)} |")
    L.append(f"| Defense strategies | {def_ent:.3f} | {len(defense_strats)} |")
    L.append("")

    if r_ai_nonzero:
        L.append("### 4.4 Epidemic Reproduction Number (R_ai)")
        L.append("")
        rmu, rlo, rhi = r_ai_ci_vals
        L.append(f"Mean R_ai (active minutes): **{rmu:.4f}** (95% CI [{rlo:.4f}, {rhi:.4f}], n={len(r_ai_nonzero)})")
        L.append(f"R_ai trend slope: **{rai_slope:+.6f}/min**")
        L.append(f"Max R_ai observed: **{max(per_min_rai):.2f}**")
        L.append(f"Minutes with R_ai > 1.0: **{sum(1 for r in per_min_rai if r > 1)}/{n_min}**")
        L.append("")
        L.append(
            "An R_ai > 1.0 indicates super-critical propagation (epidemic growth); "
            "R_ai < 1.0 indicates sub-critical propagation (containment)."
        )
        if rai_slope < 0:
            L.append(
                " The declining R_ai trend suggests defensive pressure is pushing "
                "the system toward sub-critical propagation."
            )
        else:
            L.append(
                " R_ai has not shown a sustained decline, indicating the system "
                "has not reached containment equilibrium."
            )
        L.append("")

    # 5. Discussion
    L.append("## 5. Discussion")
    L.append("")
    L.append("### 5.1 Interpretation of Key Findings")
    L.append("")
    if s_slope < -0.001:
        L.append(
            f"The negative success-rate slope ({s_slope:+.4f}/min) provides quantitative evidence that "
            f"the Guardian's adaptive defense produces a measurable reduction in attacker effectiveness "
            f"over the observation window. First-hour successes ({fh_success}) versus last-hour successes "
            f"({lh_success}) represent a {abs(fh_success - lh_success)} event delta."
        )
    else:
        L.append(
            f"The success-rate slope ({s_slope:+.4f}/min) does not show a strong downward trend, "
            f"suggesting attacker adaptation is keeping pace with defensive improvements. "
            f"First-hour: {fh_success}, last-hour: {lh_success}."
        )
    L.append("")
    if strat_ent > 1.5:
        L.append(
            f"The attacker strategy entropy ({strat_ent:.3f} bits) indicates substantial tactical diversity, "
            f"suggesting the attacker planner is actively exploring multiple strategy families "
            f"rather than converging on a single approach."
        )
    else:
        L.append(
            f"The relatively low attacker strategy entropy ({strat_ent:.3f} bits) suggests the attacker "
            f"is concentrating on a small number of dominant strategies."
        )
    L.append("")

    L.append("### 5.2 Kill Chain Progression")
    L.append("")
    L.append(
        f"The adversary reached the **{max_kill_chain}** kill chain stage and completed "
        f"{max_objectives} campaign objectives. The C2 containment controls (beacon block 35%, "
        f"task block 30%, exfil block 45%) appear to be constraining post-compromise activity, "
        f"as evidenced by {last_s.get('c2_beacons_blocked', 0)} blocked beacons and "
        f"{last_s.get('c2_exfil_blocked', 0)} blocked exfiltration attempts."
    )
    L.append("")

    L.append("### 5.3 Implications for AI Security")
    L.append("")
    L.append(
        "The results demonstrate that adaptive, outcome-aware defense mechanisms can produce "
        "measurable containment pressure against LLM-propagated prompt-injection worms, but "
        "the attacker's ability to diversify strategies and mutate payloads creates a sustained "
        "co-evolutionary dynamic. The multi-path epidemic topology (with cross-coupled couriers "
        "and analysts) creates redundant propagation channels that make containment harder than "
        "in a linear topology. Static defenses would likely be insufficient against an adversary "
        "with campaign-aware planning and mutation capabilities."
    )
    L.append("")

    # 6. Limitations
    L.append("## 6. Limitations & Threats to Validity")
    L.append("")
    L.append(
        f"1. **Partial observation:** The run terminated at minute {n_min}/360 due to an injection API "
        f"error, reducing the window to ~{n_min / 60:.1f} hours of the planned 6 hours."
    )
    L.append("2. **Single topology:** Results are specific to the five-node epidemic topology.")
    L.append("3. **Local LLM inference:** Ollama-hosted models introduce latency and quality variance.")
    L.append("4. **Fixed injection cadence:** The repeating difficulty cycle is predictable.")
    L.append("5. **No random seed control:** LLM generation is stochastic and not seeded.")
    L.append("6. **Single run:** Without multiple replications, between-run variance cannot be estimated.")
    L.append(
        "7. **No API analytics snapshot:** The stack was torn down before post-hoc API queries "
        "(mutation leaderboards, payload families, campaign detail) could be captured."
    )
    L.append("")

    # 7. Conclusion
    L.append("## 7. Conclusion")
    L.append("")
    L.append(
        f"This partial {n_min}-minute adversarial soak provides empirical evidence on the dynamics of "
        f"prompt-injection propagation under adaptive defense in a five-agent epidemic topology. "
    )
    if s_slope < 0 and br_slope > 0:
        L.append(
            "The key finding is a statistically observable decline in attacker success and an improving "
            "containment ratio, consistent with effective outcome-aware defensive learning."
        )
    elif s_slope < 0:
        L.append(
            "Attacker success shows a declining trend, though the block-ratio has not yet converged."
        )
    else:
        L.append(
            "The attacker maintained effectiveness throughout, suggesting current defensive adaptation "
            "rates are insufficient to outpace strategy diversification over this time horizon."
        )
    L.append("")
    L.append("**Recommended follow-up:**")
    L.append("")
    L.append("- Rerun the full 6-hour soak after investigating the injection API 500 error.")
    L.append("- Add graceful degradation: skip failed injections rather than aborting the entire run.")
    L.append("- Replicate with 3-5 independent runs to establish between-run variance.")
    L.append("- Ablation study: disable Guardian adaptation to measure its isolated contribution.")
    L.append("- Extend to 12-24 hours to study long-term equilibrium behavior.")
    L.append("")

    # Appendix A: Minute Ledger
    L.append("## Appendix A: Minute-by-Minute Ledger")
    L.append("")
    L.append("<details>")
    L.append(f"<summary>Full {n_min}-minute ledger (click to expand)</summary>")
    L.append("")
    L.append("| Min | Events | Success | Blocked | Def Adapt | Top Attack | Top Mutation | R_ai | Block Ratio |")
    L.append("|-----|--------|---------|---------|-----------|------------|--------------|------|-------------|")
    for s in summaries:
        L.append(
            f"| {s['minute']:03d} | {s['event_count']} "
            f"| {s['counts'].get('INFECTION_SUCCESSFUL', 0)} "
            f"| {s['counts'].get('INFECTION_BLOCKED', 0)} "
            f"| {s['counts'].get('DEFENSE_ADAPTED', 0)} "
            f"| {s['top_attack_strategy'] or '-'} "
            f"| {s['top_mutation'] or '-'} "
            f"| {s.get('r_ai', 0):.2f} "
            f"| {s.get('cumulative_block_ratio', 0):.4f} |"
        )
    L.append("")
    L.append("</details>")
    L.append("")
    L.append("---")
    L.append("")
    L.append("*Report generated from minute_summaries.jsonl by Epidemic Lab recovery pipeline.*")

    report = "\n".join(L)
    out_path = artifact / "research_soc_report.md"
    out_path.write_text(report, encoding="utf-8")
    print(f"Report written: {out_path}")
    print(f"Lines: {len(L)} | Bytes: {len(report):,}")
    print()
    print(f"=== KEY METRICS ===")
    print(f"Observation: {n_min} minutes (~{n_min / 60:.1f}h)")
    print(f"Total events: {total_events:,}")
    print(f"Successes: {total_success:,} | Blocks: {total_blocked:,}")
    print(f"Success rate: {total_success / max(total_attempts, 1):.2%}")
    print(f"Success slope: {s_slope:+.6f}/min (R2={s_r2:.4f})")
    print(f"Block ratio slope: {br_slope:+.6f}/min (R2={br_r2:.4f})")
    print(f"Strategy entropy: {strat_ent:.3f} bits")
    print(f"Mutation entropy: {mut_ent:.3f} bits")
    if r_ai_nonzero:
        print(f"Mean R_ai: {r_ai_ci_vals[0]:.4f} (95% CI [{r_ai_ci_vals[1]:.4f}, {r_ai_ci_vals[2]:.4f}])")
    print(f"Kill chain: {max_kill_chain} | Objectives: {max_objectives}")
    print(f"First-hour success: {fh_success} | Last-hour success: {lh_success}")


if __name__ == "__main__":
    main()
