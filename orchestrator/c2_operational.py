"""
Patch 6: operational realism for C2 beacons, tasks, and exfil (hashes, previews, sensitivity).
"""

from __future__ import annotations

import hashlib
import re
from typing import Any, Dict, List, Tuple
from urllib.parse import urlparse

from experiment_config.exfil_operational_runtime import get_exfil_operational_runtime_config


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def classify_exfil_sensitivity(exfil_type: str, exfil_size: int) -> str:
    """LOW | MEDIUM | HIGH | CRITICAL based on type and size."""
    cfg = get_exfil_operational_runtime_config()
    t = (exfil_type or "").lower()
    sz = max(0, int(exfil_size))
    crit_t = {"defense_config", "payload_lineage"}
    high_t = {"agent_state", "network_map"}
    if t in crit_t or sz > cfg.sensitivity_critical_bytes:
        return "CRITICAL"
    if t in high_t and sz > cfg.sensitivity_high_bytes:
        return "HIGH"
    if sz > cfg.sensitivity_medium_bytes:
        return "MEDIUM"
    return "LOW"


def destination_trust_risk(destination_system: str) -> Tuple[float, float]:
    """
    Returns (trust 0-1, risk 0-1). Unknown / non-HTTPS URLs get lower trust.
    """
    cfg = get_exfil_operational_runtime_config()
    url = str(destination_system or "").strip()
    if not url:
        return 0.35, 0.65
    try:
        p = urlparse(url if "://" in url else f"https://{url}")
        host = (p.hostname or "").lower()
        trust = cfg.dest_trust_default
        if host.endswith(".vercel.app") or host.endswith(".localhost"):
            trust = min(trust, cfg.dest_trust_third_party)
        if p.scheme == "http":
            trust *= 0.85
        trust = max(0.05, min(0.98, trust))
        risk = max(0.02, min(0.95, 1.0 - trust + cfg.dest_risk_floor))
        return round(trust, 4), round(risk, 4)
    except Exception:
        return 0.4, 0.6


def redact_exfil_preview(text: str, *, max_len: int, enabled: bool) -> str:
    cfg = get_exfil_operational_runtime_config()
    if not enabled or not text:
        s = text or ""
    else:
        s = str(text)
        if cfg.exfil_redact_email >= 0.5:
            s = re.sub(
                r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}",
                "[REDACTED_EMAIL]",
                s,
            )
        if cfg.exfil_redact_api_key >= 0.5:
            s = re.sub(
                r"(?i)(api[_-]?key|token|secret|password)\s*[:=]\s*\S+",
                r"\1=[REDACTED]",
                s,
            )
    if max_len <= 0:
        return ""
    if len(s) <= max_len:
        return s
    return s[: max(0, max_len - 3)].rstrip() + "..."


def build_synthetic_exfil_body(
    *,
    agent_id: str,
    campaign_id: str,
    injection_id: str,
    exfil_type: str,
    seed_text: str,
    target_size: int,
) -> bytes:
    hdr = f"agent_id={agent_id};campaign={campaign_id};inj={injection_id};type={exfil_type};".encode()
    body = bytearray(hdr)
    seed = (seed_text or "x").encode("utf-8", errors="replace")
    i = 0
    ts = max(1, int(target_size))
    while len(body) < ts:
        body.append(seed[i % len(seed)] if seed else ord("x"))
        i += 1
    return bytes(body[:target_size])


def compute_chunk_plan(total_size: int, chunk_max: int) -> Tuple[int, int]:
    """Returns (chunk_size, chunk_count)."""
    cm = max(256, int(chunk_max))
    ts = max(1, int(total_size))
    chunk_count = max(1, (ts + cm - 1) // cm)
    chunk_size = min(cm, ts)
    return chunk_size, chunk_count


def chunk_interception_probability(
    *,
    sensitivity: str,
    destination_risk: float,
    chunk_index: int,
    chunk_count: int,
) -> float:
    cfg = get_exfil_operational_runtime_config()
    base = cfg.interception_base
    sens_mult = {"LOW": 0.85, "MEDIUM": 1.0, "HIGH": 1.25, "CRITICAL": 1.55}.get(sensitivity, 1.0)
    late_bonus = 0.02 * chunk_index / max(1, chunk_count)
    p = base * sens_mult + destination_risk * cfg.interception_risk_weight + late_bonus
    return max(0.0, min(0.92, p))


def exfil_size_after_constraints(
    raw_size: int,
    *,
    sensitivity: str,
) -> Tuple[int, str]:
    """Returns (clamped_size, note)."""
    cfg = get_exfil_operational_runtime_config()
    limits = {
        "LOW": cfg.max_bytes_low,
        "MEDIUM": cfg.max_bytes_medium,
        "HIGH": cfg.max_bytes_high,
        "CRITICAL": cfg.max_bytes_critical,
    }
    cap = limits.get(sensitivity, limits["MEDIUM"])
    rs = max(1, int(raw_size))
    if rs <= cap:
        return rs, ""
    return cap, f"size_clamped_to_{cap}_for_{sensitivity}"
