# JobHunt — Project State Document

> This file is the single source of truth for the JobHunt codebase.
> Update this file whenever Claude Code makes changes.
> Share this file at the start of every new Claude.ai session.

---

## Project Overview

AI-powered job search platform for senior product leaders (Head of Product, VP Product, CPO, AI Product Lead).
Target markets: Netherlands/EU (primary), Dubai, Singapore, India (backup).
Local Docker deployment only. Multi-user capable.

**Owner:** Praveen Prakash  
**Admin email:** praveenp.1118@gmail.com  
**Project root:** `D:\JobHunt`  
**GitHub:** https://github.com/praveenp1118/JobHunt (public)  
**Docs:** https://praveenp1118.github.io/JobHunt — GitHub Pages, served from `/docs` on `main`  
*(Repo is **public** (as of June 24, 2026). `docs/`: `index.html` landing page +
`architecture.html` / `features.html` / `api.html` — thin pages that render the matching `*.md` source
via marked.js with shared `doc.css` + `doc.js` (consistent Tailwind styling). `.nojekyll` keeps it
pure-static — no Jekyll.)*  
**Last major build:** V3 Multi-domain-CV scoring (June 24, 2026) — every job scored vs master + ALL
domain CVs; Best Fit column + filters/sort; RSS company fix. All 19 smoke tests passing
(prior: V3 Activity Dashboard, Gmail Job Alert Parser + Option A)

---

## Infrastructure

```
docker-compose services:
  jobhunt_backend   → FastAPI, port 8000
  jobhunt_frontend  → React (Vite), port 3000
  jobhunt_db        → PostgreSQL, port 5432, db=jobhunt
  jobhunt_redis     → Redis (Celery broker)
  jobhunt_worker    → Celery worker (scanner + Gmail tasks)
  jobhunt_beat      → Celery Beat (scheduled tasks)

Useful commands:
  docker-compose logs backend --tail 30
  docker-compose logs worker --tail 20
  docker-compose exec backend alembic upgrade head
  docker-compose restart backend frontend worker beat
```

---

## Testing

API smoke tests live in `backend/tests/` (pytest + pytest-asyncio). They run
inside the backend container and hit the **live in-container uvicorn server**
over real HTTP against the real Postgres DB (not in-process) — this avoids the
pytest-asyncio cross-event-loop issue with the module-level async engine.

```
# Run the suite (pytest is in requirements.txt; rebuild backend if not yet baked in)
docker-compose exec backend pytest tests/ -v

# Single file
docker-compose exec backend pytest tests/test_api_smoke.py -v
```

