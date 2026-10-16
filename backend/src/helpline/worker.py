import asyncio
import json
import logging
import uuid
from collections.abc import Awaitable, Callable

from livekit import agents, api, rtc
from livekit.agents import (
    NOT_GIVEN,
    Agent,
    AgentServer,
    AgentSession,
    ChatMessage,
    JobContext,
    JobProcess,
    JobRequest,
    RunContext,
    function_tool,
    get_job_context,
)
from livekit.plugins import deepgram, openai, silero
from sqlalchemy import select

from helpline.calls import merge_call_trace, set_call_status
from helpline.db import SessionLocal, get_agent
from helpline.instructions import CONNECT_GREETING
from helpline.knowledge import (
    deepgram_key,
    fetch_advisory_snippet,
    format_hits,
    list_resources,
    lookup_state_contact as fetch_state_contacts,
    normalize_category,
    normalize_collection,
    openai_key,
    sanitize_query,
    search_knowledge,
)
from helpline.knowledge_collections import COLLECTION_PREVENTION
from helpline.state_contacts import normalize_state
from helpline.models import Agent as AgentRow
from helpline.models import Call, Caller, utcnow
from helpline.settings import settings
from helpline.voice import (
    AGENT_VOICE_NAME,
    STT_KEYTERMS,
    STT_REPLACE,
    TELEPHONY_TURN_HANDLING,
)

log = logging.getLogger(__name__)
server = AgentServer()


async def accept_helpline_jobs(req: JobRequest) -> None:
    await req.accept(name=AGENT_VOICE_NAME, identity="kavita-helpline")


def job_room_name(ctx: JobContext) -> str:
    """Room name from the job assignment — reliable before ctx.connect()."""
    return ctx.job.room.name or ctx.room.name or ""


def call_id_from_job(ctx: JobContext) -> uuid.UUID | None:
    raw = ctx.job.metadata or ""
    if not raw:
        return None
    try:
        value = json.loads(raw).get("call_id")
        return uuid.UUID(value) if value else None
    except (ValueError, TypeError, json.JSONDecodeError):
        return None


async def patch_call(
    ctx: JobContext,
    *,
    status: str,
    event: dict | None = None,
) -> None:
    room = job_room_name(ctx)
    call_id = call_id_from_job(ctx)
    async with SessionLocal() as db:
        ok = await set_call_status(
            db,
            room_name=room or None,
            call_id=call_id,
            status=status,
            event=event,
        )
    if not ok:
        log.warning("patch_call missed status=%s room=%s call_id=%s", status, room, call_id)


def prewarm(proc: JobProcess) -> None:
    """Load heavy imports before the first call — avoids blocking audio mid-conversation."""
    import filelock  # noqa: F401
    import huggingface_hub  # noqa: F401
    import numpy.fft  # noqa: F401

    proc.userdata["vad"] = silero.VAD.load()


server.setup_fnc = prewarm


