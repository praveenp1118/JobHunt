# Features

A detailed tour of what AIJobsHunt does, by area.

## Job Tracker

The central pipeline for every opportunity.

- **Status lifecycle:** `new → bookmarked → applied → screening → interview (r1/r2) →
  offer received → accepted / declined`, plus `rejected`, `ghosted`, `withdrawn`,
  `not interested`.
- **Scoring at a glance:** each job row shows a **dual-ring ATS/Pursuit pill** per CV entity —
  **Match** (master), **Best Fit** (best domain CV + label), **Tailored** — plus **F** (S3 factual
  integrity, the send-gate). One **ATS / Pursuit / Combined** toggle in the filter bar drives all the
  pills at once; every score column is click-to-sort.
- **Filtering & sorting:** clickable column sort plus combinable Source / Score / Domain
  filters, all persisted in the URL so a view can be shared or bookmarked.
- **Partial-JD awareness:** jobs extracted from alert-email snippets are flagged so you open the
  posting for the full description before tailoring.
- **Auto-ghosting:** applied jobs with no response after a configurable window are flagged.

## CV Management

- **Master CV** — the single source of truth. Everything else is derived from it.
- **Domain CVs** — specialised variants per industry × function × country (e.g.
  *AI &amp; Data Products × NL*). Each carries its own integrity score and status
  (`active`, `stale`, `blocked`, `review required`).
- **Versioning & rollback** — master CV versions with rollback; domain CVs track their version.
- **Changelog-driven generation** — domain CVs are built from the master via a reviewable change
  log, not a free rewrite.

## AI Tailoring

- **The golden rule** — tailoring may **reorder bullets, rephrase verbs, inject keywords, and
  deselect content**. It may **never** invent experiences, metrics, skills, or companies, or add
  anything not already in the master CV.
- **One-call package** — change log + cover letter + application email + S2 score are produced in
  a single AI call for efficiency.
- **Human-in-the-loop change review** — approve, reject, or edit each proposed change before it is
  applied.
- **S3 integrity gate** — after applying, an integrity score measures how much of the tailored CV
  is traceable to the master CV. Sending is **blocked below 85**, **amber 85–89**, **green ≥90**.
- **Country rules** — per-market formatting (e.g. remove phone/photo/DOB, add a relocation note,
  privacy-law-compliant formatting) applied automatically during tailoring.
- **Cover-letter templates** — multiple styles (hook-first, story-led, problem-solver, concise),
  regenerable on demand.

## Feed System

- **Domain-CV-driven profiles** — each feed is linked to a domain CV; its search keywords are
  generated from that CV, so scanning stays on-strategy.
- **Two source types** — RSS boards (e.g. Jobicy) and Apify actors (LinkedIn, Google Jobs).
- **Keyword pre-filter** — a rule-based, zero-cost filter built from the user's target roles +
  feed keywords runs before any paid AI scoring, so only plausible roles are scored.
- **Multi-domain scoring at ingest** — every saved job is scored against the master CV **and all**
  active domain CVs; the best domain is recorded for one-click tailoring.
- **Threshold-gated saving** — only jobs at or above the score threshold are saved; everything
  else is logged (with the reason) in the scan breakdown.

## Hybrid-RAG Scoring &amp; Cost Optimization

AIJobsHunt scores a high volume of jobs, so every Claude call uses the cheapest model that's good enough.

- **3-stage scoring pipeline** — instead of running every job through one expensive full-CV call, scoring
  is a funnel:
  - **Stage 1 — keyword pre-filter (free):** the JD is matched against the CV "essence" keyword list; jobs
    with too little overlap are rejected with **no** AI call (~60% of jobs stop here).
  - **Stage 2 — essence scoring (Haiku, ~₹0.03/job):** the compact CV essence + JD produce a quick score;
    confidently-low jobs are dropped and confidently-high jobs are saved (~25% resolved here).
  - **Stage 3 — full-CV scoring (Sonnet, ~₹0.58/job):** only **borderline** jobs (~15%) get the full,
    high-quality model. Result: ~**82% cheaper** than the original "Sonnet × all jobs" approach, with no
    quality loss on the jobs that actually matter.
- **CV essence** — extracted once per CV upload/apply (a cheap Haiku call) and cached indefinitely until the
  CV changes; powers Stages 1–2 here and several other agents.
- **Three presets + live calculator** — *Maximum Quality* / *Balanced* / *Max Savings* in Settings →
  Preferences → Scoring, each adjustable per stage, with a live ₹-per-scan estimate.
- **Night-batch mode** — optionally defer scoring: jobs are saved instantly as *pending* (Stage-1 filter
  only) and a 2 AM IST Celery batch scores them in one cheap pass; a Dashboard banner offers "Score all now".
- **Tiered models everywhere** — email classification is rules-first (free) then **Haiku**; JD highlights run
  on Haiku and are **cached per job**; feed-keyword generation and CV→markdown use Haiku; Career Insights runs
  on the CV essence. The **API Usage** tab shows the model tier (Haiku / Sonnet / Opus) and ₹ cost per call.

## ATS + Pursuit Dual Scoring