- `conftest.py` provides an `httpx.AsyncClient` and a `user_creds` fixture that
  registers a fresh **non-admin** user (random email), logs in for a token, and
  **deletes the user on teardown** (DB-level ON DELETE CASCADE cleans up the
  user's preferences / credentials / wallet / wallet_transactions) — so each run
  leaves the DB clean.
- Current coverage (25 tests, all passing):
  - `test_api_smoke.py` (7): login 200, GET /cvs/master 200, GET /jobs/stats 200 +
    `by_domain_cv` present, GET /feeds 200, GET /admin/stats 403 for non-admin,
    GET /activity/alerts 200, GET /activity/system 200.
  - `test_job_alert.py` (8): V3 rule-based classification (2-signal threshold), link
    extraction (KEEP/SKIP + cap), **email-body card extraction** (LinkedIn role/company/
    location), and **subject exclusion** (security alert). Pure functions — no Claude/net/DB.
  - `test_job_alert_integration.py` (1): `process_job_alert_email` orchestration with
    `fetch_url_content` + `parse_and_score_jd` mocked — asserts only qualifying jobs
    (S1 ≥ threshold) save with `source=gmail_alert` + `source_email_id`. Fresh engine + cleanup.
  - `test_scanner.py` (1): `_scan_feeds_for_user` (RSS mocked empty) returns the rich per-feed
    breakdown keys that become `run_log.details.feeds_summary`.
  - `test_domain_scoring.py` (2): `_best_domain` picks the highest domain CV score (pure); and a
    job with `domain_cv_scores` populated is returned by GET /api/jobs with `s1d` + scores, best = max.
  - `test_linkedin_alert.py` (4): `extract_jobs_from_linkedin_email` parses cards (title/company/
    location/url, noise dropped); `_is_linkedin_alert`; `is_job_alert_email` detects a LinkedIn alert;
    and a `gmail_alert` job with `has_partial_jd=True` surfaces the flag via GET /api/jobs.
  - `test_tailor.py` (2): `_country_rule_display` maps `CountryMaster` flags → display strings (pure);
    `POST /api/tailor/jd-highlights` returns 404 for an unknown job.
- NOT tested: `check_title_relevance` (live Playwright) and a true live end-to-end
  (real Gmail inbox + Anthropic).

---

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | FastAPI, SQLAlchemy async, Alembic, PostgreSQL |
| Auth | FastAPI-Users, JWT (7d / 30d remember me), Google OAuth |
| Frontend | React (Vite) + Tailwind CSS |
| State | Zustand (auth store, toast store) |
| Data fetching | TanStack Query (React Query) |
| AI | Anthropic Claude (user's own API key) |
| Task queue | Celery + Redis + Celery Beat |
| Email | Gmail IMAP (poll) + SMTP (send) |
| Job scanning | RSS feeds + Apify actors |
| PDF | Playwright → HTML template → PDF |
| Payments | Razorpay (V3 — not yet built) |
| Storage | Local /app/storage/ (S3 migration in V3) |
| Testing | pytest + pytest-asyncio (API smoke tests, run in-container against live server) |

---

## Folder Structure

```
D:\JobHunt\
├── backend/
│   ├── app/
│   │   ├── agents/          # Claude-powered agents
│   │   │   ├── cv_agents.py         # domain CV generation, S3 scoring
│   │   │   ├── jd_agents.py         # JD parsing, S1 scoring
│   │   │   ├── tailor_agents.py     # CV tailoring, CL, email draft
│   │   │   ├── scanner_agents.py    # batch S1 scoring for scanned jobs
│   │   │   ├── gmail_agents.py      # email classification
│   │   │   ├── feed_agents.py       # V2: feed profile auto-generation
│   │   │   └── gmail_alert_agent.py # V3: job alert email parser (rule-based detect + link extract + parse/score)
│   │   ├── mcp/             # External service clients
│   │   │   ├── gmail_mcp.py         # IMAP poll + SMTP send
│   │   │   ├── apify_mcp.py         # Apify actor runner
│   │   │   └── rss_mcp.py           # RSS feed fetcher
│   │   ├── models/          # SQLAlchemy models
│   │   │   ├── user.py              # User, UserCredentials, UserPreferences
│   │   │   ├── cv.py                # MasterCV, DomainCV, TailoredCV, CVChangelog
│   │   │   ├── job.py               # Job, EmailThread
│   │   │   ├── domain.py            # IndustryVertical, FunctionalDiscipline, CountryMaster, UserFeed, UserTargetCompany
│   │   │   ├── admin.py             # RunLog, ErrorLog, EmailAlertLog (V3), InviteCode
│   │   │   └── wallet.py            # Wallet, WalletTransaction
│   │   ├── routers/         # FastAPI routers
│   │   │   ├── auth.py              # login, register, profile, credentials, preferences, admin endpoints
│   │   │   ├── cvs.py               # master CV, domain CV, changelog
│   │   │   ├── jobs.py              # job CRUD, stats, status updates
│   │   │   ├── tailor.py            # tailor generate, changelog, apply
│   │   │   ├── gmail.py             # Gmail send, poll, test connection
│   │   │   ├── feeds.py             # feeds CRUD, scanner trigger, apify-actors search
│   │   │   ├── pdfs.py              # PDF generation endpoints
│   │   │   ├── wallet.py            # wallet balance, transactions
│   │   │   └── activity.py          # V3: activity dashboard (alerts timeline + system runs)
│   │   ├── tasks/           # Celery tasks
│   │   │   ├── scanner_tasks.py     # weekly_job_scan
│   │   │   └── gmail_tasks.py       # poll_gmail_all_users, check_ghosted_jobs
│   │   ├── utils/
│   │   │   ├── pdf_generator.py     # Playwright CV + CL PDF generation
│   │   │   ├── encryption.py        # AES-256 for API keys
│   │   │   ├── storage.py           # local file storage helpers
│   │   │   └── model.py             # V2: get_user_model() helper
│   │   ├── auth/            # FastAPI-Users config
│   │   ├── config.py        # settings from .env
│   │   ├── database.py      # async session, engine
│   │   ├── main.py          # app init, router registration
│   │   └── worker.py        # Celery app + Beat schedule
│   ├── tests/               # pytest API smoke tests (hit live in-container server)
│   │   ├── conftest.py      # httpx AsyncClient + non-admin user_creds fixtures (with teardown)
│   │   ├── test_api_smoke.py
│   │   ├── test_job_alert.py  # V3: rule-based job-alert classifier + link extraction
│   │   ├── test_job_alert_integration.py  # V3: process_job_alert_email (mocked fetch/score)
│   │   └── test_scanner.py  # V3: scanner feeds_summary breakdown
│   ├── pytest.ini           # asyncio_mode = auto
│   ├── alembic/
│   │   └── versions/        # chain tip: … → v3_activity_log → v3_domain_cv_scores → v3_partial_jd
│   │       ├── initial_migration.py
│   │       ├── v2_feed_system.py              # V2: domain_cv_id on feeds, detected_domain_cv_id on jobs
│   │       ├── a1b2c3d4e5f6_user_profile_fields.py  # users: linkedin_url, phone, current_location, salary_expectation
│   │       ├── b2c3d4e5f6a7_user_feed_actor_name.py # user_feeds.actor_name (Apify actor input matching)
│   │       ├── v3_gmail_job_alerts.py         # V3: job_alert/gmail_alert enums, email_threads + jobs columns
│   │       ├── v3_gmail_alert_prefs.py        # V3: user_preferences job-alert controls
│   │       ├── v3_activity_log.py             # V3: run_logs.details→JSONB + email_alert_logs table
│   │       ├── v3_domain_cv_scores.py         # V3: jobs.s1d + domain_cv_scores (JSONB) + best_domain_cv_id
│   │       └── v3_partial_jd.py               # V3: jobs.has_partial_jd (alert-email snippet flag)
│   └── requirements.txt
├── frontend/
│   └── src/
│       ├── api/             # Axios API clients
│       │   ├── client.js            # axios + auth interceptors
│       │   ├── auth.js              # auth endpoints
│       │   ├── cvs.js               # CV endpoints
│       │   ├── jobs.js              # jobs + tailor endpoints
│       │   ├── feeds.js             # feeds + scanner endpoints
│       │   └── activity.js          # V3: activity dashboard endpoints
│       ├── store/
│       │   ├── auth.js              # Zustand auth store (persisted)
│       │   └── toast.js             # Zustand toast store + helpers
│       ├── components/
│       │   ├── layout/
│       │   │   ├── AppLayout.jsx    # sidebar + Outlet
│       │   │   └── Sidebar.jsx      # nav with HITL badge
│       │   └── ui/
│       │       ├── Button.jsx
│       │       ├── Input.jsx
│       │       ├── Spinner.jsx
│       │       ├── Badge.jsx        # StatusBadge, MarketBadge, SourceBadge
│       │       ├── ScanFeedBreakdown.jsx  # V3: shared per-feed scan breakdown (Activity + Feeds)
│       │       ├── ScorePill.jsx    # ThreeScores (B/T/F)
│       │       └── Toast.jsx        # ToastContainer
│       └── pages/
│           ├── auth/                # Login, Register, ForgotPassword
│           ├── onboarding/          # 4-step wizard
│           ├── dashboard/           # Dashboard (overview + analytics)
│           ├── activity/            # V3: ActivityPage (Job Alerts + System tabs)
│           ├── jobs/                # JobsPage, AddJobModal, JobDetail, TailorPage (full-screen), TailorOverlay (legacy fallback)
│           ├── cvs/                 # CVsPage, MasterCVTab, DomainCVsTab
│           ├── settings/            # SettingsPage + 7 tabs; Feeds&Scanning tab (FeedsTab.jsx) is the single place for ALL feed management (RSS/Apify feeds, Target Companies, Scan History, add/edit modals, Apify Store search, per-feed run)
│           ├── wallet/              # WalletPage
│           └── admin/               # AdminPage (users, errors, stats)
├── docker-compose.yml
├── .env                     # never committed
└── CLAUDE.md                # this file
```

---

## Database Models — Key Fields

### User
- `id`, `email`, `name`, `role` (user/admin), `plan` (default/wallet)
- `is_active`, `is_superuser`, `is_verified`
- `linkedin_url`, `phone`, `current_location`, `salary_expectation`

### UserCredentials (one per user)
- `anthropic_api_key_enc` — AES-256 encrypted
- `apify_token_enc` — AES-256 encrypted
- `gmail_address`, `gmail_app_password_enc`
- `notification_email`

### UserPreferences (one per user)
- `s1_min_threshold` (default 65), `s3_block_threshold` (85), `s3_review_threshold` (90)
- `cl_tone`, `cl_template` (random/hook_first/story_led/problem_solver/concise)
- `ghost_after_days` (28), `auto_mode` (false), `auto_include_cl` (true)
- `preferred_model` — V2: claude-sonnet-4-5 / claude-opus-4-5 / claude-haiku-4-5
- `gmail_poll_interval_minutes` (60)
- `target_roles` (comma-separated string)
- V3 TO ADD: `parse_job_alerts` (bool=True), `job_alert_max_links` (int=10), `job_alert_title_filter` (bool=True)

### MasterCV
- `content_md`, `version`, `word_count`, `is_active`

### DomainCV
- `master_cv_id`, `industry_id`, `function_id`, `country_code`
- `content_md`, `version`, `status` (generating/active/stale/blocked/review_required)
- `s3_domain` (100 at creation), `s3_master` (computed by Claude)

### Job
- `company`, `role`, `location`, `market` (NL/EU/Dubai/SG/IN)
- `source` (manual/url/file/gmail/rss/apify) — V3 adds: gmail_alert
- `status` (new→bookmarked→applied→screening→interview_r1/r2→offer_received→rejected/ghosted)
- `s1` (master fit), `s1d` (best domain CV fit), `s2`, `s3_domain`, `s3_master`
- `domain_cv_scores` (JSONB `{domain_cv_id: score}` — fit vs ALL active domain CVs at ingest)
- `best_domain_cv_id` (FK → domain_cvs; highest-scoring domain CV; drives Tailor pre-select)
- `has_partial_jd` (bool) — JD is only an alert-email snippet (LinkedIn/gated cards); full JD behind `portal_url`
- `needs_hitl` (bool)
- `domain_cv_id` — CV used for tailoring
- `detected_domain_cv_id` — V2: which domain CV feed found this job
- `source_feed_id` — V2: which feed found this job
- `source_email_id` (FK → email_threads.id) — V3: the job-alert email a gmail_alert job came from

### EmailThread
- `job_id`, `direction` (sent/received), `subject`, `body_preview`
- `classification` (auto_confirmation/genuine_recruiter/interview_invite/etc)
- `needs_hitl` (bool)
- V3 TO ADD: `is_job_alert` (bool=False), `jobs_extracted` (int=0), `jobs_saved` (int=0)

### UserFeed
- `feed_type` (rss/apify), `name`, `url_or_actor`, `actor_name`
- `is_active`, `is_platform`, `is_auto_generated`
- `keywords`, `search_keywords` (Claude-generated), `job_boards` (JSON), `location`
- `domain_cv_id` — linked domain CV

---

## Core Business Rules (NEVER CHANGE)

```
CV Tailoring Golden Rule:
✅ Reorder bullets, rephrase verbs, inject keywords, deselect content
❌ NEVER invent experiences, metrics, skills, or companies
❌ NEVER add anything not in master CV

S3 Score Thresholds:
≥ 90  → green  (safe to send)
85-89 → amber  (review before sending)
< 85  → blocked (cannot send)

HITL Rule:
ALL recruiter replies require human approval before responding
NEVER auto-send replies to recruiters

Test Mode:
Default ON — all emails redirect to notification address
Must explicitly set ENV=production to send real emails

Scoring:
S1 = base fit (master CV vs JD) — computed on JD input
S2 = tailored fit (tailored CV vs JD) — computed after Apply
S3 = factual integrity % — computed after Apply
```

---

## API Endpoints Summary

### Auth (`/api/auth/`)
- `POST /login`, `POST /register`, `POST /forgot-password`
- `GET /me`, `PATCH /me/profile`, `GET /me/credentials`, `PUT /me/credentials`
- `GET /me/preferences`, `PATCH /me/preferences`
- `GET /auth/admin/industries`, `GET /auth/admin/functions`
- `GET /auth/admin/error-logs`, `PATCH /auth/admin/error-logs/{id}/resolve`
- `GET /admin/users`, `PATCH /admin/users/{id}/role`, `PATCH /admin/users/{id}/active`

### CVs (`/api/cvs/`)
- `GET /master`, `POST /master/text`, `POST /master/upload`, `PUT /master`
- `GET /master/versions`, `POST /master/rollback/{version}`
- `GET /domains`, `POST /domains/generate-changelog`
- `GET /domains/{id}/changelog`
- `POST /domains/{id}/changelog/{change_id}/approve`
- `POST /domains/{id}/changelog/{change_id}/reject`
- `PUT /domains/{id}/changelog/{change_id}/edit`
- `POST /domains/{id}/changelog/bulk`
- `POST /domains/{id}/apply` — applies changes, computes S3, auto-creates feed profile
- `POST /domains/{id}/regenerate`

### Jobs (`/api/jobs/`)
- `GET /` — params: `status`, `source`, `market`, `needs_hitl`, **`score`** (min effective score =
  `coalesce(s1d, s1)`), **`domain`** (best_domain_cv_id), `search`, `skip`, `limit`. **Returns an
  object** `{jobs: [...], total_count, unfiltered_count}` — `total_count` matches the current filters,
  `unfiltered_count` is all of the user's jobs. (All filters are server-side so counts stay accurate
  beyond the page limit.)
- `GET /stats` — pipeline counts + analytics: `total`, `by_status`, **`needs_hitl`** (boolean-flag
  count, fixed), `by_source`, `by_domain_cv` (by detected feed CV), **`by_best_domain`** (by
  best_domain_cv_id — drives the Domain filter dropdown counts), **`by_score_bucket`**
  (`{any, gte_70, gte_80, gte_90}` on `coalesce(s1d, s1)`), `score_distribution`, `avg_s1`
- `POST /parse/text`, `POST /parse/url`
- `POST /confirm/{temp_id}`
- `GET /{id}`, `PATCH /{id}/status`, `GET /{id}/emails`

### Tailor (`/api/tailor/`)
- `POST /generate`, `GET /{id}/changelog`
- `POST /{id}/changelog/{change_id}/approve|reject`
- `PUT /{id}/changelog/{change_id}/edit`
- `POST /{id}/apply`, `POST /{id}/regenerate-cl`
- `POST /followup/{job_id}`
- `POST /jd-highlights` — V3: cheap JD-only analysis for the Tailor page left panel →
  `{matches, gaps}` (Claude, `extract_jd_highlights`) + `country_rules` (derived from the
  domain CV's `CountryMaster`: phone/photo/DOB/marital removed, relocation note, privacy-law format)

### PDFs (`/api/pdfs/`)
- `GET /master-cv`, `/domain-cv/{id}`, `/tailored-cv/{id}`, `/cover-letter/{id}`

### Gmail (`/api/gmail/`)
- `POST /send-application`, `POST /reply`, `POST /poll`, `POST /test-connection`

### Feeds (`/api/`)
- `GET /feeds`, `POST /feeds`, `PATCH /feeds/{id}`, `POST /feeds/{id}/toggle`, `DELETE /feeds/{id}`
- `POST /feeds/{id}/run` — V3: run ONE feed now (synchronous) → `{jobs_found, jobs_added, duration_seconds}`
- `POST /feeds/suggest` — Claude-generates keywords from domain CV
- `GET /feeds/apify-actors?search=` — live Apify Store search
- `GET /companies`, `POST /companies`, `DELETE /companies/{id}`
- `POST /scanner/run` (all feeds, async Celery), `GET /scanner/status`

### Wallet (`/api/wallet/`)
- `GET /` — balance + transactions

### Activity (`/api/activity/`) — V3, read-only
- `GET /alerts?days=&limit=` — per-email job-alert timeline + saved-job summaries
- `GET /system?days=` — scanner_runs / gmail_polls / ghosted_checks + recent errors

### Admin (`/api/admin/`)
- `GET /stats` — platform stats (admin only, locked behind require_admin)

---

## V2 Changes (June 23, 2026)

**Status: Complete and verified — all 5 smoke tests passing.**

### DB migrations applied
- `v2_feed_system.py`: user_feeds + domain_cv_id/search_keywords/job_boards/is_auto_generated; jobs + detected_domain_cv_id/source_feed_id; user_preferences + preferred_model
- `a1b2c3d4e5f6_user_profile_fields.py`: users + linkedin_url/phone/current_location/salary_expectation
- `b2c3d4e5f6a7_user_feed_actor_name.py`: user_feeds + actor_name

### Key behavior changes
- Domain CV apply → feed profile auto-created with Claude-generated keywords
- Add feed modal is domain-CV-driven: pick CV → Claude generates keywords → editable
- Apify actor picker uses live Apify Store API (not hardcoded), sorted by popularity
- Scanner tags jobs with detected_domain_cv_id + source_feed_id
- Scanner uses actor_name for input-builder matching (not brittle opaque ID)
- All Claude calls respect user.preferred_model
- Toast notifications on all actions
- Settings has 7 tabs including Feeds & Scanning
- Dashboard analytics: S1 distribution, domain CV breakdown, source breakdown
- Admin panel: users, error log, stats (auth locked)
- Profile fields: linkedin_url, phone, current_location, salary_expectation

---

## Feed Config Loaded (June 24, 2026)

Loaded `JobHunt_Feed_Config.xlsx` ("Feeds Setup" sheet) for the owner via a one-shot script
(openpyxl). Created **3 placeholder domain CVs** seeded with the master CV (status=active, NL,
to be refined later): **D2** Supply Chain & Logistics Tech, **D3** eCommerce & Marketplace,
**D4** FinTech & Risk / Quantitative (D1 AI & Data already existed). Inserted **26 feeds**
(`is_platform=false`) associated to their domain CV — **18 active / 8 inactive** per the
sheet's "Enable Now?": D1 8 (6 on), D2 6 (4 on), D3 6 (5 on), D4 6 (3 on); 24 RSS + 2 Apify
LinkedIn (`curious_coder/linkedin-jobs-scraper`, `actor_name` set). Per-domain S1/S1d thresholds
from "Scoring Config" (D1 65 · D2 60 · D3 65 · D4 55) were **recorded but not applied** — the
platform has a single global `s1_min_threshold` (no per-domain support).
**Caveat:** ~12 of the 18 active feeds are **Indeed RSS**, which is dead (404) / rate-limited
(429) — only the Jobicy (×4) and Apify LinkedIn (×2) active feeds will actually return jobs.

---

## Known Issues / Bugs

| Issue | Status | Fix |
|---|---|---|
| PATCH /auth/me/profile drops target_roles when no preferences row | ✅ Fixed | Upsert UserPreferences in update_profile |
| Profile fields never persisted | ✅ Fixed | Added columns + migration + ProfileTab.jsx |
| Backend crashes: NameError Depends not defined in main.py | ✅ Fixed | Added missing imports |
| GET /api/admin/stats had no auth | ✅ Fixed | Locked behind require_admin |
| v2_feed_system migration never applied (orphan root) | ✅ Fixed | Re-parented onto a1b2c3d4e5f6, upgrade head |
| Scanner never set detected_domain_cv_id | ✅ Fixed | Fixed UserFeed import scope in scanner_tasks.py |
| FeedsTab Domain CV profiles section never rendered | ✅ Fixed | Added V2 fields to FeedRead schema |
| Domain CV applied pre-V2 had no feed profile | ✅ Fixed | Backfilled with create_feed_profile_for_domain_cv() |
| get_boards_for_domain() mutated shared constants | ✅ Fixed | Copy list before appending in feed_agents.py |
| jd_agents.parse_and_score_jd NameError on undefined `model` | ✅ Fixed | Added `model` param (V3) — fixes bug + threads user's model |
| Hourly Gmail poll dead — gmail_tasks imported nonexistent _process_inbox_emails | ✅ Fixed | Extracted /poll loop into shared _process_inbox_emails (V3) |
| Jobs Tracker showed no source — SourceBadge imported but never rendered | ✅ Fixed | Added Source column to JobsPage.jsx (V3) |
| Gmail job-alert poll saved 0 jobs — body_html truncated to 5KB hid all links | ✅ Fixed | Raised gmail_mcp HTML cap to 200KB (V3) |
| LinkedIn alert links are login-gated (fetch returns sign-in wall) | ✅ Handled | Option A: extract job cards from email body for gated domains, no fetch (V3) |
| Google "Security alert" misclassified as job alert | ✅ Fixed | SUBJECT_EXCLUSIONS in gmail_alert_agent + guard in gmail.py wiring (V3) |
| Worker Gmail poll crashed: `No module named 'bs4'` (worker image was stale — bs4 in requirements.txt but not in the built worker image) | ✅ Fixed permanently | Rebuilt the worker image (`docker-compose build worker && up -d worker`) → bs4 4.12.3 baked in from requirements.txt; survives container recreation. Verified: 3 tasks register, worker poll runs with `errors: []`. (lxml NOT needed — code uses stdlib `html.parser`) |
| Hourly Gmail poll classification failed: "No Anthropic API key configured" — worker used the unset platform key | ✅ Fixed | gmail_tasks now decrypts the user's own key (fallback to platform), mirroring manual /poll |
| Apify feeds 404 — `run_actor` built `acts/apify/linkedin-jobs-scraper/runs` (slash) | ✅ Fixed | `actor_id.replace('/', '~')` → `acts/apify~…/runs` (Apify's required tilde path form) |
| Indeed RSS feeds dead (ae/sg 404) / rate-limited (nl/in 429) | ✅ Fixed | Disabled the 4 platform Indeed feeds (`is_active=false`); re-enable if Indeed restores RSS |
| Apify platform feeds 404/403 on dead/rental actor slugs | ✅ Fixed (reachable) | Re-pointed via Store search (all PAY_PER_EVENT, not rental → run on free token): LinkedIn=`curious_coder/linkedin-jobs-scraper` (2.6M runs), Google=`johnvc/Google-Jobs-Scraper`. Now **400 Bad Request** = actor reached but input schema differs from our `build_linkedin_input`/`build_google_jobs_input` |
| Apify actors returned 400 / 0 jobs — wrong request body + wrong per-actor fields | ✅ Fixed | **Root cause was `run_actor` wrapping the body as `{"input": …}`** — Apify's `POST /acts/{id}/runs` takes the input as the RAW JSON body, so required fields were nested one level down and EVERY actor 400'd. Fixed the body, then matched each actor's `inputSchema` (fetched from the API): LinkedIn `curious_coder` wants `{urls:[<linkedin search URL>], count, scrapeCompany}`; Google `johnvc` wants `{query, num_results}` (the `location` field — and any location term in the query — returns 0, so location is omitted). Normalisers updated to the actors' real output fields (`companyName`/`link`/`descriptionText`; `company_name`/`source_link`). **Verified: LinkedIn 25 + Google 25 raw_results** (live scan, and re-confirmed June 24 via direct actor calls). Live `inputSchema` confirms required fields: LinkedIn `['urls']`, Google `['query']`. **Caveat:** `count`/`num_results` have a **minimum** — values like 3 → 400; the scanner uses the default **25**, which is valid, so don't set `max_results` below ~10 |
| Scanner/poll Celery tasks crashed intermittently: "Future attached to a different loop" / "Event loop is closed" | ✅ Fixed | Each task creates a new event loop, but the module-level async engine pool stayed bound to the first loop. All 3 task wrappers now `loop.run_until_complete(engine.dispose())` in `finally` before closing the loop |
| Auto-feed "AI & Data Product Leadership — NL" 429'd on nl.indeed RSS | ✅ Fixed | Re-pointed to Jobicy (`jobicy.com/?feed=job_feed&search_keywords=product+manager`) → **raw_results=29** confirmed (the `?feed=job_feed` form works; the old `feed/job_feed?…&search_region=netherlands` form returns ~3) |
| Scanner saved **nothing** — every S1 score came back 0 | ✅ Fixed | `_score_batch` referenced an undefined `model` var → `NameError` caught by the bare `except` → returned `s1_score=0` for all jobs. Added a `model` param (defaults to `settings.anthropic_model`) threaded through `batch_score_s1`. First real end-to-end: scan saved **23/29** jobs with genuine S1 scores |
| `/jobs/stats` `needs_hitl` always 0 — read a non-existent `"hitl"` status | ✅ Fixed | Replaced `counts.get("hitl", 0)` with a real `count(*) WHERE needs_hitl = true`. Also added `by_best_domain` + `by_score_bucket` for the tracker filter-pill counts |
| Jobs Tracker — filter pills/header now show live counts (Option C) | ✅ Added | `GET /jobs` returns `{jobs, total_count, unfiltered_count}` with **all filters server-side** (incl. new `score`/`domain` params); header shows "N total · M matching", each Status/Source/Score pill + Domain dropdown shows its facet count from `/jobs/stats` (zero-count pills greyed, not hidden). Note: this changed the `/jobs` response shape (array → object) — all consumers (JobsPage, AppLayout, Dashboard) updated |
| Tailor + domain-CV flows broken — undefined `model` NameError (and a `model=` TypeError) | ✅ Fixed | All 4 `tailor_agents` functions **and** 3 `cv_agents` (`generate_domain_changelog`, `apply_changes`, `compute_s3_score`) referenced an undefined `model` on `client.messages.create(...)` → `NameError`; cvs.py also passed `model=user_model` to two of them that lacked the param → `TypeError`. Added `model: Optional[str] = None` to all 7 (defaults to `settings.anthropic_model`). Then **threaded `get_user_model()` through the tailor router** (generate / apply×3 incl. `compute_s3_score` / regenerate-cl / followup) so tailoring honours each user's `preferred_model` — matching cvs.py/jobs.py. Verified full flow: generate (6 changes, S2 72) → approve all → apply (S3 92/92 **green**) → CV + cover letter + email all populated |
| Pre-filter wrongly rejected "Senior/Staff/Principal PM" as `not_a_product_role` | ✅ Fixed | Replaced the narrow hardcoded positive list with keyword-driven `pre_filter_jd(jd_text, user_keywords)` + `build_user_keywords(target_roles, feed_keywords)` (Option B). Verified: 29 Jobicy results went from 1→29 passing the pre-filter |
| Every RSS job saved with company="Unknown" | ✅ Fixed | `_parse_title` only read "Role at Company" titles, but Jobicy puts the employer in a namespaced `<job_listing:company>` field. Added `_extract_company` fallback chain (namespaced `company`/`dc:creator`/`author`/`source` → title separator → "About X:" in JD); also reads namespaced `<location>`. Removed `-`/en-dash from title separators (Jobicy roles use '–' internally). Verified: 29 Jobicy jobs → 0 Unknown |
| JD tab always showed "No JD content" for every job | ✅ Fixed | The JD tab reads `job.jd_md \|\| job.jd_raw`, but **`JobRead` never exposed `jd_raw`/`jd_md`** — so they were always undefined. Added `jd_raw`, `jd_md`, `has_partial_jd` to `JobRead`. (Verified: RSS job now returns jd_raw len 11282.) |
| RSS jobs stored only a ~200-char JD snippet | ✅ Fixed | `rss_mcp._rss_item_to_job` used the short `<description>`; the full JD lives in `<content:encoded>`. Now prefers `content:encoded` (HTML-stripped, cap raised 3000→20000). Verified: Jobicy jd_raw avg 210 → **7260** chars. Scanner also HTML-cleans `jd_raw` via BeautifulSoup as a safety net. |
| Scanner crashed mid-scan: "Multiple rows were found when one or none was required" | ✅ Fixed | The dedup + master-CV queries used `scalar_one_or_none()`, which **raises if duplicate `jd_hash` rows already exist** (from a prior scan's within-batch dups) — aborting the whole user's scan. Switched to `.scalars().first()` (scanner + all 3 gmail_alert queries) and added **within-batch dedup** (`seen_hashes`) so duplicate cards in one scan can't both save |
| Gmail event loop error in Celery worker | ✅ Fixed | new_event_loop() in gmail_tasks.py |
| Scanner event loop error | ✅ Fixed | new_event_loop() in scanner_tasks.py |
| Domain CV wizard sending codes not UUIDs | ✅ Fixed | /auth/admin/industries endpoint |
| anthropic proxies TypeError | ✅ Fixed | anthropic>=0.40.0 in requirements.txt |
| MasterCVTab paste button not working | ✅ Fixed | Reordered early return checks |

---

## Pending — Not Yet Started

```
1. ✅ DONE (June 24, 2026) — Merged /feeds page into Settings → Feeds & Scanning tab.
   FeedsPage.jsx deleted; its full functionality (RSS/Apify feeds add/edit/delete/toggle,
   Target Companies, expandable Scan History breakdown, per-feed Run, Add/Edit modals with
   domain-CV-driven keywords + Apify Store search) now lives in settings/FeedsTab.jsx.
   /feeds route + sidebar nav item removed; Dashboard "Manage feeds →" → /settings#feeds
   (SettingsPage reads the #feeds hash and widens to max-w-5xl for that tab).

2. Verify scanner correctly uses actor_name for all actor types
   (column added in b2c3d4e5f6a7 but end-to-end scan not yet confirmed)
```

---

## V3 Complete

### Gmail Job Alert Parser — ✅ COMPLETE (June 23, 2026), all 17 smoke tests passing

**What it does:** the hourly Gmail poll detects job-alert digest emails (LinkedIn,
Indeed, company careers) **rule-based — no Claude call**, extracts careers links,
cheaply pre-filters by page title (Playwright title only, ~60% fewer full fetches),
then full-fetches + parses + S1-scores matching jobs and saves them with
`source=gmail_alert`, `source_email_id` (link back to the alert), and a best-match
`detected_domain_cv_id`.

**New files**
- `backend/app/agents/gmail_alert_agent.py` — `is_job_alert_email`, `extract_job_links`,
  `check_title_relevance`, `process_job_alert_email`
- `backend/tests/test_job_alert.py` — 5 unit tests (rule-based classifier + link extraction)

**Migrations** (chain tip is now `v3_gmail_alert_prefs`)
- `v3_gmail_job_alerts.py` — `emailclassification`+`job_alert`, `jobsource`+`gmail_alert`;
  `email_threads` +`is_job_alert`/`jobs_extracted`/`jobs_saved` and `job_id`→nullable
  (alert digests aren't tied to one job); `jobs.source_email_id` (FK→email_threads)
- `v3_gmail_alert_prefs.py` — `user_preferences` +`parse_job_alerts`/`job_alert_max_links`/`job_alert_title_filter`

**Model / schema**
- `job.py`: `JobSource`+`gmail_alert`, `EmailClassification`+`job_alert`, EmailThread
  job-alert columns, `Job.source_email_id`. Two FK paths now exist between jobs↔email_threads,
  so `foreign_keys="EmailThread.job_id"` is pinned on both sides of that relationship.
- `JobSummary` +`detected_domain_cv_id` (tracker Domain column now populates via frontend map)
- `PreferencesUpdate` + `GET /me/preferences` expose the 3 new prefs

**Wiring** (`routers/gmail.py`)
- Extracted the poll loop into shared `_process_inbox_emails` — this also **fixed a
  pre-existing broken import**: `gmail_tasks.py` called `_process_inbox_emails`, which
  never existed, so the hourly Gmail poll was dead. Alerts are peeled off rule-based
  (no Claude) → `process_job_alert_email`; the rest go through the existing Claude
  classify + match/HITL flow. `/poll` is now a thin wrapper.

**Frontend**
- Settings → Gmail tab (`GmailTab.jsx`): "Parse job alert emails" toggle + Min S1 /
  Max links / Pre-filter-by-title controls
- Jobs Tracker (`JobsPage.jsx`): added the **Source column** — `SourceBadge` was imported
  but never rendered. `gmail_alert` shows **📧 Alert** (blue) via `Badge.jsx` `SOURCE_CONFIG`

**Bug fixes found along the way**
- `jd_agents.parse_and_score_jd` referenced an undefined `model` (NameError on every call)
  — added a `model` param (fixes the bug + threads the user's model through)
- `gmail_tasks` hourly poll was broken (missing `_process_inbox_emails`) — now fixed
- `gmail_mcp` truncated email `body_html` to **5 KB** — job-alert digests put their links
  ~150 KB in, so 0 links were ever extracted. Raised the HTML cap to **200 KB** (in-memory
  only; just body_preview is persisted). This was the root cause of the first live poll
  saving 0 jobs.

**Live-poll findings + Option A (parse email body directly)**
A real poll of the owner's inbox (22 emails) surfaced two realities:
1. After the 5 KB→200 KB fix, LinkedIn alerts yield ~10 links each — but they're
   `linkedin.com/comm/jobs/view/…` links that are **login-gated**: Playwright sees a "Sign in"
   title and an httpx fetch returns a sign-in wall (verified). So fetch-based parsing can't
   work for LinkedIn/Indeed/Naukri.
2. **Option A chosen** — for gated domains (`GATED_DOMAINS`), `process_job_alert_email` now
   reads structured job cards **straight from the email HTML** via
   `extract_jobs_from_email_body()` (parses each `/jobs/view/` link's separate text segments:
   role, "Company · Location", dropping noise like "Actively recruiting"), then does a
   **lightweight S1 pre-score** (`batch_score_s1` on title+company+location+snippet — no fetch,
   no Playwright) and saves jobs ≥ threshold. Public ATS links (greenhouse/lever/workday/
   careers) still use the Playwright title pre-filter + full fetch + parse/score path.
   Validated against real LinkedIn emails: clean role/company/location extraction.
3. **LinkedIn email body parsing (June 24 2026).** `extract_jobs_from_linkedin_email()` is a
   LinkedIn-focused wrapper over `extract_jobs_from_email_body` (filters to `linkedin.com`
   `/jobs/view/<id>` cards). `_is_linkedin_alert(sender)` (`linkedin.com` in sender) forces the
   email-body card path for any LinkedIn-sent alert even if link detection is conservative;
   SENDER/SUBJECT signals extended (`jobs-noreply@linkedin`, `jobalerts@linkedin`, `new jobs for`,
   `your search`). Email-extracted (gated) jobs are saved with **`has_partial_jd=True`**, real
   `company`/`role`/`location` from the card, and `portal_url` = the LinkedIn job URL — the JD is
   only the snippet, so the user opens `portal_url` for the full description before tailoring. The
   Jobs Tracker shows an amber **"Partial JD"** badge (tooltip points to the portal URL) for these.
   These jobs flow through the **same multi-domain S1/S1d scoring** as everything else.
- Also: `SUBJECT_EXCLUSIONS` (e.g. "security alert", "password", "verify your") hard-exclude
  non-job emails from both the rule-based and Claude-routed alert paths (fixes the Google
  "Security alert" false positive).
- Caveat: the IMAP poll fetches `(RFC822)` which **marks emails read** and searches `UNSEEN`
  only — each email is processed once; the fix applies to future/unread alerts.

**Test coverage (17 total):** rule-based classifier, link extraction, **email-body card
extraction**, and **subject exclusion** (`test_job_alert.py`); plus `process_job_alert_email`
orchestration with fetch/score mocked (`test_job_alert_integration.py`).
**NOT tested:** `check_title_relevance` (live Playwright) and a true live end-to-end.

---

### Activity Dashboard — ✅ COMPLETE (June 23, 2026)

Read-only `/activity` page (nav item between Dashboard and Jobs) with two tabs.

**DB** (`v3_activity_log` migration): `run_logs.details` Text→**JSONB**; new
**`email_alert_logs`** table (per-email parser record: links_found/gated/public/
below_threshold/duplicate, jobs_saved, saved_job_ids, skip_reasons, poll_run_id→run_logs).

**Backend** — `routers/activity.py` (registered at `/api/activity`):
- `GET /api/activity/alerts?days=&limit=` — per-email job-alert timeline + saved-job summaries
- `GET /api/activity/system?days=` — scanner_runs / gmail_polls / ghosted_checks RunLogs +
  error_count + recent_errors
- `process_job_alert_email` now writes an `EmailAlertLog` per email (instrumented gated +
  public paths with per-link `skip_reasons`); `gmail_tasks` creates a `gmail_poll` RunLog per
  user-poll and threads `poll_run_id` down; `scanner_tasks` writes a **rich per-feed breakdown**
  to `run_log.details` = `{feeds_run, feeds_summary: [{feed_name, feed_type, raw_results,
  pre_filter_passed, pre_filter_failed, s1_scored, above_threshold, duplicates, saved,
  rejected: [{title, company, s1, reason}], note}]}`. **Behavior change:** the scanner now
  **only saves jobs that score ≥ s1_min_threshold** (was: saved all non-dup) — low-S1 jobs go
  to `rejected` as `below_threshold`, which is why the breakdown distinguishes
  `above_threshold` from `saved`.

- **Pre-filter is keyword-driven (Option B), not a hardcoded role list.** `pre_filter_jd(jd_text,
  user_keywords)` returns `{passed, reason_code}` with this order: (1) `< 100` chars → `too_short`;
  (2) job title (first 200 chars) contains ANY of the user's keywords → **PASS**; (3) title hits a
  `SKIP_WORDS` entry (software/data engineer, devops, designer, nurse, driver, recruiter, …) →
  `not_a_product_role`; (4) otherwise **PASS** (permissive — let S1 decide). The keyword list comes
  from `build_user_keywords(target_roles, feed_keywords)` = the user's `prefs.target_roles` +
  2-word phrases mined from their active feeds' `search_keywords` + a `PRODUCT_FALLBACK_KEYWORDS`
  baseline. This replaced the old narrow positive list that wrongly rejected "Senior/Staff/Principal
  PM" as `not_a_product_role`. Both callers (`scanner_tasks`, manual `/jobs/parse` in `routers/jobs.py`)
  pass `user_keywords`. (`TARGET_TITLE_KEYWORDS` is retained — still used by `gmail_alert_agent`.)
  **Per-feed keywords:** the scanner builds a *separate* keyword set per feed
  (`feed_keywords_map[fid] = build_user_keywords(target_roles, [feed.search_keywords])`) and
  pre-filters each job with its own feed's keywords — not one combined pool across all feeds.

- **Multi-domain-CV scoring (design decision, June 24 2026). Every ingested job is scored
  against the master CV AND ALL of the user's active domain CVs — both ingestion paths
  (weekly scanner + Gmail Alert Parser) behave identically.**
  - **S1** = base fit vs the **master CV** — universal baseline, on every job.
  - **`domain_cv_scores`** = `{domain_cv_id: score}` — the job scored against **every** active
    domain CV (`status=active`, `content_md != NULL`), each a `batch_score_s1` pass against that
    CV's content. Token cost: **N jobs × M domain CVs** scoring calls (each batched 5 jobs/call).
  - **`best_domain_cv_id`** = the highest-scoring domain CV. **`s1d`** = that best score.
  - **Decision score (both paths):** gate on **`s1d` (best domain CV) when domain CVs exist, else S1**
    (`decision = s1d if domain_cvs else s1; save if decision ≥ s1_min_threshold`).
  - **Where it lives:**
    - Scanner (`scanner_tasks.py` §4b): loads all active domain CVs (+ `Industry × Country` labels),
      scores all new jobs against each, stores `s1 / s1d / domain_cv_scores / best_domain_cv_id` on
      the Job; per-job funnel logged in `run_log.details…saved_examples[]`/`rejected[]`
      (`{s1, s1d, domain_scores(labelled), best_domain_cv, decision}`). `detected_domain_cv_id`
      (feed attribution) is kept separate.
    - Gmail (`gmail_alert_agent.py`): `_load_domain_cvs_full()` + `_score_jobs_vs_domain_cvs()` +
      `_best_domain()` applied in both the gated card path and the public fetch+parse path; same
      fields stored, `s1d/domain_scores/decision` logged in `EmailAlertLog.skip_reasons[]`.
  - **DB:** `jobs.s1d` (float), `jobs.domain_cv_scores` (JSONB), `jobs.best_domain_cv_id`
    (UUID FK→domain_cvs, indexed) — migration `v3_domain_cv_scores`.
  - **API:** `JobSummary` + `JobRead` expose `s1d / domain_cv_scores / best_domain_cv_id`; the
    `GET /api/jobs` list also enriches `domain_cv_labels` (`{id: "Industry × Country"}`).
  - **Frontend:** Jobs Tracker has a **Best Fit** column (best label + `s1d` pill, `▼` popover of all
    domain CV scores with bars, best row emerald); clickable column **sort** (asc→desc→unsorted, default
    Added DESC) + **Source/Score/Domain filters** persisted in URL params. Tailor overlay Step 1
    **pre-selects `best_domain_cv_id`**, sorts options by this job's fit, shows a `Fit` pill + `best fit`
    badge per option.
  - **Validated useful:** on 29 Jobicy jobs vs the AI & Data domain CV, S1d re-ranked vs S1 — AI/data
    roles boosted (Data PM 82→88), generic demoted (Activation PM 78→68), flipping decisions at the 65
    threshold ("Senior PM, Customer Integrations" 58→**65** saved; "Eng Manager – Growth Product" 65→**58**
    rejected). Gmail verified with mocks (2 domain CVs): a job with S1=55 / domain scores {AI:80, eComm:70}
    is **saved on the best (AI=80)**, all scores stored, best = max.

**Frontend** — `pages/activity/ActivityPage.jsx` (+ `api/activity.js`): Job Alerts tab
(summary bar, expandable timeline with per-link breakdown + saved/gated/below-threshold/
duplicate states) and System tab (scanner cards expand to the per-feed breakdown —
`raw → pre-filter pass → above S1 → saved` + rejected list + notes, via shared
`components/ui/ScanFeedBreakdown.jsx`; poll cards; recent errors w/ resolve). The System tab's
**Weekly Scanner / Gmail Polls / Ghosted Check** are **collapsible accordions** (default
collapsed; header shows `N runs · last: <date> · <status>`). The /feeds **Scan History** rows
expand inline to the same breakdown (`/scanner/status` now returns `details`). The ghosted-check
Celery task now writes a `ghost_check` RunLog so the section populates.
Auto-refresh 60s; empty states; mobile-friendly stacked cards.

**Manual "Run now" controls (V3):** full manual control at every level —
- Job Alerts tab: **"Poll Gmail now"** button (POST /gmail/poll → refresh after 10s)
- System tab: per Gmail-poll card **"Poll now"**, per Scanner card **"Scan now"** (refresh after 5s)
- Feeds page: per-feed **"Run"** button (POST /feeds/{id}/run → toast "X found, Y added")
- (existing) Feeds page **"Run scan now"** runs all feeds via Celery

**Smoke tests:** activity endpoints + scanner feeds_summary (17 total now).

---

### Full-screen Tailor page — ✅ COMPLETE (June 24, 2026)

Replaced the 3-step `TailorOverlay` modal with a full-screen **3-column** experience at
`/jobs/:jobId/tailor` (`pages/jobs/TailorPage.jsx`, routed OUTSIDE `AppLayout` for max space;
the "Tailor →" buttons in JobsPage + JobDetail now `navigate()` there instead of opening the
overlay — `TailorOverlay.jsx` kept as a legacy fallback).

- **Left (280px):** job context (company/role, market, B·Best·T·F scores) · domain CV used
  (label, S3, status, version, fit, "Change domain CV" picker sorted by fit) · **JD Highlights**
  (`POST /tailor/jd-highlights` → Claude matches ✓ / gaps ○) · **Country rules applied**
  (derived from `CountryMaster`).
- **Middle (flex):** "Change log · N changes · M pending" + golden-rule subtext · Approve all /
  Reject all · per-change cards (type badge, strikethrough original → proposed, approve/reject/
  inline-edit) · sticky bottom "N approved · M rejected · P pending" + **⚡ Generate tailored CV +
  cover letter** (enabled once all changes reviewed → `POST /tailor/{id}/apply`).
- **Right (400px):** tabs **Tailored CV** (S2/S3 pills, PDF) · **Cover Letter** (regenerate, PDF) ·
  **Email Draft** (editable subject + body) · sticky send bar (S3 status, status-after-send select,
  include-CL toggle, recruiter email, **Send application** / Save draft).
- **Flow:** on load → GET job + domain CVs → auto-select `best_domain_cv_id` → generate changelog +
  JD highlights (re-runs when the domain CV is changed); apply → previews; send → `gmail/send-application`
  + status update → back to /jobs.
- New `extract_jd_highlights(jd_text)` in `tailor_agents.py` (cheap JD-only call, no CV).

---

## V3 Backlog

### 1. Gmail Job Alert Parser — ✅ COMPLETE (June 23, 2026)

Built and shipped across all 9 build-order steps — see the **"V3 Complete"**
section above for the full summary. 17/17 smoke tests passing.

---

### 2. Razorpay Wallet Top-up
- Add Razorpay SDK to requirements.txt
- `POST /api/wallet/create-order` — create Razorpay order
- `POST /api/wallet/verify-payment` — verify + credit wallet
- WalletPage.jsx: Top up button → Razorpay checkout modal
- Test with Razorpay test mode keys

### 3. S3 File Storage Migration
- Add boto3 to requirements.txt
- Add AWS_ACCESS_KEY, AWS_SECRET_KEY, S3_BUCKET to .env
- Update storage.py: save_text_file / save_binary_file → S3
- Update pdf_generator.py: return S3 URLs not local paths
- Migration: update existing file_path values to S3 URLs
- Keep local fallback for development

### 4. Production Deployment
- Add nginx reverse proxy config
- SSL termination (Let's Encrypt)
- Environment-specific docker-compose.prod.yml
- Health check endpoints
- Backup strategy for PostgreSQL
- Secrets management (not in .env)

### 5. Medium Priority
- ✅ DONE — Merge /feeds page into Settings → Feeds & Scanning tab (June 24, 2026)
- "View changes" blink after domain CV generation
- Auto-open changelog when generation finishes
- Admin: seed data editor (industry verticals, job boards)
- Admin: usage stats per user (tokens, scans, applications)
- Multi-user isolation testing
- Rate limiting per user

### 6. Low Priority
- Interview prep module
- Salary negotiation assistant
- Mobile app (iOS/Android)
- Google Sheets export of job tracker

---

## Environment Variables (.env)

```env
# LLM
ANTHROPIC_API_KEY=           # platform fallback key (optional)
ANTHROPIC_MODEL=claude-sonnet-4-5

# Database
DATABASE_URL=postgresql+asyncpg://jobhunt:jobhunt@db:5432/jobhunt

# Redis
REDIS_URL=redis://redis:6379/0

# Security
SECRET_KEY=                  # JWT secret
ENCRYPTION_KEY=              # AES-256 key for storing API keys

# Gmail
GMAIL_ADDRESS=
GMAIL_APP_PASSWORD=

# Apify
APIFY_TOKEN=                 # platform fallback token (optional)

# App config
ENV=test                     # test | production
SCORE_THRESHOLD=65
S3_BLOCK_THRESHOLD=85
S3_REVIEW_THRESHOLD=90
GHOSTED_DAYS=28
```

---

## How to Start a New Claude.ai Session

Paste this at the start:

```
I'm building JobHunt — an AI-powered job search platform.
Here is the current project state: [paste CLAUDE.md contents]

V1 and V2 are complete. Claude Code is connected in VS Code.
Starting V3 now. V3 priority order:
1. Gmail Job Alert Parser (fully designed — see spec in CLAUDE.md)
2. Razorpay wallet top-up
3. S3 storage migration
4. Production deployment

Project root: D:\JobHunt
```

---

*Last updated: June 24, 2026 — V3 Multi-domain-CV scoring; Apify feeds fixed; LinkedIn alert-email parsing + has_partial_jd; JD storage fix; full-screen 3-column Tailor page; Jobs Tracker filter counts (Option C); /feeds page merged into Settings → Feeds & Scanning; GitHub repo + Pages docs site live. All 25 smoke tests passing*