class DeskAgent(Agent):
    def __init__(
        self,
        row: AgentRow,
        trace: list[dict],
        *,
        trace_sink: Callable[[dict], Awaitable[None]] | None = None,
    ) -> None:
        super().__init__(instructions=row.instructions)
        self.row = row
        self.trace = trace
        self.incident_summary: dict[str, str] = {}
        self._trace_sink = trace_sink

    def _record(self, event: dict) -> None:
        payload = {**event, "at": utcnow().isoformat()}
        self.trace.append(payload)
        if self._trace_sink is not None:
            asyncio.create_task(self._trace_sink(payload))

    async def _scoped_search(
        self,
        tool: str,
        query: str,
        *,
        collection: str | None = None,
        category: str | None = None,
    ) -> str:
        safe_query = sanitize_query(query)
        safe_category = normalize_category(category) if category else None
        safe_collection = normalize_collection(collection) if collection else None
        self._record(
            {
                "type": "tool_call",
                "tool": tool,
                "query": safe_query,
                "collection": safe_collection,
                "category": safe_category,
            }
        )
        async with SessionLocal() as session:
            fresh = await session.get(AgentRow, self.row.id)
            if fresh is None:
                self._record({"type": "tool_result", "tool": tool, "hits": 0})
                return "No reference material is available."
            hits = await search_knowledge(
                session,
                fresh,
                safe_query,
                collection=safe_collection,
                category=safe_category,
            )
        if not hits:
            self._record({"type": "tool_result", "tool": tool, "hits": 0})
            return "Nothing relevant was found in the reference material."
        self._record(
            {
                "type": "tool_result",
                "tool": tool,
                "hits": len(hits),
                "sources": [hit.source for hit in hits],
                "preview": hits[0].content[:240],
            }
        )
        return format_hits(hits)

    @function_tool()
    async def search_knowledge(
        self,
        context: RunContext,
        query: str,
        collection: str = "",
        category: str = "",
    ) -> str:
        """Search curated helpline knowledge before stating official steps.

        Pass a focused query. Optionally scope with collection: incident_playbook,
        portal_guide, prevention, or reassurance. For playbooks and reassurance,
        pass category when known (financial_fraud, upi_fraud, sextortion,
        digital_arrest, impersonation, ransomware, hacking).
        """
        del context
        coll = collection.strip() or None
        cat = category.strip() or None
        return await self._scoped_search(
            "search_knowledge",
            query,
            collection=coll,
            category=cat,
        )

    @function_tool()
    async def list_resources(self, context: RunContext) -> str:
        """Official helplines, portal URLs, and citizen manual references.

        No parameters — returns the curated resource catalog only.
        """
        del context
        self._record({"type": "tool_call", "tool": "list_resources"})
        async with SessionLocal() as session:
            fresh = await session.get(AgentRow, self.row.id)
            if fresh is None:
                self._record({"type": "tool_result", "tool": "list_resources", "hits": 0})
                return "No resources are configured."
            hits = await list_resources(session, fresh)
        if not hits:
            self._record({"type": "tool_result", "tool": "list_resources", "hits": 0})
            return "No resources are configured."
        self._record(
            {
                "type": "tool_result",
                "tool": "list_resources",
                "hits": len(hits),
                "preview": hits[0].content[:240],
            }
        )
        return format_hits(hits)

    @function_tool()
    async def lookup_state_contact(self, context: RunContext, state: str) -> str:
        """Look up a state or UT nodal cyber cell contact from the official list.

        Pass the full state name, e.g. Karnataka or Maharashtra.
        """
        del context
        safe_state = sanitize_query(state)
        canonical = normalize_state(safe_state)
        self._record({"type": "tool_call", "tool": "lookup_state_contact", "state": safe_state})
        if canonical is None:
            self._record({"type": "tool_result", "tool": "lookup_state_contact", "hits": 0})
            return (
                "That state was not recognized. Use the full state or UT name, "
                "for example Karnataka or Tamil Nadu."
            )
        async with SessionLocal() as session:
            fresh = await session.get(AgentRow, self.row.id)
            if fresh is None:
                self._record({"type": "tool_result", "tool": "lookup_state_contact", "hits": 0})
                return "No reference material is available."
            hits = await fetch_state_contacts(session, fresh, safe_state)
        if not hits:
            self._record({"type": "tool_result", "tool": "lookup_state_contact", "hits": 0})
            return f"No nodal contact was found for {canonical.title()}."
        self._record(
            {
                "type": "tool_result",
                "tool": "lookup_state_contact",
                "hits": len(hits),
                "preview": hits[0].content[:240],
            }
        )
        return format_hits(hits)

    @function_tool()
    async def search_current_advisories(self, context: RunContext, query: str) -> str:
        """Fetch current public cyber safety advisories when prevention KB is thin.

        Use for general safety questions — not for urgent post-incident steps.
        """
        del context
        safe_query = sanitize_query(query)
        self._record({"type": "tool_call", "tool": "search_current_advisories", "query": safe_query})
        async with SessionLocal() as session:
            fresh = await session.get(AgentRow, self.row.id)
            hits = []
            if fresh is not None:
                hits = await search_knowledge(
                    session,
                    fresh,
                    safe_query,
                    collection=COLLECTION_PREVENTION,
                )
        if hits:
            self._record(
                {
                    "type": "tool_result",
                    "tool": "search_current_advisories",
                    "hits": len(hits),
                    "source": "knowledge",
                    "preview": hits[0].content[:240],
                }
            )
            return format_hits(hits)
        snippet = await fetch_advisory_snippet(safe_query)
        if snippet:
            self._record(
                {
                    "type": "tool_result",
                    "tool": "search_current_advisories",
                    "hits": 1,
                    "source": "web",
                    "preview": snippet[:240],
                }
            )
            return f"[cybercrime.gov.in advisories] {snippet}"
        self._record({"type": "tool_result", "tool": "search_current_advisories", "hits": 0})
        return "No current advisories were found for that topic."

    @function_tool()
    async def note_incident_summary(
        self,
        context: RunContext,
        incident_type: str = "",
        amount_lost: str = "",
        state: str = "",
        urgency: str = "",
        notes: str = "",
    ) -> str:
        """Record structured triage notes for the call log — not spoken to the caller."""
        del context
        summary = {
            key: value.strip()
            for key, value in {
                "incident_type": incident_type,
                "amount_lost": amount_lost,
                "state": state,
                "urgency": urgency,
                "notes": notes,
            }.items()
            if value.strip()
        }
        self.incident_summary.update(summary)
        self._record({"type": "incident_summary", **summary})
        return "Summary noted."

    async def on_enter(self) -> None:
        """Greet once the voice pipeline and caller audio are linked."""
        self.session.generate_reply(instructions=CONNECT_GREETING)

    @function_tool(name="hang_up")
    async def hang_up(self, context: RunContext) -> str:
        """Silently disconnect the phone call after you have already said goodbye.

        Invoke only after the caller is ready to end. Never say this tool's name aloud.
        """
        del context
        self._record({"type": "tool_call", "tool": "hang_up"})
        ctx = get_job_context()
        if ctx is not None:
            ctx.shutdown("agent ended call")
        return "Call ending."


