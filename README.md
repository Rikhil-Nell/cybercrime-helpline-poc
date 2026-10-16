# Cybercrime Helpline (POC)

Voice helpline desk for India's cybercrime reporting flow: LiveKit telephony, Deepgram STT/TTS, OpenAI agent with a scoped knowledge base (pgvector), and a React operations dashboard.

## Quick start

1. Copy `backend/.env.example` → `backend/.env` and fill in keys.
2. Start Docker (Docker Desktop on Windows/macOS, or the Docker daemon on Linux).
3. From the repo root:

**Windows (PowerShell)**

```powershell
.\scripts\run.ps1
```

**Linux / macOS**

```bash
chmod +x scripts/run.sh   # once, if needed
./scripts/run.sh
```

4. Open **http://127.0.0.1:5173** — dial tab for outbound tests, or call your Twilio number for inbound.

Full setup, Twilio numbers, inbound vs outbound, and troubleshooting: **[docs/USAGE.md](docs/USAGE.md)**.

## Stack

| Layer | Tech |
|-------|------|
| API + worker | Python 3.13, FastAPI, LiveKit Agents |
| Knowledge | Postgres + pgvector, MarkItDown ingest |
| Dashboard | Vite, React, shadcn |
| Telephony | LiveKit SIP + Twilio |

## Docs

- [Usage & operations](docs/USAGE.md)
- [Knowledge base design](docs/KNOWLEDGE-BASE.md)
- [Call agent reference (telephony notes)](docs/CALL-AGENT-REFERENCE.md)
