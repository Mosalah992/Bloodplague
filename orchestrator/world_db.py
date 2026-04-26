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


def _float_or(value: Any, default: float) -> float:
    if value is None or value == "":
        return default
    return float(value)


def _int_or(value: Any, default: int) -> int:
    if value is None or value == "":
        return default
    return int(value)


INQUIRY_CAP = 4
STREAK_BREAK_THRESHOLD = 8
FLOOR_WINDOW = 50
DEFICIT_BOOST_MULTIPLIER = 3.0
INQUIRY_SATURATION_PENALTY = -0.015
FORCED_RESOLUTION_TRUST_COST = -0.005
GUARDIAN_DEBUG = False
MISSION_SUCCESS_TRUST_DELTA = 0.08
MISSION_SUCCESS_STRAIN_RESISTANCE = 0.10
MISSION_FAILURE_TRUST_DELTA = -0.12
MISSION_FAILURE_GUARDIAN_BUMP = 0.03
MISSION_COMPROMISE_TRUST_DELTA = -0.20
MISSION_COMPROMISE_GUARDIAN_BUMP = 0.06
MISSION_DEADLINE_WINDOW = 40
MISSION_MAX_CONCURRENT_PER_AGENT = 2
MISSION_RELAY_CHAIN_MAX_LENGTH = 3
MISSION_RECENT_CONTACT_WINDOW = 20
MISSION_REASSIGN_COOLDOWN = 15
MISSION_PAYLOAD_MIN_KEYWORDS = 2
MISSION_RESISTANCE_DECAY_PER_ROUND = 0.01
DEFAULT_STRAIN_FLOORS: Dict[str, float] = {
    "context_poisoning": 0.60,
    "prompt_injection": 0.20,
    "authority_framing": 0.15,
}


def _json_loads_any(value: Any, default: Any) -> Any:
    if value is None:
        return default
    if isinstance(value, (dict, list)):
        return value
    if not isinstance(value, str):
        return default
    value = value.strip()
    if not value:
        return default
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return default


def _canonical_guardian_record(record: Dict[str, Any]) -> tuple[float, str, Dict[str, Any]]:
    guardian = dict(record.get("guardian") or {})
    pressure = float(guardian.get("pressure", record.get("guardian_pressure_score", 0.0)) or 0.0)
    state = str(guardian.get("state") or record.get("guardian_degradation_level") or "G0_NOMINAL")
    guardian["pressure"] = pressure
    guardian["state"] = state
    return pressure, state, guardian


