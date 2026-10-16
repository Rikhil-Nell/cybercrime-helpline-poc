"""Document ingestion and retrieval.

Parsing uses Microsoft MarkItDown (PDF, DOCX, PPTX, XLSX, HTML, CSV, and plain
text) into Markdown, then a structure-aware splitter that packs headings and
paragraphs into overlapping chunks. Retrieval is a scoped cosine search with a
score floor, returning chunks with their source document for attribution.
"""

from __future__ import annotations

import io
import re
import uuid
from dataclasses import dataclass
from pathlib import Path

from markitdown import MarkItDown, StreamInfo
from openai import AsyncOpenAI
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from helpline.knowledge_collections import (
    COLLECTIONS,
    INCIDENT_CATEGORIES,
    MAX_QUERY_LENGTH,
)
from helpline.models import Agent, KnowledgeChunk, KnowledgeSource
from helpline.settings import settings

EMBED_MODEL = "text-embedding-3-small"
EMBED_DIM = 1536
CHUNK_SIZE = 1200
CHUNK_OVERLAP = 200
PDF_CHUNK_SIZE = 700
PDF_CHUNK_OVERLAP = 120
DEFAULT_MIN_SCORE = 0.35
DEFAULT_LIMIT = 5

_markitdown = MarkItDown(enable_plugins=False)


@dataclass
class Hit:
    content: str
    source: str
    score: float
    collection: str = ""
    category: str | None = None


def normalize_collection(value: str | None) -> str | None:
    if not value:
        return None
    cleaned = value.strip().lower().replace("-", "_")
    return cleaned if cleaned in COLLECTIONS else None


def normalize_category(value: str | None) -> str | None:
    if not value:
        return None
    cleaned = value.strip().lower().replace("-", "_")
    return cleaned if cleaned in INCIDENT_CATEGORIES else None


def sanitize_query(query: str) -> str:
    """Strip control chars and cap length so callers cannot inject tool directives."""
    cleaned = "".join(ch for ch in query if ch >= " " or ch in "\n\t")
    return cleaned.strip()[:MAX_QUERY_LENGTH]


def openai_key(agent: Agent) -> str:
    return agent.openai_api_key or settings.openai_api_key


def deepgram_key(agent: Agent) -> str:
    return agent.deepgram_api_key or settings.deepgram_api_key


def parse_document(filename: str, data: bytes) -> str:
    """Convert an uploaded file to Markdown text."""
    suffix = Path(filename).suffix.lower()
    if suffix in {".txt", ".md", ""}:
        return data.decode("utf-8", errors="ignore")
    result = _markitdown.convert_stream(
        io.BytesIO(data),
        stream_info=StreamInfo(extension=suffix, filename=filename),
    )
    return result.markdown or ""


def _split_paragraphs(markdown: str) -> list[str]:
    """Break Markdown into heading-aware blocks that stay whole where possible."""
    lines = markdown.splitlines()
    blocks: list[str] = []
    buffer: list[str] = []

    def flush() -> None:
        text = "\n".join(buffer).strip()
        if text:
            blocks.append(text)
        buffer.clear()

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("#"):
            flush()
            buffer.append(line)
            flush()
        elif not stripped:
            flush()
        else:
            buffer.append(line)
    flush()
    return blocks


