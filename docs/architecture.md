# Architecture

## Overview

JobHunt is a **local, Docker-based** platform — a single `docker-compose` stack of six
services. It is designed for a small number of senior-product-leader users who bring their
own AI and scraping API keys. There is no external SaaS dependency beyond the AI provider
(Anthropic) and the job-scraping providers (Apify) the user configures.

## System diagram

```
   ┌───────────────────┐         ┌────────────────────────┐         ┌──────────────┐
   │  React Frontend   │ ───────▶│   FastAPI Backend      │ ───────▶│  PostgreSQL  │
   │  (Vite, :3000)    │  HTTPS  │   (:8000)              │  async  │              │
   └───────────────────┘         └───────────┬────────────┘         └──────────────┘
                                             │                        ┌──────────────┐
                                             ├───────────────────────▶│    Redis     │
                                             │   Anthropic Claude      │  (broker)    │
                                             ▼                         └──────┬───────┘
                                   ┌────────────────────┐                     │
                                   │  Claude (user key) │                     ▼
                                   └────────────────────┘            ┌──────────────────┐
                                                                     │  Celery Worker   │
                                                                     │  + Celery Beat   │
        ┌──────────────────────────────────────────────────────────┴──────────────────┤
        ▼                       ▼                        ▼                    ▼
  ┌────────────┐         ┌────────────┐          ┌──────────────┐     ┌──────────────┐
  │ Gmail IMAP │         │ RSS Feeds  │          │ Apify Actors │     │  Playwright  │
  │ + SMTP     │         │            │          │              │     │              │
  └────────────┘         └────────────┘          └──────────────┘     └──────────────┘
```

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
  from the email body for login-gated sources (LinkedIn/Indeed), and scores/saves matches.
- **PDF Generator** — renders CVs and cover letters to PDF via Playwright (HTML template → PDF).
- **Career Analyser** — a single cached (7-day) batch Claude call over the master CV + up to 50 tracked
  JDs that returns a readiness score and a structured gap analysis (keywords, skills, experience,
  certifications, projects, roadmap). Drives the 7-tab Career Insights page and the Dashboard widget.
- **Usage Logger** — records every Anthropic + Apify call (tokens, model, category, ₹/$ cost) via a
  per-request contextvar, powering the inline token badges and the API Usage tab.
- **Support Chat** — a rule-based FAQ engine (no AI) plus a **WebSocket** server for real-time admin
  hand-off; falls back to a ticket + email when no admin is online.
- **Billing** — Stripe subscription lifecycle (checkout / cancel / webhook / verify) with a
  `require_active_subscription` gate (402) on paid write endpoints; admins bypass.
- **Community Insights** — anonymised aggregation of scores + JD highlights + tailoring patterns
  (never CV/PII), surfaced once ≥2 members contribute. Company/role are normalised for bucket matching.

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
fetch all the user's JDs (limit 50) + master CV + question answers
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
→ v3_domain_cv_scores → v3_job_s1d → v3_partial_jd
→ v3_stripe_subscriptions → v3_chat → v3_api_usage_log
→ v3_job_s1_tokens → v3_community → v3_career_insights  (head)
```

## Tech stack

| Layer | Technology |
|---|---|
| Backend | FastAPI, SQLAlchemy (async), Alembic, PostgreSQL |
| Auth | FastAPI-Users, JWT, Google OAuth |
| Frontend | React (Vite) + Tailwind CSS |
| State / data | Zustand, TanStack Query |
| AI | Anthropic Claude (each user's own API key) |
| Task queue | Celery + Redis + Celery Beat |
| Email | Gmail IMAP (poll) + SMTP (send), BeautifulSoup HTML parsing |
| Job scanning | RSS feeds + Apify actors |
| Browser automation | Playwright (title pre-filter + PDF rendering) |
| PDF | Playwright HTML template → PDF |
| Payments | Stripe (JobHunt Pro subscription) |
| Real-time | WebSockets (support chat) |
| Storage | Local filesystem (S3 migration planned) |
| Testing | pytest + pytest-asyncio (in-container, live-server smoke tests) |

---

[← Back to home](index.html) · [Features](features.md) · [API](api.md)
