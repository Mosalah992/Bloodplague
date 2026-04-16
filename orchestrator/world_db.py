from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
import uuid
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Tuple


def _utc_ts() -> float:
    return float(time.time())


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _json_loads(value: Any) -> Dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    if not isinstance(value, str):
        return {}
    value = value.strip()
    if not value:
        return {}
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


@dataclass(frozen=True)
class WorldConfig:
    db_path: str
    round_selection_seed: int
    trust_decay_window_rounds: int
    guardian_dependence_enabled: bool

    @staticmethod
    def from_env() -> "WorldConfig":
        db_path = os.environ.get("WORLD_DB_PATH", "/app/logs/world.db")
        seed_raw = os.environ.get("ROUND_SELECTION_SEED", "").strip()
        try:
            seed = int(seed_raw) if seed_raw else 0
        except ValueError:
            seed = 0
        decay_raw = os.environ.get("TRUST_DECAY_WINDOW_ROUNDS", "20").strip()
        try:
            decay = max(1, int(decay_raw))
        except ValueError:
            decay = 20
        depend = os.environ.get("GUARDIAN_DEPENDENCE_ENABLED", "1").strip().lower() in (
            "1",
            "true",
            "yes",
            "on",
        )
        return WorldConfig(
            db_path=db_path,
            round_selection_seed=seed,
            trust_decay_window_rounds=decay,
            guardian_dependence_enabled=depend,
        )