def chunk_markdown(markdown: str, size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    """Pack structural blocks into overlapping chunks near ``size`` characters."""
    cleaned = markdown.replace("\r\n", "\n").strip()
    if not cleaned:
        return []

    blocks = _split_paragraphs(cleaned)
    chunks: list[str] = []
    current = ""

    for block in blocks:
        # A single huge block (e.g. a wall of text) is hard-split on characters.
        if len(block) > size:
            if current:
                chunks.append(current)
                current = ""
            for start in range(0, len(block), size - overlap):
                chunks.append(block[start : start + size])
            continue

        if not current:
            current = block
        elif len(current) + len(block) + 2 <= size:
            current = f"{current}\n\n{block}"
        else:
            chunks.append(current)
            tail = current[-overlap:] if overlap else ""
            current = f"{tail}\n\n{block}".strip() if tail else block

    if current:
        chunks.append(current)

    return [chunk.strip() for chunk in chunks if chunk.strip()]


async def _embed(api_key: str, texts: list[str]) -> list[list[float]]:
    client = AsyncOpenAI(api_key=api_key)
    response = await client.embeddings.create(model=EMBED_MODEL, input=texts)
    ordered = sorted(response.data, key=lambda item: item.index)
    return [item.embedding for item in ordered]


async def ingest_source(
    session: AsyncSession,
    agent: Agent,
    filename: str,
    data: bytes,
    *,
    collection: str = "general",
    category: str | None = None,
) -> KnowledgeSource:
    key = openai_key(agent)
    if not key:
        raise ValueError("No OpenAI key set for this agent, so documents cannot be embedded.")

    markdown = parse_document(filename, data)
    suffix = Path(filename).suffix.lower()
    if suffix == ".pdf":
        chunks = chunk_markdown(markdown, size=PDF_CHUNK_SIZE, overlap=PDF_CHUNK_OVERLAP)
    else:
        chunks = chunk_markdown(markdown)
    if not chunks:
        raise ValueError("No readable text was found in that file.")

    coll = normalize_collection(collection) or "general"
    cat = normalize_category(category)

    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    source = KnowledgeSource(
        agent_id=agent.id,
        filename=filename,
        collection=coll,
        category=cat,
        chunk_count=len(chunks),
    )
    session.add(source)
    await session.flush()
    (settings.upload_dir / f"{source.id}-{Path(filename).name}").write_bytes(data)

    # Embed in batches so a large document does not exceed the request limit.
    rows: list[KnowledgeChunk] = []
    for start in range(0, len(chunks), 64):
        batch = chunks[start : start + 64]
        vectors = await _embed(key, batch)
        for content, vector in zip(batch, vectors, strict=True):
            rows.append(
                KnowledgeChunk(
                    agent_id=agent.id,
                    source_id=source.id,
                    source_name=filename,
                    collection=coll,
                    category=cat,
                    content=content,
                    embedding=vector,
                )
            )
    session.add_all(rows)
    await session.commit()
    await session.refresh(source)
    return source


async def search_knowledge(
    session: AsyncSession,
    agent: Agent,
    query: str,
    *,
    collection: str | None = None,
    category: str | None = None,
    limit: int = DEFAULT_LIMIT,
    min_score: float = DEFAULT_MIN_SCORE,
) -> list[Hit]:
    key = openai_key(agent)
    safe_query = sanitize_query(query)
    if not key or not safe_query:
        return []

    coll = normalize_collection(collection)
    cat = normalize_category(category)

    vector = (await _embed(key, [safe_query]))[0]
    distance = KnowledgeChunk.embedding.cosine_distance(vector).label("distance")
    stmt = select(
        KnowledgeChunk.content,
        KnowledgeChunk.source_name,
        KnowledgeChunk.collection,
        KnowledgeChunk.category,
        distance,
    ).where(KnowledgeChunk.agent_id == agent.id)
    if coll:
        stmt = stmt.where(KnowledgeChunk.collection == coll)
    if cat:
        stmt = stmt.where(KnowledgeChunk.category == cat)
    stmt = stmt.order_by(distance).limit(min(limit, 12))
    rows = (await session.execute(stmt)).all()

    hits: list[Hit] = []
    for content, source_name, row_coll, row_cat, dist in rows:
        score = 1.0 - float(dist)
        if score < min_score:
            continue
        hits.append(
            Hit(
                content=content,
                source=source_name or "document",
                score=round(score, 4),
                collection=row_coll or "",
                category=row_cat,
            )
        )
    return hits


async def list_resources(
    session: AsyncSession,
    agent: Agent,
    *,
    limit: int = 20,
) -> list[Hit]:
    """Return resource entries without a free-text query (injection-safe catalog)."""
    from helpline.knowledge_collections import COLLECTION_RESOURCES

    stmt = (
        select(KnowledgeChunk.content, KnowledgeChunk.source_name, KnowledgeChunk.category)
        .where(
            KnowledgeChunk.agent_id == agent.id,
            KnowledgeChunk.collection == COLLECTION_RESOURCES,
        )
        .order_by(KnowledgeChunk.source_name, KnowledgeChunk.id)
        .limit(limit)
    )
    rows = (await session.execute(stmt)).all()
    return [
        Hit(
            content=content,
            source=source_name or "resource",
            score=1.0,
            collection=COLLECTION_RESOURCES,
            category=row_cat,
        )
        for content, source_name, row_cat in rows
    ]


def format_hits(hits: list[Hit]) -> str:
    if not hits:
        return "Nothing relevant was found in the reference material."
    return "\n\n".join(f"[{hit.source}] {hit.content}" for hit in hits)


async def lookup_state_contact(
    session: AsyncSession,
    agent: Agent,
    state: str,
) -> list[Hit]:
    from helpline.knowledge_collections import COLLECTION_RESOURCES
    from helpline.state_contacts import normalize_state

    canonical = normalize_state(state)
    if canonical is None:
        return []
    query = f"{canonical} nodal cyber cell grievance officer contact phone email"
    hits = await search_knowledge(
        session,
        agent,
        query,
        collection=COLLECTION_RESOURCES,
        limit=4,
        min_score=0.25,
    )
    if hits:
        return hits
    # Fallback: substring match in resource chunks
    stmt = (
        select(KnowledgeChunk.content, KnowledgeChunk.source_name, KnowledgeChunk.category)
        .where(
            KnowledgeChunk.agent_id == agent.id,
            KnowledgeChunk.collection == COLLECTION_RESOURCES,
            KnowledgeChunk.content.ilike(f"%{canonical}%"),
        )
        .limit(3)
    )
    rows = (await session.execute(stmt)).all()
    return [
        Hit(content=content, source=source_name or "resource", score=1.0, collection=COLLECTION_RESOURCES)
        for content, source_name, _ in rows
    ]


async def fetch_advisory_snippet(query: str) -> str:
    """Fetch public advisory page text — gated supplement, not statutory guidance."""
    import urllib.request

    safe = sanitize_query(query)
    if not safe:
        return ""
    url = "https://cybercrime.gov.in/Webform/CyberCrimeAdvisory.aspx"
    try:
        with urllib.request.urlopen(url, timeout=12) as resp:
            html = resp.read().decode("utf-8", errors="ignore")
    except OSError:
        return ""
    text = re.sub(r"<script[^>]*>.*?</script>", " ", html, flags=re.I | re.S)
    text = re.sub(r"<style[^>]*>.*?</style>", " ", text, flags=re.I | re.S)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return ""
    lower = text.lower()
    terms = [t for t in safe.lower().split() if len(t) > 3][:6]
    if not terms:
        return text[:1200]
    window = 400
    for term in terms:
        idx = lower.find(term)
        if idx >= 0:
            start = max(0, idx - window // 2)
            return text[start : start + window]
    return text[:1200]


async def delete_source(session: AsyncSession, source_id: uuid.UUID) -> None:
    source = await session.get(KnowledgeSource, source_id)
    if source is None:
        return
    await session.execute(delete(KnowledgeChunk).where(KnowledgeChunk.source_id == source_id))
    await session.delete(source)
    await session.commit()
