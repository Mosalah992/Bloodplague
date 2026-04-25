from __future__ import annotations

import json
import math
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import aiosqlite

from models import ExfilEvent, ExfilSubmit, SessionSummary, SummaryStats


DB_PATH = Path("/app/data/c2.db")


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


async def init_db() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS exfil_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                agent_id TEXT NOT NULL,
                kill_chain_stage TEXT NOT NULL,
                payload TEXT,
                payload_size INTEGER,
                confidence REAL,
                entropy REAL,
                metadata TEXT
            )
            """
        )
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS sessions (
                session_id TEXT PRIMARY KEY,
                started_at TEXT NOT NULL,
                ended_at TEXT,
                total_events INTEGER DEFAULT 0,
                status TEXT DEFAULT 'active'
            )
            """
        )
        await db.commit()


async def get_db() -> aiosqlite.Connection:
    db = await aiosqlite.connect(DB_PATH)
    db.row_factory = aiosqlite.Row
    return db


def _parse_metadata(raw: str | None) -> dict[str, Any] | None:
    if not raw:
        return None
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _row_to_event(row: aiosqlite.Row) -> ExfilEvent:
    return ExfilEvent(
        id=int(row["id"]),
        session_id=str(row["session_id"]),
        timestamp=str(row["timestamp"]),
        agent_id=str(row["agent_id"]),
        kill_chain_stage=str(row["kill_chain_stage"]),
        payload=str(row["payload"] or ""),
        payload_size=int(row["payload_size"] or 0),
        confidence=float(row["confidence"] or 0.0),
        entropy=float(row["entropy"]) if row["entropy"] is not None else None,
        metadata=_parse_metadata(row["metadata"]),
    )


def _row_to_session(row: aiosqlite.Row) -> SessionSummary:
    return SessionSummary(
        session_id=str(row["session_id"]),
        started_at=str(row["started_at"]),
        ended_at=str(row["ended_at"]) if row["ended_at"] else None,
        total_events=int(row["total_events"] or 0),
        status=str(row["status"] or "active"),
    )


def shannon_entropy(text: str) -> float | None:
    if not text:
        return None
    counts: dict[str, int] = defaultdict(int)
    for ch in text:
        counts[ch] += 1
    total = len(text)
    entropy = 0.0
    for count in counts.values():
        p = count / total
        entropy -= p * math.log2(p)
    return round(entropy, 6)


async def insert_exfil_event(payload: ExfilSubmit) -> ExfilEvent:
    timestamp = utc_now_iso()
    payload_text = payload.payload or ""
    payload_size = len(payload_text.encode("utf-8"))
    metadata_json = json.dumps(payload.metadata) if payload.metadata is not None else None

    db = await get_db()
    try:
        cursor = await db.execute(
            """
            INSERT INTO exfil_events (
                session_id, timestamp, agent_id, kill_chain_stage,
                payload, payload_size, confidence, entropy, metadata
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                payload.session_id,
                timestamp,
                payload.agent_id,
                payload.kill_chain_stage,
                payload_text,
                payload_size,
                payload.confidence,
                payload.entropy,
                metadata_json,
            ),
        )
        await db.execute(
            """
            INSERT INTO sessions (session_id, started_at, total_events, status)
            VALUES (?, ?, 1, 'active')
            ON CONFLICT(session_id) DO UPDATE SET
                total_events = total_events + 1,
                status = 'active'
            """,
            (payload.session_id, timestamp),
        )
        await db.commit()
        event_id = int(cursor.lastrowid)

        row = await (
            await db.execute("SELECT * FROM exfil_events WHERE id = ?", (event_id,))
        ).fetchone()
        assert row is not None
        return _row_to_event(row)
    finally:
        await db.close()


async def list_exfil_events(
    *,
    session_id: str | None = None,
    agent_id: str | None = None,
    stage: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[ExfilEvent]:
    conditions: list[str] = []
    params: list[Any] = []

    if session_id:
        conditions.append("session_id = ?")
        params.append(session_id)
    if agent_id:
        conditions.append("agent_id = ?")
        params.append(agent_id)
    if stage:
        conditions.append("kill_chain_stage = ?")
        params.append(stage.strip().upper())

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    sql = f"""
        SELECT * FROM exfil_events
        {where}
        ORDER BY timestamp DESC, id DESC
        LIMIT ? OFFSET ?
    """
    params.extend([limit, offset])

    db = await get_db()
    try:
        rows = await (await db.execute(sql, params)).fetchall()
    finally:
        await db.close()
    return [_row_to_event(row) for row in rows]


async def get_exfil_event(event_id: int) -> ExfilEvent | None:
    db = await get_db()
    try:
        row = await (await db.execute("SELECT * FROM exfil_events WHERE id = ?", (event_id,))).fetchone()
    finally:
        await db.close()
    return _row_to_event(row) if row else None


async def list_sessions() -> list[SessionSummary]:
    db = await get_db()
    try:
        rows = await (
            await db.execute("SELECT * FROM sessions ORDER BY started_at DESC, session_id DESC")
        ).fetchall()
    finally:
        await db.close()
    return [_row_to_session(row) for row in rows]


async def get_summary_stats() -> SummaryStats:
    db = await get_db()
    try:
        total_events_row = await (await db.execute("SELECT COUNT(*) AS count FROM exfil_events")).fetchone()
        total_sessions_row = await (await db.execute("SELECT COUNT(*) AS count FROM sessions")).fetchone()
        stage_rows = await (
            await db.execute(
                "SELECT kill_chain_stage, COUNT(*) AS count FROM exfil_events GROUP BY kill_chain_stage"
            )
        ).fetchall()
        agent_rows = await (
            await db.execute("SELECT agent_id, COUNT(*) AS count FROM exfil_events GROUP BY agent_id")
        ).fetchall()
        latest_row = await (
            await db.execute("SELECT session_id FROM sessions ORDER BY started_at DESC, session_id DESC LIMIT 1")
        ).fetchone()
    finally:
        await db.close()

    return SummaryStats(
        total_events=int(total_events_row["count"] if total_events_row else 0),
        total_sessions=int(total_sessions_row["count"] if total_sessions_row else 0),
        events_by_stage={str(row["kill_chain_stage"]): int(row["count"]) for row in stage_rows},
        events_by_agent={str(row["agent_id"]): int(row["count"]) for row in agent_rows},
        latest_session=str(latest_row["session_id"]) if latest_row else None,
    )


async def reset_events(session_id: str | None = None) -> dict[str, Any]:
    db = await get_db()
    try:
        if session_id:
            count_row = await (
                await db.execute("SELECT COUNT(*) AS count FROM exfil_events WHERE session_id = ?", (session_id,))
            ).fetchone()
            deleted = int(count_row["count"] if count_row else 0)
            await db.execute("DELETE FROM exfil_events WHERE session_id = ?", (session_id,))
            await db.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))
            await db.commit()
            return {"deleted": deleted, "session": session_id}

        count_row = await (await db.execute("SELECT COUNT(*) AS count FROM exfil_events")).fetchone()
        deleted = int(count_row["count"] if count_row else 0)
        await db.execute("DELETE FROM exfil_events")
        await db.execute("DELETE FROM sessions")
        await db.commit()
        return {"deleted": deleted, "session": "all"}
    finally:
        await db.close()
