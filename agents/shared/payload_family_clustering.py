"""
Patch 7: payload family clustering, novelty class, and dedup signals (complements strain_id lineage).

Uses normalized content hash (exact), structural token signature (family id), and optional
token Jaccard vs recent payloads (near duplicate). Strain tracking remains authoritative for lineage.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Literal, Optional, Sequence, Tuple

from shared.config.payload_family_clustering_runtime import get_payload_family_clustering_config
from shared.mutation_strategy import token_jaccard
from shared.payload_utils import hash_payload, normalize_payload_text

NoveltyClass = Literal["exact_duplicate", "near_duplicate", "same_family_new_mutation", "novel"]


def normalized_content_hash(payload: Any) -> str:
    """SHA-256 of normalize_payload_text (exact duplicate key)."""
    return hash_payload(payload)


def structural_signature(text: str) -> str:
    """
    Collapse cosmetic variance: hex/numbers placeholders + sorted structural tokens.
    """
    t = normalize_payload_text(text)
    if not t:
        return ""
    t = re.sub(r"[0-9a-fA-F]{8,}", "<HEX>", t)
    t = re.sub(r"\b\d+\b", "<N>", t)
    # Bracket / SIM_* / key=value-ish chunks
    chunks = re.findall(
        r"\[SIM_ATTACK[^\]]*\]|SIM_[A-Z_]+\[[^\]]*\]|SIM_[A-Z_]+|"
        r"[a-zA-Z_][a-zA-Z0-9_]*=<[^>]+>|"
        r"<[A-Z_]+>",
        t,
    )
    if not chunks:
        chunks = re.findall(r"[a-z]{4,}", t.lower())[:48]
    uniq = sorted(set(chunks))
    sig = "|".join(uniq)[:480]
    return sig


def family_cluster_id(struct_sig: str) -> str:
    if not struct_sig:
        h = hashlib.sha256(b"<empty_struct>").hexdigest()[:16]
    else:
        h = hashlib.sha256(struct_sig.encode("utf-8", errors="replace")).hexdigest()[:16]
    return f"pfam_{h}"


def semantic_similarity(a: str, b: str) -> float:
    """Optional lightweight similarity (token Jaccard on 3+ char alnum tokens)."""
    return token_jaccard(a, b)


@dataclass
class PayloadFamilyFeatures:
    norm_text: str
    norm_hash: str
    struct_sig: str
    family_id: str


def build_family_features(payload: Any) -> PayloadFamilyFeatures:
    norm_text = normalize_payload_text(payload)
    nh = normalized_content_hash(payload)
    ss = structural_signature(norm_text)
    return PayloadFamilyFeatures(
        norm_text=norm_text,
        norm_hash=nh,
        struct_sig=ss,
        family_id=family_cluster_id(ss),
    )


def classify_novelty(
    feat: PayloadFamilyFeatures,
    *,
    seen_norm_hashes: set,
    recent_texts: Sequence[str],
    family_emission_counts: Dict[str, int],
) -> Tuple[NoveltyClass, float, Dict[str, Any]]:
    """
    Classify vs planner-local history (before recording this emission).
    """
    pfc = get_payload_family_clustering_config()
    near_t = pfc.near_dup_jaccard
    use_semantic = pfc.semantic_sim_enabled

    details: Dict[str, Any] = {"family_id": feat.family_id, "struct_sig_len": len(feat.struct_sig)}

    if feat.norm_hash and feat.norm_hash in seen_norm_hashes:
        return "exact_duplicate", 0.0, {**details, "max_jaccard": 1.0}

    max_j = 0.0
    if feat.norm_text and recent_texts:
        sample = recent_texts[-32:] if len(recent_texts) > 32 else list(recent_texts)
        for prev in sample:
            if not prev:
                continue
            if use_semantic:
                max_j = max(max_j, semantic_similarity(feat.norm_text, prev))
            else:
                max_j = max(max_j, 1.0 if feat.norm_text == prev else 0.0)

    details["max_jaccard"] = round(max_j, 4)

    if max_j >= near_t:
        return "near_duplicate", 0.22, details

    fam_count = int(family_emission_counts.get(feat.family_id, 0))
    details["prior_family_emissions"] = fam_count
    if fam_count > 0 and feat.norm_hash not in seen_norm_hashes:
        return "same_family_new_mutation", 0.58, details

    return "novel", 1.0, details


def novelty_score_for_class(cls: str) -> float:
    return {
        "exact_duplicate": 0.0,
        "near_duplicate": 0.22,
        "same_family_new_mutation": 0.58,
        "novel": 1.0,
    }.get(cls, 0.5)


def dedupe_exact_payload(payload: str, seen_norm_hashes: set, rng: Any) -> str:
    """Append a simulation-only token so normalized hash changes (single hop)."""
    if not payload or not seen_norm_hashes:
        return payload
    nh = normalized_content_hash(payload)
    if nh not in seen_norm_hashes:
        return payload
    suffix = f"|pdv={rng.randint(1, 10_000_000)}"
    return payload + suffix


def family_cluster_metrics(family_id_counts: Dict[str, int]) -> Dict[str, Any]:
    if not family_id_counts:
        return {
            "distinct_families": 0,
            "total_classified_emissions": 0,
            "top_family_ids": [],
            "family_entropy": 0.0,
        }
    total = sum(family_id_counts.values())
    distinct = len(family_id_counts)
    top = sorted(family_id_counts.items(), key=lambda x: (-x[1], x[0]))[:12]
    # Shannon entropy over family distribution (nats)
    import math

    ent = 0.0
    for c in family_id_counts.values():
        if c <= 0:
            continue
        p = c / total
        ent -= p * math.log(p + 1e-12)
    return {
        "distinct_families": distinct,
        "total_classified_emissions": total,
        "top_family_ids": [{"family_id": fid, "count": cnt} for fid, cnt in top],
        "family_entropy": round(ent, 4),
    }


def build_payload_family_metadata(
    payload: Any,
    *,
    seen_norm_hashes: set,
    recent_texts: Sequence[str],
    family_emission_counts: Dict[str, int],
) -> Tuple[Dict[str, Any], NoveltyClass]:
    feat = build_family_features(payload)
    cls, score, det = classify_novelty(
        feat,
        seen_norm_hashes=seen_norm_hashes,
        recent_texts=recent_texts,
        family_emission_counts=family_emission_counts,
    )
    meta = {
        "payload_family_id": feat.family_id,
        "payload_norm_hash_full": feat.norm_hash,
        "payload_struct_signature": feat.struct_sig[:220],
        "payload_novelty_class": cls,
        "payload_novelty_score": round(score, 4),
        "payload_family_prior_count": int(family_emission_counts.get(feat.family_id, 0)),
        **{k: v for k, v in det.items() if k != "family_id"},
    }
    return meta, cls


__all__ = [
    "PayloadFamilyFeatures",
    "NoveltyClass",
    "build_family_features",
    "classify_novelty",
    "normalized_content_hash",
    "structural_signature",
    "family_cluster_id",
    "semantic_similarity",
    "novelty_score_for_class",
    "dedupe_exact_payload",
    "family_cluster_metrics",
    "build_payload_family_metadata",
]