Beyond fit, each job is judged on two axes per CV entity (master / domain / tailored):

- **ATS score (0–100)** — simulates an automated screening pass: keyword density, required skills,
  experience years, seniority alignment, and education, with a **hard-requirement dealbreaker** cap (only
  for mandatory language like "must"/"required", never "preferred").
- **Pursuit score (0–100)** — a recruiter's judgement of whether you should pursue it: human appeal,
  career-move quality, achievability (competition), and timing — plus a recommendation
  (*Apply now / Get referral / Review first / Skip*).
- **Dual-ring pill** — ATS as the outer ring, Pursuit the inner, with a centre number that follows the
  **ATS / Pursuit / Combined** toggle. Surfaced in the Tracker, the Tailor page (Master → Domain → Tailored
  with deltas), Job detail (full component breakdown), the Dashboard, and Career Insights.
- **Career Readiness from real data** — the Readiness tab aggregates these actual component scores across all
  your scored jobs into a **live dual radar** (ATS 5-axis / Pursuit 4-axis) — instant, free, always current,
  and filter-aware — instead of a one-off AI estimate. Both scorers run on Haiku (~₹0.15/job); existing jobs
  are scored via an opt-in backfill, and new scanned jobs optionally via a per-scan toggle.

## Gmail Integration

- **Job-alert parsing** — hourly inbox poll detects job-alert digests (rule-based, no AI cost),
  extracts job cards directly from the email body for login-gated sources (LinkedIn/Indeed), and
  scores + saves the relevant ones (full 3-stage RAG on fetchable URLs) with a link back to the source email.
- **Email-to-AIJobsHunt** — forward any job URL to your job-search Gmail with a subject containing `jobhunt`
  or starting with `jh:`. AIJobsHunt fetches the page, parses + scores it, saves it (**📥 Email** source), and
  emails you a confirmation with the scores and a tracker link.
- **Auto-detect external applications** — the poll recognises LinkedIn / Indeed "application sent / received"
  confirmations, flips the matching `new`/`bookmarked` job to **Applied** (linking the email), or adds the
  job if it wasn't tracked yet.
- **Recruiter mail** — genuine recruiter replies are classified and flagged for **human approval**;
  replies are never auto-sent.
- **Send applications** — CV + cover letter sent via SMTP. **Test mode is on by default** — all
  outbound mail is redirected to a notification address until production is explicitly enabled.
- **Follow-ups** — automatic follow-up email drafting for applications with no response.

## Activity Dashboard

- **Per-feed scan funnels** — `raw → pre-filter passed → above threshold → saved`, with a rejected
  list and reasons, per feed, per run.
- **Job-alert timeline** — per-email breakdown of links found / gated / public / below-threshold /
  duplicate, and which jobs were saved.
- **System runs** — collapsible sections for the weekly scanner, Gmail polls, and ghosted checks,
  each showing run history and status.
- **Manual controls** — "run now" at every level (scan all, scan one feed, poll Gmail).
- **Auto-refresh & error log** with one-click resolve.

## Career Insights ✨

- **One batch analysis** — a single cached (7-day) Claude call across your CV essence and up to **100**
  tracked JDs (best-fit first) produces a readiness score and a structured gap analysis.
- **Seven tabs** — *Readiness* (overall + per-axis bars across Keywords / Skills / Experience /
  Certifications / Projects), *Keywords* (missing vs present, by JD frequency), *Skills*, *Experience*
  (with reframe suggestions), *Certifications*, *Build* (existing + suggested projects), and *Roadmap*.
- **Actionable roadmap** — checkable items grouped *This week / This month / Next 3 months*; completing
  one adjusts your readiness score by its impact %.
- **Sharpening questions** — five optional questions refine the analysis.
- **Dashboard widget** — readiness %, mini per-axis bars, the top action, and the last analysis cost.
- **Community benchmark** — anonymised, opt-in role-level patterns (shown once ≥2 members contribute).
- **Cost transparency** — the token + ₹ cost of each analysis is shown via a token badge.

## API Usage Visibility

- **Every external call logged** — each Anthropic and Apify call is recorded with token counts,
  model, category, and an estimated cost in ₹ and $.
- **Inline token badges** — a shared 10-colour badge ("⚡ tokens · ₹cost") appears at the point of
  action in 12 places (tailoring, domain CVs, scoring, parse, feeds, career, …).
- **Settings → API Usage** — a 30-day rolling log with a category breakdown, row expansion, a
  "verify on the Anthropic Console" link per row, and **CSV export**.

## Support Chat

- **On every page** — a widget (bottom-right) available to guests and logged-in users alike.
- **Rule-based FAQ bot** — 12 keyword categories answer common questions with **no AI cost**.
- **Live hand-off** — when an admin is online, messages route over a **WebSocket** in real time;
  when offline, a support **ticket** is created and the admin is emailed.
- **Attachments** — image / PDF / doc up to 5 MB.
- **Admin console** — `/admin/chat` with presence heartbeat, canned replies, internal notes, and tickets.

## Access — Invite-or-Pay

