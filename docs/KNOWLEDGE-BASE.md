# Knowledge base architecture — 1930 helpline

Curated from [cybercrime.gov.in](https://www.cybercrime.gov.in) FAQ, citizen manuals, advisories, and online safety content. The agent does **not** rely on a single RAG blob — each tool searches a **fixed collection**.

## Collections → tools

| Collection | Tool | When the agent uses it |
|------------|------|------------------------|
| `incident_playbook` | `search_incident_playbook` | Immediate post-incident steps by crime type |
| `portal_guide` | `search_portal_guide` | How to file/track on cybercrime.gov.in |
| `prevention` | `search_prevention` | Safety tips, hygiene, FAQs |
| `reassurance` | `search_reassurance` | Calm facts (recovery windows, scam patterns) — no case stories |
| `resources` | `list_resources` | Helplines, URLs, handbook links (no free-text query) |
| `agent_bounds` | *(not exposed as tool)* | Compliance reference for prompt authors |

## Incident categories (portal-aligned)

Used as optional tags on playbook / reassurance chunks:

| Category | Portal track | Example caller situation |
|----------|--------------|--------------------------|
| `financial_fraud` | Other cybercrime | Investment scam, job fraud with payment |
| `upi_fraud` | Other cybercrime | Wrong refund, fake GPay support |
| `digital_arrest` | Other cybercrime | Video-call "CBI/police" extortion |
| `sextortion` | Women/child or other | Blackmail with intimate images |
| `cseam_rgr` | **Women/child** | CSEAM, circulated RGR content |
| `impersonation` | Other | Fake profile, CEO fraud |
| `social_media` | Other | Abuse, hacked account |
| `ransomware` | Other | Encrypted files, ransom note |
| `hacking` | Other | Unauthorized access |
| `cryptocurrency` | Other | Crypto investment fraud |
| `cyber_bullying` | Women/child or other | Harassment at school/work online |
| `cyber_stalking` | Women/child or other | Repeated unwanted contact |
| `online_gambling` | Other | Betting app fraud |
| `cyber_trafficking` | Other | Recruitment/trafficking online |
| `other` | Either | Does not fit above |

## Where to put new content

| Source on portal | Collection | Notes |
|------------------|------------|-------|
| Citizen Manual — financial fraud | `portal_guide` + `incident_playbook/financial_fraud` | Split navigation vs steps |
| Citizen Manual — RGR | `portal_guide` + `incident_playbook/cseam_rgr` | Women/child track |
| FAQ (complaint types, evidence) | `portal_guide` | Chunk by FAQ topic |
| Online Safety Tips page | `prevention` | Parents, teens, orgs |
| Student handbook (38 pp) | `prevention` | One file per chapter or audience |
| Cyber awareness booklets | `prevention` | RBI ombudsman, social media booklet |
| Advisories (current scams) | `prevention` or future `web_search` gate | Prefer ingested PDFs for stability |
| "You may recover money" framing | `reassurance/financial_fraud` | No outcome promises |
| Digital arrest is fake | `reassurance/digital_arrest` | |
| 1930, 112, portal URLs | `resources` | Single canonical list |
| Agent must not promise refunds | `agent_bounds` | Not a live tool |

## Official resources to ingest next

Download from the portal (automated fetch often returns 500):

1. [Citizen Manual](https://www.cybercrime.gov.in/Webform/Citizen_Manual.aspx) — three PDFs
2. [FAQ](https://www.cybercrime.gov.in/Webform/FAQ.aspx)
3. [Cyber awareness](https://cybercrime.gov.in/webform/cyberaware.aspx) — booklets
4. [Online safety / student handbook](https://cybercrime.gov.in/webform/Crime_OnlineSafetyTips.aspx)

Place files in `backend/knowledge_seed/<collection>/` and run:

```powershell
cd backend
uv run python scripts/seed_knowledge.py
```

Dashboard upload: pick **collection** (and **category** for playbooks) before choosing the file.

## Security — no prompt-configurable tools

- Tool names and collection filters are **hardcoded** in `worker.py`.
- `list_resources` accepts **no query** — callers cannot inject search terms into it.
- Search queries are sanitized (length cap, control-char strip).
- `category` and `collection` arguments are validated against allowlists; unknown values are dropped.
- Upload API rejects unknown collection/category values.
- The LLM cannot register new tools or change embedding scope via instructions.

This prevents "tool injection" — the model being tricked into acting like it has broader powers than retrieval over approved corpora.

## Call script pattern

The default system prompt (`backend/src/helpline/instructions.py`) follows the proven outbound script shape:

1. **Connect** — permission, AI disclosure  
2. **Listen** — one open question, empathy  
3. **Triage** — fill blanks (type, time, amount, urgency)  
4. **Educate** — tools before facts  
5. **Guide** — one step at a time  
6. **Close** — repeat next action  

Reference: `docs/call-script-extract.md` (LegalShield eviction script — structural template only).
