"""Call status and trace helpers shared by the API and worker."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from helpline.models import Call, utcnow

log = logging.getLogger(__name__)


def duration_seconds(started_at: datetime, ended_at: datetime | None) -> int | None:
    if ended_at is None:
        return None
    return max(0, int((ended_at - started_at).total_seconds()))


def call_detail(call: Call) -> dict:
    ended = call.ended_at
    return {
        "id": str(call.id),
        "agent_id": str(call.agent_id) if call.agent_id else None,
        "room_name": call.room_name,
        "direction": call.direction,
        "phone": call.phone,
        "status": call.status,
        "transcript": call.transcript or [],
        "trace": call.trace or [],
        "started_at": call.started_at.isoformat(),
        "ended_at": ended.isoformat() if ended else None,
        "duration_seconds": duration_seconds(call.started_at, ended),
    }


async def resolve_call(
    session: AsyncSession,
    *,
    room_name: str | None = None,
    call_id: uuid.UUID | str | None = None,
) -> Call | None:
    call: Call | None = None
    if call_id is not None:
        call = await session.get(Call, uuid.UUID(str(call_id)))
    if call is None and room_name:
        call = await session.scalar(select(Call).where(Call.room_name == room_name))
    return call


async def set_call_status(
    session: AsyncSession,
    *,
    room_name: str | None = None,
    call_id: uuid.UUID | str | None = None,
    status: str,
    event: dict | None = None,
) -> bool:
    call = await resolve_call(session, room_name=room_name, call_id=call_id)
    if call is None:
        log.warning("call not found for status=%s room=%s call_id=%s", status, room_name, call_id)
        return False
    call.status = status
    if event:
        trace = list(call.trace or [])
        trace.append({**event, "at": utcnow().isoformat()})
        call.trace = trace
    await session.commit()
    return True


async def merge_call_trace(
    session: AsyncSession,
    *,
    room_name: str | None = None,
    call_id: uuid.UUID | str | None = None,
    events: list[dict],
) -> bool:
    if not events:
        return True
    call = await resolve_call(session, room_name=room_name, call_id=call_id)
    if call is None:
        log.warning("call not found for trace merge room=%s call_id=%s", room_name, call_id)
        return False
    trace = list(call.trace or [])
    trace.extend(events)
    call.trace = trace
    await session.commit()
    return True