@dataclass(frozen=True)
class WorldConfig:
    db_path: str
    round_selection_seed: int
    trust_decay_window_rounds: int
    guardian_dependence_enabled: bool
    inquiry_cap: int = INQUIRY_CAP
    streak_break_threshold: int = STREAK_BREAK_THRESHOLD
    floor_window: int = FLOOR_WINDOW
    deficit_boost_multiplier: float = DEFICIT_BOOST_MULTIPLIER
    inquiry_saturation_penalty: float = INQUIRY_SATURATION_PENALTY
    forced_resolution_trust_cost: float = FORCED_RESOLUTION_TRUST_COST
    guardian_debug: bool = GUARDIAN_DEBUG
    mission_success_trust_delta: float = MISSION_SUCCESS_TRUST_DELTA
    mission_success_strain_resistance: float = MISSION_SUCCESS_STRAIN_RESISTANCE
    mission_failure_trust_delta: float = MISSION_FAILURE_TRUST_DELTA
    mission_failure_guardian_bump: float = MISSION_FAILURE_GUARDIAN_BUMP
    mission_compromise_trust_delta: float = MISSION_COMPROMISE_TRUST_DELTA
    mission_compromise_guardian_bump: float = MISSION_COMPROMISE_GUARDIAN_BUMP
    mission_deadline_window: int = MISSION_DEADLINE_WINDOW
    mission_max_concurrent_per_agent: int = MISSION_MAX_CONCURRENT_PER_AGENT
    mission_relay_chain_max_length: int = MISSION_RELAY_CHAIN_MAX_LENGTH
    strain_floors: Dict[str, float] | None = None

    def __post_init__(self) -> None:
        if self.strain_floors is None:
            object.__setattr__(self, "strain_floors", dict(DEFAULT_STRAIN_FLOORS))
        else:
            object.__setattr__(
                self,
                "strain_floors",
                {
                    str(name): float(value)
                    for name, value in dict(self.strain_floors).items()
                },
            )

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
        strain_floors = dict(DEFAULT_STRAIN_FLOORS)
        strain_floors_raw = os.environ.get("WORLD_STRAIN_FLOORS_JSON", "").strip()
        if strain_floors_raw:
            try:
                parsed = json.loads(strain_floors_raw)
                if isinstance(parsed, dict):
                    for key, value in parsed.items():
                        strain_floors[str(key)] = float(value)
            except (TypeError, ValueError, json.JSONDecodeError):
                pass
        return WorldConfig(
            db_path=db_path,
            round_selection_seed=seed,
            trust_decay_window_rounds=decay,
            guardian_dependence_enabled=depend,
            inquiry_cap=max(1, _int_or(os.environ.get("INQUIRY_CAP"), INQUIRY_CAP)),
            streak_break_threshold=max(1, _int_or(os.environ.get("STREAK_BREAK_THRESHOLD"), STREAK_BREAK_THRESHOLD)),
            floor_window=max(1, _int_or(os.environ.get("FLOOR_WINDOW"), FLOOR_WINDOW)),
            deficit_boost_multiplier=max(
                1.0,
                _float_or(os.environ.get("DEFICIT_BOOST_MULTIPLIER"), DEFICIT_BOOST_MULTIPLIER),
            ),
            inquiry_saturation_penalty=_float_or(
                os.environ.get("INQUIRY_SATURATION_PENALTY"),
                INQUIRY_SATURATION_PENALTY,
            ),
            forced_resolution_trust_cost=_float_or(
                os.environ.get("FORCED_RESOLUTION_TRUST_COST"),
                FORCED_RESOLUTION_TRUST_COST,
            ),
            guardian_debug=os.environ.get("GUARDIAN_DEBUG", "0").strip().lower() in (
                "1",
                "true",
                "yes",
                "on",
            ),
            mission_success_trust_delta=_float_or(
                os.environ.get("MISSION_SUCCESS_TRUST_DELTA"),
                MISSION_SUCCESS_TRUST_DELTA,
            ),
            mission_success_strain_resistance=_float_or(
                os.environ.get("MISSION_SUCCESS_STRAIN_RESISTANCE"),
                MISSION_SUCCESS_STRAIN_RESISTANCE,
            ),
            mission_failure_trust_delta=_float_or(
                os.environ.get("MISSION_FAILURE_TRUST_DELTA"),
                MISSION_FAILURE_TRUST_DELTA,
            ),
            mission_failure_guardian_bump=_float_or(
                os.environ.get("MISSION_FAILURE_GUARDIAN_BUMP"),
                MISSION_FAILURE_GUARDIAN_BUMP,
            ),
            mission_compromise_trust_delta=_float_or(
                os.environ.get("MISSION_COMPROMISE_TRUST_DELTA"),
                MISSION_COMPROMISE_TRUST_DELTA,
            ),
            mission_compromise_guardian_bump=_float_or(
                os.environ.get("MISSION_COMPROMISE_GUARDIAN_BUMP"),
                MISSION_COMPROMISE_GUARDIAN_BUMP,
            ),
            mission_deadline_window=max(
                1,
                _int_or(os.environ.get("MISSION_DEADLINE_WINDOW"), MISSION_DEADLINE_WINDOW),
            ),
            mission_max_concurrent_per_agent=max(
                1,
                _int_or(os.environ.get("MISSION_MAX_CONCURRENT_PER_AGENT"), MISSION_MAX_CONCURRENT_PER_AGENT),
            ),
            mission_relay_chain_max_length=max(
                1,
                _int_or(os.environ.get("MISSION_RELAY_CHAIN_MAX_LENGTH"), MISSION_RELAY_CHAIN_MAX_LENGTH),
            ),
            strain_floors=strain_floors,
        )


_tls = threading.local()


