"""
Patch 8: SQLite integrity verification for telemetry stores (SIEM index, event logger).
"""

from __future__ import annotations

import json
import sqlite3
import time
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List


def verify_sqlite_integrity(db_path: str, *, full_check: bool = False) -> Dict[str, Any]:
    """
    Run PRAGMA quick_check; optionally integrity_check (slower).
    Missing file is treated as ok (nothing to corrupt yet).
    """
    path = Path(db_path)
    if not path.exists():
        return {
            "path": str(path),
            "ok": True,
            "skipped": True,
            "reason": "file_missing",
            "checked_at": time.time(),
        }
    detail_rows: List[str] = []
    ok = True
    try:
        conn = sqlite3.connect(str(path), timeout=5.0)
        try:
            if full_check:
                cur = conn.execute("PRAGMA integrity_check")
                rows = [str(r[0]) for r in cur.fetchall()]
                detail_rows = rows
                ok = len(rows) == 1 and str(rows[0]).lower() == "ok"
            else:
                row = conn.execute("PRAGMA quick_check").fetchone()
                msg = str(row[0]) if row else ""
                detail_rows = [msg]
                ok = msg.lower() == "ok"
        finally:
            conn.close()
    except sqlite3.DatabaseError as exc:
        ok = False
        detail_rows = [str(exc)]
    return {
        "path": str(path),
        "ok": ok,
        "skipped": False,
        "quick_check": not full_check,
        "detail": " | ".join(detail_rows)[:2000],
        "checked_at": time.time(),
    }


def summarize_jsonl_run(run_dir: str, *, max_minutes: int = 5) -> Dict[str, Any]:
    """Lightweight local summary for a soak/archive run directory (no orchestrator)."""
    root = Path(run_dir)
    out: Dict[str, Any] = {"run_dir": str(root.resolve()), "exists": root.exists()}
    if not root.exists():
        return out
    progress = root / "progress.json"
    if progress.exists():
        try:
            out["progress"] = json.loads(progress.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            out["progress_error"] = True
    minute_path = root / "minute_summaries.jsonl"
    tops: List[Dict[str, Any]] = []
    if minute_path.exists():
        try:
            for i, line in enumerate(minute_path.read_text(encoding="utf-8").splitlines()):
                if i >= max_minutes:
                    break
                try:
                    tops.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
            fam_totals: Counter[str] = Counter()
            for row in tops:
                for item in row.get("top_payload_families") or []:
                    fid = str(item.get("family_id") or "")
                    if fid:
                        fam_totals[fid] += int(item.get("count") or 0)
            out["minute_sample_count"] = len(tops)
            out["top_payload_families_rollup"] = [
                {"family_id": f, "count": c} for f, c in fam_totals.most_common(8)
            ]
        except OSError:
            out["minute_read_error"] = True
    return out


__all__ = ["verify_sqlite_integrity", "summarize_jsonl_run"]
