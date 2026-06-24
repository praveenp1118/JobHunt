# Features

A detailed tour of what JobHunt does, by area.

## Job Tracker

The central pipeline for every opportunity.

- **Status lifecycle:** `new → bookmarked → applied → screening → interview (r1/r2) →
  offer received → accepted / declined`, plus `rejected`, `ghosted`, `withdrawn`,
  `not interested`.
- **Scoring at a glance:** each job row shows **B** (S1, base fit), **Best Fit** (S1d, best
  domain CV with an expandable popover of all domain scores), **T** (S2, tailored fit) and
  **F** (S3, integrity).
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

## Gmail Integration

- **Job-alert parsing** — hourly inbox poll detects job-alert digests (rule-based, no AI cost),
  extracts job cards directly from the email body for login-gated sources (LinkedIn/Indeed), and
  scores + saves the relevant ones with a link back to the source email.
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

## Admin Panel

- **Users** — list, role and active-status management.
- **Error log** — platform errors with resolve.
- **Platform stats** — usage overview (admin-only, access-controlled).

---

[← Back to home](index.html) · [Architecture](architecture.md) · [API](api.md)