- **Open registration, inert account** — anyone can sign up, but a new account is read-only until
  **entitled**. Entitlement comes two ways, both reusing the existing subscription columns:
  - **Invite key** — redeem a **single-use** `JH-XXXX-XXXX` key for **30 days free** (no card). Redemption is
    atomic and race-safe (row-locked), so two users can't win the same key.
  - **AIJobsHunt Pro** — a **Stripe** subscription (₹500/mo); each user brings their own Anthropic + Apify keys.
- **Gated writes** — **every Claude-calling route** (tailoring, scanning, JD parsing/scoring, sending, career
  analysis, CV essence…) returns **402 `entitlement_required`** until entitled; **admins bypass**. Read, auth,
  billing, and PDF generation stay open. The gate is **expiry-aware**, so an invite's free month lapses with
  no background job. The scheduled scanner + Gmail poll also skip un-entitled users.
- **Extension requests** — an invited user whose free period has lapsed (or is within 5 days) can request an
  extension from an in-app banner; the request is queued in-app (source of truth) and best-effort emails the
  admin. Admins manage keys and extension requests (grant / deny) from the **Admin panel** (with a pending-count
  badge), and can extend any user directly.
- **Billing lifecycle** — Stripe checkout, cancel (at period end), resubscribe, and a webhook-driven status sync.

## Public Landing Page

- **Marketing site** at **[aijobshunt.com](https://aijobshunt.com)** (React/Vite) — the logged-out home:
  animated product mocks (score rings, rotating panels), the ATS + Pursuit story, BYOK/pricing, an
  invite-key redemption field, and a rule-based FAQ chat.
- **SEO** — static `<title>` / meta / canonical, OpenGraph + Twitter cards (1200×630 share image), JSON-LD
  (`SoftwareApplication` + `Organization`), `robots.txt`, `sitemap.xml`, and a PWA `manifest.json` + icons.

## Community Insights

- **Anonymised sharing** — opt-in pooling of job scores, JD highlights, and tailoring patterns.
  **Never** CV content or PII. Company + role are normalised so casing/punctuation can't split buckets.
- **Privacy floor** — insights surface only once **≥2 members** have contributed.
- **Zero-cost reuse** — recipients see aggregated insights on the Add-Job screen, Job Detail, the Tailor
  panel, and the tracker without spending any tokens.

## CV Templates

- **Two rule sets** — *aesthetic* rules (font, size, headings, margins, line-spacing, bullets, accent
  colour) drive deterministic **PDF styling**; *content* rules (never-modify sections, section order, page
  budget) are injected into the **tailor prompt** so Claude respects them.
- **Global + per-domain overrides** — one template per user, with optional overrides per domain CV.
- **Live previews** — the Master CV tab and each domain CV render with the chosen template.
- **Overflow guard** — after tailoring, if the CV exceeds your page budget you get a warning with a
  one-click **trim to fit** (removes the lowest-impact changes; never your bullet de-selections).

## Security & Governance

- **Encryption & auth** — AES-256 for CV content and API keys, bcrypt password hashing, JWT sessions;
  API keys are never returned to the browser (only `has_*` flags).
- **Rate limiting** — per-user, per-action daily/hourly limits on the paid AI endpoints, with an
  `X-RateLimit-Remaining` header and an in-app transparency panel.
- **Prompt-injection hardening** — all user-provided content (CVs, JDs) is wrapped in XML tags with an
  explicit instruction to the model to treat it as data, never as commands.
- **Anti-hallucination check** — every metric in a tailored CV is verified against the master CV; invented
  figures are flagged (defence-in-depth alongside the S3 integrity gate).
- **Login lockout** — five failed attempts per email triggers a 15-minute lockout (Redis-backed).
- **Audit log** — an immutable trail of security events (logins, key updates, sends, exports, deletions,
  rate-limit hits, hallucination flags) with IP + user-agent.
- **Hardening** — security-headers middleware (no-sniff, frame-deny, referrer/permissions policy), CORS
  pinned to the configured frontend origin, and a global error handler that never leaks internals.

## Privacy & GDPR

- **Data summary** — see exactly what AIJobsHunt stores about you.
- **Export** — download all your data (profile, CVs, jobs, applications, usage) as a ZIP.
- **Right to erasure** — request account deletion with a **30-day grace period**; a daily task purges
  scheduled accounts (storage → Stripe customer → database, CASCADE).
- **Consent** — required Terms + Privacy agreement at sign-up, and a one-time consent banner for existing users.
- **Legal pages** — static **[Privacy Policy](privacy.html)**, **[Terms of Service](terms.html)**, and
  **[Cookie Policy](cookies.html)** served from GitHub Pages, linked from the app footer and the auth pages.

## Admin Panel

- **Users** — list, role and active-status management.
- **Error log** — platform errors with resolve.
- **Platform stats** — usage overview (admin-only, access-controlled).
- **Support chat console** — see the Support Chat section above.
- **Governance dashboard** — audit-event counts, rate-limit 429s, failed logins, data exports,
  hallucination flags, pending deletions, and the last 100 audit-log entries (admin override to cancel a deletion).

---

[← Back to home](index.html) · [Architecture](architecture.md) · [API](api.md)
