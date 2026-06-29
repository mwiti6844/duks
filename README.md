# CarDuka AI Agent Demo

A chat-first web app where a logged-in user talks to an AI agent that helps them
shop on **CarDuka** — Kenya's NCBA-backed car marketplace. The agent streams
**inline generative UI** (car cards, comparison tables, an interactive financing
calculator, live auction countdowns, a bid-confirmation modal, AI price verdicts,
and cited knowledge answers) as it reasons over seeded marketplace data and a small
RAG knowledge base. **Demo only — all data is dummy/seeded.**

## Architecture

```
Browser ──HTTPS──> web (Next.js BFF, PUBLIC)
                    - HTTP-only cookie auth (opaque JWT) + CSRF (Origin/Host, SameSite)
                    - streaming proxy for /api/*  (fetch + ReadableStream)
                    - SSR readiness gate + client poller
                    └─internal─> api (FastAPI, PRIVATE)
                                  ├ JWT verify (only api holds JWT_SECRET)
                                  ├ /api/health (503 until seed + embeddings done)
                                  ├ LangGraph router → discovery / transaction / rag /
                                  │                      profile / listings
                                  ├ deterministic tools (authz + financial rules)
                                  ├ SQLite (curated hero rows + 20 real listings; sold comps)
                                  ├ ChromaDB in-memory (image-baked ONNX MiniLM model, CPU)
                                  └ Redis (conversation context + pending bids/listing drafts)
```

- **Only `web` is public.** It's a BFF that forwards `/api/*` to the private `api`,
  injecting the JWT (kept in an HTTP-only cookie) as a `Bearer` token.
- **Streaming:** LangGraph nodes publish transport-neutral execution events via the
  stream writer; an SSE adapter serializes them. Components are validated against an
  allow-listed Pydantic schema before streaming.
- **Interactive generative UI:** car and auction cards send typed, server-validated
  actions when clicked. Contextual follow-up cards offer executable next steps such as
  compare, price verdict, financing, bidding, and auction guidance. Redis stores recent
  structured turns so components remain interactive after refresh.
- **Bidding (human-in-the-loop):** chat prepares a **signed, expiring** bid proposal
  (HMAC + random `proposal_id`) and streams a confirm modal. Only
  `POST /api/bids/confirm` persists — idempotently, guarded by a UNIQUE `proposal_id`
  DB constraint, so a refresh/retry never double-bids.
- **Selling (Listings agent):** a 5th specialist uses the configured LLM for open-ended
  structured extraction, then validates make, model, year, mileage, price, transmission,
  fuel, condition, body type, and location without inventing defaults. A signed, expiring
  draft is streamed as a confirm card; `POST /api/listings/confirm` persists once,
  idempotently (UNIQUE `source_draft_id`). Ownership is by the authenticated `user_id`.
- **RAG:** answers are grounded in retrieved chunks; citations come from chunk
  metadata; off-domain questions are declined.
- **Personas, not permissions:** David (buyer) and Sarah (seller) are display personas
  only — every journey (buy, sell, finance, bid) is open to every authenticated user.
- **Memory:** Redis holds recent turns and structured session context (active journey,
  search constraints, displayed IDs, and the focused entity). Confirmed preferences are
  stored by `user_id` in SQLite and survive new browser sessions. Listings, bids, and
  prices are always reloaded from the database. Railway requires Redis; the in-memory
  fallback is limited to local development and tests.
- **Seed data:** curated hero rows guarantee the scripted demo, augmented by **20 real
  CarDuka listings** parsed from a scrape (real prices, descriptions, NCBA CDN images).
  Six "sold" rows are **simulated sales derived from real listings** (synthesized
  sold-price/date for price-verdict comparables — not real transaction data).
- **LLM:** Claude `claude-sonnet-4-6` is the default (router + agents); Groq
  `llama-3.3-70b-versatile` is a streaming failover. A deterministic fake runs the
  demo keyless (`USE_FAKE_LLM=1`).

## Repo layout

```
carduka/
  api/   FastAPI + LangGraph (Python 3.12, PRIVATE service)
  web/   Next.js App Router BFF (Node 24, PUBLIC service)
  docker-compose.yml   local parity: web + api + redis
  railway.json         Railway deploy hints (healthcheck /api/health)
```

## Run locally

### Option A — Docker Compose (closest to Railway)

```bash
cp .env.example .env        # add ANTHROPIC_API_KEY (and optionally GROQ_API_KEY)
docker compose up --build
# open http://localhost:3000
```

### Option B — two processes

```bash
# API (private)
cd api
python3.12 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
USE_FAKE_LLM=1 uvicorn app.main:app --port 8000      # or set ANTHROPIC_API_KEY

# Web (public BFF) — separate terminal
cd web
npm install
API_INTERNAL_URL=http://localhost:8000 npm run dev    # http://localhost:3000
```

