# Architecture

## Overview

AIJobsHunt is a **Docker-based** platform — a `docker-compose` stack of six services, plus a **Caddy**
reverse proxy (automatic HTTPS) in production. It runs locally for development and is live at
**[aijobshunt.com](https://aijobshunt.com)**. It is designed for a small number of senior-product-leader
users who bring their own AI and scraping API keys. There is no external SaaS dependency beyond the AI
provider (Anthropic) and the job-scraping providers (Apify) the user configures. A **public React landing
page** is served at the site root; the authenticated SPA lives behind it. **Access is invite-or-pay** — a
new account is inert until it redeems an invite key or subscribes.

## System diagram

<div class="my-7 rounded-2xl border border-slate-200 bg-gradient-to-b from-slate-50 to-white p-5 sm:p-7">
  <div class="flex justify-center">
    <div class="w-72 rounded-xl border border-sky-200 bg-sky-50 px-4 py-3 text-center shadow-sm">
      <div class="text-sm font-semibold text-sky-900">React Frontend</div>
      <div class="text-[11px] text-sky-600" style="font-family:ui-monospace,Menlo,monospace">Vite · Tailwind · Recharts · :3000</div>
    </div>
  </div>
  <div class="text-center text-slate-400 text-xs my-2">▲ &nbsp;HTTPS · REST + WebSocket&nbsp; ▼</div>
  <div class="grid grid-cols-1 sm:grid-cols-3 gap-3 items-stretch">
    <div class="rounded-xl border border-slate-300 bg-white px-4 py-3 text-center shadow-sm flex flex-col justify-center">
      <div class="text-sm font-semibold text-slate-800">PostgreSQL</div>
      <div class="text-[11px] text-slate-500" style="font-family:ui-monospace,Menlo,monospace">jobs · CVs · feeds · logs</div>
    </div>
    <div class="rounded-xl border-2 border-emerald-300 bg-emerald-50 px-4 py-3 text-center shadow-sm flex flex-col justify-center">
      <div class="text-sm font-semibold text-emerald-900">FastAPI Backend</div>
      <div class="text-[11px] text-emerald-600" style="font-family:ui-monospace,Menlo,monospace">async · auth · AI orchestration · :8000</div>
    </div>
    <div class="rounded-xl border border-slate-300 bg-white px-4 py-3 text-center shadow-sm flex flex-col justify-center">
      <div class="text-sm font-semibold text-slate-800">Redis</div>
      <div class="text-[11px] text-slate-500" style="font-family:ui-monospace,Menlo,monospace">Celery broker</div>
    </div>
  </div>
  <div class="text-center text-slate-400 text-xs my-2">▼</div>
  <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
    <div class="rounded-xl border border-amber-200 bg-amber-50 px-4 py-3">
      <div class="text-sm font-semibold text-amber-900 text-center mb-2">🤖 AI engine — Claude (user's key)</div>
      <div class="flex flex-wrap justify-center gap-1.5 text-[11px]">
        <span class="rounded-full bg-white border border-amber-200 px-2 py-0.5 text-amber-700">3-stage RAG scorer</span>
        <span class="rounded-full bg-white border border-amber-200 px-2 py-0.5 text-amber-700">Essence agent</span>
        <span class="rounded-full bg-white border border-amber-200 px-2 py-0.5 text-amber-700">Tailor · JD parse</span>
        <span class="rounded-full bg-white border border-amber-200 px-2 py-0.5 text-amber-700">Career analyser</span>
        <span class="rounded-full bg-white border border-amber-200 px-2 py-0.5 text-amber-700">Tiered: Haiku ⇢ Sonnet</span>
      </div>
    </div>
    <div class="rounded-xl border border-violet-200 bg-violet-50 px-4 py-3">
      <div class="text-sm font-semibold text-violet-900 text-center mb-2">⚙ Celery Worker + Beat</div>
      <div class="flex flex-wrap justify-center gap-1.5 text-[11px]">
        <span class="rounded-full bg-white border border-violet-200 px-2 py-0.5 text-violet-700">Feed scanner</span>
        <span class="rounded-full bg-white border border-violet-200 px-2 py-0.5 text-violet-700">Gmail poll</span>
        <span class="rounded-full bg-white border border-violet-200 px-2 py-0.5 text-violet-700">Night-batch · 2 AM</span>
        <span class="rounded-full bg-white border border-violet-200 px-2 py-0.5 text-violet-700">Ghost check</span>
      </div>
    </div>
  </div>
  <div class="text-center text-slate-400 text-xs my-2">▼ &nbsp;external integrations&nbsp; ▼</div>
  <div class="grid grid-cols-2 sm:grid-cols-5 gap-2.5">
    <div class="rounded-xl border border-slate-200 bg-white px-3 py-2.5 text-center shadow-sm">
      <div class="text-[13px] font-semibold text-slate-700">Gmail</div>
      <div class="text-[10px] text-slate-500" style="font-family:ui-monospace,Menlo,monospace">IMAP + SMTP</div>
    </div>
    <div class="rounded-xl border border-slate-200 bg-white px-3 py-2.5 text-center shadow-sm">
      <div class="text-[13px] font-semibold text-slate-700">RSS Feeds</div>
      <div class="text-[10px] text-slate-500" style="font-family:ui-monospace,Menlo,monospace">Jobicy …</div>
    </div>
    <div class="rounded-xl border border-slate-200 bg-white px-3 py-2.5 text-center shadow-sm">
      <div class="text-[13px] font-semibold text-slate-700">Apify</div>
      <div class="text-[10px] text-slate-500" style="font-family:ui-monospace,Menlo,monospace">LinkedIn · Google</div>
    </div>
    <div class="rounded-xl border border-slate-200 bg-white px-3 py-2.5 text-center shadow-sm">
      <div class="text-[13px] font-semibold text-slate-700">Playwright</div>
      <div class="text-[10px] text-slate-500" style="font-family:ui-monospace,Menlo,monospace">title · PDF</div>
    </div>
    <div class="rounded-xl border border-slate-200 bg-white px-3 py-2.5 text-center shadow-sm">
      <div class="text-[13px] font-semibold text-slate-700">Stripe</div>
      <div class="text-[10px] text-slate-500" style="font-family:ui-monospace,Menlo,monospace">subscriptions</div>
    </div>
  </div>
</div>

### Services (`docker-compose`)

| Service | Role |
|---|---|
| `jobhunt_frontend` | React (Vite) SPA — the tracker, CV manager, tailor UI, dashboards |
| `jobhunt_backend` | FastAPI app — REST API, auth, AI orchestration |
| `jobhunt_db` | PostgreSQL — jobs, CVs, feeds, email threads, run logs |
| `jobhunt_redis` | Redis — Celery broker |
| `jobhunt_worker` | Celery worker — feed scans, Gmail polls, ghosting checks |
| `jobhunt_beat` | Celery Beat — schedules the recurring tasks |

## Core components

- **JD Parser** — extracts structured fields (company, role, location, market, seniority,
  skills, salary, recruiter email) from raw job text or a fetched URL.
- **Scorer** — four scores:
  - **S1** — base fit of the JD against the **master CV**.
  - **S1d** — contextual fit against the **best-matching domain CV** (a job is scored against
    *every* active domain CV; the highest wins).
  - **S2** — fit of the **tailored CV** against the JD (computed after applying changes).
  - **S3** — **factual integrity**: what fraction of the tailored CV is traceable to the master
    CV. Acts as a hard send-gate (≥90 green, 85–89 amber, <85 blocked).
- **CV Tailor** — produces a bounded change log (reorder / rephrase / keyword-injection /
  deselect) plus a cover letter and an application email. The **golden rule**: never invent
  experiences, metrics, skills, or companies — only re-present what is already in the master CV.
- **Feed Scanner** — runs RSS and Apify feeds, each linked to a domain CV; keyword profiles are
  derived from the domain CV; a rule-based keyword pre-filter runs before any paid scoring call.
- **Gmail Parser** — detects job-alert digest emails (rule-based), extracts job cards directly
  from the email body for login-gated sources (LinkedIn/Indeed), and scores/saves matches. Also runs the
  **Email-to-AIJobsHunt** classifier (save a URL by emailing it) and **auto-detects external applications**
  from "application sent/received" confirmations.
- **RAG Scorer** — the 3-stage hybrid pipeline (keyword pre-filter → essence scoring → full-CV scoring)
  shared by the scanner, the public-URL alert path, and manual adds. Reads its per-stage config from the
  user's preferences (preset-driven).
- **Essence Agent** — extracts a compact CV "essence" JSON (keywords, identity, strengths, seniority,
  markets) once per CV upload/apply (Haiku); cached indefinitely and reused by Stages 1–2 and other agents.
- **Night-Batch task** — a 2 AM IST Celery job that scores jobs saved as *pending* during the day (overnight
  scoring-timing mode), plus a manual "Score now / Score all" path.
- **CV Template system** — a global template per user (aesthetic rules → PDF; content rules → tailor prompt)
  with optional per-domain overrides and an overflow "trim to fit" guard.
- **PDF Generator** — renders CVs and cover letters to PDF via Playwright (HTML template → PDF).
- **Career Analyser** — a single cached (7-day) batch Claude call over the **CV essence** + up to **100**
  best-fit tracked JDs that returns a readiness score and a structured gap analysis (keywords, skills,
  experience, certifications, projects, roadmap). Drives the 7-tab Career Insights page and the Dashboard widget.
- **Usage Logger** — records every Anthropic + Apify call (tokens, model, category, ₹/$ cost) via a
  per-request contextvar, powering the inline token badges and the API Usage tab.
- **Support Chat** — a rule-based FAQ engine (no AI) plus a **WebSocket** server for real-time admin
  hand-off; falls back to a ticket + email when no admin is online.
- **Access — invite-or-pay** — registration is open, but a new account is **inert** until **entitled**,
  either by redeeming a **single-use invite key** (`invitation_keys`; 30 days free, atomic/race-safe
  `SELECT … FOR UPDATE` redemption) or via a **Stripe subscription**. Entitlement reuses the existing
  `subscription_status` / `subscription_end` columns + `entitlement_source` (`invite` | `stripe`). The
  `require_active_subscription` gate (**402 `entitlement_required`**) is **expiry-aware** (an invite's free
  month lapses with no background job) and applied to **every Claude-calling route** (jobs · cvs · tailor ·
  feeds · career · gmail) plus the scheduled scanner / Gmail poll; **admins bypass**. Invited-lapsed users
  file an **extension request** (in-app queue is the source of truth + best-effort admin email); admins
  generate/revoke keys and grant extensions from the Admin panel.
- **Billing** — Stripe subscription lifecycle (checkout / cancel / webhook / verify) feeding the same
  entitlement columns the access gate reads.
- **Community Insights** — anonymised aggregation of scores + JD highlights + tailoring patterns
  (never CV/PII), surfaced once ≥2 members contribute. Company/role are normalised for bucket matching.
- **Security & governance layer** — a `rate_limiter` (per-user/action limits, DB-backed), a `cv_validator`
  (anti-hallucination — metrics must trace to the master CV), an `audit_logger` (immutable trail), Redis
  `login_security` (5-failure lockout), an `input_validator` (upload type/size), prompt-injection hardening
  (XML-tagged user content in every agent), a security-headers middleware, and a global error handler.
- **Privacy / GDPR** — data summary, ZIP export, and right-to-erasure with a 30-day grace window enforced by
  a daily `purge_deleted_accounts` Celery task (storage → Stripe customer → database CASCADE).

## Data flow

### Four input pipelines (all converge on the same scoring + save path)

1. **Manual** — paste JD text or a URL → JD parser → S1 + multi-domain scoring → save.
2. **Feed scan** — scheduled (or on-demand) RSS/Apify fetch → keyword pre-filter → dedup →
   S1 + multi-domain scoring → threshold-gated save, tagged with the source feed + domain CV.
3. **Gmail job alerts** — hourly IMAP poll → rule-based alert detection → email-body card
   extraction (gated sources) or fetch + parse (public ATS links) → scoring → save.
4. **Gmail recruiter mail** — the same poll classifies genuine recruiter replies and flags them
   for human-in-the-loop approval (replies are never auto-sent).

### Tailor → apply → send flow

```
Select domain CV (best-fit pre-selected)
      │
      ▼
Generate package  ── one Claude call ──▶  change log + cover letter + email draft + S2
      │
      ▼
Review change log  (approve / reject / edit each bounded change)
      │
      ▼
Apply  ──▶  tailored CV + S3 integrity score (domain + master)  ──▶  green / amber / blocked
      │
      ▼
Send application  ──▶  Gmail SMTP (test mode redirects to a notification address by default)
      │
      ▼
Track  ──▶  status lifecycle + recruiter thread + follow-up drafting
```

### Scoring pipeline

```
JD ingested
   │
   ▼
S1  (master CV vs JD)
   │
   ▼
keyword pre-filter  (rule-based, zero-cost — drops clearly non-product roles)
   │
   ▼
S1d  (scored against ALL active domain CVs)  ──▶  best_domain_cv_id = highest
   │
   ▼
threshold gate  (decision = s1d if domain CVs exist else s1; save if ≥ s1_min_threshold)
   │
   ▼
saved to tracker
   │
   ▼
S2  (tailored CV vs JD, after tailoring)
   │
   ▼
S3  (factual-integrity check — % traceable to the master CV; hard send-gate)
```

### Gmail alert pipeline

```
hourly IMAP poll
   │
   ▼
classify  (rule-based, no AI)  ──▶  job_alert detected
   │
   ▼
extract links from the HTML body (cap raised to 200 KB)
   ├── LinkedIn / gated  ──▶  parse job cards from the email body (no fetch — login wall)
   │                            └─ SKIP_WORDS title filter → saved unscored, has_partial_jd=True
   └── public ATS URLs   ──▶  Playwright title pre-filter → fetch → JD parse → multi-domain score
                                └─ save if S1d ≥ threshold
   │
   ▼
partial-JD jobs: optional background fetch_and_rescore_partial_job (manual button → Celery)
```

### Career Insights pipeline

```
user triggers analysis  (explicit — never auto-charges)
   │
   ▼
fetch the user's best-fit JDs (limit 100, S1d DESC) + CV essence + question answers
   │
   ▼
ONE batch Claude call (analyse_career_gaps, max_tokens 8000)
   │
   ▼
structured gap-analysis JSON  ──▶  save to career_analysis (readiness + per-axis scores)
   │
   ▼
generate career_roadmap_items  +  cache for 7 days (expires_at)
   │
   ▼
community insights  (anonymised, opt-in, surfaced at ≥2 contributors)
```

### Token visibility

```
every Claude call
   │
   ▼
log_anthropic_usage()  ──▶  api_usage_logs  (one row per call)
   │                          (contextvar set at the request boundary attributes the session/user)
   ▼
per-call cost in ₹ / $  (PRICING per model; INR = USD × 83.5)
   │
   ▼
TokenBadge component (shared 10-colour scale) at 12 UI locations
   │
   ▼
Settings → API Usage tab  ──▶  30-day log + category breakdown + CSV export
```

## Migration chain

Alembic revisions, base → head:

```
base → 7bad (initial) → f6a2 → a1b2 (user profile fields)
→ v2_feed_system → b2c3 (feed actor_name)
→ v3_gmail_job_alerts → v3_gmail_alert_prefs → v3_activity_log
→ v3_domain_cv_scores → v3_partial_jd → v3_stripe_subscriptions
→ v3_chat → v3_api_usage_log → v3_job_s1_tokens → v3_community
→ v3_career_insights → v3_cv_template → v3_gdpr_consent → v3_governance
→ v3_career_filters → v3_rag_scoring → v3_night_batch → v3_auto_detect_apps
→ v3_email_to_jobhunt → v3_optimization → v3_email_source
→ v3_ats_pursuit → v3_dual_scan_gate → v3_invite_or_pay
→ v4_tailor_draft_persistence  (head)
```

## Scoring Pipeline — Hybrid RAG

To minimise token cost without losing accuracy on saved jobs, AIJobsHunt scores jobs through a
3-stage hybrid-RAG pipeline (the scanner and the public-URL alert path both use it).

```
Job arrives (scanner / Gmail alert)
        │
        ▼
Stage 1 — Keyword pre-filter (FREE)
   match JD text against the CV "essence" keyword list
   < threshold matches → REJECT (no API call) — ~55% filtered here
        │
        ▼
Stage 2 — Essence scoring (cheap, e.g. Haiku)
   send the compact CV essence JSON + JD → fast 0-100 relevance score
   < reject threshold → REJECT — ~25% filtered here   (~₹0.03/job)
        │
        ▼
Stage 3 — Full-CV scoring (quality, e.g. Sonnet)
   only borderline jobs (or when there's no essence) get the FULL CV + JD
   accurate final S1 — ~15-20% of jobs reach here     (~₹0.58/job)
        │
        ▼
Domain-CV scoring (cheap)  — only if S1 ≥ a min threshold; finds best_domain_cv_id
```

### CV Essence

Computed **once per CV upload/update** with Haiku (~₹0.08), stored in `master_cvs.essence_json`
and `domain_cvs.essence_json`. It is a small JSON blob — `keywords` (20-30 searchable terms),
`core_identity`, `top_experiences`, `domain_strengths` (1-10 per domain), `seniority_level`,
`markets`, `education`, `certifications`, `years_experience`. Stage 1 uses the keyword list;
Stage 2 scores against the whole essence instead of the full CV.

### Cost

| Approach | Cost/scan | Quality |
|---|---|---|
| Old (full CV × Sonnet × all jobs) | ~₹165 | ✅ |
| Hybrid RAG — Balanced preset | ~₹28 | ✅ |
| Hybrid RAG — Maximum Savings | ~₹10 | ⚠️ |
| Hybrid RAG — Maximum Quality | ~₹80 | ✅✅ |

≈ **82% cheaper** on the Balanced preset, with no quality loss on the jobs that clear the threshold.

### Tiered models beyond scoring

The same "cheapest sufficient model" principle is applied to every other Claude call:

| Call | Optimization |
|---|---|
| Email classification | rules-first (free) → **Haiku** for the rest |
| JD highlights (Tailor page) | **Haiku** + CV essence, **cached per job** (`jobs.jd_highlights_json`) |
| Feed keyword generation | **Haiku** + CV essence |
| CV text → markdown | **Haiku** |
| Career Insights | CV essence (not full text), up to 100 best-fit JDs |
| Manual JD parse | Haiku-essence first, Sonnet full-CV only if borderline |

The **API Usage** tab shows a per-call model-tier badge (Haiku / Sonnet / Opus) and a `by_model` cost summary.

## CV Template System

Two independent rule sets, both stored per user (with optional per-domain overrides):

- **Aesthetic rules** — font family/size, heading style, margins, line spacing, bullet glyph, accent colour →
  compiled to a deterministic CSS override block applied by the PDF generator (master / domain / tailored).
- **Content rules** — `max_pages` (→ `max_words` = pages × 300), `never_modify_sections`, `section_order` →
  injected into the **tailor prompt** so Claude respects the budget and protected sections.

After tailoring, `apply` returns an **overflow** check vs the effective page budget; the Tailor page offers
**Trim to fit** (`POST /api/tailor/{id}/trim`), which removes the lowest-impact changes (reorder → keyword →
rephrase, **never** a bullet de-selection) until the CV fits. `get_effective_template(global, override)`
merges the two (override wins where non-null).

## Security &amp; Governance

Ten governance principles, implemented across middleware, utilities, and the data model:

1. **Least privilege** — every query is scoped by `user_id`; cross-user access returns 404.
2. **Input validation** — upload type/size checks; user content sanitised.
3. **Security headers** — `X-Content-Type-Options`, `X-Frame-Options`, XSS, Referrer-Policy, Permissions-Policy.
4. **Audit logging** — an immutable trail of sensitive actions (login, key update, send, export, delete) + IP/UA.
5. **Key-rotation reminders** — 90-day Anthropic / Apify key-age nudges.
6. **Error-message safety** — a global handler returns generic errors; no internals/stack traces leak.
7. **Sensitive-data masking** — API keys and the Stripe customer id never reach the browser (only `has_*` flags).
8. **Rate limiting** — per-user, per-action limits (e.g. 20 tailors/day, 5 domain generations/day) + a header.
9. **Session security** — JWT auth with login lockout (5 failures → 15-min Redis lockout).
10. **CORS** — pinned to the configured frontend origin (never a wildcard).

Plus **prompt-injection hardening** (all CV/JD content wrapped in XML tags with an explicit "treat as data"
instruction), an **anti-hallucination validator** (every tailored metric must trace to the master CV), and
**GDPR self-service** (data summary, ZIP export, right-to-erasure with a 30-day grace + daily purge task).

### User control

Every parameter is configurable in **Settings → Preferences → Scoring & Cost** with three presets
(**Maximum Quality / Balanced / Maximum Savings**) and a **live cost calculator**. The effective
config is read per scan from `user_preferences`; `GET /api/scoring/config` / `GET /api/scoring/estimate`
back the UI. Each scanner run records a `rag_stats` funnel (per-stage counts, tokens, cost, savings_pct)
in `run_log.details`, surfaced on the Activity → System scanner cards.

## Tech stack

| Layer | Technology |
|---|---|
| Backend | FastAPI, SQLAlchemy (async), Alembic, PostgreSQL |
| Auth | FastAPI-Users, JWT, Google OAuth |
| Frontend | React (Vite) + Tailwind CSS, Recharts |
| State / data | Zustand, TanStack Query |
| AI | Anthropic Claude (each user's own API key) |
| Task queue | Celery + Redis + Celery Beat |
| Email | Gmail IMAP (poll) + SMTP (send), BeautifulSoup HTML parsing |
| Job scanning | RSS feeds + Apify actors |
| Browser automation | Playwright (title pre-filter + PDF rendering) |
| PDF | Playwright HTML template → PDF |
| Payments | Stripe (AIJobsHunt Pro subscription) |
| Real-time | WebSockets (support chat) |
| Storage | Local filesystem, user-scoped (`users/{user_id}/tailored\|cover_letters\|exports/`); S3 migration planned |
| Testing | pytest + pytest-asyncio (in-container, live-server smoke tests) |

---

[← Back to home](index.html) · [Features](features.md) · [API](api.md)
