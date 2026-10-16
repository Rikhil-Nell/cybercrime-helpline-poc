import asyncio
import uuid

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from helpline.instructions import DEFAULT_INSTRUCTIONS, LEGACY_INSTRUCTION_MARKERS
from helpline.models import Agent, Base
from helpline.settings import settings

_engines: dict[int, AsyncEngine] = {}
_session_makers: dict[int, async_sessionmaker[AsyncSession]] = {}


def _loop_key() -> int:
    return id(asyncio.get_running_loop())


def _ensure_loop_engine() -> async_sessionmaker[AsyncSession]:
    key = _loop_key()
    if key not in _session_makers:
        eng = create_async_engine(settings.database_url)
        _engines[key] = eng
        _session_makers[key] = async_sessionmaker(eng, expire_on_commit=False)
    return _session_makers[key]


class SessionLocalFactory:
    """Create DB sessions on the current event loop (required for LiveKit job subprocesses)."""

    def __call__(self) -> AsyncSession:
        return _ensure_loop_engine()()


SessionLocal = SessionLocalFactory()


async def dispose_engines() -> None:
    for eng in list(_engines.values()):
        await eng.dispose()
    _engines.clear()
    _session_makers.clear()


async def init_db() -> None:
    _ensure_loop_engine()
    eng = _engines[_loop_key()]
    async with eng.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(
            text("ALTER TABLE calls ADD COLUMN IF NOT EXISTS trace JSON NOT NULL DEFAULT '[]'")
        )
        await conn.execute(
            text(
                "ALTER TABLE calls ADD COLUMN IF NOT EXISTS status VARCHAR(32) NOT NULL DEFAULT 'ended'"
            )
        )
        await conn.execute(
            text(
                "ALTER TABLE knowledge_sources ADD COLUMN IF NOT EXISTS "
                "collection VARCHAR(64) NOT NULL DEFAULT 'general'"
            )
        )
        await conn.execute(
            text(
                "ALTER TABLE knowledge_sources ADD COLUMN IF NOT EXISTS category VARCHAR(64)"
            )
        )
        await conn.execute(
            text(
                "ALTER TABLE knowledge_chunks ADD COLUMN IF NOT EXISTS "
                "collection VARCHAR(64) NOT NULL DEFAULT 'general'"
            )
        )
        await conn.execute(
            text("ALTER TABLE knowledge_chunks ADD COLUMN IF NOT EXISTS category VARCHAR(64)")
        )

    async with SessionLocal() as session:
        agent = await session.scalar(select(Agent).where(Agent.is_default.is_(True)))
        if agent is None:
            agent = await session.scalar(select(Agent).order_by(Agent.created_at).limit(1))
        if agent is None:
            session.add(
                Agent(
                    name="Cybercrime desk",
                    instructions=DEFAULT_INSTRUCTIONS,
                    is_default=True,
                )
            )
            await session.commit()
            return

        changed = False
        if agent.name in {"1930 desk", "1930 Cybercrime Helpline desk"}:
            agent.name = "Cybercrime desk"
            changed = True
        if any(marker in agent.instructions for marker in LEGACY_INSTRUCTION_MARKERS):
            agent.instructions = DEFAULT_INSTRUCTIONS
            changed = True
        if changed:
            await session.commit()


async def get_agent(session: AsyncSession, agent_id: uuid.UUID | None) -> Agent | None:
    if agent_id is not None:
        agent = await session.get(Agent, agent_id)
        if agent is not None:
            return agent
    return await session.scalar(select(Agent).where(Agent.is_default.is_(True)))
