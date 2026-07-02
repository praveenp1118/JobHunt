<div align="center">

# AIJobsHunt

**AI-powered job search platform for senior product leaders** — live at **[aijobshunt.com](https://aijobshunt.com)**

[![Live](https://img.shields.io/badge/live-aijobshunt.com-059669)](https://aijobshunt.com)
[![Docs](https://img.shields.io/badge/docs-GitHub%20Pages-10b981)](https://praveenp1118.github.io/JobHunt)
![FastAPI](https://img.shields.io/badge/FastAPI-009688?logo=fastapi&logoColor=white)
![React](https://img.shields.io/badge/React-20232a?logo=react&logoColor=61dafb)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-4169e1?logo=postgresql&logoColor=white)
![Claude](https://img.shields.io/badge/Claude%20AI-d97757)
![Celery](https://img.shields.io/badge/Celery%20%2B%20Redis-37814a?logo=celery&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-2496ed?logo=docker&logoColor=white)

🌐 **[Live app → aijobshunt.com](https://aijobshunt.com)** &nbsp;·&nbsp; 📖 **[Documentation →](https://praveenp1118.github.io/JobHunt)**

</div>

---

## Overview

AIJobsHunt automates the highest-effort parts of a senior product leadership job search. It scans
curated job feeds and Gmail job-alert digests, scores every opportunity against your **master CV**
and multiple **domain-specific CVs**, then tailors your CV and cover letter for each role — making
only bounded, factual edits and **never inventing experience**. Everything is tracked end-to-end,
from discovery to application to recruiter follow-up.

It runs as a Docker stack — locally for development and in production at
**[aijobshunt.com](https://aijobshunt.com)** (Caddy reverse proxy + automatic HTTPS). Each user brings
their own AI (Anthropic) and scraping (Apify) API keys. **Access is invite-or-pay**: registration is open,
but a new account is inert (read-only) until it redeems an invite key or subscribes.

## Key features

- **AI CV tailoring** — per-job CV + cover letter with a strict *golden rule* (reorder, rephrase,
  inject keywords, deselect — never invent), gated by a factual-integrity score before sending.
- **Multi-domain scoring** — every job is scored against the master CV **and all** active domain
  CVs; the best-fit domain surfaces automatically and pre-selects when you tailor.
- **ATS + Pursuit dual scoring** — beyond fit, every job gets two judgement scores per CV entity
  (master / domain / tailored): an **ATS** score (simulated automated screening — keyword/skills/experience/
  seniority/education, with a hard-requirement dealbreaker cap) and a **Pursuit** score (should you pursue it?
  — human appeal, career-move quality, achievability, timing). Shown as a dual-ring pill (ATS outer, Pursuit
  inner) across the Tracker, Tailor page, Job detail, Dashboard, and Career Insights, with an ATS/Pursuit/
  Combined toggle. Career **Readiness** aggregates these real scores (no AI call) into a live dual radar.
- **Hybrid-RAG scoring pipeline** — a 3-stage funnel cuts scoring cost ~**82%** with no quality loss on
  saved jobs: Stage 1 keyword pre-filter (free) → Stage 2 essence scoring (Haiku) → Stage 3 full-CV scoring
  (Sonnet, borderline jobs only). The CV "essence" is extracted once and cached. Three presets (Maximum
  Quality / Balanced / Max Savings) + a live cost calculator in Settings, plus an optional **night-batch**
  mode that scores the day's jobs cheaply at 2 AM.
- **Tiered-model cost optimization** — every Claude call uses the cheapest sufficient model: email
  classification is rules-first (free) then Haiku; JD highlights are Haiku + **cached per job**; feed keywords
  and CV→markdown use Haiku; career insights run on the CV essence. The API Usage tab shows the model tier
  (Haiku / Sonnet / Opus) and ₹ cost per call.
- **Email-to-AIJobsHunt** — forward any job URL to your job-search Gmail with a subject containing `jobhunt`
  or starting with `jh:`; it's auto-fetched, parsed, scored, and saved (📥 Email source) with a confirmation
  email back to you.
- **Auto-detect external applications** — the Gmail poll recognises LinkedIn / Indeed "application sent /
  received" confirmations, flips the matching tracked job to **Applied**, and links the email — or adds the
  job if it wasn't tracked.
- **Gmail job-alert parser** — detects LinkedIn / Indeed / company alert digests (rule-based, no
  AI cost) and extracts job cards straight from the email body for login-gated sources.
- **Feed scanner** — scheduled RSS + Apify (LinkedIn, Google Jobs) scanning, with domain-CV-driven
  keyword profiles and a free keyword pre-filter before any paid scoring call.
- **Activity dashboard** — per-feed scan funnels (`raw → pre-filter → above-threshold → saved`),
  job-alert timelines, error logs, and manual "run now" controls.
- **Application tracking** — full pipeline (`new → applied → interview → offer → ghosted`), recruiter
  email threads, human-in-the-loop reply approval, and automatic follow-up drafting.
- **Career Insights ✨** — one cached (7-day) batch Claude call across all your tracked JDs produces a
  readiness score and a 7-tab gap analysis (Readiness · Keywords · Skills · Experience · Certifications ·
  Build · Roadmap) with a checkable improvement roadmap and a Dashboard readiness widget.
- **API usage visibility** — every Claude + Apify call is logged with token counts and ₹/$ cost; inline
  token badges appear at the point of action (12 locations) plus a Settings → API Usage tab with CSV export.
- **Support chat** — an in-app widget on every page: a rule-based FAQ bot (12 categories, **no AI cost**)
  with live WebSocket hand-off to an admin when online, or a ticket + email when offline.
- **Community insights** — opt-in, fully anonymised sharing of job scores + JD highlights + tailoring
  patterns (never CV content or PII); recipients spend **0 tokens**. Surfaces only at ≥2 contributors.
- **Invite-or-pay access** — registration is open, but a new account is **inert** (read-only) until
  **entitled**, either by redeeming a **single-use invite key** (30 days free) or **subscribing** to
  AIJobsHunt Pro (₹500/mo via Stripe). **Every Claude-calling route is gated** (402 until entitled) and the
  gate is **expiry-aware** (an invite's free month lapses with no background job). Admins bypass. Invited
  users can request an extension (in-app queue + best-effort admin email); admins generate/revoke keys and
  grant extensions from an **Admin panel**.
- **Public landing page** — a fast, responsive marketing site at **[aijobshunt.com](https://aijobshunt.com)**
  (React/Vite) with animated product mocks, invite-key redemption + signup, and full SEO (OpenGraph / Twitter
  / JSON-LD, sitemap, PWA manifest).
- **Templates** — one global CV template (font / size / margins / accent / bullets → deterministic PDF
  styling) plus content rules (never-modify sections, section order, page budget) injected into the tailor
  prompt; per-domain overrides, live previews, and an overflow "trim to fit" guard.
- **Security & governance** — AES-256 encryption, bcrypt + JWT, per-user **rate limiting**, **prompt-injection
  hardening** (XML-tagged user content), an **anti-hallucination** check (no invented metrics), security-headers
  middleware, Redis **login lockout**, and an immutable **audit log**.
- **GDPR self-service** — Settings → Privacy: data summary, one-click **JSON/markdown export** (ZIP),
  rate-limit transparency, and **right-to-erasure** with a 30-day grace period; admins get a Governance dashboard.

## Screenshots

**Landing page** — the public site: scored, tailored, tracked — honestly:

![Landing page](docs/screenshots/landing.png)

**Dashboard** — your search at a glance: ATS + Pursuit averages, career readiness, feed performance:

![Dashboard](docs/screenshots/dashboard.png)

**Job Tracker** — every job scored against your master CV and all domain CVs, with ATS + Pursuit dual rings:

![Job Tracker](docs/screenshots/tracker.png)

**AI Tailor** — bounded change log with a live CV / cover-letter / email preview:

![AI Tailor](docs/screenshots/tailor.png)

<table>
  <tr>
    <td width="50%" valign="top"><b>Activity dashboard</b><br/><img src="docs/screenshots/activity.png" alt="Activity dashboard"/></td>
    <td width="50%" valign="top"><b>My CVs — master + domain</b><br/><img src="docs/screenshots/cvs.png" alt="My CVs"/></td>
  </tr>
  <tr>
    <td width="50%" valign="top"><b>Feeds &amp; scanning</b><br/><img src="docs/screenshots/feeds.png" alt="Feeds and scanning"/></td>
    <td width="50%" valign="top"><b>Admin — invites &amp; access</b><br/><img src="docs/screenshots/admin.png" alt="Admin invites and access"/></td>
  </tr>
</table>

## The scoring model

| Score | Meaning | Computed |
|---|---|---|
| **S1** | Base fit — JD vs **master CV** | At ingest |
| **S1d** | Contextual fit — JD vs **best-matching domain CV** (scored against all, highest wins) | At ingest |
| **S2** | Tailored fit — JD vs the **tailored CV** | After applying tailor changes |
| **S3** | **Factual integrity** — % of the tailored CV traceable to the master CV | After applying — hard send-gate (≥90 green · 85–89 amber · <85 blocked) |

Plus a complementary **dual-judgement** layer per CV entity: **ATS** (will it pass automated screening?) and
**Pursuit** (should you pursue it?), each 0–100 with a component breakdown — surfaced as a dual-ring pill.

## Architecture

Docker stack — six services behind a Caddy reverse proxy (auto-HTTPS) in production. The FastAPI
backend serves the React SPA + public landing and orchestrates AI calls; the Celery worker drives the
input pipelines.

```mermaid
flowchart TD
    U([Visitor / user]) -->|HTTPS| CADDY["Caddy · auto-HTTPS<br/>aijobshunt.com"]
    CADDY -->|/api/*| BE
    CADDY -->|else| FE["React Frontend<br/>Vite · Tailwind · landing + SPA"]
    FE -->|REST + WebSocket| BE["FastAPI Backend<br/>async · auth · AI orchestration · :8000"]
    BE --> DB[("PostgreSQL<br/>jobs · CVs · feeds · logs")]
    BE --> RD[("Redis<br/>Celery broker")]
    BE --> AI["Claude — user's key<br/>3-stage RAG · essence · tailor · career"]
    RD --> WK["Celery Worker + Beat<br/>feed scan · Gmail poll · night-batch · ghost check"]
    WK --> DB
    WK --> AI
    WK --> GM["Gmail<br/>IMAP + SMTP"]
    WK --> RSS["RSS Feeds<br/>Jobicy …"]
    WK --> AP["Apify Actors<br/>LinkedIn · Google"]
    BE --> PW["Playwright<br/>title pre-filter · PDF"]
    WK --> PW
```

See the full write-up in **[docs/architecture.md](docs/architecture.md)**.

## Tech stack

| Layer | Technology |
|---|---|
| Backend | FastAPI, SQLAlchemy (async), Alembic, PostgreSQL |
| Auth | FastAPI-Users, JWT, Google OAuth |
| Frontend | React (Vite) + Tailwind CSS, Zustand, TanStack Query, Recharts |
| AI | Anthropic Claude (each user's own API key) |
| Task queue | Celery + Redis + Celery Beat |
| Email | Gmail IMAP (poll) + SMTP (send), BeautifulSoup HTML parsing |
| Job scanning | RSS feeds + Apify actors |
| Browser / PDF | Playwright (title pre-filter + HTML→PDF) |
| Storage | Local filesystem, user-scoped (`users/{user_id}/tailored\|cover_letters\|exports/`) — S3 migration planned |
| Payments / access | Stripe (AIJobsHunt Pro subscription) + single-use invite keys (invite-or-pay gate) |
| Deployment | Docker Compose · Caddy reverse proxy (automatic HTTPS) at aijobshunt.com |
| Real-time | WebSockets (support chat) |
| Security | AES-256, bcrypt, JWT, security headers, per-user rate limiting, Redis login lockout, audit log |
| Testing | pytest + pytest-asyncio (in-container live-server smoke tests) |

## Project structure

```
JobHunt/
├── backend/            # FastAPI app
│   └── app/
│       ├── agents/     # Claude-powered agents (CV, JD, tailor, scanner, gmail)
│       ├── mcp/        # External clients (Gmail IMAP/SMTP, Apify, RSS)
│       ├── models/     # SQLAlchemy models
│       ├── routers/    # API routes
│       ├── tasks/      # Celery tasks (scanner, gmail polls)
│       └── utils/      # PDF, encryption, storage, model helpers
├── frontend/           # React (Vite) SPA
├── docs/               # GitHub Pages documentation site
├── docker-compose.yml
└── CLAUDE.md           # Single source of truth for project state
```

## Getting started

> Requires Docker + Docker Compose.

```bash
# 1. Configure environment (fill in your own keys — never commit .env)
cp .env.example .env

# 2. Start the stack
docker-compose up -d

# 3. Apply database migrations
docker-compose exec backend alembic upgrade head
```

- Frontend → http://localhost:3000
- Backend API → http://localhost:8000

Each user supplies their own **Anthropic API key** (for AI) and optional **Apify token**
(for scraping) and **Gmail app password** (for email) in the app's Settings.

The first account (seeded from `ADMIN_EMAIL` in `.env`) is the **admin** and bypasses the access gate.
New accounts are inert until entitled — generate **invite keys** from the Admin panel (or subscribe) to
onboard others. A production deploy uses `docker-compose.prod.yml` + `Caddyfile` (see `CLAUDE.md` →
Deployment).

## Testing

```bash
docker-compose exec backend pytest tests/ -v
```

The suite runs **in-container against the live uvicorn server** over real HTTP against the real
Postgres DB — **148 smoke tests** (145 passing + 3 skipped live/owner-absent) covering the API, scanner,
Gmail alert parser, multi-domain scoring, the hybrid-RAG pipeline, tiered-model optimization, ATS + Pursuit
dual scoring, career readiness, billing, the **invite-or-pay access gate** (key redemption, races, expiry,
extension requests), governance, templates, and more.

## Documentation

- 🌐 **[Live docs site](https://praveenp1118.github.io/JobHunt)** — landing page + architecture / features / API
- [docs/architecture.md](docs/architecture.md) · [docs/features.md](docs/features.md) · [docs/api.md](docs/api.md)
- [CLAUDE.md](CLAUDE.md) — detailed, evolving project-state document

## Status

Active personal project — **live at [aijobshunt.com](https://aijobshunt.com)** (Docker + Caddy, automatic
HTTPS). Core platform (V1–V3) is **feature-complete**: CV management, AI tailoring, multi-domain scoring, the
**hybrid-RAG scoring pipeline** + tiered-model cost optimization, feed scanning, Gmail alert parsing,
**Email-to-AIJobsHunt**, auto-detected applications, the activity dashboard, Career Insights, API usage
visibility, support chat, community insights, CV templates, an **ATS + Pursuit dual-scoring** layer with a
real-data career-readiness radar, a security-first governance layer (rate limiting, prompt-injection
hardening, audit logs, GDPR export/erasure) with static legal pages + registration consent, an
**invite-or-pay access gate** (single-use keys · 30-day entitlement · Stripe · extension requests), and a
**public marketing landing page**. **148 smoke tests (145 passing + 3 skipped).**

## License

Personal project — no open-source license is currently applied (all rights reserved).
