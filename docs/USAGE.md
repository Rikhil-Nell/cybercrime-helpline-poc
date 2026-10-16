# Cybercrime Helpline — usage & operations

This POC runs a **voice agent (Kavita)** on a LiveKit worker, with a web **operations desk** for monitoring, knowledge, instructions, and call logs.

## Prerequisites

| Tool | Purpose |
|------|---------|
| [Docker Desktop](https://www.docker.com/products/docker-desktop/) | Postgres + pgvector (`compose.yaml`, port **5433**) |
| [uv](https://docs.astral.sh/uv/) | Python deps in `backend/` |
| Node.js 20+ | Dashboard in `web/` |
| LiveKit Cloud project | Rooms, agent dispatch, SIP |
| Twilio account | Phone number + SIP to LiveKit |
| OpenAI API key | LLM + embeddings |
| Deepgram API key | STT + TTS |

## First-time setup

### 1. Environment

```powershell
cd backend
copy .env.example .env
```

Edit `backend/.env`:

| Variable | Meaning |
|----------|---------|
| `LIVEKIT_URL` | `wss://…livekit.cloud` |
| `LIVEKIT_API_KEY` / `LIVEKIT_API_SECRET` | LiveKit project credentials |
| `SIP_OUTBOUND_TRUNK_ID` | LiveKit **outbound** SIP trunk ID (`ST_…`) |
| `TWILIO_NUMBER` | E.164 number on your inbound/outbound trunks (e.g. `+1…`) |
| `OPENAI_API_KEY` | Agent + knowledge embeddings |
| `DEEPGRAM_API_KEY` | Speech on calls |
| `DATABASE_URL` | Default matches Docker: `postgresql+asyncpg://helpline:helpline@127.0.0.1:5433/helpline` |
| `AGENT_NAME` | Must match worker registration (default **`helpline`**) |

Never commit `.env` — it is gitignored.

### 2. Seed the knowledge base (once)

```powershell
cd backend
uv run python scripts/seed_knowledge.py
```

Optional: ingest official PDFs from cybercrime.gov.in:

```powershell
uv run python scripts/seed_knowledge.py --pdfs-only
uv run python scripts/seed_knowledge.py --force   # re-ingest everything
```

### 3. Run everything

From repo root:

```powershell
.\scripts\run.ps1
```

Same as `.\scripts\dev.ps1`. Starts Postgres, API (`8000`), LiveKit worker, dashboard (`5173`).

- Dashboard: http://127.0.0.1:5173  
- Health: http://127.0.0.1:8000/api/health  

Stop with **Ctrl+C** in that terminal (stops API, worker, and UI).

---

## Inbound vs outbound

| Mode | Who starts the call | POC cost note |
|------|---------------------|---------------|
| **Inbound** | Caller dials your **Twilio number** | Typical demo path; you pay Twilio inbound minutes |
| **Outbound** | Dashboard **Dial** → API dispatches worker → worker dials callee | **US/international outbound is costly**; Twilio trial only allows **verified** destination numbers |

The **same worker** handles both. Inbound uses LiveKit SIP dispatch rules; outbound uses dashboard dispatch + `create_sip_participant`.

For day-to-day demos, **inbound is enough**: call the Twilio number from a phone that is allowed on your account.

---

## Inbound: receive calls on your Twilio number

On API startup, `ensure_inbound()` (in `telephony.py`) tries to:

1. Create or find a LiveKit **inbound SIP trunk** for `TWILIO_NUMBER`.
2. Create dispatch rule **`helpline-inbound`** → rooms `call-*` → agent **`helpline`**.

You still must wire **Twilio → LiveKit** (one-time):

1. In **LiveKit Cloud** → SIP → note inbound SIP URI / trunk for your project.
2. In **Twilio** → your number’s **Voice** configuration → route incoming calls to that SIP destination (Elastic SIP Trunk or LiveKit’s documented Twilio integration).

Checklist:

- `TWILIO_NUMBER` in `.env` matches the number in Twilio and on LiveKit trunks.
- Worker log shows `registered worker` with `agent_name=helpline`.
- No duplicate cloud agent named `helpline` stealing jobs (LiveKit Cloud → Agents).

When someone calls, Kavita should greet after the SIP participant joins. Call rows may appear in **Call logs** when the worker persists on hangup (inbound logging is lighter than outbound until you add explicit call rows on SIP dispatch).

---

## Outbound: dial from the dashboard

1. Open **Dial**, enter E.164 (e.g. `+917386175224`).
2. Watch **Pipeline** (dispatched → worker → ringing → answered → conversation → complete).
3. **Live monitor** shows room transcriptions (Kavita + Caller).

### Allow a number to receive outbound calls (Twilio)

On a **trial** Twilio account, outbound can only reach **verified** numbers:

1. Twilio Console → **Phone Numbers** → **Verified Caller IDs** (or **Trial** → verify a number).
2. Add the callee’s mobile; complete OTP verification.
3. Twilio Console → **Voice** → **Geo permissions** → enable countries you dial (e.g. India **+91** if calling from a US trunk).

On a **paid** account, geographic restrictions still apply — enable destinations you need.

LiveKit **outbound trunk** must use a valid Twilio termination address and caller ID (`SIP_OUTBOUND_TRUNK_ID` in `.env`). If the trunk still points at an old/reclaimed trial number, update the trunk in LiveKit to match `TWILIO_NUMBER`.

---

## Operations desk (dashboard)

| Tab | Use |
|-----|-----|
| **Dial** | Outbound test calls + live monitor |
| **Knowledge** | Upload docs by collection; view chunks |
| **Instructions** | Edit system prompt (markdown preview → click to edit) |
| **Call logs** | Transcript + agent tool trace |

Dark mode: header toggle. Agent voice name in-room: **Kavita**.

---

## Agent tools (voice)

- `search_knowledge` — scoped RAG (playbooks, portal, prevention, reassurance)
- `list_resources` — helplines, URLs, manuals
- `lookup_state_contact` — state nodal contacts
- `search_current_advisories` — prevention KB + public advisory page
- `note_incident_summary` — structured triage in trace
- `hang_up` — end call after goodbye

Retrieval uses **OpenAI embeddings + pgvector**, not raw prompt dump.

---

## Manual run (separate terminals)

If you prefer not to use `run.ps1`:

```powershell
docker compose up -d
cd backend
uv run uvicorn helpline.api:app --host 127.0.0.1 --port 8000
uv run python -m helpline.worker dev
cd ..\web
npm install
npm run dev -- --host 127.0.0.1 --port 5173
```

Only **one** worker process should register as `helpline`. Kill stray workers before testing:

```powershell
Get-CimInstance Win32_Process -Filter "Name = 'python.exe'" |
  Where-Object { $_.CommandLine -match 'helpline\.worker' } |
  ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
```

---

## Troubleshooting

| Symptom | Things to check |
|---------|------------------|
| Pipeline stuck on **Dispatched** | Worker running? `registered worker` in log? Same `AGENT_NAME` everywhere? |
| Kavita speaks, caller not transcribed | Restart worker after code changes; stable network to LiveKit/Deepgram; speak a full sentence after greeting |
| Outbound **480** / failed | Callee not verified (trial), geo permissions, or bad trunk number |
| Worker drops off after hours | Network/DNS to LiveKit — restart worker |
| No tool calls in trace | Prompt + model behavior; ensure KB seeded and OpenAI key set |
| Instructions UI old prompt | Restart API (migrates legacy DB prompt on startup) |

---

## Production notes (out of scope for POC)

- Real **1930** routing would terminate on your SIP ingress, same inbound trunk + dispatch pattern.
- Move secrets to a vault; run worker on a stable host with TURN if needed (`LIVEKIT_ICE_RELAY`).
- Disable or rename conflicting LiveKit **cloud** agents when developing locally.