def agent_id_from_job(ctx: JobContext) -> uuid.UUID | None:
    raw = ctx.job.metadata or ""
    if not raw:
        return None
    try:
        value = json.loads(raw).get("agent_id")
        return uuid.UUID(value) if value else None
    except (ValueError, TypeError, json.JSONDecodeError):
        return None


def dial_target(ctx: JobContext) -> str | None:
    """Phone number to dial for outbound jobs, from the dispatch metadata."""
    raw = ctx.job.metadata or ""
    if not raw:
        return None
    try:
        meta = json.loads(raw)
        return meta.get("phone_number") or meta.get("phone")
    except (ValueError, TypeError, json.JSONDecodeError):
        return None


async def wait_for_caller(ctx: JobContext, phone: str | None) -> None:
    """Wait until the SIP caller is in the room and publishing audio."""
    sip_kind = rtc.ParticipantKind.PARTICIPANT_KIND_SIP
    if phone:
        try:
            participant = await ctx.wait_for_participant(identity=phone, kind=sip_kind)
            log.info("caller linked identity=%s", participant.identity)
            return
        except Exception:
            log.warning("caller identity %s not found, waiting for any SIP participant", phone)
    participant = await ctx.wait_for_participant(kind=sip_kind)
    log.info("caller linked identity=%s", participant.identity)


def phone_from_room(ctx: JobContext) -> str | None:
    for participant in ctx.room.remote_participants.values():
        phone = participant.attributes.get("sip.phoneNumber")
        if phone:
            return phone
    return None


def transcript_of(session: AgentSession, trace: list[dict]) -> list[dict]:
    lines: list[dict] = []
    for item in session.history.items:
        if isinstance(item, ChatMessage) and item.text_content:
            lines.append({"role": item.role, "text": item.text_content})
    for event in trace:
        if event.get("type") == "incident_summary":
            lines.append({"role": "tool", "text": json.dumps(event), "tool": "note_incident_summary"})
        elif event.get("type") == "tool_call":
            tool = event.get("tool", "tool")
            if tool == "list_resources":
                text = "list_resources()"
            elif tool == "lookup_state_contact":
                text = f"lookup_state_contact({event.get('state', '')!r})"
            elif tool == "hang_up":
                text = "hang_up()"
            else:
                parts = [f"{tool}({event.get('query', '')!r}"]
                if event.get("collection"):
                    parts.append(f", collection={event.get('collection')!r}")
                if event.get("category"):
                    parts.append(f", category={event.get('category')!r}")
                text = "".join(parts) + ")"
            lines.append({"role": "tool", "text": text, "tool": tool})
        elif event.get("type") == "tool_result":
            preview = event.get("preview") or "no results"
            lines.append(
                {
                    "role": "tool",
                    "text": preview,
                    "tool": event.get("tool"),
                    "hits": event.get("hits", 0),
                }
            )
    return lines


