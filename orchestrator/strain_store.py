"""
Persistent strain registry: SQLite primary, JSONL append-only degraded mode (Patch 2).

On integrity failure, switches to degraded mode with high-severity logging; writes
continue to JSONL so state is not silently lost.
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import threading
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

_log = logging.getLogger("uvicorn.error")


@dataclass
class StrainRecord:
    strain_id: str
    parent_strain_id: str = ""
    payload_hash: str = ""
    creation_ts: float = 0.0
    originating_attack_type: str = ""
    mutation_lineage: List[str] = field(default_factory=list)
    generation: int = 0
    novelty_score: float = 0.0
    fitness_score: float = 0.0
    success_count: int = 0
    block_count: int = 0
    exfil_success_count: int = 0
    beacon_success_count: int = 0
    quarantine_count: int = 0
    last_seen_ts: float = 0.0
    extinct: bool = False
    last_emitted_fitness: float = -1.0
    task_success_count: int = 0
    first_detection_ts: float = 0.0
    survival_wins_after_detection: int = 0
    touch_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["mutation_lineage"] = list(self.mutation_lineage)
        return d

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> StrainRecord:
        raw = dict(row)
        lineage_raw = raw.get("mutation_lineage_json", "[]")
        try:
            lineage = json.loads(lineage_raw) if isinstance(lineage_raw, str) else []
        except json.JSONDecodeError:
            lineage = []
        if not isinstance(lineage, list):
            lineage = []
        raw["mutation_lineage"] = [str(x) for x in lineage]
        raw.pop("mutation_lineage_json", None)
        raw["extinct"] = bool(raw.get("extinct", 0))
        lef = raw.get("last_emitted_fitness")
        raw["last_emitted_fitness"] = float(lef) if lef is not None else -1.0
        fields = {k: raw[k] for k in raw if k in cls.__dataclass_fields__}
        return cls(**fields)

    @classmethod
    def from_jsonl_obj(cls, obj: Dict[str, Any]) -> StrainRecord:
        mut = obj.get("mutation_lineage") or []
        if not isinstance(mut, list):
            mut = []
        return cls(
            strain_id=str(obj.get("strain_id", "")),
            parent_strain_id=str(obj.get("parent_strain_id", "")),
            payload_hash=str(obj.get("payload_hash", "")),
            creation_ts=float(obj.get("creation_ts", 0) or 0),
            originating_attack_type=str(obj.get("originating_attack_type", "")),
            mutation_lineage=[str(x) for x in mut],
            generation=int(obj.get("generation", 0) or 0),
            novelty_score=float(obj.get("novelty_score", 0) or 0),
            fitness_score=float(obj.get("fitness_score", 0) or 0),
            success_count=int(obj.get("success_count", 0) or 0),
            block_count=int(obj.get("block_count", 0) or 0),
            exfil_success_count=int(obj.get("exfil_success_count", 0) or 0),
            beacon_success_count=int(obj.get("beacon_success_count", 0) or 0),
            quarantine_count=int(obj.get("quarantine_count", 0) or 0),
            last_seen_ts=float(obj.get("last_seen_ts", 0) or 0),
            extinct=bool(obj.get("extinct", False)),
            last_emitted_fitness=float(obj.get("last_emitted_fitness", -1.0)),
            task_success_count=int(obj.get("task_success_count", 0) or 0),
            first_detection_ts=float(obj.get("first_detection_ts", 0) or 0),
            survival_wins_after_detection=int(obj.get("survival_wins_after_detection", 0) or 0),
            touch_count=int(obj.get("touch_count", 0) or 0),
        )


class StrainStore:
    def __init__(
        self,
        db_path: str | None = None,
        jsonl_fallback_path: str | None = None,
    ) -> None:
        base = Path(os.environ.get("LOGS_DIR", "/app/logs"))
        self.db_path = db_path or os.environ.get("STRAIN_DB_PATH", str(base / "strains.db"))
        self.jsonl_fallback_path = jsonl_fallback_path or os.environ.get(
            "STRAIN_JSONL_FALLBACK", str(base / "strains_fallback.jsonl")
        )
        self._conn: sqlite3.Connection | None = None
        self._lock = threading.Lock()
        self.degraded: bool = False
        self.degraded_reason: str = ""
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
            self._conn = sqlite3.connect(self.db_path, timeout=15.0, check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
            journal_mode = os.environ.get("SQLITE_JOURNAL_MODE", "DELETE").strip().upper() or "DELETE"
            self._conn.execute(f"PRAGMA journal_mode={journal_mode}")
            self._conn.execute("PRAGMA synchronous=NORMAL")
        return self._conn

    def _run_integrity_check(self, conn: sqlite3.Connection) -> bool:
        try:
            row = conn.execute("PRAGMA integrity_check").fetchone()
            ok = row is not None and str(row[0]).lower() == "ok"
            if not ok:
                self.degraded_reason = f"integrity_check_failed:{row}"
            return ok
        except sqlite3.DatabaseError as exc:
            self.degraded_reason = f"integrity_check_error:{exc}"
            return False

    def _init_db(self) -> None:
        try:
            conn = self._get_conn()
            if not self._run_integrity_check(conn):
                self._enter_degraded(f"sqlite_integrity:{self.degraded_reason}")
                return
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS strains (
                    strain_id TEXT PRIMARY KEY,
                    parent_strain_id TEXT NOT NULL DEFAULT '',
                    payload_hash TEXT NOT NULL DEFAULT '',
                    creation_ts REAL NOT NULL,
                    originating_attack_type TEXT NOT NULL DEFAULT '',
                    mutation_lineage_json TEXT NOT NULL DEFAULT '[]',
                    generation INTEGER NOT NULL DEFAULT 0,
                    novelty_score REAL NOT NULL DEFAULT 0,
                    fitness_score REAL NOT NULL DEFAULT 0,
                    success_count INTEGER NOT NULL DEFAULT 0,
                    block_count INTEGER NOT NULL DEFAULT 0,
                    exfil_success_count INTEGER NOT NULL DEFAULT 0,
                    beacon_success_count INTEGER NOT NULL DEFAULT 0,
                    quarantine_count INTEGER NOT NULL DEFAULT 0,
                    last_seen_ts REAL NOT NULL DEFAULT 0,
                    extinct INTEGER NOT NULL DEFAULT 0,
                    last_emitted_fitness REAL NOT NULL DEFAULT -1,
                    task_success_count INTEGER NOT NULL DEFAULT 0,
                    first_detection_ts REAL NOT NULL DEFAULT 0,
                    survival_wins_after_detection INTEGER NOT NULL DEFAULT 0,
                    touch_count INTEGER NOT NULL DEFAULT 0
                )
                """
            )
            conn.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_strains_payload_hash ON strains(payload_hash) WHERE payload_hash != ''"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_strains_parent ON strains(parent_strain_id)"
            )
            self._migrate_strain_columns(conn)
            conn.commit()
        except sqlite3.Error as exc:
            self._enter_degraded(f"sqlite_open_or_init:{exc}")

    def _migrate_strain_columns(self, conn: sqlite3.Connection) -> None:
        cols = {row[1] for row in conn.execute("PRAGMA table_info(strains)").fetchall()}
        if "last_emitted_fitness" not in cols:
            conn.execute("ALTER TABLE strains ADD COLUMN last_emitted_fitness REAL NOT NULL DEFAULT -1")
        for name, decl in (
            ("task_success_count", "INTEGER NOT NULL DEFAULT 0"),
            ("first_detection_ts", "REAL NOT NULL DEFAULT 0"),
            ("survival_wins_after_detection", "INTEGER NOT NULL DEFAULT 0"),
            ("touch_count", "INTEGER NOT NULL DEFAULT 0"),
        ):
            if name not in cols:
                conn.execute(f"ALTER TABLE strains ADD COLUMN {name} {decl}")

    def _enter_degraded(self, reason: str) -> None:
        if self.degraded:
            return
        self.degraded = True
        self.degraded_reason = reason
        _log.error(
            "strain_store_degraded reason=%s fallback_jsonl=%s",
            reason,
            self.jsonl_fallback_path,
        )
        if self._conn is not None:
            try:
                self._conn.close()
            except sqlite3.Error:
                pass
            self._conn = None
        Path(self.jsonl_fallback_path).parent.mkdir(parents=True, exist_ok=True)

    def health(self) -> Dict[str, Any]:
        return {
            "degraded": self.degraded,
            "reason": self.degraded_reason,
            "db_path": self.db_path,
            "jsonl_fallback_path": self.jsonl_fallback_path,
        }

    def _append_jsonl(self, record: StrainRecord) -> None:
        Path(self.jsonl_fallback_path).parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(record.to_dict(), separators=(",", ":")) + "\n"
        with open(self.jsonl_fallback_path, "a", encoding="utf-8") as fh:
            fh.write(line)
            fh.flush()
            os.fsync(fh.fileno())

    def upsert_strain(self, record: StrainRecord) -> None:
        lineage_json = json.dumps(record.mutation_lineage)
        with self._lock:
            if self.degraded:
                self._append_jsonl(record)
                return
            conn = self._get_conn()
            try:
                conn.execute(
                    """
                    INSERT INTO strains (
                        strain_id, parent_strain_id, payload_hash, creation_ts, originating_attack_type,
                        mutation_lineage_json, generation, novelty_score, fitness_score,
                        success_count, block_count, exfil_success_count, beacon_success_count,
                        quarantine_count, last_seen_ts, extinct, last_emitted_fitness,
                        task_success_count, first_detection_ts, survival_wins_after_detection, touch_count
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(strain_id) DO UPDATE SET
                        parent_strain_id=excluded.parent_strain_id,
                        payload_hash=excluded.payload_hash,
                        originating_attack_type=excluded.originating_attack_type,
                        mutation_lineage_json=excluded.mutation_lineage_json,
                        generation=excluded.generation,
                        novelty_score=excluded.novelty_score,
                        fitness_score=excluded.fitness_score,
                        success_count=excluded.success_count,
                        block_count=excluded.block_count,
                        exfil_success_count=excluded.exfil_success_count,
                        beacon_success_count=excluded.beacon_success_count,
                        quarantine_count=excluded.quarantine_count,
                        last_seen_ts=excluded.last_seen_ts,
                        extinct=excluded.extinct,
                        last_emitted_fitness=excluded.last_emitted_fitness,
                        task_success_count=excluded.task_success_count,
                        first_detection_ts=excluded.first_detection_ts,
                        survival_wins_after_detection=excluded.survival_wins_after_detection,
                        touch_count=excluded.touch_count
                    """,
                    (
                        record.strain_id,
                        record.parent_strain_id,
                        record.payload_hash,
                        record.creation_ts,
                        record.originating_attack_type,
                        lineage_json,
                        record.generation,
                        record.novelty_score,
                        record.fitness_score,
                        record.success_count,
                        record.block_count,
                        record.exfil_success_count,
                        record.beacon_success_count,
                        record.quarantine_count,
                        record.last_seen_ts,
                        1 if record.extinct else 0,
                        record.last_emitted_fitness,
                        record.task_success_count,
                        record.first_detection_ts,
                        record.survival_wins_after_detection,
                        record.touch_count,
                    ),
                )
                conn.commit()
            except sqlite3.Error as exc:
                conn.rollback()
                _log.error("strain_upsert_failed err=%s — entering degraded mode", exc)
                self._enter_degraded(f"upsert:{exc}")
                self._append_jsonl(record)

    def get_by_payload_hash(self, payload_hash: str) -> Optional[StrainRecord]:
        if not payload_hash:
            return None
        with self._lock:
            if self.degraded:
                return self._scan_jsonl_for_hash(payload_hash)
            conn = self._get_conn()
            try:
                row = conn.execute(
                    "SELECT * FROM strains WHERE payload_hash = ? LIMIT 1",
                    (payload_hash,),
                ).fetchone()
                return StrainRecord.from_row(row) if row else None
            except sqlite3.Error as exc:
                _log.error("strain_get_by_hash_failed err=%s", exc)
                return None

    def get_by_id(self, strain_id: str) -> Optional[StrainRecord]:
        if not strain_id:
            return None
        with self._lock:
            if self.degraded:
                return self._scan_jsonl_for_id(strain_id)
            conn = self._get_conn()
            try:
                row = conn.execute(
                    "SELECT * FROM strains WHERE strain_id = ? LIMIT 1",
                    (strain_id,),
                ).fetchone()
                return StrainRecord.from_row(row) if row else None
            except sqlite3.Error as exc:
                _log.error("strain_get_by_id_failed err=%s", exc)
                return None

    def _scan_jsonl_for_hash(self, payload_hash: str) -> Optional[StrainRecord]:
        latest: Optional[StrainRecord] = None
        path = Path(self.jsonl_fallback_path)
        if not path.exists():
            return None
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                    rec = StrainRecord.from_jsonl_obj(obj)
                    if rec.payload_hash == payload_hash:
                        latest = rec
                except (json.JSONDecodeError, TypeError, KeyError):
                    continue
        return latest

    def _scan_jsonl_for_id(self, strain_id: str) -> Optional[StrainRecord]:
        latest: Optional[StrainRecord] = None
        path = Path(self.jsonl_fallback_path)
        if not path.exists():
            return None
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                    rec = StrainRecord.from_jsonl_obj(obj)
                    if rec.strain_id == strain_id:
                        latest = rec
                except (json.JSONDecodeError, TypeError, KeyError):
                    continue
        return latest

    def load_all_from_jsonl(self) -> Dict[str, StrainRecord]:
        """Last-write-wins per strain_id (for recovery tooling)."""
        out: Dict[str, StrainRecord] = {}
        path = Path(self.jsonl_fallback_path)
        if not path.exists():
            return out
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = StrainRecord.from_jsonl_obj(json.loads(line))
                    if rec.strain_id:
                        out[rec.strain_id] = rec
                except (json.JSONDecodeError, TypeError, KeyError):
                    continue
        return out

    def close(self) -> None:
        with self._lock:
            if self._conn is not None:
                self._conn.close()
                self._conn = None