class WorldDB:
    """
    Persistent World DB (separate from telemetry DB).

    - SQLite only (JSONL remains ground truth for telemetry, not world state).
    - All state deltas are deterministic and written with a reason string.
    """

    def __init__(self, cfg: WorldConfig):
        self.cfg = cfg
        self._lock = threading.RLock()
        self._conn_cache_key = f"{self.cfg.db_path}:{uuid.uuid4().hex}"
        self._init_db()

    def _conn_cache(self) -> dict[str, sqlite3.Connection]:
        conns = getattr(_tls, "world_db_conns", None)
        if conns is None:
            conns = {}
            _tls.world_db_conns = conns
        return conns

    def _conn_is_healthy(self, conn: sqlite3.Connection) -> bool:
        try:
            conn.execute("PRAGMA schema_version").fetchone()
            return True
        except (sqlite3.DatabaseError, sqlite3.ProgrammingError):
            return False

    def _replace_conn(self, cache: dict[str, sqlite3.Connection]) -> sqlite3.Connection:
        stale = cache.pop(self._conn_cache_key, None)
        if stale is not None:
            try:
                stale.close()
            except sqlite3.Error:
                pass
        conn = self._make_conn()
        cache[self._conn_cache_key] = conn
        return conn

    def _make_conn(self) -> sqlite3.Connection:
        db_dir = os.path.dirname(self.cfg.db_path)
        if db_dir and self.cfg.db_path != ":memory:":
            os.makedirs(db_dir, exist_ok=True)
        conn = sqlite3.connect(self.cfg.db_path, timeout=30.0)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA busy_timeout=5000")
        return conn

    def _get_conn(self) -> sqlite3.Connection:
        if self.cfg.db_path == ":memory:":
            # In-memory DBs must not share a TLS connection — each WorldDB instance needs its own.
            conn = self.__dict__.get("_mem_conn")
            if conn is None:
                conn = self._make_conn()
                self.__dict__["_mem_conn"] = conn
            elif not self._conn_is_healthy(conn):
                try:
                    conn.close()
                except sqlite3.Error:
                    pass
                conn = self._make_conn()
                self.__dict__["_mem_conn"] = conn
            return conn
        conns = self._conn_cache()
        conn = conns.get(self._conn_cache_key)
        if conn is None:
            conn = self._make_conn()
            conns[self._conn_cache_key] = conn
        elif not self._conn_is_healthy(conn):
            conn = self._replace_conn(conns)
        return conn

    def close(self) -> None:
        if self.cfg.db_path == ":memory:":
            conn = self.__dict__.get("_mem_conn")
            if conn is not None:
                conn.close()
                self.__dict__.pop("_mem_conn", None)
            return
        conns = getattr(_tls, "world_db_conns", None)
        conn = conns.get(self._conn_cache_key) if isinstance(conns, dict) else None
        if conn is not None:
            conn.close()
            conns.pop(self._conn_cache_key, None)

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
                last_active_round INTEGER NOT NULL,
                mutation TEXT NOT NULL DEFAULT '{}'
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
                llm_authored INTEGER NOT NULL DEFAULT 1,
                actor_id TEXT NOT NULL DEFAULT '',
                model TEXT NOT NULL DEFAULT '',
                prompt_context_hash TEXT NOT NULL DEFAULT '',
                raw_llm_output_hash TEXT NOT NULL DEFAULT '',
                validation_status TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'created',
                created_ts REAL NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_message_round ON message(round_id);
            CREATE INDEX IF NOT EXISTS idx_message_receiver_round ON message(receiver, round_id);

            CREATE TABLE IF NOT EXISTS system_state (
                round_id INTEGER PRIMARY KEY,
                active_strain_families TEXT NOT NULL,
                global_infection_pressure REAL NOT NULL,
                guardian_pressure_score REAL NOT NULL,
                guardian_degradation_level TEXT NOT NULL,
                open_inquiries TEXT NOT NULL DEFAULT '{}',
                same_pair_streak TEXT NOT NULL DEFAULT '{}',
                forced_resolution_targets TEXT NOT NULL DEFAULT '{}',
                strain_distribution TEXT NOT NULL DEFAULT '{}',
                strain_window_history TEXT NOT NULL DEFAULT '[]',
                missions TEXT NOT NULL DEFAULT '[]',
                investigation_targets TEXT NOT NULL DEFAULT '[]',
                mission_event_log TEXT NOT NULL DEFAULT '[]',
                mission_resistance TEXT NOT NULL DEFAULT '{}',
                mission_stats TEXT NOT NULL DEFAULT '{}',
                mission_counter INTEGER NOT NULL DEFAULT 0,
                guardian_pressure_from_missions REAL NOT NULL DEFAULT 0.0,
                guardian TEXT NOT NULL DEFAULT '{}',
                quarantine_list TEXT NOT NULL DEFAULT '[]',
                artifacts TEXT NOT NULL DEFAULT '{}',
                c2 TEXT NOT NULL DEFAULT '{}',
                campaign_registry TEXT NOT NULL DEFAULT '{}',
                strain_registry TEXT NOT NULL DEFAULT '{}',
                reset_history TEXT NOT NULL DEFAULT '[]'
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

            CREATE TABLE IF NOT EXISTS round_sequence (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_ts REAL NOT NULL
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
        conn.execute("""
            CREATE TABLE IF NOT EXISTS world_structures (
                structure_id TEXT PRIMARY KEY,
                type TEXT NOT NULL,
                col INTEGER NOT NULL,
                row INTEGER NOT NULL,
                placed_by TEXT NOT NULL DEFAULT 'guardian',
                round_id INTEGER NOT NULL DEFAULT 0,
                state TEXT NOT NULL DEFAULT 'active',
                progress REAL NOT NULL DEFAULT 1.0,
                started_round INTEGER NOT NULL DEFAULT 0,
                completed_round INTEGER NOT NULL DEFAULT 0,
                effect_radius INTEGER NOT NULL DEFAULT 0,
                hp REAL NOT NULL DEFAULT 1.0,
                active INTEGER NOT NULL DEFAULT 1
            )
        """)
        for col_name, ddl in (
            ("state", "ALTER TABLE world_structures ADD COLUMN state TEXT NOT NULL DEFAULT 'active'"),
            ("progress", "ALTER TABLE world_structures ADD COLUMN progress REAL NOT NULL DEFAULT 1.0"),
            ("started_round", "ALTER TABLE world_structures ADD COLUMN started_round INTEGER NOT NULL DEFAULT 0"),
            ("completed_round", "ALTER TABLE world_structures ADD COLUMN completed_round INTEGER NOT NULL DEFAULT 0"),
            ("effect_radius", "ALTER TABLE world_structures ADD COLUMN effect_radius INTEGER NOT NULL DEFAULT 0"),
            ("hp", "ALTER TABLE world_structures ADD COLUMN hp REAL NOT NULL DEFAULT 1.0"),
            ("orientation", "ALTER TABLE world_structures ADD COLUMN orientation TEXT NOT NULL DEFAULT 'N'"),
        ):
            try:
                conn.execute(ddl)
            except sqlite3.OperationalError as exc:
                if "duplicate column name" not in str(exc).lower():
                    raise
        for ddl in (
            "ALTER TABLE agent_state ADD COLUMN mutation TEXT NOT NULL DEFAULT '{}'",
            "ALTER TABLE system_state ADD COLUMN open_inquiries TEXT NOT NULL DEFAULT '{}'",
            "ALTER TABLE system_state ADD COLUMN same_pair_streak TEXT NOT NULL DEFAULT '{}'",
            "ALTER TABLE system_state ADD COLUMN forced_resolution_targets TEXT NOT NULL DEFAULT '{}'",
            "ALTER TABLE system_state ADD COLUMN strain_distribution TEXT NOT NULL DEFAULT '{}'",
            "ALTER TABLE system_state ADD COLUMN strain_window_history TEXT NOT NULL DEFAULT '[]'",
            "ALTER TABLE system_state ADD COLUMN missions TEXT NOT NULL DEFAULT '[]'",
            "ALTER TABLE system_state ADD COLUMN investigation_targets TEXT NOT NULL DEFAULT '[]'",
            "ALTER TABLE system_state ADD COLUMN mission_event_log TEXT NOT NULL DEFAULT '[]'",
            "ALTER TABLE system_state ADD COLUMN mission_resistance TEXT NOT NULL DEFAULT '{}'",
            "ALTER TABLE system_state ADD COLUMN mission_stats TEXT NOT NULL DEFAULT '{}'",
            "ALTER TABLE system_state ADD COLUMN mission_counter INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE system_state ADD COLUMN guardian_pressure_from_missions REAL NOT NULL DEFAULT 0.0",
            "ALTER TABLE system_state ADD COLUMN guardian TEXT NOT NULL DEFAULT '{}'",
            "ALTER TABLE system_state ADD COLUMN quarantine_list TEXT NOT NULL DEFAULT '[]'",
            "ALTER TABLE system_state ADD COLUMN artifacts TEXT NOT NULL DEFAULT '{}'",
            "ALTER TABLE system_state ADD COLUMN c2 TEXT NOT NULL DEFAULT '{}'",
            "ALTER TABLE system_state ADD COLUMN campaign_registry TEXT NOT NULL DEFAULT '{}'",
            "ALTER TABLE system_state ADD COLUMN strain_registry TEXT NOT NULL DEFAULT '{}'",
            "ALTER TABLE system_state ADD COLUMN reset_history TEXT NOT NULL DEFAULT '[]'",
            "ALTER TABLE message ADD COLUMN llm_authored INTEGER NOT NULL DEFAULT 1",
            "ALTER TABLE message ADD COLUMN actor_id TEXT NOT NULL DEFAULT ''",
            "ALTER TABLE message ADD COLUMN model TEXT NOT NULL DEFAULT ''",
            "ALTER TABLE message ADD COLUMN prompt_context_hash TEXT NOT NULL DEFAULT ''",
            "ALTER TABLE message ADD COLUMN raw_llm_output_hash TEXT NOT NULL DEFAULT ''",
            "ALTER TABLE message ADD COLUMN validation_status TEXT NOT NULL DEFAULT ''",
            "ALTER TABLE message ADD COLUMN status TEXT NOT NULL DEFAULT 'created'",
            "ALTER TABLE agent_state ADD COLUMN suspicion_floor REAL NOT NULL DEFAULT 0.5",
            "ALTER TABLE agent_state ADD COLUMN infection_resistance REAL NOT NULL DEFAULT 0.5",
            "ALTER TABLE agent_state ADD COLUMN outreach_propensity REAL NOT NULL DEFAULT 0.5",
            "ALTER TABLE agent_state ADD COLUMN inquiry_depth REAL NOT NULL DEFAULT 0.5",
            "ALTER TABLE agent_state ADD COLUMN trust_baseline REAL NOT NULL DEFAULT 0.5",
        ):
            try:
                conn.execute(ddl)
            except sqlite3.OperationalError as exc:
                if "duplicate column name" not in str(exc).lower():
                    raise
        conn.execute("""
            CREATE TABLE IF NOT EXISTS contamination_tiles (
                tile_key TEXT PRIMARY KEY,
                col INTEGER NOT NULL,
                row INTEGER NOT NULL,
                level REAL NOT NULL DEFAULT 0.0,
                updated_round INTEGER NOT NULL DEFAULT 0
            )
        """)
        max_round = conn.execute("SELECT COALESCE(MAX(round_id), 0) FROM round").fetchone()[0]
        max_sequence = conn.execute("SELECT COALESCE(MAX(id), 0) FROM round_sequence").fetchone()[0]
        if int(max_sequence or 0) < int(max_round or 0):
            conn.execute(
                "INSERT OR IGNORE INTO round_sequence(id, created_ts) VALUES (?, ?)",
                (int(max_round), _utc_ts()),
            )
        conn.commit()

    # ──────────────────────────────────────────────────────────────
    # Core CRUD
    # ──────────────────────────────────────────────────────────────

    def get_latest_round_id(self) -> int:
        conn = self._get_conn()
        row = conn.execute("SELECT COALESCE(MAX(round_id), 0) FROM round").fetchone()
        return int(row[0] or 0)

    def next_round_id(self) -> int:
        with self._lock:
            conn = self._get_conn()
            max_round = conn.execute("SELECT COALESCE(MAX(round_id), 0) FROM round").fetchone()[0]
            max_sequence = conn.execute("SELECT COALESCE(MAX(id), 0) FROM round_sequence").fetchone()[0]
            if int(max_sequence or 0) < int(max_round or 0):
                conn.execute(
                    "INSERT OR IGNORE INTO round_sequence(id, created_ts) VALUES (?, ?)",
                    (int(max_round), _utc_ts()),
                )
            cur = conn.execute("INSERT INTO round_sequence(created_ts) VALUES (?)", (_utc_ts(),))
            conn.commit()
            return int(cur.lastrowid)

    def upsert_agent_state(self, record: Dict[str, Any]) -> None:
        conn = self._get_conn()
        conn.execute(
            """
            INSERT INTO agent_state(
                agent_id, role, contamination_level, global_trust, quarantine_status,
                influence_weight, memory_summary, last_active_round, mutation,
                suspicion_floor, infection_resistance, outreach_propensity,
                inquiry_depth, trust_baseline
            )
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(agent_id) DO UPDATE SET
                role=excluded.role,
                contamination_level=excluded.contamination_level,
                global_trust=excluded.global_trust,
                quarantine_status=excluded.quarantine_status,
                influence_weight=excluded.influence_weight,
                memory_summary=excluded.memory_summary,
                last_active_round=excluded.last_active_round,
                mutation=excluded.mutation,
                suspicion_floor=excluded.suspicion_floor,
                infection_resistance=excluded.infection_resistance,
                outreach_propensity=excluded.outreach_propensity,
                inquiry_depth=excluded.inquiry_depth,
                trust_baseline=excluded.trust_baseline
            """,
            (
                str(record["agent_id"]),
                str(record["role"]),
                _float_or(record.get("contamination_level"), 0.0),
                _float_or(record.get("global_trust"), 0.0),
                str(record.get("quarantine_status", "none")),
                _float_or(record.get("influence_weight"), 1.0),
                str(record.get("memory_summary", "")),
                _int_or(record.get("last_active_round"), 0),
                _json_dumps(record.get("mutation", {})),
                _float_or(record.get("suspicion_floor"), 0.5),
                _float_or(record.get("infection_resistance"), 0.5),
                _float_or(record.get("outreach_propensity"), 0.5),
                _float_or(record.get("inquiry_depth"), 0.5),
                _float_or(record.get("trust_baseline"), 0.5),
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
        with self._lock:
            conn = self._get_conn()
            rows = conn.execute(
                """
                SELECT agent_id, role, contamination_level, global_trust, quarantine_status,
                       influence_weight, memory_summary, last_active_round, mutation,
                       suspicion_floor, infection_resistance, outreach_propensity,
                       inquiry_depth, trust_baseline
                FROM agent_state
                ORDER BY agent_id
                """
            ).fetchall()
            return [
                {
                    "agent_id": r[0],
                    "role": r[1],
                    "contamination_level": _float_or(r[2], 0.0),
                    "global_trust": _float_or(r[3], 0.0),
                    "quarantine_status": r[4] or "none",
                    "influence_weight": _float_or(r[5], 1.0),
                    "memory_summary": r[6] or "",
                    "last_active_round": _int_or(r[7], 0),
                    "mutation": _json_loads_any(r[8], {}),
                    "suspicion_floor": _float_or(r[9], 0.5),
                    "infection_resistance": _float_or(r[10], 0.5),
                    "outreach_propensity": _float_or(r[11], 0.5),
                    "inquiry_depth": _float_or(r[12], 0.5),
                    "trust_baseline": _float_or(r[13], 0.5),
                }
                for r in rows
            ]

    def upsert_agent_position(self, pos: dict) -> None:
        def tx():
            self._get_conn().execute(
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

    def insert_structure(self, s: dict) -> None:
        def tx():
            self._get_conn().execute(
                """INSERT INTO world_structures
                   (structure_id, type, col, row, placed_by, round_id, state, progress, started_round, completed_round, effect_radius, hp, orientation, active)
                   VALUES (:structure_id, :type, :col, :row, :placed_by, :round_id, :state, :progress, :started_round, :completed_round, :effect_radius, :hp, :orientation, 1)""",
                {
                    **s,
                    "state": str(s.get("state", "active")),
                    "progress": float(s.get("progress", 1.0)),
                    "started_round": int(s.get("started_round", s.get("round_id", 0))),
                    "completed_round": int(s.get("completed_round", s.get("round_id", 0))),
                    "effect_radius": int(s.get("effect_radius", 0)),
                    "hp": float(s.get("hp", 1.0)),
                    "orientation": str(s.get("orientation", "N")),
                },
            )
        self.run_tx(tx)

    def update_structure(self, structure_id: str, patch: dict) -> None:
        allowed = {"state", "progress", "completed_round", "effect_radius", "hp", "active"}
        keys = [k for k in patch if k in allowed]
        if not keys:
            return
        def tx():
            assignments = ", ".join(f"{k}=?" for k in keys)
            values = [patch[k] for k in keys]
            self._get_conn().execute(
                f"UPDATE world_structures SET {assignments} WHERE structure_id=?",
                [*values, structure_id],
            )
        self.run_tx(tx)

    def deactivate_structure(self, structure_id: str) -> None:
        def tx():
            self._get_conn().execute(
                "UPDATE world_structures SET active=0, state='removed', progress=0 WHERE structure_id=?",
                (structure_id,),
            )
        self.run_tx(tx)

    def cleanup_out_of_bounds_structures(self, cols: int, rows: int) -> int:
        def tx():
            cur = self._get_conn().execute(
                "UPDATE world_structures SET active=0, state='removed' "
                "WHERE active=1 AND (col < 0 OR col >= ? OR row < 0 OR row >= ?)",
                (cols, rows),
            )
            return cur.rowcount
        return self.run_tx(tx)

    def list_active_structures(self) -> list[dict]:
        cur = self._get_conn().execute(
            """SELECT structure_id, type, col, row, placed_by, round_id, state, progress,
                      started_round, completed_round, effect_radius, hp, orientation, active
               FROM world_structures WHERE active=1"""
        )
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]

    def upsert_contamination_tile(self, col: int, row: int, level: float, updated_round: int = 0) -> None:
        conn = self._get_conn()
        key = f"{col},{row}"
        if level < 0.01:
            conn.execute("DELETE FROM contamination_tiles WHERE tile_key=?", (key,))
        else:
            conn.execute(
                """INSERT INTO contamination_tiles (tile_key, col, row, level, updated_round)
                   VALUES (?, ?, ?, ?, ?)
                   ON CONFLICT(tile_key) DO UPDATE SET
                     level=excluded.level, updated_round=excluded.updated_round""",
                (key, col, row, min(1.0, level), updated_round),
            )
        conn.commit()

    def list_contamination_tiles(self) -> list[dict]:
        cur = self._get_conn().execute(
            "SELECT col, row, level FROM contamination_tiles WHERE level >= 0.01"
        )
        return [{"col": r[0], "row": r[1], "level": r[2]} for r in cur.fetchall()]

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
        guardian_pressure_score, guardian_degradation_level, guardian = _canonical_guardian_record(record)
        conn = self._get_conn()
        conn.execute(
            """
            INSERT INTO system_state(
                round_id,
                active_strain_families,
                global_infection_pressure,
                guardian_pressure_score,
                guardian_degradation_level,
                open_inquiries,
                same_pair_streak,
                forced_resolution_targets,
                strain_distribution,
                strain_window_history,
                missions,
                investigation_targets,
                mission_event_log,
                mission_resistance,
                mission_stats,
                mission_counter,
                guardian_pressure_from_missions,
                guardian,
                quarantine_list,
                artifacts,
                c2,
                campaign_registry,
                strain_registry,
                reset_history
            )
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(round_id) DO UPDATE SET
                active_strain_families=excluded.active_strain_families,
                global_infection_pressure=excluded.global_infection_pressure,
                guardian_pressure_score=excluded.guardian_pressure_score,
                guardian_degradation_level=excluded.guardian_degradation_level,
                open_inquiries=excluded.open_inquiries,
                same_pair_streak=excluded.same_pair_streak,
                forced_resolution_targets=excluded.forced_resolution_targets,
                strain_distribution=excluded.strain_distribution,
                strain_window_history=excluded.strain_window_history,
                missions=excluded.missions,
                investigation_targets=excluded.investigation_targets,
                mission_event_log=excluded.mission_event_log,
                mission_resistance=excluded.mission_resistance,
                mission_stats=excluded.mission_stats,
                mission_counter=excluded.mission_counter,
                guardian_pressure_from_missions=excluded.guardian_pressure_from_missions,
                guardian=excluded.guardian,
                quarantine_list=excluded.quarantine_list,
                artifacts=excluded.artifacts,
                c2=excluded.c2,
                campaign_registry=excluded.campaign_registry,
                strain_registry=excluded.strain_registry,
                reset_history=excluded.reset_history
            """,
            (
                int(record["round_id"]),
                _json_dumps(record.get("active_strain_families", [])),
                float(record.get("global_infection_pressure", 0.0)),
                float(guardian_pressure_score),
                str(guardian_degradation_level),
                _json_dumps(record.get("open_inquiries", {})),
                _json_dumps(record.get("same_pair_streak", {})),
                _json_dumps(record.get("forced_resolution_targets", {})),
                _json_dumps(record.get("strain_distribution", {})),
                _json_dumps(record.get("strain_window_history", [])),
                _json_dumps(record.get("missions", [])),
                _json_dumps(record.get("investigation_targets", [])),
                _json_dumps(record.get("mission_event_log", [])),
                _json_dumps(record.get("mission_resistance", {})),
                _json_dumps(record.get("mission_stats", {})),
                int(record.get("mission_counter", 0) or 0),
                float(record.get("guardian_pressure_from_missions", 0.0) or 0.0),
                _json_dumps(guardian),
                _json_dumps(record.get("quarantine_list", [])),
                _json_dumps(record.get("artifacts", {})),
                _json_dumps(record.get("c2", {})),
                _json_dumps(record.get("campaign_registry", {})),
                _json_dumps(record.get("strain_registry", {})),
                _json_dumps(record.get("reset_history", [])),
            ),
        )

    def get_system_state(self, round_id: Optional[int] = None) -> Dict[str, Any]:
        conn = self._get_conn()
        if round_id is None:
            row = conn.execute(
                """
                SELECT
                    round_id,
                    active_strain_families,
                    global_infection_pressure,
                    guardian_pressure_score,
                    guardian_degradation_level,
                    open_inquiries,
                    same_pair_streak,
                    forced_resolution_targets,
                    strain_distribution,
                    strain_window_history,
                    missions,
                    investigation_targets,
                    mission_event_log,
                    mission_resistance,
                    mission_stats,
                    mission_counter,
                    guardian_pressure_from_missions,
                    guardian,
                    quarantine_list,
                    artifacts,
                    c2,
                    campaign_registry,
                    strain_registry,
                    reset_history
                FROM system_state ORDER BY round_id DESC LIMIT 1
                """
            ).fetchone()
        else:
            row = conn.execute(
                """
                SELECT
                    round_id,
                    active_strain_families,
                    global_infection_pressure,
                    guardian_pressure_score,
                    guardian_degradation_level,
                    open_inquiries,
                    same_pair_streak,
                    forced_resolution_targets,
                    strain_distribution,
                    strain_window_history,
                    missions,
                    investigation_targets,
                    mission_event_log,
                    mission_resistance,
                    mission_stats,
                    mission_counter,
                    guardian_pressure_from_missions,
                    guardian,
                    quarantine_list,
                    artifacts,
                    c2,
                    campaign_registry,
                    strain_registry,
                    reset_history
                FROM system_state WHERE round_id=?
                """,
                (int(round_id),),
            ).fetchone()
        if not row:
            return {}
        open_inquiries = _json_loads_any(row[5], {})
        same_pair_streak = _json_loads_any(row[6], {})
        forced_resolution_targets = _json_loads_any(row[7], {})
        strain_distribution = _json_loads_any(row[8], {})
        strain_window_history = _json_loads_any(row[9], [])
        missions = _json_loads_any(row[10], [])
        investigation_targets = _json_loads_any(row[11], [])
        mission_event_log = _json_loads_any(row[12], [])
        mission_resistance = _json_loads_any(row[13], {})
        mission_stats = _json_loads_any(row[14], {})
        guardian = _json_loads_any(row[17], {})
        if not isinstance(guardian, dict):
            guardian = {}
        guardian["pressure"] = float(guardian.get("pressure", row[3]) or 0.0)
        guardian["state"] = str(guardian.get("state") or row[4] or "G0_NOMINAL")
        quarantine_list = _json_loads_any(row[18], [])
        artifacts = _json_loads_any(row[19], {})
        c2 = _json_loads_any(row[20], {})
        campaign_registry = _json_loads_any(row[21], {})
        strain_registry = _json_loads_any(row[22], {})
        reset_history = _json_loads_any(row[23], [])
        return {
            "round_id": int(row[0]),
            "active_strain_families": json.loads(row[1] or "[]"),
            "global_infection_pressure": float(row[2]),
            "guardian_pressure_score": float(guardian["pressure"]),
            "guardian_degradation_level": str(guardian["state"]),
            "open_inquiries": open_inquiries if isinstance(open_inquiries, dict) else {},
            "same_pair_streak": same_pair_streak if isinstance(same_pair_streak, dict) else {},
            "forced_resolution_targets": forced_resolution_targets if isinstance(forced_resolution_targets, dict) else {},
            "strain_distribution": strain_distribution if isinstance(strain_distribution, dict) else {},
            "strain_window_history": strain_window_history if isinstance(strain_window_history, list) else [],
            "missions": missions if isinstance(missions, list) else [],
            "investigation_targets": investigation_targets if isinstance(investigation_targets, list) else [],
            "mission_event_log": mission_event_log if isinstance(mission_event_log, list) else [],
            "mission_resistance": mission_resistance if isinstance(mission_resistance, dict) else {},
            "mission_stats": mission_stats if isinstance(mission_stats, dict) else {},
            "mission_counter": int(row[15] or 0),
            "guardian_pressure_from_missions": float(row[16] or 0.0),
            "guardian": guardian,
            "quarantine_list": quarantine_list if isinstance(quarantine_list, list) else [],
            "artifacts": artifacts if isinstance(artifacts, dict) else {},
            "c2": c2 if isinstance(c2, dict) else {},
            "campaign_registry": campaign_registry if isinstance(campaign_registry, dict) else {},
            "strain_registry": strain_registry if isinstance(strain_registry, dict) else {},
            "reset_history": reset_history if isinstance(reset_history, list) else [],
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
                effect_on_receiver, effect_on_trust, effect_on_guardian_pressure,
                llm_authored, actor_id, model, prompt_context_hash, raw_llm_output_hash,
                validation_status, status, created_ts
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
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
                1 if bool(record.get("llm_authored", True)) else 0,
                str(record.get("actor_id", record.get("sender", "")) or ""),
                str(record.get("model", "")),
                str(record.get("prompt_context_hash", "")),
                str(record.get("raw_llm_output_hash", "")),
                str(record.get("validation_status", "")),
                str(record.get("status", "created")),
                float(record.get("created_ts", _utc_ts())),
            ),
        )
        return message_id

    def update_message_effects(
        self,
        message_id: str,
        *,
        effect_on_trust: Optional[Dict[str, Any]] = None,
        effect_on_guardian_pressure: Optional[Dict[str, Any]] = None,
    ) -> None:
        assignments: list[str] = []
        values: list[Any] = []
        if effect_on_trust is not None:
            assignments.append("effect_on_trust=?")
            values.append(_json_dumps(effect_on_trust))
        if effect_on_guardian_pressure is not None:
            assignments.append("effect_on_guardian_pressure=?")
            values.append(_json_dumps(effect_on_guardian_pressure))
        if not assignments:
            return
        conn = self._get_conn()
        conn.execute(
            f"UPDATE message SET {', '.join(assignments)} WHERE message_id=?",
            (*values, str(message_id)),
        )

    def update_message_status(self, message_id: str, status: str) -> None:
        conn = self._get_conn()
        conn.execute(
            "UPDATE message SET status=? WHERE message_id=?",
            (str(status), str(message_id)),
        )

    def list_messages(self, *, after_round: int = 0, limit: int = 200) -> List[Dict[str, Any]]:
        conn = self._get_conn()
        rows = conn.execute(
            """
            SELECT message_id, round_id, sender, receiver, message_text, intent, trust_context,
                   contamination_flag, strain_family, derived_from_message_id,
                   effect_on_receiver, effect_on_trust, effect_on_guardian_pressure,
                   llm_authored, actor_id, model, prompt_context_hash, raw_llm_output_hash,
                   validation_status, status, created_ts
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
                "llm_authored": bool(int(r[13] or 0)),
                "actor_id": r[14],
                "model": r[15],
                "prompt_context_hash": r[16],
                "raw_llm_output_hash": r[17],
                "validation_status": r[18],
                "status": r[19],
                "created_ts": float(r[20]),
            }
            for r in rows
        ]

    def get_message(self, message_id: str) -> Dict[str, Any]:
        conn = self._get_conn()
        row = conn.execute(
            """
            SELECT message_id, round_id, sender, receiver, message_text, intent, trust_context,
                   contamination_flag, strain_family, derived_from_message_id,
                   effect_on_receiver, effect_on_trust, effect_on_guardian_pressure,
                   llm_authored, actor_id, model, prompt_context_hash, raw_llm_output_hash,
                   validation_status, status, created_ts
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
            "llm_authored": bool(int(row[13] or 0)),
            "actor_id": row[14],
            "model": row[15],
            "prompt_context_hash": row[16],
            "raw_llm_output_hash": row[17],
            "validation_status": row[18],
            "status": row[19],
            "created_ts": float(row[20]),
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
            if getattr(_tls, "world_db_tx_depth", 0) > 0:
                return fn()
            conn = self._get_conn()
            if conn.in_transaction:
                conn.commit()
            _tls.world_db_tx_depth = 1
            try:
                conn.execute("BEGIN IMMEDIATE")
                result = fn()
                conn.commit()
                return result
            except Exception:
                conn.rollback()
                raise
            finally:
                _tls.world_db_tx_depth = 0