async def persist(ctx: JobContext, session: AgentSession, row: AgentRow, trace: list[dict]) -> None:
    phone = phone_from_room(ctx) or dial_target(ctx)
    lines = transcript_of(session, trace)
    room = job_room_name(ctx)
    call_id = call_id_from_job(ctx)
    async with SessionLocal() as db:
        from helpline.calls import resolve_call

        call = await resolve_call(db, room_name=room or None, call_id=call_id)
        if call is None:
            log.warning("persist: call not found room=%s call_id=%s — creating fallback row", room, call_id)
            call = Call(
                agent_id=row.id,
                room_name=room or ctx.room.name,
                direction="inbound",
                phone=phone,
                started_at=utcnow(),
            )
            db.add(call)
        call.transcript = lines
        call.status = "ended"
        call.ended_at = utcnow()
        call.phone = call.phone or phone
        merged = list(call.trace or []) + trace
        merged.append({"type": "status", "status": "ended", "at": utcnow().isoformat()})
        call.trace = merged
        if phone:
            caller = await db.scalar(select(Caller).where(Caller.phone == phone))
            if caller is None:
                caller = Caller(phone=phone, display_name=phone)
                db.add(caller)
            caller.last_call_at = utcnow()
        await db.commit()


def rtc_connect_options() -> rtc.RtcConfiguration | None:
    if not settings.livekit_ice_relay:
        return None
    return rtc.RtcConfiguration(ice_transport_type=rtc.IceTransportType.TRANSPORT_RELAY)


async def place_outbound_call(ctx: JobContext, phone: str) -> bool:
    """Dial a phone from inside the job, after media is connected."""
    room = job_room_name(ctx)
    await patch_call(
        ctx,
        status="ringing",
        event={"type": "status", "status": "ringing", "phone": phone},
    )
    try:
        await ctx.api.sip.create_sip_participant(
            api.CreateSIPParticipantRequest(
                sip_trunk_id=settings.sip_outbound_trunk_id,
                sip_call_to=phone,
                room_name=room,
                participant_identity=phone,
                wait_until_answered=True,
            )
        )
        log.info("outbound call answered: %s", phone)
        await patch_call(
            ctx,
            status="answered",
            event={"type": "status", "status": "answered", "phone": phone},
        )
        return True
    except api.TwirpError as exc:
        log.error(
            "outbound dial failed: %s (sip %s %s)",
            exc.message,
            exc.metadata.get("sip_status_code"),
            exc.metadata.get("sip_status"),
        )
        await patch_call(
            ctx,
            status="failed",
            event={"type": "status", "status": "failed", "error": exc.message},
        )
        return False


@server.rtc_session(agent_name=settings.agent_name, on_request=accept_helpline_jobs)
async def helpline_agent(ctx: JobContext) -> None:
    room = job_room_name(ctx)
    log.info("job received room=%s metadata=%s", room, ctx.job.metadata)
    trace: list[dict] = []

    async def trace_sink(event: dict) -> None:
        async with SessionLocal() as db:
            await merge_call_trace(
                db,
                room_name=room or None,
                call_id=call_id_from_job(ctx),
                events=[event],
            )

    async with SessionLocal() as db:
        row = await get_agent(db, agent_id_from_job(ctx))
    if row is None:
        log.error("no agent configured")
        return

    await patch_call(
        ctx,
        status="worker_joined",
        event={"type": "status", "status": "worker_joined"},
    )

    await ctx.connect(rtc_config=rtc_connect_options())

    phone = dial_target(ctx)
    if phone:
        answered = await place_outbound_call(ctx, phone)
        if not answered:
            ctx.shutdown()
            return

    await wait_for_caller(ctx, phone)

    dg = deepgram_key(row) or NOT_GIVEN
    oai = openai_key(row) or NOT_GIVEN
    if dg is NOT_GIVEN:
        log.error("No Deepgram API key configured — STT/TTS will not work on this call")

    vad = ctx.proc.userdata.get("vad")
    if vad is None:
        vad = silero.VAD.load()

    voice = AgentSession(
        stt=deepgram.STT(
            model=row.stt_model,
            api_key=dg,
            keyterm=STT_KEYTERMS,
            replace=STT_REPLACE,
            smart_format=True,
            filler_words=True,
            numerals=True,
            # Phone lines need longer silence before end-of-utterance than web mic.
            endpointing_ms=400,
            utterance_end_ms=1200,
        ),
        llm=openai.LLM(model=row.llm_model, api_key=oai),
        tts=deepgram.TTS(model=row.tts_model, api_key=None if dg is NOT_GIVEN else dg),
        vad=vad,
        turn_handling=TELEPHONY_TURN_HANDLING,
        user_away_timeout=45.0,
    )

    await patch_call(
        ctx,
        status="active",
        event={"type": "status", "status": "active"},
    )

    async def on_shutdown() -> None:
        await persist(ctx, voice, row, trace)

    ctx.add_shutdown_callback(on_shutdown)
    await voice.start(agent=DeskAgent(row, trace, trace_sink=trace_sink), room=ctx.room)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    log.info("starting worker agent_name=%s", settings.agent_name)
    agents.cli.run_app(server)