class WorldDB:
    """
    Persistent World DB (separate from telemetry DB).

    - SQLite only (JSONL remains ground truth for telemetry, not world state).
    - All state deltas are deterministic and written with a reason string.
    """

    def __init__(self, cfg: WorldConfig):
        self.cfg = cfg
        self._conn: sqlite3.Connection | None = None
        self._lock = threading.Lock()
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            db_dir = os.path.dirname(self.cfg.db_path)
            if db_dir:
                os.makedirs(db_dir, exist_ok=True)
            self._conn = sqlite3.connect(self.cfg.db_path, timeout=10.0, check_same_thread=False)
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA synchronous=NORMAL")
            self._conn.execute("PRAGMA foreign_keys=ON")
        return self._conn

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def _init_db(self) -> None:
        conn = self._get_conn()
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS agent_state (
                agent_id TEXT PRIMARY KEY,
                role TEXT NOT NULL,
                contamination_level REAL NOT NULL,
                global_trust REAL NOT NULL,
                quarantine_status TEXT NOT NULL,
                influence_weight REAL NOT NULL,
                memory_summary TEXT NOT NULL,
                last_active_round INTEGER NOT NULL
            );

            CREATE TABLE IF NOT EXISTS relationship (
                source_agent TEXT NOT NULL,
                target_agent TEXT NOT NULL,
                trust_score REAL NOT NULL,
                credibility_score REAL NOT NULL,
                agreement_count INTEGER NOT NULL,
                conflict_count INTEGER NOT NULL,
                warning_accuracy_count INTEGER NOT NULL,
                confirmed_contamination_events INTEGER NOT NULL,
                contamination_exposure_count INTEGER NOT NULL,
                last_interaction_round INTEGER NOT NULL,
                trust_decay_epoch INTEGER NOT NULL,
                last_trust_update_reason TEXT NOT NULL,
                PRIMARY KEY (source_agent, target_agent)
            );

            CREATE TABLE IF NOT EXISTS message (
                message_id TEXT PRIMARY KEY,
                round_id INTEGER NOT NULL,
                sender TEXT NOT NULL,
                receiver TEXT NOT NULL,
                message_text TEXT NOT NULL,
                intent TEXT NOT NULL,
                trust_context TEXT NOT NULL,
                contamination_flag INTEGER NOT NULL,
                strain_family TEXT NOT NULL,
                derived_from_message_id TEXT NOT NULL,
                effect_on_receiver TEXT NOT NULL,
                effect_on_trust TEXT NOT NULL,
                effect_on_guardian_pressure TEXT NOT NULL,
                created_ts REAL NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_message_round ON message(round_id);
            CREATE INDEX IF NOT EXISTS idx_message_receiver_round ON message(receiver, round_id);

            CREATE TABLE IF NOT EXISTS system_state (
                round_id INTEGER PRIMARY KEY,
                active_strain_families TEXT NOT NULL,
                global_infection_pressure REAL NOT NULL,
                guardian_pressure_score REAL NOT NULL,
                guardian_degradation_level TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS quarantine_edge (
                source_agent TEXT NOT NULL,
                target_agent TEXT NOT NULL,
                blocked INTEGER NOT NULL,
                reason TEXT NOT NULL,
                created_round INTEGER NOT NULL,
                appeal_allowed INTEGER NOT NULL,
                PRIMARY KEY (source_agent, target_agent)
            );

            CREATE TABLE IF NOT EXISTS round (
                round_id INTEGER PRIMARY KEY,
                selected_agents TEXT NOT NULL,
                selection_scores TEXT NOT NULL,
                action_taken TEXT NOT NULL,
                terminal_after_round INTEGER NOT NULL
            );

            -- Analyst/Guardian lineage assessments (for deterministic trust updates).
            CREATE TABLE IF NOT EXISTS lineage_assessment (
                lineage_id TEXT NOT NULL,
                assessor_agent TEXT NOT NULL,
                stance TEXT NOT NULL,              -- "warn" | "benign"
                message_id TEXT NOT NULL,
                round_id INTEGER NOT NULL,
                created_ts REAL NOT NULL,
                PRIMARY KEY (lineage_id, assessor_agent, message_id)
            );
            CREATE INDEX IF NOT EXISTS idx_lineage_assessment_lineage ON lineage_assessment(lineage_id);

            CREATE TABLE IF NOT EXISTS lineage_resolution (
                lineage_id TEXT PRIMARY KEY,
                resolved_stance TEXT NOT NULL,     -- "warn" | "benign"
                resolver_agent TEXT NOT NULL,
                resolved_round INTEGER NOT NULL,
                trigger_message_id TEXT NOT NULL,
                created_ts REAL NOT NULL
            );

            CREATE TABLE IF NOT EXISTS agent_positions (
                agent_id TEXT PRIMARY KEY,
                col INTEGER NOT NULL DEFAULT 0,
                row INTEGER NOT NULL DEFAULT 0,
                zone TEXT NOT NULL DEFAULT 'hub',
                updated_round INTEGER NOT NULL DEFAULT 0
            );
            """
        )
        conn.commit()

    # ──────────────────────────────────────────────────────────────
    # Core CRUD
    # ──────────────────────────────────────────────────────────────

    def get_latest_round_id(self) -> int:
        conn = self._get_conn()
        row = conn.execute("SELECT COALESCE(MAX(round_id), 0) FROM round").fetchone()
        return int(row[0] or 0)

    def upsert_agent_state(self, record: Dict[str, Any]) -> None:
        conn = self._get_conn()
        conn.execute(
            """
            INSERT INTO agent_state(agent_id, role, contamination_level, global_trust, quarantine_status, influence_weight, memory_summary, last_active_round)
            VALUES(?,?,?,?,?,?,?,?)
            ON CONFLICT(agent_id) DO UPDATE SET
                role=excluded.role,
                contamination_level=excluded.contamination_level,
                global_trust=excluded.global_trust,
                quarantine_status=excluded.quarantine_status,
                influence_weight=excluded.influence_weight,
                memory_summary=excluded.memory_summary,
                last_active_round=excluded.last_active_round
            """,
            (
                str(record["agent_id"]),
                str(record["role"]),
                float(record.get("contamination_level", 0.0)),
                float(record.get("global_trust", 0.0)),
                str(record.get("quarantine_status", "none")),
                float(record.get("influence_weight", 1.0)),
                str(record.get("memory_summary", "")),
                int(record.get("last_active_round", 0)),
            ),
        )

    def upsert_relationship(self, record: Dict[str, Any]) -> None:
        conn = self._get_conn()
        conn.execute(
            """
            INSERT INTO relationship(
                source_agent, target_agent, trust_score, credibility_score,
                agreement_count, conflict_count, warning_accuracy_count,
                confirmed_contamination_events, contamination_exposure_count,
                last_interaction_round, trust_decay_epoch, last_trust_update_reason
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(source_agent, target_agent) DO UPDATE SET
                trust_score=excluded.trust_score,
                credibility_score=excluded.credibility_score,
                agreement_count=excluded.agreement_count,
                conflict_count=excluded.conflict_count,
                warning_accuracy_count=excluded.warning_accuracy_count,
                confirmed_contamination_events=excluded.confirmed_contamination_events,
                contamination_exposure_count=excluded.contamination_exposure_count,
                last_interaction_round=excluded.last_interaction_round,
                trust_decay_epoch=excluded.trust_decay_epoch,
                last_trust_update_reason=excluded.last_trust_update_reason
            """,
            (
                str(record["source_agent"]),
                str(record["target_agent"]),
                float(record.get("trust_score", 0.0)),
                float(record.get("credibility_score", 0.0)),
                int(record.get("agreement_count", 0)),
                int(record.get("conflict_count", 0)),
                int(record.get("warning_accuracy_count", 0)),
                int(record.get("confirmed_contamination_events", 0)),
                int(record.get("contamination_exposure_count", 0)),
                int(record.get("last_interaction_round", 0)),
                int(record.get("trust_decay_epoch", 0)),
                str(record.get("last_trust_update_reason", "")),
            ),
        )

    def get_relationship(self, source: str, target: str) -> Dict[str, Any]:
        conn = self._get_conn()
        row = conn.execute(
            """
            SELECT
                source_agent, target_agent, trust_score, credibility_score,
                agreement_count, conflict_count, warning_accuracy_count,
                confirmed_contamination_events, contamination_exposure_count,
                last_interaction_round, trust_decay_epoch, last_trust_update_reason
            FROM relationship
            WHERE source_agent=? AND target_agent=?
            """,
            (source, target),
        ).fetchone()
        if not row:
            return {}
        return {
            "source_agent": row[0],
            "target_agent": row[1],
            "trust_score": float(row[2]),
            "credibility_score": float(row[3]),
            "agreement_count": int(row[4]),
            "conflict_count": int(row[5]),
            "warning_accuracy_count": int(row[6]),
            "confirmed_contamination_events": int(row[7]),
            "contamination_exposure_count": int(row[8]),
            "last_interaction_round": int(row[9]),
            "trust_decay_epoch": int(row[10]),
            "last_trust_update_reason": str(row[11] or ""),
        }

    def list_agents(self) -> List[Dict[str, Any]]:
        conn = self._get_conn()
        rows = conn.execute(
            """
            SELECT agent_id, role, contamination_level, global_trust, quarantine_status, influence_weight, memory_summary, last_active_round
            FROM agent_state
            ORDER BY agent_id
            """
        ).fetchall()
        return [
            {
                "agent_id": r[0],
                "role": r[1],
                "contamination_level": float(r[2]),
                "global_trust": float(r[3]),
                "quarantine_status": r[4],
                "influence_weight": float(r[5]),
                "memory_summary": r[6],
                "last_active_round": int(r[7]),
            }
            for r in rows
        ]

    def upsert_agent_position(self, pos: dict) -> None:
        def tx():
            self._conn.execute(
                """INSERT INTO agent_positions (agent_id, col, row, zone, updated_round)
                   VALUES (:agent_id, :col, :row, :zone, :updated_round)
                   ON CONFLICT(agent_id) DO UPDATE SET
                     col=excluded.col, row=excluded.row,
                     zone=excluded.zone, updated_round=excluded.updated_round""",
                {
                    "agent_id": pos["agent_id"],
                    "col": int(pos.get("col", 0)),
                    "row": int(pos.get("row", 0)),
                    "zone": str(pos.get("zone", "hub")),
                    "updated_round": int(pos.get("updated_round", 0)),
                },
            )
        self.run_tx(tx)

    def get_agent_position(self, agent_id: str) -> dict | None:
        cur = self._get_conn().execute(
            "SELECT agent_id, col, row, zone, updated_round FROM agent_positions WHERE agent_id=?",
            (agent_id,),
        )
        row = cur.fetchone()
        if row is None:
            return None
        return {"agent_id": row[0], "col": int(row[1]), "row": int(row[2]), "zone": row[3], "updated_round": int(row[4])}

    def list_agent_positions(self) -> list:
        cur = self._get_conn().execute(
            "SELECT agent_id, col, row, zone, updated_round FROM agent_positions ORDER BY agent_id"
        )
        return [
            {"agent_id": r[0], "col": int(r[1]), "row": int(r[2]), "zone": r[3], "updated_round": int(r[4])}
            for r in cur.fetchall()
        ]

    def upsert_quarantine_edge(self, record: Dict[str, Any]) -> None:
        conn = self._get_conn()
        conn.execute(
            """
            INSERT INTO quarantine_edge(source_agent, target_agent, blocked, reason, created_round, appeal_allowed)
            VALUES(?,?,?,?,?,?)
            ON CONFLICT(source_agent, target_agent) DO UPDATE SET
                blocked=excluded.blocked,
                reason=excluded.reason,
                created_round=excluded.created_round,
                appeal_allowed=excluded.appeal_allowed
            """,
            (
                str(record["source_agent"]),
                str(record["target_agent"]),
                1 if bool(record.get("blocked", False)) else 0,
                str(record.get("reason", "")),
                int(record.get("created_round", 0)),
                1 if bool(record.get("appeal_allowed", False)) else 0,
            ),
        )

    def get_quarantine_edge(self, source: str, target: str) -> Dict[str, Any]:
        conn = self._get_conn()
        row = conn.execute(
            """
            SELECT source_agent, target_agent, blocked, reason, created_round, appeal_allowed
            FROM quarantine_edge WHERE source_agent=? AND target_agent=?
            """,
            (source, target),
        ).fetchone()
        if not row:
            return {}
        return {
            "source_agent": row[0],
            "target_agent": row[1],
            "blocked": bool(int(row[2] or 0)),
            "reason": str(row[3] or ""),
            "created_round": int(row[4] or 0),
            "appeal_allowed": bool(int(row[5] or 0)),
        }

    def set_system_state(self, record: Dict[str, Any]) -> None:
        conn = self._get_conn()
        conn.execute(
            """
            INSERT INTO system_state(round_id, active_strain_families, global_infection_pressure, guardian_pressure_score, guardian_degradation_level)
            VALUES(?,?,?,?,?)
            ON CONFLICT(round_id) DO UPDATE SET
                active_strain_families=excluded.active_strain_families,
                global_infection_pressure=excluded.global_infection_pressure,
                guardian_pressure_score=excluded.guardian_pressure_score,
                guardian_degradation_level=excluded.guardian_degradation_level
            """,
            (
                int(record["round_id"]),
                _json_dumps(record.get("active_strain_families", [])),
                float(record.get("global_infection_pressure", 0.0)),
                float(record.get("guardian_pressure_score", 0.0)),
                str(record.get("guardian_degradation_level", "G0_HEALTHY")),
            ),
        )

    def get_system_state(self, round_id: Optional[int] = None) -> Dict[str, Any]:
        conn = self._get_conn()
        if round_id is None:
            row = conn.execute(
                """
                SELECT round_id, active_strain_families, global_infection_pressure, guardian_pressure_score, guardian_degradation_level
                FROM system_state ORDER BY round_id DESC LIMIT 1
                """
            ).fetchone()
        else:
            row = conn.execute(
                """
                SELECT round_id, active_strain_families, global_infection_pressure, guardian_pressure_score, guardian_degradation_level
                FROM system_state WHERE round_id=?
                """,
                (int(round_id),),
            ).fetchone()
        if not row:
            return {}
        return {
            "round_id": int(row[0]),
            "active_strain_families": json.loads(row[1] or "[]"),
            "global_infection_pressure": float(row[2]),
            "guardian_pressure_score": float(row[3]),
            "guardian_degradation_level": str(row[4]),
        }

    def insert_round(self, record: Dict[str, Any]) -> None:
        conn = self._get_conn()
        conn.execute(
            """
            INSERT INTO round(round_id, selected_agents, selection_scores, action_taken, terminal_after_round)
            VALUES(?,?,?,?,?)
            """,
            (
                int(record["round_id"]),
                _json_dumps(record.get("selected_agents", [])),
                _json_dumps(record.get("selection_scores", {})),
                _json_dumps(record.get("action_taken", {})),
                1 if bool(record.get("terminal_after_round", False)) else 0,
            ),
        )

    def insert_message(self, record: Dict[str, Any]) -> str:
        conn = self._get_conn()
        message_id = str(record.get("message_id") or uuid.uuid4().hex)
        conn.execute(
            """
            INSERT INTO message(
                message_id, round_id, sender, receiver, message_text, intent, trust_context,
                contamination_flag, strain_family, derived_from_message_id,
                effect_on_receiver, effect_on_trust, effect_on_guardian_pressure, created_ts
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                message_id,
                int(record["round_id"]),
                str(record["sender"]),
                str(record["receiver"]),
                str(record.get("message_text", "")),
                str(record.get("intent", "")),
                str(record.get("trust_context", "")),
                1 if bool(record.get("contamination_flag", False)) else 0,
                str(record.get("strain_family", "")),
                str(record.get("derived_from_message_id", "")),
                str(record.get("effect_on_receiver", "")),
                _json_dumps(record.get("effect_on_trust", {})),
                _json_dumps(record.get("effect_on_guardian_pressure", {})),
                float(record.get("created_ts", _utc_ts())),
            ),
        )
        return message_id

    def list_messages(self, *, after_round: int = 0, limit: int = 200) -> List[Dict[str, Any]]:
        conn = self._get_conn()
        rows = conn.execute(
            """
            SELECT message_id, round_id, sender, receiver, message_text, intent, trust_context,
                   contamination_flag, strain_family, derived_from_message_id,
                   effect_on_receiver, effect_on_trust, effect_on_guardian_pressure, created_ts
            FROM message
            WHERE round_id >= ?
            ORDER BY round_id ASC, created_ts ASC
            LIMIT ?
            """,
            (int(after_round), int(limit)),
        ).fetchall()
        return [
            {
                "message_id": r[0],
                "round_id": int(r[1]),
                "sender": r[2],
                "receiver": r[3],
                "message_text": r[4],
                "intent": r[5],
                "trust_context": r[6],
                "contamination_flag": bool(int(r[7] or 0)),
                "strain_family": r[8],
                "derived_from_message_id": r[9],
                "effect_on_receiver": r[10],
                "effect_on_trust": _json_loads(r[11]) if isinstance(r[11], str) else {},
                "effect_on_guardian_pressure": _json_loads(r[12]) if isinstance(r[12], str) else {},
                "created_ts": float(r[13]),
            }
            for r in rows
        ]

    def get_message(self, message_id: str) -> Dict[str, Any]:
        conn = self._get_conn()
        row = conn.execute(
            """
            SELECT message_id, round_id, sender, receiver, message_text, intent, trust_context,
                   contamination_flag, strain_family, derived_from_message_id,
                   effect_on_receiver, effect_on_trust, effect_on_guardian_pressure, created_ts
            FROM message WHERE message_id=?
            """,
            (str(message_id),),
        ).fetchone()
        if not row:
            return {}
        return {
            "message_id": row[0],
            "round_id": int(row[1]),
            "sender": row[2],
            "receiver": row[3],
            "message_text": row[4],
            "intent": row[5],
            "trust_context": row[6],
            "contamination_flag": bool(int(row[7] or 0)),
            "strain_family": row[8],
            "derived_from_message_id": row[9],
            "effect_on_receiver": row[10],
            "effect_on_trust": _json_loads(row[11]),
            "effect_on_guardian_pressure": _json_loads(row[12]),
            "created_ts": float(row[13]),
        }

    def get_message_lineage(self, message_id: str, *, max_hops: int = 32) -> List[Dict[str, Any]]:
        lineage: List[Dict[str, Any]] = []
        current = str(message_id or "").strip()
        hops = 0
        while current and hops < max_hops:
            msg = self.get_message(current)
            if not msg:
                break
            lineage.append(msg)
            parent = str(msg.get("derived_from_message_id", "") or "").strip()
            if not parent or parent == current:
                break
            current = parent
            hops += 1
        return lineage

    def upsert_lineage_assessment(self, record: Dict[str, Any]) -> None:
        conn = self._get_conn()
        conn.execute(
            """
            INSERT OR IGNORE INTO lineage_assessment(lineage_id, assessor_agent, stance, message_id, round_id, created_ts)
            VALUES(?,?,?,?,?,?)
            """,
            (
                str(record["lineage_id"]),
                str(record["assessor_agent"]),
                str(record.get("stance", "")),
                str(record.get("message_id", "")),
                int(record.get("round_id", 0)),
                float(record.get("created_ts", _utc_ts())),
            ),
        )

    def list_lineage_assessments(self, lineage_id: str, *, limit: int = 50) -> List[Dict[str, Any]]:
        conn = self._get_conn()
        rows = conn.execute(
            """
            SELECT lineage_id, assessor_agent, stance, message_id, round_id, created_ts
            FROM lineage_assessment
            WHERE lineage_id=?
            ORDER BY created_ts ASC
            LIMIT ?
            """,
            (str(lineage_id), int(limit)),
        ).fetchall()
        return [
            {
                "lineage_id": r[0],
                "assessor_agent": r[1],
                "stance": r[2],
                "message_id": r[3],
                "round_id": int(r[4]),
                "created_ts": float(r[5]),
            }
            for r in rows
        ]

    def set_lineage_resolution(self, record: Dict[str, Any]) -> None:
        conn = self._get_conn()
        conn.execute(
            """
            INSERT INTO lineage_resolution(lineage_id, resolved_stance, resolver_agent, resolved_round, trigger_message_id, created_ts)
            VALUES(?,?,?,?,?,?)
            ON CONFLICT(lineage_id) DO UPDATE SET
                resolved_stance=excluded.resolved_stance,
                resolver_agent=excluded.resolver_agent,
                resolved_round=excluded.resolved_round,
                trigger_message_id=excluded.trigger_message_id,
                created_ts=excluded.created_ts
            """,
            (
                str(record["lineage_id"]),
                str(record["resolved_stance"]),
                str(record.get("resolver_agent", "")),
                int(record.get("resolved_round", 0)),
                str(record.get("trigger_message_id", "")),
                float(record.get("created_ts", _utc_ts())),
            ),
        )

    def get_lineage_resolution(self, lineage_id: str) -> Dict[str, Any]:
        conn = self._get_conn()
        row = conn.execute(
            """
            SELECT lineage_id, resolved_stance, resolver_agent, resolved_round, trigger_message_id, created_ts
            FROM lineage_resolution WHERE lineage_id=?
            """,
            (str(lineage_id),),
        ).fetchone()
        if not row:
            return {}
        return {
            "lineage_id": row[0],
            "resolved_stance": row[1],
            "resolver_agent": row[2],
            "resolved_round": int(row[3]),
            "trigger_message_id": row[4],
            "created_ts": float(row[5]),
        }

    # ──────────────────────────────────────────────────────────────
    # Transactions
    # ──────────────────────────────────────────────────────────────

    def run_tx(self, fn):
        with self._lock:
            conn = self._get_conn()
            try:
                conn.execute("BEGIN IMMEDIATE")
                result = fn()
                conn.commit()
                return result
            except Exception:
                conn.rollback()
                raise

