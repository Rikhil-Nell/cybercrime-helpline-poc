"""Ingest curated knowledge_seed/ files and official PDFs into the vector store.

Usage (from backend/):
    uv run python scripts/seed_knowledge.py
    uv run python scripts/seed_knowledge.py --force   # re-ingest even if filename exists
    uv run python scripts/seed_knowledge.py --pdfs-only
"""

from __future__ import annotations

import argparse
import asyncio
import http.client
import re
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import select

from helpline.db import SessionLocal, get_agent, init_db
from helpline.knowledge import chunk_markdown, ingest_source, parse_document
from helpline.knowledge_collections import COLLECTIONS, INCIDENT_CATEGORIES
from helpline.models import KnowledgeSource

SEED_ROOT = Path(__file__).resolve().parent.parent / "knowledge_seed"

BASE = "https://cybercrime.gov.in"


@dataclass(frozen=True)
class RemotePdf:
    collection: str
    category: str | None
    url: str
    filename: str


OFFICIAL_PDFS: tuple[RemotePdf, ...] = (
    RemotePdf(
        "portal_guide",
        None,
        f"{BASE}/UploadMedia/MHA-CitizenManualReportOtherCyberCrime-v10.pdf",
        "citizen-manual-other-cybercrime.pdf",
    ),
    RemotePdf(
        "portal_guide",
        None,
        f"{BASE}/UploadMedia/instructions_citizenreportingcyberfrauds.pdf",
        "citizen-reporting-cyber-frauds.pdf",
    ),
    RemotePdf(
        "portal_guide",
        None,
        f"{BASE}/UploadMedia/MHA-CitizenManualReportCPRGRcomplaints-v10.pdf",
        "citizen-manual-cprgr.pdf",
    ),
    RemotePdf(
        "prevention",
        None,
        f"{BASE}/UploadMedia/PublicNotice.pdf",
        "public-notice-cyber-safety.pdf",
    ),
    RemotePdf(
        "prevention",
        None,
        f"{BASE}/UploadMedia/PublicNotice_CPGRAMS.pdf",
        "public-notice-cpgrams.pdf",
    ),
    RemotePdf(
        "prevention",
        None,
        f"{BASE}/pdf/Fake%20EMail%20Alert%20Content.pdf",
        "fake-email-alert.pdf",
    ),
)


def download_pdf(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "helpline-seed/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            chunks: list[bytes] = []
            while True:
                block = resp.read(65536)
                if not block:
                    break
                chunks.append(block)
            return b"".join(chunks)
    except http.client.IncompleteRead as exc:
        if len(exc.partial) > 10_000:
            return exc.partial
        raise


def discover_brochure_pdfs() -> list[RemotePdf]:
    """Scrape safety-tips pages for brochure PDF links."""
    pages = (
        f"{BASE}/Webform/CyberSafetyTips.aspx",
        f"{BASE}/Webform/CyberCrimeAdvisory.aspx",
    )
    found: dict[str, RemotePdf] = {}
    for page in pages:
        try:
            req = urllib.request.Request(page, headers={"User-Agent": "helpline-seed/1.0"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                html = resp.read().decode("utf-8", errors="ignore")
        except OSError as exc:
            print(f"skip (page fetch failed): {page} ({exc})")
            continue
        for match in re.finditer(r'(?:href|src)="([^"]+\.pdf[^"]*)"', html, flags=re.I):
            href = match.group(1)
            if href.startswith("/"):
                url = BASE + href
            elif href.startswith("http"):
                url = href
            else:
                continue
            name = Path(url.split("?", 1)[0]).name.lower()
            if name in {item.filename for item in OFFICIAL_PDFS}:
                continue
            slug = re.sub(r"[^a-z0-9]+", "-", name.removesuffix(".pdf")).strip("-") or "brochure"
            found[url] = RemotePdf("prevention", None, url, name if name.endswith(".pdf") else f"{slug}.pdf")
    return list(found.values())


def preview_pdf(data: bytes, filename: str) -> tuple[int, int]:
    """Return (char_count, chunk_count) without embedding."""
    markdown = parse_document(filename, data)
    chunks = chunk_markdown(markdown, size=700, overlap=120)
    return len(markdown), len(chunks)


async def ingest_markdown(force: bool) -> tuple[int, int]:
    ingested = 0
    skipped = 0
    async with SessionLocal() as session:
        agent = await get_agent(session, None)
        if agent is None:
            raise SystemExit("No default agent found. Start the API once to create it.")

        existing = {
            row.filename
            for row in await session.scalars(
                select(KnowledgeSource).where(KnowledgeSource.agent_id == agent.id)
            )
        }

        for path in sorted(SEED_ROOT.rglob("*.md")):
            collection = path.parent.name
            if collection not in COLLECTIONS:
                print(f"skip (unknown collection folder): {path}")
                skipped += 1
                continue

            category = None
            if collection in {"incident_playbook", "reassurance"}:
                cat_norm = path.stem.replace("-", "_")
                if cat_norm in INCIDENT_CATEGORIES:
                    category = cat_norm

            filename = f"seed/{collection}/{path.name}"
            if filename in existing and not force:
                print(f"skip (exists): {filename}")
                skipped += 1
                continue

            data = path.read_bytes()
            source = await ingest_source(
                session,
                agent,
                filename,
                data,
                collection=collection,
                category=category,
            )
            print(f"ingested: {filename} -> {source.chunk_count} chunks")
            ingested += 1

    return ingested, skipped


async def ingest_pdfs(force: bool) -> tuple[int, int]:
    ingested = 0
    skipped = 0
    async with SessionLocal() as session:
        agent = await get_agent(session, None)
        if agent is None:
            raise SystemExit("No default agent found.")

        existing = {
            row.filename
            for row in await session.scalars(
                select(KnowledgeSource).where(KnowledgeSource.agent_id == agent.id)
            )
        }

        remote_pdfs = list(OFFICIAL_PDFS)
        discovered = discover_brochure_pdfs()
        print(f"discovered {len(discovered)} brochure PDF(s) from safety pages")
        remote_pdfs.extend(discovered)

        for item in remote_pdfs:
            filename = f"seed/{item.collection}/{item.filename}"
            if filename in existing and not force:
                print(f"skip (exists): {filename}")
                skipped += 1
                continue
            try:
                data = download_pdf(item.url)
            except (OSError, http.client.HTTPException) as exc:
                print(f"skip (download failed): {item.url} ({exc})")
                skipped += 1
                continue

            chars, chunk_count = preview_pdf(data, item.filename)
            print(f"extracted: {item.filename} -> {chars} chars, {chunk_count} chunk(s) planned")
            if chunk_count == 0:
                print(f"skip (no text): {filename}")
                skipped += 1
                continue

            source = await ingest_source(
                session,
                agent,
                filename,
                data,
                collection=item.collection,
                category=item.category,
            )
            print(f"ingested: {filename} -> {source.chunk_count} chunks")
            ingested += 1

    return ingested, skipped


async def main(force: bool, pdfs_only: bool) -> None:
    await init_db()
    total_ingested = 0
    total_skipped = 0
    if not pdfs_only:
        ingested, skipped = await ingest_markdown(force)
        total_ingested += ingested
        total_skipped += skipped
    ingested, skipped = await ingest_pdfs(force)
    total_ingested += ingested
    total_skipped += skipped
    print(f"done: {total_ingested} ingested, {total_skipped} skipped")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true", help="Re-ingest seed files")
    parser.add_argument("--pdfs-only", action="store_true", help="Only download and ingest PDFs")
    args = parser.parse_args()
    asyncio.run(main(args.force, args.pdfs_only))
