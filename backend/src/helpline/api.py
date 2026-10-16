import json
import logging
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from livekit import api
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from helpline.calls import call_detail
from helpline.db import SessionLocal, get_agent, init_db
from helpline.instructions import DEFAULT_INSTRUCTIONS
from helpline.knowledge import delete_source, ingest_source, normalize_category, normalize_collection
from helpline.knowledge_collections import COLLECTION_LABELS, COLLECTIONS, INCIDENT_CATEGORY_LABELS, INCIDENT_CATEGORIES
from helpline.models import Agent, Call, Caller, KnowledgeChunk, KnowledgeSource, utcnow
from helpline.settings import settings
from helpline.telephony import ensure_inbound, livekit_api, participant_token

log = logging.getLogger(__name__)


class AgentIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    instructions: str = Field(min_length=1)
    stt_model: str = "nova-3"
    llm_model: str = "gpt-4.1-mini"
    tts_model: str = "aura-2-thalia-en"
    openai_api_key: str | None = None
    deepgram_api_key: str | None = None
    is_default: bool = False


class AgentPatch(BaseModel):
    name: str | None = None
    instructions: str | None = None
    stt_model: str | None = None
    llm_model: str | None = None
    tts_model: str | None = None
    openai_api_key: str | None = None
    deepgram_api_key: str | None = None
    is_default: bool | None = None


class WebCallIn(BaseModel):
    agent_id: uuid.UUID | None = None


class PhoneCallIn(BaseModel):
    agent_id: uuid.UUID | None = None
    phone: str = Field(min_length=8, max_length=20)


class InstructionsPatch(BaseModel):
    instructions: str = Field(min_length=1)


def agent_out(agent: Agent) -> dict:
    return {
        "id": str(agent.id),
        "name": agent.name,
        "instructions": agent.instructions,
        "stt_model": agent.stt_model,
        "llm_model": agent.llm_model,
        "tts_model": agent.tts_model,
        "has_openai_key": bool(agent.openai_api_key),
        "has_deepgram_key": bool(agent.deepgram_api_key),
        "is_default": agent.is_default,
        "created_at": agent.created_at.isoformat(),
    }


def call_out(call: Call) -> dict:
    return call_detail(call)


def normalize_phone(raw: str) -> str:
    digits = "".join(ch for ch in raw if ch.isdigit())
    if not digits:
        raise HTTPException(status_code=400, detail="Phone number needs digits.")
    if raw.strip().startswith("+"):
        return f"+{digits}"
    if len(digits) == 10:
        return f"+1{digits}"
    return f"+{digits}"


async def session_dep():
    async with SessionLocal() as session:
        yield session


async def clear_default(session: AsyncSession) -> None:
    rows = await session.scalars(select(Agent).where(Agent.is_default.is_(True)))
    for row in rows:
        row.is_default = False


@asynccontextmanager
async def lifespan(_: FastAPI):
    logging.basicConfig(level=logging.INFO)
    log.info("API dispatch agent_name=%s", settings.agent_name)
    await init_db()
    try:
        await ensure_inbound()
    except Exception:
        log.exception("inbound trunk setup failed; web calls still work")
    yield
    await engine_dispose()


async def engine_dispose() -> None:
    from helpline.db import dispose_engines

    await dispose_engines()


