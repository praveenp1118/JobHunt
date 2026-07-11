# JobHunt — Project State Document

> This file is the single source of truth for the JobHunt codebase.
> Update this file whenever Claude Code makes changes.
> Share this file at the start of every new Claude.ai session.

---

## Project Overview

AI-powered job search platform for senior product leaders (Head of Product, VP Product, CPO, AI Product Lead).
Target markets: Netherlands/EU (primary), Dubai, Singapore, India (backup). Multi-user capable.

**Public brand: AIJobsHunt — LIVE at https://aijobshunt.com** (Docker + Caddy auto-HTTPS; verified 200,
`www`→apex 301). The **codebase, repo, Docker services, and DB stay named `jobhunt`** — "AIJobsHunt" is the
product/domain brand only (used across the landing page, README, and the GitHub Pages docs). Runs locally for
dev and in production via `docker-compose.prod.yml` + `Caddyfile`.

**Owner:** Praveen Prakash  
**Admin email:** praveenp.1118@gmail.com  
**Project root:** `D:\JobHunt`  
**Live site:** https://aijobshunt.com (production)  
**GitHub:** https://github.com/praveenp1118/JobHunt (public)  
**Docs:** https://praveenp1118.github.io/JobHunt — GitHub Pages, served from `/docs` on `main`  
*(Repo is **public** (as of June 24, 2026). `docs/`: `index.html` landing page +
`architecture.html` / `features.html` / `api.html` — thin pages that render the matching `*.md` source
via marked.js with shared `doc.css` + `doc.js` (consistent Tailwind styling). `.nojekyll` keeps it
pure-static — no Jekyll.)*  
**Last major build:** Cost-optimization sweep + docs refresh (June 27, 2026) — hybrid-RAG scoring (3-stage,
~82% cheaper) + tiered models across ALL Claude calls (email classification rules-first→Haiku, JD highlights
Haiku+cached, feed keywords Haiku, career insights essence), Email-to-JobHunt, auto-detected applications,
night-batch scoring. **All 114 smoke tests passing.** Platform is feature-complete for launch.
(prior majors: CV Templates, Governance/GDPR, Career Insights, Community, Stripe, Support Chat,
Multi-domain-CV scoring, Activity Dashboard, Gmail Job Alert Parser)

---

## Claude Code Configuration

Rules and commands live in the `.claude/` folder. Claude Code auto-loads rules when editing
relevant files.

### Rules (auto-applied):
- `security.md` — user_id filters, key safety, prompt injection protection
- `testing.md` — test requirements, naming
- `api-conventions.md` — endpoint patterns
- `cost-optimization.md` — model selection, caching, RAG pipeline
- `db-conventions.md` — migrations, query patterns
- `frontend-conventions.md` — components, styling

### Commands (slash commands):
- `/project:test` — run full test suite
- `/project:backfill` — run score backfill
- `/project:scan` — trigger manual scan
- `/project:logs` — show service logs

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

## Deployment (Production)