> First API start downloads the ONNX embedding model unless you build the Docker image
> (which bakes it in). The readiness page covers this wait.

> **Fresh DB required for v4.** The schema gained columns (`profile_context`, listing
> `owner_id` / `source_draft_id` / `description`). SQLite `create_all()` does not ALTER
> existing tables, so delete any old demo DB before the first v4 run:
> `find /tmp -name 'carduka*.db' -delete`. On Railway the SQLite DB is ephemeral, so a
> redeploy is a fresh DB automatically.

## Demo flow

**David demo journey:**
1. Open `/` → readiness gate → **sign in as David** (one click).
2. Choose **Buy a car** to start a neutral needs-and-budget intake, or type a specific
   request such as *"Find me a Subaru Forester under 2.5M"*.
3. The agent renders matching **car cards** inline.
4. *"Compare the first two"* → **comparison table** (ordinal resolved deterministically).
5. *"Is the price fair?"* → **AI price verdict** over sold comparables.
6. *"What would financing look like?"* → **interactive calculator** (drag deposit/term).
7. *"Show me auctions"* → **live countdown timers**.
8. *"Bid 1.8M on the Subaru Forester"* → **confirm modal**; confirm to place it
   (refresh mid-bid and the modal restores from Redis).
9. *"How do auctions work?"* → **cited knowledge answer**.

**Sarah demo journey:** sign in as Sarah → *"I want to sell my car"* → the **Listings agent**
collects the details turn-by-turn (try *"Sell my 2016 Toyota Fielder"* to fill several at
once) → a **listing summary** card appears → **Confirm & publish** (idempotent; refresh
mid-listing and the draft restores).

The empty chat exposes the **6 journeys as typed action cards** — Buy, Sell, Finance, and
the informational Trade-In / Insure / Dealer-Finance journeys. Cards do not hide
model/budget assumptions: Buy asks for search criteria, while Finance asks for a selected
vehicle or its real price before rendering a calculator.

Demo accounts are ordinary CarDuka users, not buyer/seller account types. Any
authenticated user can search, list a vehicle, finance, or bid; persisted records are
isolated by the authenticated user id.

Trade-In, Insurance, and Dealer Finance answers are retrieved from focused Chroma chunks
derived from CarDuka's public service pages and terms. Citation chips link to those source
pages. These informational answers do not invent approval, valuation, premium, or policy
terms.

Confirming **Publish listing** calls `POST /api/listings/confirm` and creates an active,
owner-scoped SQLite row exactly once. The UI displays the resulting listing id. **Journeys**
returns to the six starting cards without ending the session; **Exit** signs out and
returns to the demo-user chooser.

The web UI uses CarDuka's public brand mark and core palette: yellow `#FECE2D`, ink
`#0E0E0B`, red `#FF000D`, neutral surfaces, and accessible dark text on yellow controls.

Expand **Agent trace** under any assistant message to see routing, tool calls +
timings, citation ids, and the prompt version.

## Tests

```bash
cd api && . .venv/bin/activate && pytest          # auth, routing, memory, HITL bids,
                                                  # listings (slot-fill, idempotent confirm,
                                                  # cross-user isolation, tamper, sticky/cancel),
                                                  # seed augmentation, replay protection,
                                                  # schema validation, ordinal resolution,
                                                  # RAG citations, price verdict + eval fixtures
cd web && npm run build                           # type-check + production build
```

## Deploy to Railway

1. Create a project and add the **Redis** plugin.
2. Service **api** — root `api/`, Dockerfile build. It's private (no public domain).
   Env: `ANTHROPIC_API_KEY`, `GROQ_API_KEY` (optional), `JWT_SECRET`,
   `BID_SIGNING_SECRET`, `REDIS_URL` (from the plugin). Health check: `/api/health`.
3. Service **web** — root `web/`, Dockerfile build. Public. Env:
   `API_INTERNAL_URL` = the api service's internal URL.
4. The **web** service URL is your shareable demo link. At least one LLM provider key
   must be set on `api`, or it fails fast at startup.

## Environment variables

| Service | Variable | Notes |
|---|---|---|
| api | `ANTHROPIC_API_KEY` | default LLM (`claude-sonnet-4-6`); ≥1 provider key required |
| api | `GROQ_API_KEY` | streaming failover (`llama-3.3-70b-versatile`) |
| api | `JWT_SECRET` | only the api holds this |
| api | `BID_SIGNING_SECRET` | HMAC for signed bid proposals |
| api | `REDIS_URL` | Required on Railway/production |
| api | `ALLOW_IN_MEMORY_SESSIONS` | Local/test escape hatch only |
| api | `APP_ENV` | Set to `production` outside local development |
| api | `USE_FAKE_LLM=1` | run keyless with the deterministic fake |
| web | `API_INTERNAL_URL` | server-only, runtime; **no** `NEXT_PUBLIC_` prefix |
```