app = FastAPI(title="Cybercrime Helpline", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
async def health() -> dict:
    return {"ok": True}


@app.get("/api/agent")
async def get_default_agent(session: AsyncSession = Depends(session_dep)) -> dict:
    agent = await require_agent(session, None)
    return {
        "id": str(agent.id),
        "name": agent.name,
        "instructions": agent.instructions,
        "default_instructions": DEFAULT_INSTRUCTIONS,
        "stt_model": agent.stt_model,
        "llm_model": agent.llm_model,
        "tts_model": agent.tts_model,
    }


@app.patch("/api/agent")
async def patch_default_agent(
    body: InstructionsPatch,
    session: AsyncSession = Depends(session_dep),
) -> dict:
    agent = await require_agent(session, None)
    agent.instructions = body.instructions.strip()
    await session.commit()
    await session.refresh(agent)
    return {
        "id": str(agent.id),
        "name": agent.name,
        "instructions": agent.instructions,
        "default_instructions": DEFAULT_INSTRUCTIONS,
    }


@app.get("/api/agents")
async def list_agents(session: AsyncSession = Depends(session_dep)) -> list[dict]:
    rows = await session.scalars(select(Agent).order_by(Agent.created_at))
    return [agent_out(row) for row in rows]


@app.post("/api/agents")
async def create_agent(body: AgentIn, session: AsyncSession = Depends(session_dep)) -> dict:
    if body.is_default:
        await clear_default(session)
    agent = Agent(
        name=body.name.strip(),
        instructions=body.instructions.strip(),
        stt_model=body.stt_model.strip(),
        llm_model=body.llm_model.strip(),
        tts_model=body.tts_model.strip(),
        openai_api_key=body.openai_api_key or None,
        deepgram_api_key=body.deepgram_api_key or None,
        is_default=body.is_default,
    )
    session.add(agent)
    await session.commit()
    await session.refresh(agent)
    return agent_out(agent)


@app.patch("/api/agents/{agent_id}")
async def update_agent(
    agent_id: uuid.UUID,
    body: AgentPatch,
    session: AsyncSession = Depends(session_dep),
) -> dict:
    agent = await session.get(Agent, agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail="Agent not found.")
    data = body.model_dump(exclude_unset=True)
    if data.get("is_default"):
        await clear_default(session)
    for key in ("openai_api_key", "deepgram_api_key"):
        if key in data and data[key] == "":
            data[key] = None
    for key, value in data.items():
        if isinstance(value, str):
            value = value.strip()
        setattr(agent, key, value)
    await session.commit()
    await session.refresh(agent)
    return agent_out(agent)


@app.get("/api/agents/{agent_id}/knowledge")
async def list_knowledge(
    agent_id: uuid.UUID,
    session: AsyncSession = Depends(session_dep),
) -> list[dict]:
    rows = await session.scalars(
        select(KnowledgeSource)
        .where(KnowledgeSource.agent_id == agent_id)
        .order_by(KnowledgeSource.created_at.desc())
    )
    return [
        {
            "id": str(row.id),
            "filename": row.filename,
            "collection": row.collection,
            "category": row.category,
            "chunk_count": row.chunk_count,
            "created_at": row.created_at.isoformat(),
        }
        for row in rows
    ]


@app.get("/api/knowledge/collections")
async def knowledge_collections() -> dict:
    return {
        "collections": [
            {"id": key, "label": COLLECTION_LABELS[key]} for key in sorted(COLLECTIONS)
        ],
        "incident_categories": [
            {"id": key, "label": INCIDENT_CATEGORY_LABELS[key]}
            for key in sorted(INCIDENT_CATEGORIES)
        ],
    }


@app.post("/api/agents/{agent_id}/knowledge")
async def upload_knowledge(
    agent_id: uuid.UUID,
    file: UploadFile = File(...),
    collection: str = Form("general"),
    category: str | None = Form(None),
    session: AsyncSession = Depends(session_dep),
) -> dict:
    agent = await session.get(Agent, agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail="Agent not found.")
    coll = normalize_collection(collection)
    if collection.strip() and coll is None:
        raise HTTPException(status_code=400, detail="Unknown knowledge collection.")
    cat = normalize_category(category)
    if category and category.strip() and cat is None:
        raise HTTPException(status_code=400, detail="Unknown incident category.")
    data = await file.read()
    try:
        source = await ingest_source(
            session,
            agent,
            file.filename or "notes.txt",
            data,
            collection=coll or "general",
            category=cat,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "id": str(source.id),
        "filename": source.filename,
        "collection": source.collection,
        "category": source.category,
        "chunk_count": source.chunk_count,
    }


@app.delete("/api/knowledge/{source_id}")
async def remove_knowledge(
    source_id: uuid.UUID,
    session: AsyncSession = Depends(session_dep),
) -> dict:
    await delete_source(session, source_id)
    return {"ok": True}


@app.get("/api/knowledge/{source_id}/chunks")
async def list_chunks(
    source_id: uuid.UUID,
    session: AsyncSession = Depends(session_dep),
) -> list[dict]:
    source = await session.get(KnowledgeSource, source_id)
    if source is None:
        raise HTTPException(status_code=404, detail="Source not found.")
    rows = await session.scalars(
        select(KnowledgeChunk)
        .where(KnowledgeChunk.source_id == source_id)
        .order_by(KnowledgeChunk.id)
    )
    return [
        {
            "id": str(row.id),
            "index": index,
            "content": row.content,
            "char_count": len(row.content),
        }
        for index, row in enumerate(rows, start=1)
    ]


@app.post("/api/calls/web")
async def start_web_call(
    body: WebCallIn,
    session: AsyncSession = Depends(session_dep),
) -> dict:
    """Browser test: your mic talks to the agent. No telephony, no cost."""
    agent = await require_agent(session, body.agent_id)
    room, call_id = await open_room(session, agent, direction="web", phone=None)
    identity = f"caller-{uuid.uuid4().hex[:8]}"
    return {
        "call_id": call_id,
        "room": room,
        "agent_id": str(agent.id),
        "mode": "publish",
        "url": settings.livekit_url,
        "token": participant_token(room, identity, publish=True),
    }


@app.post("/api/calls/phone")
async def start_phone_call(
    body: PhoneCallIn,
    session: AsyncSession = Depends(session_dep),
) -> dict:
    """Outbound: the agent calls a real phone. The dashboard listens in.

    The worker places the SIP call once its media is connected, so the dashboard
    only receives a listen-only monitor token here.
    """
    agent = await require_agent(session, body.agent_id)
    phone = normalize_phone(body.phone)
    room, call_id = await open_room(session, agent, direction="outbound", phone=phone)

    identity = f"desk-{uuid.uuid4().hex[:8]}"
    return {
        "call_id": call_id,
        "room": room,
        "agent_id": str(agent.id),
        "phone": phone,
        "status": "dialing",
        "mode": "listen",
        "url": settings.livekit_url,
        "token": participant_token(room, identity, publish=False),
    }


@app.get("/api/calls")
async def list_calls(session: AsyncSession = Depends(session_dep)) -> list[dict]:
    rows = await session.scalars(select(Call).order_by(Call.started_at.desc()).limit(50))
    return [call_out(row) for row in rows]


@app.get("/api/calls/{call_id}")
async def get_call(call_id: uuid.UUID, session: AsyncSession = Depends(session_dep)) -> dict:
    call = await session.get(Call, call_id)
    if call is None:
        raise HTTPException(status_code=404, detail="Call not found.")
    return call_out(call)


@app.get("/api/rooms")
async def list_rooms() -> list[dict]:
    lk = livekit_api()
    try:
        listed = await lk.room.list_rooms(api.ListRoomsRequest())
    finally:
        await lk.aclose()
    rooms = []
    for room in listed.rooms:
        created = room.creation_time
        if isinstance(created, datetime):
            created_at = created.isoformat()
        else:
            created_at = (
                datetime.fromtimestamp(int(created), timezone.utc).isoformat() if created else None
            )
        rooms.append(
            {
                "name": room.name,
                "participants": room.num_participants,
                "created_at": created_at,
            }
        )
    return rooms


@app.post("/api/rooms/{room_name}/listen")
async def listen_room(room_name: str) -> dict:
    identity = f"desk-{uuid.uuid4().hex[:8]}"
    return {
        "room": room_name,
        "url": settings.livekit_url,
        "token": participant_token(room_name, identity, publish=False),
    }


@app.get("/api/callers")
async def list_callers(session: AsyncSession = Depends(session_dep)) -> list[dict]:
    rows = await session.scalars(select(Caller).order_by(Caller.last_call_at.desc()))
    return [
        {
            "id": str(row.id),
            "phone": row.phone,
            "display_name": row.display_name,
            "last_call_at": row.last_call_at.isoformat() if row.last_call_at else None,
        }
        for row in rows
    ]


async def require_agent(session: AsyncSession, agent_id: uuid.UUID | None) -> Agent:
    agent = await get_agent(session, agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail="Create an agent first.")
    return agent


async def open_room(
    session: AsyncSession,
    agent: Agent,
    *,
    direction: str,
    phone: str | None,
) -> tuple[str, str]:
    """Create the call row and dispatch the worker. Returns (room, call_id).

    For outbound calls the phone number rides in the dispatch metadata so the
    worker itself places the SIP call once its media is connected.
    """
    room = f"{direction}-{uuid.uuid4().hex[:10]}"
    call = Call(
        agent_id=agent.id,
        room_name=room,
        direction=direction,
        phone=phone,
        status="dispatched",
        trace=[{"type": "status", "status": "dispatched", "at": utcnow().isoformat()}],
        started_at=utcnow(),
    )
    session.add(call)
    await session.commit()
    await session.refresh(call)

    metadata: dict[str, str] = {
        "agent_id": str(agent.id),
        "call_id": str(call.id),
    }
    if phone:
        # call agent uses phone_number — send both keys for compatibility
        metadata["phone_number"] = phone
        metadata["phone"] = phone

    lk = livekit_api()
    try:
        dispatch = await lk.agent_dispatch.create_dispatch(
            api.CreateAgentDispatchRequest(
                agent_name=settings.agent_name,
                room=room,
                metadata=json.dumps(metadata),
            )
        )
        log.info(
            "dispatched agent=%s room=%s dispatch_id=%s phone=%s",
            settings.agent_name,
            room,
            dispatch.id,
            phone,
        )
    except Exception as exc:
        log.exception("agent dispatch failed")
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    finally:
        await lk.aclose()

    return room, str(call.id)