Production runs the **same 6 services** as dev plus a **Caddy** reverse proxy that terminates TLS
(automatic HTTPS via Let's Encrypt) — domain **aijobshunt.com** (+ www → apex redirect). Artifacts:

- `docker-compose.prod.yml` — prod topology (built images, no `--reload`, no source bind-mounts).
- `Caddyfile` — TLS + same-origin routing.
- `frontend/Dockerfile.prod` — multi-stage: `node:20` build (`npm ci && npm run build`) → `nginx:alpine` static serve.
- `frontend/nginx.conf` — SPA server on :80 (`try_files … /index.html`, gzip, immutable cache on hashed assets, no-cache on index.html).
- `.env.production.example` — full env template (copy → `.env.production`, which is **gitignored**).

### Prod architecture
```
Internet ──443/80──▶ Caddy (jobhunt_caddy, auto-HTTPS)
                       ├── /api/*  ──▶ backend:8000   (FastAPI)
                       └── else    ──▶ frontend:80    (nginx static Vite build)
   backend / worker / beat ──▶ db:5432 (pgdata vol) · redis:6379 (appendonly)
```
- **Same-origin:** the SPA calls the relative path `/api` (axios `baseURL:'/api'`), Caddy routes `/api/*`
  to the backend and everything else to the static frontend. No CORS preflight in prod; CORS is still
  pinned to `FRONTEND_URL` (`https://aijobshunt.com`) as defence-in-depth.
- **Only Caddy publishes host ports (80/443).** db/redis/backend/frontend have **no** host port mappings —
  they talk over the internal Docker network only.
- **Persistence:** named volumes `pgdata` (Postgres), `redis_data` (AOF), `cv_storage` (PDFs, on backend +
  worker), `caddy_data` + `caddy_config` (certs/state).
- **`ENV` stays `test` by default** — outbound application/HITL email is redirected to `NOTIFICATION_EMAIL`.
  Set `ENV=production` **only** after verifying real recruiter email sending is intended.

### Two-phase deploy runbook
On the server (Docker + Compose installed, DNS A-records for `aijobshunt.com` + `www` → the host, ports 80/443 open):

```bash
# Phase 1 — configure + build + start (Caddy fetches TLS certs automatically)
cp .env.production.example .env.production      # then fill in real secrets
#   SECRET_KEY:  openssl rand -hex 32
#   FERNET_KEY:  python -c "from cryptography.fernet import Fernet;print(Fernet.generate_key().decode())"
docker-compose -f docker-compose.prod.yml --env-file .env.production up -d --build

# Phase 2 — apply DB migrations (once the backend/db are up)
docker-compose -f docker-compose.prod.yml --env-file .env.production exec backend alembic upgrade head

# Verify
docker-compose -f docker-compose.prod.yml ps          # all Up; caddy healthy
docker-compose -f docker-compose.prod.yml logs caddy --tail 30   # cert issuance
curl -I https://aijobshunt.com                        # 200 + valid TLS
```
Redeploy after a code change: `git pull` → `up -d --build` → `alembic upgrade head` (if migrations changed).
**Note:** `--env-file .env.production` is required so compose resolves `${POSTGRES_*}` interpolation (and each
service also loads it via `env_file:`). The Stripe webhook endpoint is `https://aijobshunt.com/api/billing/webhook`.

---

## Access Model — Invite-or-Pay (migration `v3_invite_or_pay`)

**Registration is open, but a new account is INERT** — it can log in and browse read-only views, but
**every Claude-calling (paid) feature returns 402** until the account is **entitled**. Entitlement comes
two ways, both reusing the **existing Stripe columns** (`users.subscription_status` / `subscription_end`
— NOT duplicated) plus `users.entitlement_source` (`'invite'` | `'stripe'` | NULL):
- **Invite** — redeem a single-use key → `subscription_status='active'`, `subscription_end=now+grants_days`
  (default 30), `entitlement_source='invite'`.
- **Stripe** — subscribe (unchanged) → `entitlement_source='stripe'`, `subscription_end` kept fresh by the webhook.

### The gate is now expiry-aware
`utils/subscription.py::is_entitled(user)` = **admin OR (`status=='active'` AND `subscription_end` not in the
past)**. This is how an invited user's free period ends **with no background job** — there's no Stripe webhook
to flip an invite's status, so the past-`subscription_end` check alone lapses them → 402. `require_active_subscription`
raises **402 `{code:"entitlement_required"}`** (renamed from `subscription_required`). Admins always bypass.

### Closed the token-spend gap (jobs.py was ungated)
The gate was previously hand-applied to only 7 endpoints and **all of `jobs.py` was missed** — parsing/scoring
(real Claude calls) were reachable un-entitled. Now **every Claude-reachable route is gated**:
- **jobs.py:** `parse/text`, `parse/url`, `parse/file`, `score-now`, `score-pending`, `backfill-scores`,
  `fetch-jd`, `add-full-jd`, `score-s1`.
- **cvs.py:** `master/upload` (Claude file→markdown), `master/recompute-essence`, `domains/{id}/recompute-essence`
  (`generate-changelog` + `domains/{id}/apply` already gated). Free saves (`master/text`, `master` PUT, rollback)
  stay ungated but their **optional essence call skips for un-entitled users** (`is_entitled` guard in
  `_compute_master_essence`/`_compute_domain_essence`) — zero tokens for inert users.
- **tailor.py:** `jd-highlights`, `trim`, `regenerate-cl`, `followup` (`generate` + `apply` already gated).
- **feeds.py:** `feeds/suggest`, `feeds/{id}/run` (`scanner/run` already gated).
- **career.py:** `analyse`; **gmail.py:** `poll`, `send-application` (already gated).
- **Background tasks:** the scheduled `weekly_job_scan` + hourly `poll_gmail_all_users` per-user loops now
  **skip un-entitled users** (they call Claude on the platform's schedule).
- **Deliberately ungated (genuinely free):** all GET reads/list/detail, auth, billing, `jobs/confirm`,
  `jobs/{id}/status`, PDF generation (Playwright only, no Claude), chat (rule-based FAQ), scoring config.
- Routers are all **mixed** (free reads + paid routes), so gating is **per-route** `dependencies=[Depends(
  require_active_subscription)]` (no fully-paid router to gate wholesale).

### Endpoints (`routers/access.py`, mounted at `/api`)
- **`POST /invites/redeem` `{code}`** — atomic + race-safe (`SELECT … FOR UPDATE` locks the key row so two
  users racing one code can't both win), idempotent for the same user re-submitting their own key. Invalid if
  redeemed OR revoked OR past `key_expires_at`.
- **Admin:** `POST /admin/invites` (generate N, `grants_days`, optional `key_expires_at`; codes `JH-XXXX-XXXX`
  from a crypto-random unambiguous alphabet, collision-checked), `GET /admin/invites` (status =
  unredeemed/redeemed/revoked/expired), `POST /admin/invites/{id}/revoke`, `PATCH /admin/invites/{id}/extend`.
- **Extension requests (invited-lapsed users):** `POST /extension-requests` saves a pending row **(in-app queue
  is the source of truth)** then **best-effort** emails the admin via platform SMTP — **swallows** SMTP failure
  (logs a warning) so the request always saves. `GET /extension-requests` (own). Admin: `GET /admin/extension-requests`
  (+ `pending_count` nav badge), `POST /admin/extension-requests/{id}/grant` (+N days, default 30) / `/deny`.
  Admin comp/grace tool: `PATCH /admin/users/{id}/extend-subscription` (extend ANY user directly).

### Frontend
- **Onboarding Subscribe step:** an **"Enter invitation key"** input (`JH-XXXX-XXXX`) → `/invites/redeem`; on
  success the step shows the entitled state. Stripe path kept; **Skip for now** remains (browse-only, paid → 402).
- **AppLayout banner:** invite-lapsed / near-lapse (≤5 days) users see **"Request extension"** (→ `POST
  /extension-requests`) **only** when `entitlement_source==='invite'` — never for Stripe users. `GET
  /billing/subscription` now returns `entitlement_source` + an **expiry-aware `is_active`**.
- **Admin panel:** **Invites tab** (generate + copy-to-clipboard, status list, revoke, extend deadline) and
  **Extension Requests tab** (pending queue, grant/deny) with a **pending-count badge** on the tab.
- `UserRead` now exposes `subscription_status`/`subscription_plan`/`subscription_end`/`entitlement_source`.

---

## Public Landing Page (`/`) — "AIJobsHunt"

The logged-out marketing site rendered at **`/`** (React/Vite, not the old `/`→`/dashboard` redirect).
Brand **AIJobsHunt**, logo monogram **JH**, emerald `#059669` + navy `#0b1220`; fonts Space Grotesk
(display) / Inter (body) / JetBrains Mono (metrics). Built from a static HTML prototype
(`frontend/aijobshunt-landing.html`, kept for reference).

- **Files:** `frontend/src/pages/landing/LandingPage.jsx` (all sections + animated score rings, staggered
  auto-rotating panels, persona rotator, FAQ accordion, pre-login canned-FAQ chat, mobile hamburger) +
  `landing.css` (**every rule scoped under `.aijh`** so none of it leaks into the app — Vite bundles CSS
  globally; keyframes are `aijh-*`). `frontend/src/lib/analytics.js` = GA4 loader (**reads `VITE_GA_ID`
  from env — never hardcoded**; no-op if unset) + `trackEvent()` (hooked on every CTA:
  nav/hero/pricing/finale/footer/chat).
- **Routing** (`App.jsx`): `/` → `LandingRoute` (logged-out → landing; **authenticated → `/dashboard`**),
  lazy-loaded as its own chunk (48 kB / 12 kB gz JS + 32 kB / 6.5 kB gz CSS — never bloats the app bundle).
  Added **`/signup`** as a public alias of `/register`. The app's global support `ChatWidget` is suppressed
  on `/` (landing ships its own).
- **Wiring (real, not stubs):** Get access/Subscribe → `/register`; Log in → `/login`; invite **Redeem**
  stashes the key in `sessionStorage.pendingInviteKey` then routes to `/register` — **Onboarding prefills
  the invite input from it**. (Stripe checkout + `/invites/redeem` both require auth, so the logged-out
  entry point is signup → onboarding, where the existing Subscribe step handles both paths.)
- **Responsive** (mobile-first, ≤1120px cap): nav links ≥940px else hamburger slide-in (Esc/scrim/link
  close); hero `100dvh`; How-it-works 5 steps → horizontal snap-scroll on phone; all 2-col grids stack;
  Gmail funnel horizontal→vertical on mobile; chat panel near-full-width on phones; touch targets ≥44px.
  Honors `prefers-reduced-motion` and **pauses rotators/personas off-screen** (IntersectionObserver).
  **Verified via headless Chromium (Playwright) at 375/768/1440: 0 console errors, 0 page errors, 0px
  horizontal overflow, nav↔hamburger swap correct.**

### SEO (Option 1 — static tags now; prerender = fast-follow)
- **`index.html` head** (crawler-visible): title *"AIJobsHunt — AI CV tailoring & ATS scoring, without
  inventing a thing"*, meta description, `canonical=https://aijobshunt.com/`, robots, theme-color, full
  **Open Graph** + **Twitter** (`summary_large_image`, image `…/og-image.png` 1200×630), and two
  **JSON-LD** blocks (`SoftwareApplication` w/ `offers` ₹500 INR "platform fee, BYOK AI at cost" +
  `Organization`). Fonts use **preconnect + preload** (self-hosting is the follow-up). GA is injected by
  the env-driven util, so no Measurement ID sits in static HTML.
- **Semantic HTML:** single `<h1>` (hero), `<h2>` per section (two mention **ATS**/**Pursuit**/
  **tailoring**), `<nav>/<main>/<footer>`, `aria-label`s, `aria-expanded` on hamburger/FAQ.
- **Static files** in `frontend/public/` (Vite copies to build root; nginx `try_files` serves them — **no
  Caddyfile change needed**): `robots.txt` (→ sitemap), `sitemap.xml` (just `/`), `manifest.json`,
  `favicon.svg` (JH monogram). `index.html` links `apple-touch-icon.png` + manifest.
- **Icons + share image — all generated** in `frontend/public/` (rendered from the JH mark / the
  `aijobshunt-og-image.html` template via headless Chromium): `og-image.png` (1200×630),
  `apple-touch-icon.png` (180×180), `icon-192.png`, `icon-512.png` — every referenced icon/asset path
  resolves (verified: no 404s, all copied into `dist/`). The four "See it" panels are faithful CSS/SVG mocks
  — a `TODO(screenshots)` comment in `LandingPage.jsx` marks where to swap in real product `<img>`s. (The OG
  *generator* HTML lives in `frontend/` root, NOT in `public/`, so it never ships to prod.)
- **Analytics wiring:** `VITE_GA_ID` (GA4 Measurement ID) is read at BUILD time. Dev → `frontend/.env` (see
  the committed `frontend/.env.example`); prod → `.env.production` → **docker-compose `build.args`** →
  `Dockerfile.prod` `ARG/ENV VITE_GA_ID` → embedded in the bundle. Unset = analytics disabled. Changing it
  needs a rebuild (`up -d --build`), not a restart.
- **Prerender fast-follow (NOT yet wired):** add `react-snap` (or `vite-plugin-prerender`) with
  `include:['/']`, `crawl:false`, and switch `main.jsx` to `hydrateRoot` for prerendered routes — kept OUT
  of the default `npm run build` so the prod image build can't break; the SPA stays SPA. Lighthouse SEO/a11y
  are already high from the static head + semantic markup (headless Chrome runs the JS).
- **Gotcha fixed — Tailwind `.ring` collision:** the mock's dual score rings must use the class
  **`scorering`, NOT `ring`** — a bare `ring` class makes Tailwind emit its `.ring` utility (a blue
  box-shadow, `rgb(59 130 246/.5)`) which then paints a rectangle around each ring (the scoped `.aijh .ring`
  rule didn't reset `box-shadow`). Renaming to `scorering` avoids the utility entirely. General rule: don't
  reuse bare Tailwind utility names (`ring`, `container`, `block`, …) as landing class names.

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
- Current coverage (148 tests: 145 passing + 3 skipped live/owner-absent):
  - `test_invite_or_pay.py` (10): redeem a valid key → user active + `entitlement_source=invite`;
    redeem used/revoked/expired key → 400; unknown key → 404; **two users racing one key → exactly
    one wins** (row-locked); non-entitled user hits `score-now` → **402**; **invited-lapsed** (active
    status but past `subscription_end`) → **402**; **admin bypasses** (→ 404 not 402); extension-request
    **saves even when SMTP is unset** (in-app queue is the source of truth). Admin/user rows torn down per test.
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
  - `test_auto_mode.py` (1): **live** auto-mode pipeline — auto_mode ON → generate → bulk approve_all →
    apply → asserts CV/CL/email (with greeting) non-empty + s2>0 + s3>0 + s3_status green/amber. Uses the
    owner's real master/domain CV + a job and makes REAL Claude calls (~80s); **skips** if those aren't
    present (clean CI). Restores the owner's original `auto_mode`.
  - `test_billing.py` (4): GET /billing/subscription returns inactive/none for a fresh user;
    create-checkout-session is wired (200 w/ `checkout_url` when Stripe fully configured, else
    502 bad-price / 503 not-configured); the subscription gate **blocks** POST /tailor/generate
    with **402** for a non-admin inactive user, and **allows** GET /jobs (read-only, 200).
  - `test_chat.py` (10): rule-based FAQ matching (anthropic/gmail/no-match — pure); guest +
    logged-in conversation create with FAQ-bot reply; no-match → ticket suggestion; admin message
    (`sender_type=admin`); ticket create (`JH-###`); admin presence online; and presence **offline
    after the 5-min timeout** (backdated `last_seen`). Guest convs cleaned up by `guest_email`;
    admin paths use the owner token (skip if absent).
  - `test_usage.py` (5): Anthropic cost math (sonnet 1000/500 → $0.0105 / ₹0.877); `log_anthropic_usage`
    + `log_apify_usage` write correct token/run/cost rows (owner, cleaned up by tag); `GET /usage/logs`
    returns `{logs, summary.anthropic, summary.apify}`; `GET /usage/export` returns a CSV with the header row.
    Plus 3 **live** (skip-if-owner-absent) tests: tailor `generate`, `parse/text`, and domain
    `generate-changelog` each return `tokens_used`/`cost_inr` (`s1_tokens` for parse) > 0 in the response.
  - `test_community.py` (7): `normalize_role` (pure); `upsert` creates an insight (contributor_count=1,
    avg scores, keyword pattern from an approved injection); a 2nd contributor merges (running average,
    count=2); `get_community_insights` returns **None for 1 contributor** but data for **2** (privacy
    floor) and strips the internal `_approved`; `POST /community/share/{job}` 200; `PATCH
    /community/preferences` flips `community_sharing_enabled`. Real temp users/jobs, cleaned up.
  - `test_career.py` (5): GET /career/analysis serialization (available/scores/roadmap_items/last_cost_inr);
    **7-day cache** (`is_fresh` true for future `expires_at`, false when expired); roadmap completion
    **+impact_pct** updates readiness (70→73→70 on toggle); community **warming_up** when < 2 contributors;
    career questions save + read back. DB-seeded (no live Claude — the analysis pipeline is live-verified).
  - `test_rag_scoring.py` (14): essence schema; the 3 presets' config; `estimate_scan_cost`; **3-stage
    routing** (Stage 1 keyword reject/pass w/ NO model call; Stage 2 uses the haiku model; Stage 3 uses
    sonnet for borderline; confident save ≥ borderline_high skips Stage 3; domain scoring skipped below
    min_s1) via a monkeypatched `batch_score_s1` (deterministic, free); `config_from_prefs`; `GET
    /scoring/estimate`; `master_cvs.essence_json` round-trips.
  - `test_cv_essence_isolation.py` (2): `_save_master_cv` returns a valid `MasterCVRead` (no `MissingGreenlet`)
    both when essence extraction **succeeds** (commits → would expire the PK → reproduced the prod 500) and
    when it **raises** (CV still saved, `essence_json=None`). Calls the real function with a production-like
    `expire_on_commit=False` session + monkeypatched key/essence.
  - `test_career_readiness.py` (6): `GET /career/readiness-scores` returns `{no_data}` when unscored;
    ATS/Pursuit components normalize to 0-100 (score/max·100); the cross-job average aggregates correctly
    (kw 30 & 15 → 75); `avg_ats`/`avg_pursuit`/`overall` (weighted 0.4/0.6); and the `market`/`feed_id`
    filters scope the aggregation.
  - `test_dual_scoring.py` (10): ATS scorer returns 5 components + applies the dealbreaker cap; Pursuit
    scorer returns 4 components + a recommendation; `compute_dual_scores` runs both in parallel and sets
    `ats_<entity>`/`pursuit_<entity>` + `score_components[entity]` for master/domain/tailored; the
    `default_score_view` pref persists; null scores serialize gracefully (`GET /jobs` + `/jobs/{id}/scores`);
    `POST /jobs/backfill-scores` returns a job count + cost estimate; `/jobs/stats` exposes the
    apply-now/get-referral/skip buckets. (Anthropic mocked — no live calls.)
  - `test_optimization.py` (9): email `rule_classify` (rejection/interview/None); JD highlights use Haiku
    (`JD_HIGHLIGHTS_MODEL` + a monkeypatched-client call asserting `model=haiku`) and are **cached** per job
    (a pre-seeded `jd_highlights_json` with a matching JD signature → endpoint returns `cached:true`, no
    Claude); feed keywords default to Haiku; the gmail-alert public path wires the 3-stage config
    (`config_from_prefs`/`s1_essence_model`/`s1_borderline_low`/`s1_full_model`); and `tiered_parse_and_score`
    escalates Haiku-essence → Sonnet-full only for borderline scores (`stage3_full`, calls `[haiku, sonnet]`).
  - `test_email_to_jobhunt.py` (4): `is_save_job_email` detects save signals + `jh:`/`jt:` prefixes
    (pure); `extract_first_url` pulls the first real job URL (anchors/text/subject, skips social/footer);
    `process_save_job_email` (mocked fetch/parse) saves a `manual`/`new` job with `portal_url` + S1 +
    `source_email_id` + an `email_to_jobhunt` EmailAlertLog; and **no-ops** when the email has no URL.
  - `test_auto_detect.py` (4): `extract_company_role` parses LinkedIn/Indeed confirmation subjects
    (company + role, and `(None, None)` for non-confirmations — pure regex); `detect_external_application`
    **matches** a `new`/`bookmarked` job by company → flips it to `applied` (+`applied_at`, EmailThread,
    EmailAlertLog), **creates** an applied `gmail_alert` job when there's no match, and **no-ops** on an
    unparseable subject.
  - `test_night_batch.py` (4): pending jobs expose `scoring_status="pending"` (+`pending_count` in stats)
    and aren't scored; `score_pending_for_user` scores all pending (monkeypatched scorer → scored, s1 set);
    `POST /jobs/{id}/score-now` no-ops on an already-scored job; default timing is `immediate`.
  - `test_governance.py` (12): rate limit blocks after limit + resets after the window; hallucination
    validator catches an invented metric / passes a valid CV; prompt-injection hardening present (XML tags
    + SECURITY INSTRUCTION in jd/tailor/career agents); data export returns a ZIP; deletion request schedules
    +30d / cancel clears it; **login lockout after 5 failures (429)**; **user isolation** (other user's job →
    404); **credentials never return key values**; audit log records login_success.
  - `test_templates.py` (6): `get_effective_template` merge (override wins where not null, global kept where
    null); `build_content_rules_prompt` includes the word budget + never-modify sections; `check_overflow`
    detects excess (750 words vs 600 → 2.5 pages); `_TRIM_PRIORITY` order (reorder→keyword→rephrase, never
    deselect); GET /templates/cv returns defaults (Calibri/600/2pg); PUT recomputes `max_words` (3pg→900).
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
| Payments | **Stripe** — JobHunt Pro subscription ₹500/mo (Razorpay wallet code present but unused) |
| Storage | Local /app/storage/, user-scoped (`users/{user_id}/tailored|cover_letters|exports/`); S3 migration planned |
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
│   │   ├── (models) chat.py         # V3: ChatConversation, ChatMessage, ChatTicket, AdminPresence
│   │   ├── (routers) chat.py        # V3: support chat REST + WebSocket (rule-based FAQ, NO Claude)
│   │   ├── (utils) chat_faq.py      # V3: 12 keyword FAQ rules + match_faq() (NO Claude)
│   │   ├── (models) usage.py        # V3: APIUsageLog (Anthropic + Apify call log)
│   │   ├── (utils) usage_logger.py  # V3: log_call/log_anthropic_usage/log_apify_usage + set_usage_user contextvar
│   │   ├── (routers) usage.py       # V3: GET /usage/logs + /usage/export (token + cost visibility)
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
│   │   │   ├── billing.py           # V3: Stripe subscription (checkout, cancel, webhook, verify-session)
│   │   │   └── activity.py          # V3: activity dashboard (alerts timeline + system runs)
│   │   ├── tasks/           # Celery tasks
│   │   │   ├── scanner_tasks.py     # weekly_job_scan
│   │   │   └── gmail_tasks.py       # poll_gmail_all_users, check_ghosted_jobs
│   │   ├── utils/
│   │   │   ├── pdf_generator.py     # Playwright CV + CL PDF generation
│   │   │   ├── encryption.py        # AES-256 for API keys
│   │   │   ├── storage.py           # local file storage helpers (user-scoped: users/{user_id}/{tailored|cover_letters|exports}/; readable PDF names {user8}_{job8}_{Company}_{cv|cl}.pdf)
│   │   │   ├── subscription.py      # V3: require_active_subscription gate (402; admin bypass)
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
│   │   └── versions/        # chain tip: … → v3_ats_pursuit → v3_dual_scan_gate → v3_invite_or_pay
│   │       ├── initial_migration.py
│   │       ├── v2_feed_system.py              # V2: domain_cv_id on feeds, detected_domain_cv_id on jobs
│   │       ├── a1b2c3d4e5f6_user_profile_fields.py  # users: linkedin_url, phone, current_location, salary_expectation
│   │       ├── b2c3d4e5f6a7_user_feed_actor_name.py # user_feeds.actor_name (Apify actor input matching)
│   │       ├── v3_gmail_job_alerts.py         # V3: job_alert/gmail_alert enums, email_threads + jobs columns
│   │       ├── v3_gmail_alert_prefs.py        # V3: user_preferences job-alert controls
│   │       ├── v3_activity_log.py             # V3: run_logs.details→JSONB + email_alert_logs table
│   │       ├── v3_domain_cv_scores.py         # V3: jobs.s1d + domain_cv_scores (JSONB) + best_domain_cv_id
│   │       ├── v3_partial_jd.py               # V3: jobs.has_partial_jd (alert-email snippet flag)
│   │       ├── v3_stripe_subscriptions.py     # V3: users.stripe_customer_id + subscription_* fields
│   │       ├── v3_chat.py                      # V3: chat_conversations/messages/tickets + admin_presence
│   │       ├── v3_api_usage_log.py             # V3: api_usage_logs (Anthropic + Apify usage tracking)
│   │       └── v3_job_s1_tokens.py             # V3: jobs.s1_tokens + s1_cost_inr (manual-parse cost badge)
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
│       │       ├── TokenBadge.jsx   # V3: inline "⚡ 12.4K · ₹1.24" cost badge (10-colour scale) — shared
│       │       └── Toast.jsx        # ToastContainer
│       └── pages/
│           ├── auth/                # Login, Register, ForgotPassword
│           ├── onboarding/          # 4-step wizard
│           ├── dashboard/           # Dashboard (overview + analytics)
│           ├── activity/            # V3: ActivityPage (Job Alerts + System tabs)
│           ├── jobs/                # JobsPage, AddJobModal, JobDetail, TailorPage (full-screen), TailorOverlay (legacy fallback)
│           ├── cvs/                 # CVsPage, MasterCVTab, DomainCVsTab
│           ├── settings/            # SettingsPage + 8 tabs (Profile · Plan&Keys · Gmail · Auto · Preferences · Feeds&Scanning · Error Log · API Usage); UsageTab.jsx = token+cost visibility; Feeds&Scanning tab (FeedsTab.jsx) is the single place for ALL feed management (RSS/Apify feeds, Target Companies, Scan History, add/edit modals, Apify Store search, per-feed run)
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
- V3 Stripe: `stripe_customer_id`, `subscription_status` (inactive/active/expired/cancelled/past_due),
  `subscription_plan` (none/pro), `subscription_end`, `subscription_id`

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
- `jd_highlights_json` (JSONB) — **cached** Tailor-page JD highlights `{matches, gaps, _jd_sig}`; computed
  once (Haiku + CV essence) and reused until the JD changes (`_jd_sig` = sha256(jd)[:16]). Migration `v3_optimization`.
- `ats_master`/`pursuit_master`/`ats_domain`/`pursuit_domain`/`ats_tailored`/`pursuit_tailored` (Float) +
  `score_components` (JSONB `{entity: {ats:{…}, pursuit:{…}}}`) — V3 ATS + Pursuit dual scoring. Migration `v3_ats_pursuit`.
- `has_partial_jd` (bool) — JD is only an alert-email snippet (LinkedIn/gated cards); full JD behind
  `portal_url`. Saved **unscored** (`s1`/`s1d`/`domain_cv_scores`/`best_domain_cv_id` = NULL) — a 50-char
  snippet scores unreliably. Score it by fetching the full JD (`POST /jobs/{id}/fetch-jd` → background
  `fetch_and_rescore_partial_job`, which sets `has_partial_jd=False` on success or stays partial on a login wall)
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

### Chat (V3 support chat — `models/chat.py`)
- **ChatConversation**: `user_id` (null for guests), `guest_name`/`guest_email`, `status`
  (open/in_progress/resolved/closed), `category`, `assigned_to`, `is_guest`
- **ChatMessage**: `conversation_id`, `sender_id`, `sender_type` (user/guest/admin/bot), `content`,
  `message_type` (text/image/file/system), `attachment_*`, `is_internal_note`, `read_at`
- **ChatTicket**: `conversation_id`, `ticket_number` (`JH-###`), `title`, `status`, `priority`, `resolved_at`
- **AdminPresence**: `admin_id` (unique), `is_online`, `last_seen` (5-min auto-timeout = offline)

### APIUsageLog (V3 usage tracking — `models/usage.py`)
- One row per external API call. `provider` (anthropic/apify), `agent_name`, `category` (tailoring/
  scoring/domain_cv/scanner/gmail/other), `entity_type`/`entity_id`/`entity_label`, `model`,
  `input_tokens`/`output_tokens`/`total_tokens`, `estimated_cost_usd`/`estimated_cost_inr`,
  Apify: `actor_id`/`runs_requested`/`runs_returned`/`jobs_saved`, `result_summary`, `created_at`.
  Indexes on (user_id, created_at) / (user_id, provider) / (user_id, category).

### Community (V3 — `models/community.py`)
- **CommunityJobInsight**: `company`, `role_normalized` (lowercased/stripped), `market`, `jd_hash`,
  `contributor_count`, `avg_s1`/`avg_s1d`, `best_domain_cv_label`, `jd_highlights`/`keyword_patterns`/
  `tailoring_patterns` (JSONB), `response_data`. Surfaced only when `contributor_count ≥ 2`. NO CV/PII.
- **CommunityContribution**: `user_id`, `job_id`, `insight_id`, `contributed_scores`/`highlights`/`tailoring`,
  `is_anonymous` (default True). One per (user, job) — idempotent.
- **UserPreferences** + `community_sharing_enabled` (bool, default False) — opt-in.

### Career Insights (V3 — `models/career.py`)
- **CareerAnalysis** (one per **(user, filter)** — unique `(user_id, filter_hash)`): `readiness_score` +
  `keywords_score`/`skills_score`/`experience_score`/`certifications_score`, `analysis_json` (JSONB — full
  Claude output incl. `last_cost_inr`/`last_tokens`), `jd_count`, `last_analysed_at`, `expires_at` (=+7 days),
  + **filter fields** (`filter_hash`/`filter_source`/`filter_feed_id`/`filter_domain_cv_id`/`filter_market`/
  `filter_label`). 7-day cache **per filter combination** (migration `v3_career_filters`).
- **CareerRoadmapItem**: `category` (keyword/skill/cert/project/experience), `title`, `impact_pct`,
  `timeframe` (this_week/this_month/3_months), `is_completed`, `sort_order`. Completing an item adjusts
  the readiness score by ±`impact_pct`.
- **CareerQuestion**: `question_key` (manages_pms/github_public/b2c_experience/relocation/willing_to_do),
  `answer`. Unique (user_id, question_key).
- **CommunityCareerInsight**: `role_category`, `insight_type` (keyword/skill/cert/project), `insight_value`,
  `frequency_pct`, `contributor_count`, `success_stories`. Surfaced only when ≥ 2 contributors (warming_up).

### CV Template (V3 — `models/cv_template.py`)
- **CVTemplate** (one per user, unique): **aesthetic** (`font_family`/`font_size`/`heading_font_family`/
  `heading_font_size`/`heading_bold`/`margin_size` narrow|normal|wide/`line_spacing`/`bullet_style` •|–|▪|none/
  `accent_color`), **page** (`max_pages`, `overflow_action` warn|auto_trim), **content** (`never_modify_sections`
  JSONB, `section_order` JSONB, `max_words` = max_pages×300). Two rule sets: aesthetic → PDF (deterministic),
  content → tailor prompt (Claude follows).
- **DomainCVTemplateOverride** (one per domain CV, unique): all fields **nullable** — null = "use global".
  `get_effective_template(global, override)` merges (override wins where not null).

### Governance (V3 — `models/governance.py`, migration `v3_governance`)
- **User** + `gdpr_consent_at` (v3_gdpr_consent), `marketing_consent`, `data_deletion_requested_at`,
  `data_deletion_scheduled_at` (+30-day grace). **UserCredentials** + `anthropic_key_updated_at`/
  `apify_token_updated_at` (90-day rotation reminder).
- **RateLimitLog**: `user_id`, `action`, `count`, `window_start`/`window_end`. Limiter sums `count` in the
  rolling window. **AuditLog**: `user_id` (SET NULL on purge), `action`, `ip_address`, `user_agent`,
  `details` (JSONB), `created_at`. Immutable security trail.

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
  `coalesce(s1d, s1)`), **`domain`** (best_domain_cv_id), `search`, **`sort`** (`best_fit`→`s1d` |
  `s1` | `company` | `role` | `market` | `status` | `source` | `created_at`), **`order`** (`asc`|`desc`),
  **`hide_partial`** (default **true** — hides partial-JD/LinkedIn-gated unscored jobs;
  `has_partial_jd=false OR NULL`. **Override:** when the **source filter is `gmail_alert`** (Alert), the
  partial hide is **skipped** — every alert job is partial, so hiding them would make the Alert filter
  return nothing; the frontend shows "Alert jobs shown (partial JD)" instead of the Hide toggle there),
  `skip`, `limit`. **Returns an object** `{jobs: [...], total_count, unfiltered_count}` — `total_count`
  matches the current filters, `unfiltered_count` is all of the user's jobs. (All filters **and the sort**
  are server-side so counts stay accurate and the correct rows surface beyond the page limit. Score sorts
  push NULLs last; every non-date sort tiebreaks on `created_at DESC`, then a **final unique `Job.id DESC`
  tiebreaker** so paginated `offset`/`limit` pages never overlap. The **Jobs Tracker is server-side
  paginated** (25/page via `skip`/`limit` + the shared `Pagination` component; page resets on any
  filter/sort change).)
- `GET /stats` — pipeline counts + analytics: `total`, `by_status`, **`needs_hitl`** (boolean-flag
  count, fixed), `by_source`, `by_domain_cv` (by detected feed CV), **`by_best_domain`** (by
  best_domain_cv_id — drives the Domain filter dropdown counts), **`by_score_bucket`**
  (`{any, gte_70, gte_80, gte_90}` on `coalesce(s1d, s1)`), `score_distribution`, `avg_s1`,
  **`partial_count`** (jobs with `has_partial_jd=True` — drives the "Show partial (N)" toggle). **Accepts
  filters** `source`/`feed_id`/`domain_cv_id`/`market` (Dashboard filter dropdown): pipeline + score stats
  scope to the filter, **facet counts** (`by_source`/`by_market`/`by_best_domain`/`by_domain_cv`) stay
  unfiltered so the dropdown always shows each option's full count; also returns **`unfiltered_total`** +
  **`by_market`**. (`GET /jobs` gained a matching **`feed`** param = `source_feed_id`.)
- `POST /parse/text`, `POST /parse/url`
- `POST /confirm/{temp_id}`
- `GET /{id}`, `PATCH /{id}/status`, `GET /{id}/emails`
- `POST /{id}/fetch-jd` — V3: queue a background fetch of the full JD (from `portal_url`) +
  re-score for a partial-JD job → `{status: "queued"}` (Celery `tasks.fetch_partial_jd`)
- `POST /{id}/add-full-jd` — V3: user pastes the full JD (read on LinkedIn) → saves `jd_raw`,
  sets `has_partial_jd=False`, queues S1+S1d scoring → `{queued: true}` (Celery `tasks.score_pasted_jd`
  → `rescore_partial_job_from_text`, scores from the pasted text, no fetch)

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
- `GET /feeds/with-counts` — active feeds + `job_count` each (Dashboard filter dropdown)
- `GET /feeds/performance` — per-feed breakdown `{feed_id, feed_name, feed_type, job_count, avg_s1d, avg_s1,
  applied_count, above_threshold_count, quality_score}` (= `avg_s1d/100·0.6 + applied/count·0.4`, null if
  unscored), ordered by quality DESC, plus a synthetic **Gmail Alerts** row. Drives the Dashboard **Feed
  Performance** card (click a row → `?filter=feed:{id}`).
- `POST /feeds/suggest` — Claude-generates keywords from domain CV
- `GET /feeds/apify-actors?search=` — live Apify Store search
- `GET /companies`, `POST /companies`, `DELETE /companies/{id}`
- `POST /scanner/run` (all feeds, async Celery), `GET /scanner/status`

### Wallet (`/api/wallet/`)
- `GET /` — balance + transactions

### Billing (`/api/billing/`) — V3, Stripe JobHunt Pro (₹500/mo)
- `POST /create-checkout-session` — `{plan, success_url, cancel_url}` → `{checkout_url}` (get/create
  Stripe customer, create subscription Checkout Session)
- `GET /subscription` — `{plan, status, subscription_end, stripe_customer_id, is_active}`
- `POST /cancel` — `Subscription.modify(cancel_at_period_end=True)`; sets status `cancelled`
- `POST /webhook` — Stripe-signature verified; handles `checkout.session.completed` /
  `invoice.payment_succeeded` (→ active, +30d) / `invoice.payment_failed` (→ past_due) /
  `customer.subscription.deleted` (→ expired). No auth.
- `GET /verify-session?session_id=` — success-page polling; activates the user if `payment_status=paid`
- **Gate:** `require_active_subscription` (utils/subscription.py) returns **402** for non-active
  non-admin users on: tailor `generate`/`apply`, `cvs/domains/generate-changelog`,
  `cvs/domains/{id}/apply`, `feeds/scanner/run`, `gmail/send-application`, `gmail/poll`. **Admins
  bypass.** GET / auth / billing / dashboard endpoints are NOT gated.

### Activity (`/api/activity/`) — V3, read-only
- `GET /alerts?days=&limit=` — per-email job-alert timeline + saved-job summaries
- `GET /system?days=` — scanner_runs / gmail_polls / ghosted_checks + recent errors

### Admin (`/api/admin/`)
- `GET /stats` — platform stats (admin only, locked behind require_admin)

### Privacy / Governance (`/api/privacy/`, `/api/admin/governance`) — V3, security-first
- **`GET /api/privacy/summary`** — counts of the user's data + deletion schedule. **`GET /export`** — a ZIP
  (profile.json / master_cv.md / domain_cvs/ / jobs.json / tailored_cvs/ / applications.json / usage_log.json)
  → audit `export_data`. **`POST /delete-request`** `{confirm}` → sets `data_deletion_scheduled_at` +30d,
  cancels Stripe sub (best-effort), audit `delete_account_request`. **`POST /cancel-deletion`**. **`GET
  /rate-limits`** — remaining calls per action (read-only). Daily Celery **`tasks.purge_deleted_accounts`**
  purges accounts past the grace window (storage → Stripe customer → User row CASCADE).
- **`GET /api/admin/governance`** (admin) → audit_events_today, rate_limit_violations, failed_logins (24h),
  data_exports_today, hallucination_violations (7d), pending_deletions[], audit_logs (last 100). **`POST
  /api/admin/governance/cancel-deletion/{user_id}`** — admin override. Admin **Governance tab**; Settings
  **Privacy tab** (9th) — data summary / export / legal links / rate-limit transparency / delete-account.
- **Security utilities** (`utils/`): `rate_limiter` (per-user/action limits: tailor_generate 20/d,
  domain_generate 5/d, career_analyse 3/d, jd_parse 50/d, gmail_poll_manual 3/h, scanner_run_manual 2/h;
  wired to those 6 endpoints + `X-RateLimit-Remaining` header), `cv_validator` (anti-hallucination — every
  metric in the tailored CV must exist in the master; `apply` returns `hallucination_check`),
  `audit_logger` (fire-and-forget; logs login/register/logout/profile/key_update/application_sent/
  export/delete + rate_limit_exceeded + hallucination_flagged), `login_security` (Redis: 5 failures →
  15-min lockout), `input_validator` (file-type/size on CV + chat uploads). **Prompt-injection hardening:**
  jd/tailor/career agents wrap user content in `<cv_content>`/`<job_description>`/`<jd_n>` XML tags + a
  SECURITY INSTRUCTION. **Security headers** middleware (X-Content-Type-Options/X-Frame-Options/XSS/
  Referrer-Policy/Permissions-Policy), CORS pinned to `frontend_url`, **global error handler** (no internals
  leaked). **Masking:** `stripe_customer_id` no longer returned to the frontend (→ `has_customer`); keys only
  surface as `has_*` booleans.

### Settings (`/api/settings/`)
- `GET /mode` — send-mode visibility → `{mode: "test"|"production", notification_email}` (where an outgoing application email will actually go; surfaced as a banner in the Tailor Email Draft tab)
- `GET /legal-urls` — **public, no auth** → `{privacy_url, terms_url, cookies_url}` (from `config.py`; drives the AppLayout footer + auth-page links). **Legal pages** are static HTML in `/docs` (`privacy.html`/`terms.html`/`cookies.html`, styled like index.html) → served at `https://praveenp1118.github.io/JobHunt/privacy.html` etc. (**Pages serves from `/docs`, so the URL has NO `/docs/` segment**). `POST /auth/consent` stamps `users.gdpr_consent_at` (idempotent); set on register (required checkbox) and via a one-time **GDPR banner** in AppLayout for existing users with `gdpr_consent_at = NULL`. `UserRead` exposes `gdpr_consent_at`. Migration `v3_gdpr_consent`.

### Chat (`/api/chat/`) — V3, support chat (**rule-based FAQ, NO Claude/AI**)
- `POST /conversations` — optional auth (guests). `{guest_name?, guest_email?, first_message}` →
  `{conversation_id, bot_response, admin_online}` (FAQ-bot reply only when no admin online)
- `GET /conversations` — **admin**; all conversations + per-conversation `unread` + `total_unread`
- `GET /conversations/{id}` — owner/guest/admin; conversation + messages (internal notes hidden from non-admins)
- `PATCH /conversations/{id}` — **admin**; update status (resolve/close) / category
- `POST /conversations/{id}/messages` — user/admin. User+admin-offline → `match_faq` auto-reply
  (or no-match ticket suggestion); admin → plain save. Pushes over WebSocket.
- `POST /conversations/{id}/messages/{msg_id}/read` — mark read
- `POST /tickets` — `{conversation_id, title?, priority?}` → auto `JH-###`; emails the admin
- `GET /tickets` (admin) · `PATCH /tickets/{id}` (admin) — status/priority
- `POST /presence` (admin) `{is_online}` · `GET /presence` — `{is_online, last_seen}` (5-min auto-timeout)
- `POST /upload` — optional auth; multipart (≤5 MB; image/PDF/doc/docx) → `{url, name, size, type}`
  · `GET /attachments/{filename}` — serve
- **WS** `/ws/chat/{conversation_id}` — real-time message push + typing/read relay (`ConnectionManager`)

### Usage (`/api/usage/`) — V3, API token + cost visibility
- `GET /logs` — params `provider` (anthropic/apify/all), `category` (tailoring/scoring/domain_cv/scanner/
  gmail/other/all), `days` (30), `limit` (100) → `{logs: [...], summary: {anthropic: {total_tokens,
  total_cost_usd, total_cost_inr, call_count, by_category}, apify: {total_runs, total_cost_usd,
  total_cost_inr, actor_count}}}` (summary covers the whole window)
- `GET /export?days=` — CSV download (`date, provider, agent, category, for, tokens, cost_usd, cost_inr, model`)
- **How rows get written:** `usage_logger.set_usage_user(user_id)` is called at the request boundary
  (`get_user_model`) + in Celery tasks (scanner/gmail-poll/fetch); each agent calls `log_call(...)` right
  after `client.messages.create` to read `.usage` off the response and log (contextvar attribution, own
  session, fire-and-forget — never blocks/breaks the agent). Apify runs logged in the scanner via
  `log_apify_usage`. Pricing per-model in `usage_logger.PRICING`; INR = USD × 83.5 (approximate).

### Community (`/api/community/`) — V3, anonymised insight sharing (opt-in, ≥2 contributors)
- `GET /insights?company=&role=&market=&jd_hash=` → aggregated insights **only if contributor_count ≥ 2**
  (else `{available: false}`). Shape: `{available, contributor_count, avg_s1, avg_s1d, best_domain_cv_label,
  jd_highlights:[{text,votes,category}], keyword_patterns:[{keyword,injection_count,approval_rate}],
  tailoring_patterns:[{change_type,approval_count,total_count}], tokens_saved}`. Tries `jd_hash` then company+role.
- `POST /share/{job_id}` — manually contribute a job's insights → `{shared, insight_id}`
- `GET /my-contributions` — `[{job_id, company, role, contributor_count, contributed_at, insight_id}]`
- `PATCH /preferences` — `{community_sharing_enabled}` (UserPreferences)
- **Auto-share:** on `gmail/send-application` and on PATCH `jobs/{id}/status` → `applied`, if the user opted in,
  `community.maybe_share_on_apply` contributes the job's anonymised data (fire-and-forget). **NO CV content/PII** —
  only scores (running average), JD highlights + keyword/tailoring patterns derived from the **approved changelog**.
  `GET /jobs` enriches each `JobSummary` with `community_available`/`community_contributors` (one batched query).
  Company is matched via **`normalize_company`** (lowercase + strip punctuation + trim, same as
  `normalize_role`) so "Adyen"/"adyen"/"ADYEN"/"Adyen, Inc." collapse to one bucket — stored + queried
  normalized in `upsert`, `get_community_insights`, and the `GET /jobs` enrichment. Insights also surface
  on the **Add-Job parse screen** (compact `CommunityInsights` below the S1 pills → decide save/skip before
  spending tailoring tokens) and the Contributions "View →" deep-links to `/jobs?open={id}` (JobsPage reads
  `?open=`/`?id=` on mount → opens that job's detail panel, then clears the param).

### Career (`/api/career/`) — V3, cached gap analysis (7-day TTL)
- `GET /analysis` → cached analysis or `{available: false, needs_analysis: true}`. **Never auto-charges**
  (cost safety) — the frontend triggers explicitly. **Accepts filter params** `source`/`feed_id`/
  `domain_cv_id`/`market` → returns the cached analysis **for that filter** (each cached 7 days separately).
  Shape: `{available, readiness_score, scores{...}, analysis, roadmap_items[], is_fresh, jd_count,
  last_analysed_at, expires_at, last_cost_inr, last_tokens, filter_hash, filter_label}`.
- `POST /analyse` — **subscription-gated** (402, admins bypass). **Accepts the same filter params** → analyses
  only the filtered JDs (up to 50). One batch Claude call (`analyse_career_gaps`) over the master CV + filtered
  JDs + answers → upserts CareerAnalysis by `(user_id, filter_hash)` + roadmap items (scoped by `filter_hash`);
  returns the shape **plus `tokens_used`/`cost_inr`**. Logs usage with **category="career"**. **CareerPage** +
  Dashboard **CareerWidget** share the grouped `JobFilterSelect` dropdown (`?filter=…`); the page shows
  "Analysis based on N jobs · {filter_label} · Last updated {date}" and the widget shows
  "{label} readiness: X% (vs Y% overall)".
- `POST /questions` `{question_key, answer}` · `GET /questions` — the 5 sharpening questions.
- `PATCH /roadmap/{item_id}` `{is_completed}` → `{updated, new_readiness_score}` (±impact_pct).
- `GET /community` → role-category insights or `{warming_up: true, contributor_count}` (< 2 contributors).
- `POST /share` — opt in; copies anonymised keyword patterns to `community_career_insights` (no CV/PII).
- **Agent:** `agents/career_agent.py::analyse_career_gaps` — sync Anthropic client, `max_tokens=8000`,
  robust JSON parse (trims truncated tails). **CareerPage** has 7 tabs (Readiness **recharts RadarChart** +
  summary bars / Keywords / Skills / Experience / Certifications / Build / Roadmap), a 5-question modal, a
  TokenBadge after analysis, and a Dashboard **CareerWidget** (readiness + mini-bars + top action + "⚡ ₹cost").

### Templates (`/api/templates/`) — V3, CV template (aesthetic + content rules)
- `GET /cv` — user's global `CVTemplate` (auto-creates a default row if missing). `PUT /cv` — create/update;
  **`max_words` is recomputed from `max_pages`** (×300), never set directly. `GET /cv/fonts` — the 8-font list.
- `GET /domain/{domain_cv_id}` → `{override}` (or null). `PUT /domain/{id}` — upsert (only non-null fields;
  clearing `max_pages` clears `max_words`). `DELETE /domain/{id}` — revert to global.
- **Wiring:** the tailor `generate` injects `build_content_rules_prompt(effective)` into the system prompt
  (`generate_tailor_package(content_rules=…)`); PDF endpoints (master/domain/tailored) apply
  `build_pdf_styles(effective)` via `cv_md_to_pdf(pdf_styles=…)` → a CSS-override block (font/size/margin/
  accent/bullets); tailor `apply` returns **`overflow`** (`check_overflow` vs the effective `max_words`);
  **`POST /tailor/{id}/trim`** removes the lowest-impact approved changes (reorder → keyword_injection →
  rephrase; **never deselect**) in priority batches, re-applying until it fits → `{trimmed_cv_md,
  removed_changes, word_count, max_words, fits}`. **Frontend:** My CVs **Template tab** (form + live preview),
  per-domain-CV **"▸ Template overrides"** collapsible, and a TailorPage **overflow modal**
  (Trim to fit / Allow this time / Review manually).
- **Live CV previews** (`components/cv/CVPreview.jsx` — dependency-free markdown→HTML + scoped template
  CSS): the **Master CV tab** show-view is now 2-column (left = styled live preview using the global
  template, right = markdown source); each **Domain CV card** has a **"👁 Live preview"** button → modal
  rendering that domain CV with its **effective** template (global merged with the card's override, via
  `utils/template.js::mergeTemplate`). Previews render the *real* CV content (the Template-tab preview
  stays a sample mock for tweaking settings).

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

### Open

- **Tailored CV not persisted / re-tailors on return:** After tailoring a CV for a JD and navigating away
  (e.g. to Home/Dashboard) then returning, the tailored draft is lost and tailoring re-runs from scratch,
  spending Claude tokens a second time. **Likely cause:** the tailored result is held only in React state
  (not persisted server-side), and/or the tailor view doesn't check for an existing draft before calling
  Claude. **Fix:** persist the tailored CV + change log per (user, job); load the existing draft on return;
  re-run Claude only on an explicit "Re-tailor" action. **Priority:** medium (cost + UX).

### Fixed

| Issue | Status | Fix |
|---|---|---|
| Master CV upload/text + domain apply returned a generic 500 ("internal error") even though the CV saved | ✅ Fixed | Root cause was **`MissingGreenlet`**: the one-time essence step `commit()`s, and the following `MasterCVRead.model_validate(master)` (after the earlier `session.refresh`) triggered a lazy PK reload during *synchronous* Pydantic validation → async IO outside the greenlet → 500 (NOT a JSON-parse or token-field issue). Added **`await session.refresh(master)`/`refresh(domain_cv)` after the essence call**, before serialization, in `_save_master_cv` (covers upload + text) and `apply_domain_cv_changes`. Also hardened `essence_agent._parse_json` to never raise (returns `{}`). `tokens_used`/`cost_inr` were already `Optional`. Essence extraction was already isolated in try/except (a failed Haiku call leaves `essence_json=None`, CV still saved). Proven by `test_cv_essence_isolation.py` (reverting the refresh reproduces the exact `MissingGreenlet`). |
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
| Stripe webhook returned 200 but never updated the DB; verify-session 500'd | ✅ Fixed | Root cause: stripe SDK 15.x `StripeObject` has **no `dict.get()`** — `obj.get("customer")` → `AttributeError: get`. The webhook's `except Exception` swallowed it (→ 200, no DB write) and verify-session had no catch (→ 500). Fixed with a bracket-access `_g(obj, key, default)` helper across the webhook + verify-session, plus `logger.exception`. Live-verified: checkout → active; cancel → expired. |
| Partial-JD (LinkedIn alert) jobs scored B=0 — S1 on a ~50-char snippet is unreliable | ✅ Fixed | Gated cards are now saved **unscored** (`_save_gated_cards` no longer calls Claude — `s1`/`s1d`/`domain_cv_scores`/`best_domain_cv_id` = NULL, `has_partial_jd=True`). New **`fetch_and_rescore_partial_job`** fetches the full JD from `portal_url` and computes real S1 + S1d (clears `has_partial_jd`; stays partial on a login wall). Exposed via **`POST /jobs/{id}/fetch-jd`** (Celery `tasks.fetch_partial_jd`) + a **"↻ Fetch full JD + score"** button in JobDetail. One-off reset cleared the 5 existing `s1=0` partial jobs → NULL. Tracker shows **"—"** (not "0") for NULL scores (ScorePill); score-bucket filters already exclude NULLs (`coalesce(s1d,s1)` + `is not None`) |
| Scanner aborted with "Multiple rows were found" for a user (still recurring) | ✅ Fixed | `_scan_feeds_for_user` loaded `UserPreferences` with `scalar_one_or_none()`, which **raises** if a user has duplicate prefs rows → aborted the whole user's scan. Switched to `.scalars().first()` (matches the dedup + master-CV queries that were already `.first()`) |
| Gmail alert jobs showed "No link" (`portal_url` NULL) | ✅ Fixed | `_save_gated_cards` now **skips cards with no `url`** (`reason: "no_url"`) — a partial-JD job with no portal URL is unusable (can't open to read the full JD). `portal_url=card['url']` was already set; the NULLs were url-less noise cards |
| More non-PM roles from Gmail alerts (CTO, Program Manager, Technology Strategy/Advisory, Strategy Consultant) | ✅ Fixed | Expanded `jd_agents.SKIP_WORDS` with `chief technology officer`/`technology officer`/`technology strategy`/`technology advisor`/`strategy consultant`/`strategy & advisory`/`advisory`/`program manager`/`project manager`/`program management`. **NB:** bare `cto` is deliberately **not** added — it is a substring of "dire**cto**r" and would wrongly skip "Director of Product" (verified keep/drop set) |
| Non-PM roles in Gmail alert cards (e.g. "Head of Surveillance", "Sales Director") were saved | ✅ Fixed | `_save_gated_cards` had **zero title filtering** — every LinkedIn card was saved. Added a `SKIP_WORDS` title check in the gated-card loop (skips → `reason: "skipped_non_product"`) and **expanded `jd_agents.SKIP_WORDS`** with surveillance / security officer / commercial operations / sales-finance-operations-supply-chain director / legal counsel / procurement / logistics / customer success / account manager. Verified the keep-list ("ai strategy", "digital product", "product owner") still passes. **Investigation also confirmed (not bugs):** (1) `fetch_partial_jd` works but is **manual-trigger only** (button) — not auto-queued, and **all 56 alert jobs are LinkedIn login-gated** (`portal_url` linkedin.com), so the full-JD fetch can't bypass the login wall anyway; (2) the **score filter is correct** — `coalesce(s1d,s1) >= N` excludes NULL-scored partial jobs (the ≥70 view = 24 apify + 15 rss + 11 *scored* alert jobs; 44 unscored correctly show "—") |
| Jobs Tracker sort (e.g. Best Fit) only sorted the current page | ✅ Fixed | Sorting was **frontend-only** over the fetched ≤50-row page, so a high-`s1d` job sitting beyond the `created_at`-DESC page limit never surfaced when sorting by Best Fit (e.g. Ruby Labs s1d=92 missing from the top next to EWOR s1d=92). Moved sorting **server-side, before pagination**: `GET /jobs` now takes `sort`/`order` (`best_fit`→`s1d`, plus `s1`/`company`/`role`/`market`/`status`/`source`/`created_at`), pushes NULL scores last, and **tiebreaks on `created_at DESC`** for equal scores. JobsPage passes `sort`/`order` (from the URL) and renders the server order as-is (removed the client `useMemo` re-sort). Verified on 68 jobs: both 92s now top, 88-group tiebroken by date |
| Jobs Tracker — filter pills/header now show live counts (Option C) | ✅ Added | `GET /jobs` returns `{jobs, total_count, unfiltered_count}` with **all filters server-side** (incl. new `score`/`domain` params); header shows "N total · M matching", each Status/Source/Score pill + Domain dropdown shows its facet count from `/jobs/stats` (zero-count pills greyed, not hidden). Note: this changed the `/jobs` response shape (array → object) — all consumers (JobsPage, AppLayout, Dashboard) updated |
| Tailor + domain-CV flows broken — undefined `model` NameError (and a `model=` TypeError) | ✅ Fixed | All 4 `tailor_agents` functions **and** 3 `cv_agents` (`generate_domain_changelog`, `apply_changes`, `compute_s3_score`) referenced an undefined `model` on `client.messages.create(...)` → `NameError`; cvs.py also passed `model=user_model` to two of them that lacked the param → `TypeError`. Added `model: Optional[str] = None` to all 7 (defaults to `settings.anthropic_model`). Then **threaded `get_user_model()` through the tailor router** (generate / apply×3 incl. `compute_s3_score` / regenerate-cl / followup) so tailoring honours each user's `preferred_model` — matching cvs.py/jobs.py. Verified full flow: generate (6 changes, S2 72) → approve all → apply (S3 92/92 **green**) → CV + cover letter + email all populated |
| Tailor page enhancements (auto-mode gating, email tab, PDF filenames) | ✅ Added (June 24, 2026) | **(1)** Respects `auto_mode`: when OFF, the page no longer auto-calls Claude on load — the middle panel shows a **"⚡ Suggest changes"** button (fetched from `GET /auth/me/preferences`); when ON, auto-generates as before. JD highlights still load either way. **(2)** Email Draft tab adds a **To** recipient (job.recruiter_email or "open the portal" note) + **📎 Attachments** list (CV + CL filenames). **(3)** Email body now has a greeting/sign-off — `generate_tailor_package` takes `recruiter_email` and the prompt opens "Hi <recruiter/Hiring Team>," … "Best regards, <name>". **(4)** Clean, neutral PDF filenames via `pdf_generator.make_filename(user_name, suffix)` → **`{FirstnameLastname}_CV.pdf`** / **`{FirstnameLastname}_CoverLetter.pdf`** (first+last from `user.name.split()`, special chars stripped). Deliberately **no company/role** — sending company-specific filenames to many firms looks suspicious; the job is tracked internally via `tailored_cv_id`. Used by `pdfs.py` + mirrored in the frontend email-tab attachment list. **(5)** Email Draft tab shows a **send-mode banner** — amber *"🟠 Test mode ON — email will be sent to {notification_email}"* / green *"🟢 Production mode — email goes to {recruiter_email}"* — from new **`GET /api/settings/mode`** → `{mode: "test"\|"production", notification_email}` (per-user notification address, falling back to `settings.notification_email` then login email). **(6)** Sidebar nav reordered → Dashboard · Jobs · My CVs · Activity · Settings · Wallet · Admin |
| Tailor page: CV/CL/Email blank, T/F never populated | ✅ Fixed | Backend was fine (apply → 200, returns full CV/CL/email + persists s2/s3). The **"Generate tailored CV + cover letter" button was gated on `changelog.length > 0`** — a 0-change generation (or not-yet-loaded changelog) left it permanently disabled, so apply never ran. Changed to `allReviewed = !!tailoredCvId && changelogData !== undefined && pending.length === 0` (enables once generation done + nothing pending, incl. the valid 0-changes case) |
| Admin → Users page broken (blank / error) | ✅ Fixed | API **path mismatch**: frontend called `/admin/users` (+`/{id}/role`,`/active`) → `/api/admin/users` → **404**; the routes actually live in the auth router at `/api/auth/admin/users`. (`/admin/stats` worked — it's defined in main.py.) Pointed AdminPage at `/auth/admin/users…`. Verified 200, returns the user with role dropdown |
| Tailoring could alter protected CV sections / metrics | ✅ Fixed | Added **PRESERVATION RULES** to the `generate_tailor_package` prompt: only modify EXPERIENCE/SUMMARY; never touch EDUCATION/CERTIFICATIONS; never change section order, headers, or contact line; preserve all metrics/numbers + the candidate's voice; consistent bullet format. Verified: a generate produced 6 changes, all in SUMMARY/EXPERIENCE |
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

### 2. Payments — ✅ COMPLETE (Stripe subscription, June 24, 2026)

**Superseded the Razorpay wallet plan** — JobHunt is now a single-plan **subscription** (JobHunt
Pro, ₹500/mo via Stripe); users bring their own Anthropic + Apify keys. Built across 12 steps:
- **DB:** `v3_stripe_subscriptions` migration → User `stripe_customer_id`/`subscription_*` fields.
- **Backend:** `routers/billing.py` (checkout / subscription / cancel / webhook / verify-session;
  Stripe SDK calls in `asyncio.to_thread`), `utils/subscription.py` gate (**402**, admin bypass)
  on the 7 paid write endpoints. `config.py` Stripe settings.
- **Frontend:** `api/billing.js`; PlanKeysTab subscription card (Subscribe/Cancel/Resubscribe) +
  educational Anthropic/Apify key docs; AppLayout status banner (amber inactive / red past_due /
  yellow cancelled, hidden on settings/billing + for admins); `/billing/success` page; onboarding
  wizard gains **Subscribe as Step 1** (Skip-for-now allowed).
- **Tests:** `test_billing.py` (4) — subscription status, checkout wiring, gate 402 on tailor,
  GET /jobs allowed. Stripe lib baked into the backend image.
- **✅ Live-verified (test mode, June 24 2026):** full checkout → `checkout.session.completed` +
  `invoice.payment_succeeded` → subscription **active/pro**; cancel → `customer.subscription.deleted`
  → **expired** (DB flips ~3s after the Stripe CLI forwards the event); non-admin tailor → **402**.
- **⚠️ Stripe SDK 15.x caveat:** the SDK (API `2026-05-27.dahlia`) `StripeObject` does **NOT** expose
  `dict.get()` — `obj.get("customer")` routes through `__getattr__` and raises `AttributeError: get`.
  Use **bracket access** instead. `billing.py` has a `_g(obj, key, default=None)` helper
  (`try: obj[key] except (KeyError, TypeError, AttributeError): default`) used across the webhook +
  verify-session; the webhook also uses `logger.exception` so handler errors surface (the original
  `.get()` bug made every webhook return 200 while silently failing to update the DB, and verify-session 500'd).
- **⚠️ Config note:** `STRIPE_PRO_PRICE_ID` must be a **Price** id (`price_…`), not a **Product**
  id (`prod_…`) — checkout 502s ("No such price") otherwise. `STRIPE_WEBHOOK_SECRET` (`whsec_…`) needed
  for the webhook path. `.env` changes need a container **recreate** (`up -d --force-recreate backend`),
  not just `restart` — docker-compose injects `env_file` values at creation. (Razorpay wallet code remains, unused.)

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

# Stripe (JobHunt Pro subscription)
STRIPE_SECRET_KEY=           # sk_test_… / sk_live_…
STRIPE_PUBLISHABLE_KEY=      # pk_test_… / pk_live_…
STRIPE_PRO_PRICE_ID=         # price_… (a Price id, NOT a prod_… Product id)
STRIPE_WEBHOOK_SECRET=       # whsec_… (from `stripe listen` or the Dashboard webhook)

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

V1, V2, V3 complete. All optimizations done.
114 tests passing. Claude Code connected.

Next priorities:
1. Home page + login flow
2. Production deployment
3. Test CV template + Career Insights end-to-end

Platform is feature-complete for launch.

Project root: D:\JobHunt
```

---

*Last updated: July 3, 2026 — **Invite-or-pay + public landing page + docs rebrand; production LIVE.**
Shipped the **invite-or-pay access gate** (single-use `JH-XXXX-XXXX` keys · 30-day entitlement · expiry-aware
402 gate on every Claude route · extension requests · admin panel; migration `v3_invite_or_pay`; 148 tests),
the **public landing page** at **aijobshunt.com** (React/Vite, scoped `.aijh` CSS, SEO + OG/JSON-LD + PWA
icons, GA via `VITE_GA_ID` build-arg; renamed the ring class off Tailwind's `.ring` utility), and **deployed
production** (Docker + Caddy — verified live, HTTP 200). Then refreshed **README + GitHub Pages docs**:
rebranded the product name **JobHunt → AIJobsHunt** (keeping repo/Docker/DB names + `jh:`/`JH-` prefixes +
repo URLs), **published the live URL** (aijobshunt.com), added invite-or-pay + landing to features, updated
the **migration chain → v3_invite_or_pay**, replaced the messy README ASCII **architecture diagram with a
Mermaid** one, bumped the **test count → 148**, and **replaced the docs screenshots** with fresh real-app
captures (landing · dashboard · tracker · tailor · activity · cvs · feeds · admin). Prior: June 29, 2026 —
**Storage refactor + Claude Code config + infra cleanup.** PDFs now save to a
**user-scoped layout** — `users/{user_id}/tailored/` (CV) and `users/{user_id}/cover_letters/` (CL), with
readable storage names `{user8}_{job8}_{Company}_{cv|cl}.pdf` (`storage.py` helpers `tailored_pdf_path` /
`cover_letter_pdf_path` / `export_path` / `pdf_storage_name`; folders auto-create on first write). **Existing
files untouched** (their old paths still resolve via `/app/storage/{path}`); only new generations use the new
structure. The GDPR export ZIP stays in-memory (no disk path). `.gitignore` now also ignores `cv.md` / `*.pdf`
/ `/storage/`. Added **`.claude/rules/`** (security/testing/api/cost/db/frontend conventions) + **`.claude/
commands/`** (test/backfill/scan/logs) — Claude Code guidance only, zero runtime impact. Removed a long-orphaned
**`jobhunt_app` Streamlit container** (old V1 prototype, crash-looping on a missing `dashboard/app.py`, not in
the compose file); the live stack is the 6 defined services. **Tracker score toggle moved to the filter bar +
all score columns sortable.**
The ATS/Pursuit/Combined toggle now lives in the filter bar ("View" group, beside Domain/Partial) and drives
**all** dual pills at once (Match/master, Best Fit/domain, Tailored) — freeing the Match header. Every score
column is now clickable-to-sort: **Match** → `{metric}_master`, **Best Fit** → `{metric}_domain`, **Tailored**
→ `{metric}_tailored` (metric = the active toggle), **F** → `s3` (added to the sort_map + nullslast). All
resolve via the backend `_score_expr`/sort_map (verified: pursuit_domain/ats_domain/combined_domain/
pursuit_tailored/s3 sorts all 200). **Jobs Tracker migrated off the old RAG fit columns to ATS + Pursuit dual
pills.** Removed the **B** (s1) column entirely — the **Match** dual-ring pill (master ATS/Pursuit) replaces
it. **Best Fit** is now a **domain** ATS/Pursuit dual pill (`ats_domain`/`pursuit_domain`) + the domain-CV
label (was the old s1d number/popover); **T** became **Tailored** (`ats_tailored`/`pursuit_tailored` dual
pill, "—" until tailored). **F** (factual-integrity send-gate) is kept — it's a distinct metric ATS/Pursuit
don't replace. A single ATS/Pursuit/Combined toggle in the Match header drives the view for all three dual
pills; each pill's tooltip pulls `score_components.{master|domain|tailored}`. (B=s1 was the old single base-fit
score; it's superseded by master ATS [will it pass screening] + Pursuit [should you pursue]. Filter/sort still
support all entities via `_score_expr`.) **Career Readiness from real scores**: the Career Insights **Readiness tab**
now aggregates **real ATS + Pursuit component scores** from `jobs.score_components` instead of a Claude
estimate — instant, free, always current, over ALL scored jobs. New **`GET /api/career/readiness-scores`**
(filter-aware: source/feed_id/domain_cv_id/market) Python-aggregates the master entity's components,
normalises each to 0-100 (score/max·100), and returns `{ats:{overall,components,top_gap}, pursuit:{…},
overall (ATS·0.4+Pursuit·0.6), avg_ats, avg_pursuit, jobs_scored, filter_label}` (or `{no_data:true}` when
nothing scored). Readiness tab shows a **dual radar with an ATS/Pursuit toggle** (5 / 4 axes) + component
bars + weakest-component insight (→ Keywords / Roadmap tab), a green "Readiness from N real scores" banner,
and **falls back to the Claude estimate** when no scores yet (prompts to backfill). The **sidebar %** + the
**Dashboard CareerWidget** (4 bars: Keywords/Skills (ATS), Career fit/Achievability (Pursuit)) also use real
data when available. **All other Career tabs (Keywords/Skills/Experience/Certs/Build/Roadmap) stay Claude**
— complementary (real data = what the scores say; Claude = what to do). No Claude call for readiness. 136
tests. **ATS + Pursuit — all surfaces + filter integration** (migration
`v3_dual_scan_gate`): completed the dual-scoring rollout. **UI surfaces wired:** Jobs Tracker **Match**
column (DualRingPill + header toggle + tooltip, default view loaded from prefs), **Tailor** left panel
(Master→Domain→Tailored DualScorePanel with deltas + an insight line), **Dashboard** Score-overview card
(avg Pursuit/ATS + apply-now + insight), **Job Detail** Scores tab (lg pill + Master/Domain/Tailored entity
tabs + 5 ATS / 4 Pursuit component bars + top strength/gap + recommendation, from `GET /jobs/{id}/scores`),
**Feed Performance** quality-bar ATS/Pursuit toggle, **Career Insights** banner (avg ATS/Pursuit for the
filtered set). **Filter integration:** `GET /jobs` `score_field` accepts **`{ats|pursuit|combined}_{master|domain|tailored}`**
(+ legacy `s1`) resolved by a shared `_score_expr` helper used by **both** the score filter and the sort, so
both follow the active CV entity. The Tracker pill, score-filter pills, and Match-header sort use **domain**
scores when a Domain filter is active (`scoreField` = `ats_domain` etc; pill falls back to master + a "Master*"
label when a job has no domain score), else **master**; sublabel shows "Pursuit · Domain". Tracker score pills
+ Match-header sort follow the active ATS/Pursuit/Combined toggle (the toggle's saved default is applied **once**
on load via a `useRef` guard — a prefs refetch no longer snaps it back); `/feeds/performance` returns `avg_ats_master`/`avg_pursuit_master`; `/jobs/stats`
averages already scope to the dashboard filter. **Scanner gate:** `UserPreferences.auto_dual_score_on_scan`
(default **False**) — when on, the scanner computes master + (best-)domain dual scores for saved jobs.
**Retry/fallback:** both scorers retry once on malformed JSON, else default 50/50 with `error_flag`.
**Live-verified** (Haiku): AstraZeneca AI-strategy director → ATS 26 (**dealbreaker correctly applied** —
product leader vs pharma role), Pursuit 41, valid JSON both. **Deferred:** Career radar dimension-swap (8e)
— the analysis produces gap axes, not ATS/Pursuit component dimensions; the context bar covers the filter
value. 130 tests. **ATS + Pursuit dual scoring** (migration `v3_ats_pursuit`): two scores per
CV entity — **ATS** (simulated automated screening, 5 components, dealbreaker cap at 40) and **Pursuit**
(should-you-pursue judgment, 4 components + a recommendation), per master/domain/tailored. New agents
`agents/ats_scorer.py` (Haiku), `agents/pursuit_scorer.py` (Haiku), and `agents/dual_scorer.py`
(`compute_dual_scores` runs both **in parallel** via `asyncio.to_thread`+`gather`, persists
`ats_<entity>`/`pursuit_<entity>` + merges the breakdown into `jobs.score_components`). **Job** gains
`ats_master/pursuit_master/ats_domain/pursuit_domain/ats_tailored/pursuit_tailored` (Float, indexes on
master pair) + `score_components` (JSONB); **UserPreferences** gains `default_score_view` (ats/pursuit/
**combined**, default pursuit) + `score_pill_style` (dual_ring/single/number_only). **Wired live:** manual
JD parse (master, returned for immediate display + persisted on confirm) and **tailor apply** (tailored).
**Frontend:** `DualRingPill` (SVG — ATS outer ring, Pursuit inner ring, centre number follows the view) +
`ScoreTooltip` (absolute-positioned breakdown) + `ScoreToggle` (ATS/Pursuit/Combined) — wired into the
**Jobs Tracker** as a new **Match** column with a header toggle. **API:** `GET /jobs` + `/jobs/{id}` expose
all 6 fields; **`GET /jobs/{id}/scores`** (full per-entity breakdown); **`POST /jobs/backfill-scores`**
(opt-in, returns job count + ₹ estimate, queues `tasks.backfill_dual_scores` — master scores for existing
jobs, ~5/sec); `/jobs/stats` adds `avg_ats_master`/`avg_pursuit_master` + `apply_now_count`(ats≥70 &
pursuit≥75)/`get_referral_count`(ats<70 & pursuit≥75)/`skip_count`(pursuit<60). **Settings → Scoring**:
score-display radios + the backfill button. 124 tests. **DEFERRED (noted):** ongoing dual scoring in the
**scanner** + **domain** flows (cost — backfill covers existing jobs); and the deeper UI surfaces from the
spec (Tailor left panel, Dashboard score card, Job-Detail breakdown tabs, Career Insights, Feed Performance)
— the Tracker pill + tooltip + toggle + Settings + backfill is the working slice. **Email-to-JobHunt source** (migration `v3_email_source`): jobs saved by
emailing a URL now use a distinct **`JobSource.email_to_jobhunt`** (was `manual`) — Manual = pasted JD in the
app, **📥 Email** = emailed a URL. `SourceBadge` (`📥 Email`, blue), a Jobs Tracker source filter pill, and
the `/jobs/stats` `by_source` facet (GROUP BY, auto-includes it) all surface it. **Cost optimization: RAG +
tiered models across ALL Claude calls** (migration
`v3_optimization` adds `jobs.jd_highlights_json`). **Email classification** (`gmail_agents`): rules-first —
sender `quick_classify` then content-pattern `rule_classify` (both FREE), and the remaining ~30% now use
**Haiku** (`CLASSIFY_MODEL`) not Sonnet (~85% cheaper). **Gmail alert public-URL path** (`gmail_alert_agent`):
full 3-stage hybrid-RAG — Stage 1 keyword filter (free) → Stage 2 essence score (Haiku) → Stage 3 full-CV
(Sonnet, **borderline only**) → domain scoring (config model, gated on min S1). **Manual JD parse** (jobs
`parse/text|url` via new `jd_agents.tiered_parse_and_score`): Haiku+essence first, Sonnet full-CV only if
borderline; returns `stage` → AddJobModal shows "Haiku" / "Sonnet — borderline". **JD highlights**
(`extract_jd_highlights`): Haiku + CV-essence context (≈60% fewer input tokens) + **cached per job** in
`jd_highlights_json` (endpoint returns `cached:true` on a JD-signature hit — never re-runs unless the JD
changes). **Feed keywords** (`generate_feed_keywords`): Haiku + CV essence. **text_to_markdown_cv**: Haiku.
**Career insights** (`analyse_career_gaps`): CV essence instead of full text, `career_model` from prefs, JD
limit 50→**100** (ordered best-fit/S1d DESC). **API Usage tab**: per-row **Model** tier badge (Haiku/Sonnet/
Opus) + a `by_model` summary ("Haiku calls: N · ₹X / Sonnet calls: M · ₹Y / Total"). **Scheduler night batch:**
the **scanner** already defers scoring in overnight mode (night-batch feature); **deliberately NOT** deferring
hourly **email classification** to 2 AM (would delay time-sensitive recruiter/interview emails — rules-first +
Haiku already cut that cost ~85% without delay). 114 tests. **Email to JobHunt** (migration `v3_email_to_jobhunt`): email any job URL to
your job-search Gmail with a subject containing "jobhunt"/"job hunt"/"save job"/"crawl"/"track this"/"add to
tracker" — or starting with **`jh:`** / **`jt:`** — and the poll fetches + parses + RAG-scores the URL and
saves it (`source=email_to_jobhunt`, `status=new`, `portal_url`), then emails a confirmation back ("✅ Saved to JobHunt:
{role} at {company} · S1/Best Fit · View link"). `gmail_alert_agent.py` adds `is_save_job_email` (rule-based,
no Claude), `extract_first_url` (anchors/text/subject, skips social/footer), and `process_save_job_email`
(fetch→`parse_and_score_jd`→domain scoring→save, **no threshold gate** — the user asked for it). Wired into
`_process_inbox_emails` (peeled off **first**, before alert detection) via `_handle_save_job` (creates the
EmailThread + sends the confirmation). Gated by `UserPreferences.enable_email_to_jobhunt` (default **True**;
Settings → Gmail section with the user's job-search address + Copy button). `EmailClassification.save_job`
enum value added; `POST /gmail/poll` returns `jobs_saved_via_email`; `GET /activity/alerts` rows gain an
`email_to_jobhunt` `{action, company, role, s1, s1d, url}` field → blue "📥 Email-to-JobHunt: Saved …" card.
**Phase 2 (not built):** a `jh:` subject with role+company but **no URL** logs `action=no_url` (future:
search Apify/Google for the best match). 105 tests. **Alert source filter fix**: selecting the Jobs Tracker **Alert**
(`gmail_alert`) source returned **0 jobs** because every alert job is partial-JD (LinkedIn-gated) and the
default "Hide Partial JD ✓" hid them all. `GET /jobs` now **skips `hide_partial` when the source filter is
exactly `gmail_alert`** (alert jobs always show under the Alert filter); the Tracker replaces the partial
toggle with a muted "Alert jobs shown (partial JD)" note for that filter. Verified: Alert + hide_partial
now returns 100 (was 0); RSS still hides partials. 101 tests (+1 assertion in `test_linkedin_alert`).
**Auto-detect external applications** (migration `v3_auto_detect_apps`):
when the Gmail poll classifies an email as `auto_confirmation` (an automated "application sent/received"
message), `agents/application_detector.py` extracts the company (+ role) from the subject — **pure regex,
no Claude** (LinkedIn/Indeed/generic ATS patterns) — then either **matches** a `new`/`bookmarked` tracked
job by company (ILIKE + first-word fallback) → flips it to **applied** (`applied_at` = email time), or
**creates** a new applied job (`source=gmail_alert`). Either way it links the email via an EmailThread and
writes an `EmailAlertLog` so it surfaces in **Activity → Job Alerts** as a green "✅ Auto-detected: Applied
to {company}" card. Gated by `UserPreferences.auto_detect_applications` (default **True**; toggle in Settings
→ Gmail). `POST /gmail/poll` returns `applications_detected`; `GET /activity/alerts` rows gain an
`auto_application` `{action, company, role}` field. Created jobs show as **Applied** with the **📧 Alert**
source badge in the Tracker. 101 tests. **Jobs Tracker filter fixes**: server-side **pagination** (25/page via
`skip`/`limit` + shared `Pagination`, page resets on filter/sort change) — fixed a latent **non-deterministic
ordering bug** (added a final unique `Job.id DESC` tiebreaker so paginated pages never overlap); filter bar
now **2 rows max** (Row 1 Source+Score pills, Row 2 Domain dropdown [max-w-180px, truncated] + Partial toggle
on the same line); renamed the partial toggle to **"Hide Partial JD ✓" / "Show Partial JD (N)"**.
**Night-batch scoring** (RAG add-on, migration `v3_night_batch`): per-user
`UserPreferences.scoring_timing` (**immediate** [default, safe] / overnight / manual) + `night_batch_time`
(IST, informational); `Job.scoring_status` (scored/pending/failed). In **overnight/manual** mode the scanner
saves jobs **unscored** (`scoring_status="pending"`, only the free Stage-1 keyword filter runs — no Claude);
the nightly Celery task **`tasks.score_pending_jobs_batch`** (beat 21:30 UTC = 2 AM IST, batch 20, RunType
`night_batch`) scores all overnight users' pending jobs; `score_pending_for_user` is shared by the task +
**`POST /jobs/{id}/score-now`** (single) + **`POST /jobs/score-pending`** (all). Jobs Tracker shows **⏳** for
pending (B + Best Fit) w/ "Score now" in JobDetail; Dashboard amber banner "⏳ N pending — will score tonight
[Score all now]" (`pending_count` in `/jobs/stats`); Settings → Scoring **timing radios** (+ overnight ~28%
cheaper note); Activity → System **Night Batch** section. 97 tests. **Hybrid-RAG scoring pipeline** (major scoring rearchitecture, migration
`v3_rag_scoring`): replaced "full CV × Sonnet × all jobs" with a **3-stage** pipeline — **Stage 1** keyword
pre-filter (FREE, JD vs the CV-essence keyword list), **Stage 2** essence scoring (cheap Haiku vs a compact
`essence_json`), **Stage 3** full-CV scoring (Sonnet, only borderline/no-essence jobs) + domain scoring (only
if S1 ≥ min). **CV essence** (`master_cvs.essence_json` / `domain_cvs.essence_json`) extracted once per
upload/apply by **`agents/essence_agent.py`** (Haiku, ~₹0.08; keywords/core_identity/top_experiences/
domain_strengths/…), triggered in `_save_master_cv` + domain apply (+ `POST /cvs/master|domains/{id}/
recompute-essence`). **`agents/rag_scorer.py`** = `hybrid_rag_score` + `SCORING_PRESETS` (maximum_quality/
balanced/maximum_savings) + `estimate_scan_cost`. Wired into `scanner_tasks` (writes a `rag_stats` funnel to
`run_log.details`) + the gmail-alert public-URL path (Stage 1). **11 scoring-config fields** on
`UserPreferences`; **`/api/scoring/config` (GET/PATCH) + `/estimate`**; **Settings → Preferences → Scoring &
Cost** (3 preset cards + per-stage controls + **live cost calculator**); Activity scanner cards show the RAG
funnel + "Saved ₹X vs unoptimized". Target ₹165→~₹28/scan (~82%, balanced); live-verified (essence 29
keywords; estimate 90.5% savings; preset switching). Graceful fallback: no essence → full-CV scoring (no
savings, no quality loss). 93 tests. **Pagination + 3 bug fixes**: a reusable **`Pagination.jsx`** (`Pagination`
component + `usePagination(items, perPage)` hook — "Showing X-Y of N", max-5 page buttons w/ ellipsis,
prev/next) applied **client-side** (slices already-fetched arrays — **no endpoint shape changes; server
lists are already capped at ≤100 rows, so client-side slicing is safe and avoids touching 7 endpoints +
their tests**) to 11 list views + a nested **skip-reasons expand/collapse** ("+ Show N more", first 5) in
the Activity → Job-Alert expanded detail: Activity Job-Alerts (10), Activity System Scanner/Polls/Ghosted/Recent-Errors (10 each), Settings
Scan-History (10) / API-Usage (20) / Error-Log (10), Admin Users (20) / Error-Log (10) / Governance audit
(20). **Bugs:** scanner "Multiple rows" (UserPreferences `scalar_one_or_none`→`.first()`); Gmail-alert "No
link" (skip url-less gated cards); expanded alert SKIP_WORDS (CTO/Program-Manager/Strategy/Advisory — bare
`cto` excluded as it substrings "director"). 79 tests. **Career Insights filter** (same source/feed/domain/market dropdown as the
Dashboard, shared `JobFilterSelect`): `GET/POST /api/career/analy*` accept `source`/`feed_id`/`domain_cv_id`/
`market`, analyse only the filtered JDs, and **cache per filter combination** (`CareerAnalysis` is now one per
`(user_id, filter_hash)` — migration `v3_career_filters`, roadmap items scoped by `filter_hash`); CareerPage
shows "Analysis based on N jobs · {filter_label}", the Dashboard CareerWidget shows "{label} readiness: X% (vs
Y% overall)" when a filter is active. **Dashboard filter + Feed Performance card**: a grouped filter dropdown
(top-right, by Source / Feed / Domain CV / Market) drives `/dashboard?filter=source:rss|feed:{id}|domain:{id}|
market:NL` — all pipeline stats, charts, and the recent-jobs table scope to it, with a "Showing N of M jobs"
indicator; `GET /jobs/stats` accepts `source`/`feed_id`/`domain_cv_id`/`market` (facet counts stay unfiltered)
+ returns `unfiltered_total`/`by_market`, `GET /jobs` gained a `feed` param, new `GET /feeds/with-counts` +
`GET /feeds/performance`. **Feed Performance** card (Overview, below pipeline stats): per-feed jobs / avg fit /
applied / quality bar, click-to-filter, + a synthetic Gmail Alerts row. 79 tests. **Governance & security-first build** (`v3_governance` migration: User
deletion/marketing fields + Creds key-rotation timestamps + `rate_limit_log` + `audit_logs`): per-user
**rate limiting** on 6 paid endpoints (+ `X-RateLimit-Remaining`), **anti-hallucination** validator on
tailor apply (`hallucination_check`), **prompt-injection hardening** (XML-tagged user content + SECURITY
INSTRUCTION in jd/tailor/career agents), **security-headers middleware** + **global error handler** + CORS
pinned to `frontend_url`, **login lockout** (Redis, 5 fails → 15 min), **audit logging** across auth/key/
send/export/delete + 429s + hallucination flags, **input validation** on uploads, **masking** fix
(`stripe_customer_id` no longer exposed), **GDPR self-service** (`/api/privacy` summary/export-ZIP/
delete-request[+30d grace]/cancel + daily `purge_deleted_accounts` task), **Settings → Privacy tab** (9th),
**admin Governance tab** + `/api/admin/governance`, **90-day key-rotation reminders**. 79 tests, live-verified
(security headers, rate-limit 429, login lockout, export ZIP, isolation, masking). **Legal pages + GDPR consent**: static **Privacy / Terms / Cookies** HTML in
`/docs` (styled like index.html, cross-linked, served at `…/JobHunt/privacy.html` — Pages serves from `/docs`
so **no `/docs/` in the URL**, contrary to the original spec); `config.py` + `.env.example` hold the 3 URLs;
**`GET /api/settings/legal-urls`** (public) drives the **AppLayout footer** + Login/Register links; **Register**
has a required "I agree to Terms + Privacy" checkbox; **`users.gdpr_consent_at`** (migration `v3_gdpr_consent`,
exposed on `UserRead`) + **`POST /api/auth/consent`** → a one-time **GDPR banner** in AppLayout for existing
users (NULL consent), and consent auto-recorded on register. 67 tests. **CV Template system** (My CVs → **Template tab**): one global `CVTemplate`
per user + per-domain overrides, two rule sets — **aesthetic** (font/size/heading/margins/line-spacing/bullets/
accent → deterministic **PDF styles** via `cv_md_to_pdf(pdf_styles)` CSS-override block on master/domain/tailored)
and **content** (never-modify sections / section order / `max_words`=pages×300 → injected into the **tailor
prompt** via `generate_tailor_package(content_rules)`). `v3_cv_template` migration (`cv_template` +
`domain_cv_template_overrides`, nullable=use-global), `templates` router (cv/fonts/domain GET·PUT·DELETE),
`utils/cv_template.py` (`get_effective_template`/`build_content_rules_prompt`/`build_pdf_styles`/`check_overflow`),
TemplateTab (form + live preview) + per-domain "▸ Template overrides" collapsible. Tailor `apply` returns
**`overflow`** (page-budget check) → TailorPage **overflow modal** (**Trim** via `POST /tailor/{id}/trim` removes
lowest-impact changes reorder→keyword→rephrase, never deselect / Allow / Review). 67 tests, live-verified.
**Partial-JD UX + radar + non-LinkedIn auto-fetch**: Jobs Tracker now
**hides partial-JD (LinkedIn-gated, unscored) jobs by default** (`GET /jobs?hide_partial=true`; `partial_count`
in stats; "Hide partial ✓ / Show partial (N)" toggle persisted in the URL). Shown partial rows render at 75%
opacity with a **View →** (opens `portal_url`) instead of Tailor, and a tooltip on the "—" score cells. JobDetail
gets an amber "⚠️ Partial JD — scores unavailable" banner, **Open job posting**, and a **Paste full JD** textarea →
**`POST /jobs/{id}/add-full-jd`** (saves `jd_raw`, clears `has_partial_jd`, queues `tasks.score_pasted_jd` →
`rescore_partial_job_from_text` = S1+S1d from the pasted text, no fetch); Tailor is **disabled** until the full JD
is added. **Career Insights Readiness tab** now shows a **recharts RadarChart** (5 axes) above the summary bars.
**Auto-fetch:** `_save_gated_cards` now **queues `fetch_partial_jd` (countdown 15s) for non-LinkedIn (public ATS)
gated URLs only** — LinkedIn is skipped (login wall). Live-verified (hide/show, add-full-jd 200 → flag flips + JD
saved + worker picks up `score_pasted_jd`). 61 tests. **Docs refresh** (README + GitHub Pages `/docs` fully updated; all features
documented in `/docs`): new feature cards/sections for Career Insights / API Usage / Support Chat / Stripe /
Community across index.html, features.md, architecture.md, api.md; hero stats band (61 tests · 40+ endpoints ·
7-tab career · 12 token-badge spots); **architecture.md now has the 4 pipeline flows** (Scoring / Gmail Alert /
Career Insights / Token Visibility) + the **full Alembic migration chain** (base → … → v3_career_insights head);
api.md has all endpoint groups (career/usage/community/billing/chat) +
**Gmail alert non-PM filter fix** (`_save_gated_cards` now applies `SKIP_WORDS`; expanded the list; confirmed
the fetch task + score filter are not bugs — all 56 alert jobs are LinkedIn login-gated). **Career Insights**
(`/career`, "Career Insights ✨" nav between Activity &
Settings w/ readiness % badge): ONE batch Claude call (`analyse_career_gaps`, category="career", 7-day cache)
across the user's master CV + up to 50 JDs → readiness score + per-axis scores + missing keywords / skill gaps /
experience reframes / cert + project suggestions / roadmap. `v3_career_insights` migration (`career_analysis`/
`career_roadmap_items`/`career_questions`/`community_career_insights`), `career` router (analysis/analyse[gated
402]/questions/roadmap/community/share), 7-tab CareerPage + 5-question modal + TokenBadge, Dashboard CareerWidget
("⚡ ₹cost · Refresh"), roadmap completion adjusts readiness ±impact_pct, community warming-up (≥2 contributors),
Add-to-CV nav hint (`/cvs?suggest=`), "Career" pill in UsageTab. Live-verified (readiness 72, 14.5K tokens ₹9). 60 tests.
**Community Insights** (opt-in, anonymised, ≥2 contributors to surface): users
share job scores + JD highlights + tailoring patterns (NO CV/PII) — `community` router/`utils`, `v3_community`
migration (`community_job_insights`/`community_contributions` + `UserPreferences.community_sharing_enabled`),
auto-share on apply (`maybe_share_on_apply`), `CommunityInsights.jsx` wired into Job Detail (💡 tab), Jobs
Tracker (💡 badge via `JobSummary.community_available`), Tailor left panel (compact), Settings→Preferences
toggle, `/community/contributions` page + Sidebar nav; recipients spend **0 tokens**. 55 tests.
**Inline token badges** (`TokenBadge.jsx`, shared 10-colour scale): show
"⚡ tokens · ₹cost" at the point of action. Backend exposes `tokens_used`/`cost_inr` on tailor
generate/apply (apply also `session_tokens` = the job's full tailoring total)/regenerate-cl, cvs
generate-changelog/apply, and `s1_tokens`/`s1_cost_inr` on `parse/text` — read off `response.usage` via
per-request session contextvars in `usage_logger` (`set_usage_entity` tags rows by job/domain CV for
queryable totals). Wired at **all 12 points**: Tailor (changelog header, apply session total, regen-CL toast),
Domain CVs (changelog + apply toasts), Add-Job parse result, Plan&Keys static cost-estimate panel,
**Jobs Tracker B-column badge** (manual/url-parsed jobs only — `jobs.s1_tokens`/`s1_cost_inr` persisted in
the confirm step + exposed on `JobSummary`; batch-scanned jobs stay NULL → no badge, by design),
**Master-CV file upload** (`MasterCVRead.tokens_used`), **Feeds** (per-feed Run toast + `feeds/{id}/run`
returns `tokens_used`/`apify_runs`/`apify_cost`; `feeds/suggest` keyword-gen badge; Scan-History rows show
the run's `usage_summary`). **Also fixed** a latent 500 in `parse/text` (`JDParseResult.pre_filter_reason`
+ `company`/`role`/`jd_language` could be `None` for a JD that *passes* the pre-filter).
**API Usage tab** (Settings → API Usage, 8th tab): per-call token + cost
visibility over `api_usage_logs` (`v3_api_usage_log` migration). `usage_logger` logs every Anthropic
`client.messages.create` (13 agent call-sites add `log_call`) via a contextvar set at the request boundary
(`get_user_model`) + Celery tasks; Apify runs logged in the scanner. `GET /api/usage/logs` (summary +
by-category) + `/export` CSV; `UsageTab.jsx` (10-colour token badges, category bar chart, sub-tabs,
row-expand, verify-on-console links); Activity scanner cards show per-run usage totals. **Support chat system** (rule-based FAQ + human admin, **NO Claude/AI**: `chat` router REST + WebSocket, 12-rule `chat_faq.py`, `v3_chat` migration → conversations/messages/tickets/admin_presence, lazy `ChatWidget` on all app pages, `/admin/chat` console w/ presence heartbeat + canned replies + internal notes + tickets, file upload ≤5 MB, ticket/admin-reply emails); **Stripe checkout/webhook live-verified in test mode** (checkout→active, cancel→expired, non-admin tailor 402) + **webhook bug fixed** (stripe SDK 15.x `StripeObject` has no `.get()` → bracket-access `_g` helper); V3 Multi-domain-CV scoring; Apify feeds fixed (+ count floor); LinkedIn alert-email parsing + has_partial_jd; JD storage fix; full-screen 3-column Tailor page; Jobs Tracker filter counts (Option C); /feeds merged into Settings → Feeds & Scanning; 3 bug fixes (tailor apply-button gating, admin users API path, CV preservation rules); tailor enhancements (auto-mode "Suggest changes" gating, email recipient/attachments/greeting); **clean neutral PDF filenames `{FirstnameLastname}_CV.pdf`**; **send-mode banner in Email Draft tab + `GET /api/settings/mode`**; **sidebar nav reordered** (Dashboard · Jobs · My CVs · Activity · Settings · Wallet · Admin); **server-side Jobs Tracker sort** (`GET /jobs` `sort`/`order`, NULLs last, `created_at DESC` tiebreak — fixes Best Fit sort missing high-s1d rows beyond the page limit); **Stripe payments + subscription system** (JobHunt Pro ₹500/mo — billing router, `require_active_subscription` 402 gate on paid endpoints w/ admin bypass, PlanKeysTab plan card + key docs, AppLayout status banner, `/billing/success`, onboarding Subscribe step, `v3_stripe_subscriptions` migration); **partial-JD jobs saved unscored + "Fetch full JD" re-score** (`POST /jobs/{id}/fetch-jd` → `fetch_and_rescore_partial_job`; tracker shows "—" for NULL scores); GitHub repo + Pages docs site live. **Community follow-ups:** insights on the Add-Job parse screen
(compact card, decide before tailoring), Contributions "View →" deep-link fixed (`/jobs?open={id}` →
JobsPage opens the detail panel), and **`normalize_company`** matching so company-name casing/punctuation
no longer splits buckets. All 136 smoke tests passing*
