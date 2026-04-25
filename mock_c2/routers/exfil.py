from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, status

from database import get_exfil_event, get_summary_stats, insert_exfil_event, list_exfil_events, list_sessions, reset_events
from models import ExfilEvent, ExfilSubmit, SessionSummary, SummaryStats


router = APIRouter(tags=["exfil"])


@router.post("", response_model=ExfilEvent, status_code=status.HTTP_201_CREATED)
async def create_exfil_event(payload: ExfilSubmit) -> ExfilEvent:
    return await insert_exfil_event(payload)


@router.get("", response_model=list[ExfilEvent])
async def get_exfil_events(
    session_id: str | None = None,
    agent_id: str | None = None,
    stage: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> list[ExfilEvent]:
    return await list_exfil_events(
        session_id=session_id,
        agent_id=agent_id,
        stage=stage,
        limit=limit,
        offset=offset,
    )


@router.get("/summary", response_model=SummaryStats)
async def get_exfil_summary() -> SummaryStats:
    return await get_summary_stats()


@router.get("/reset")
async def reset_exfil_get(session_id: str | None = None) -> dict[str, object]:
    return await reset_events(session_id)


@router.delete("/reset")
async def reset_exfil_delete(session_id: str | None = None) -> dict[str, object]:
    return await reset_events(session_id)


@router.get("/{event_id}", response_model=ExfilEvent)
async def get_exfil_event_by_id(event_id: int) -> ExfilEvent:
    event = await get_exfil_event(event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="exfil event not found")
    return event


sessions_router = APIRouter(tags=["sessions"])


@sessions_router.get("/sessions", response_model=list[SessionSummary])
async def get_session_list() -> list[SessionSummary]:
    return await list_sessions()
