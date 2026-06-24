# API Reference

A high-level map of the REST API. All routes are served under `/api` and require a JWT
(via `Authorization: Bearer …`) unless noted. This is a product-level overview, not an
implementation spec.

## Auth — `/api/auth`

| Method & path | Purpose |
|---|---|
| `POST /login`, `POST /register` | Email + password auth (JWT) |
| `POST /forgot-password` | Start password reset |
| `GET /me`, `PATCH /me/profile` | Current user + profile fields |
| `GET/PUT /me/credentials` | Manage encrypted API keys (Anthropic, Apify, Gmail) |
| `GET/PATCH /me/preferences` | Scoring thresholds, model, automation, job-alert controls |
| `GET /admin/users`, `PATCH /admin/users/{id}/…` | Admin user management |

## CVs — `/api/cvs`

| Method & path | Purpose |
|---|---|
| `GET /master`, `POST /master/text`, `POST /master/upload`, `PUT /master` | Master CV |
| `GET /master/versions`, `POST /master/rollback/{version}` | Versioning |
| `GET /domains`, `POST /domains/generate-changelog` | Domain CVs |
| `GET /domains/{id}/changelog`, `…/approve|reject|edit` | Review changes |
| `POST /domains/{id}/apply` | Apply changes, compute S3, auto-create feed profile |

## Jobs — `/api/jobs`

| Method & path | Purpose |
|---|---|
| `GET /` | List jobs (status / source / score / domain filters, search) |
| `GET /stats` | Pipeline counts + analytics (by domain CV, score, source) |
| `POST /parse/text`, `POST /parse/url` | Ingest a job from text or URL |
| `GET /{id}`, `PATCH /{id}/status` | Job detail + status updates |
| `GET /{id}/emails` | Recruiter email thread for a job |

## Tailor — `/api/tailor`

| Method & path | Purpose |
|---|---|
| `POST /generate` | One call → change log + cover letter + email + S2 |
| `GET /{id}/changelog`, `…/approve|reject|edit` | Review tailoring changes |
| `POST /{id}/apply` | Apply changes, compute S3 (domain + master) |
| `POST /{id}/regenerate-cl` | Regenerate the cover letter (different template) |
| `POST /jd-highlights` | JD analysis (matches / gaps) + country rules for the tailor page |
| `POST /followup/{job_id}` | Draft a follow-up email |

## Feeds — `/api`

| Method & path | Purpose |
|---|---|
| `GET /feeds`, `POST /feeds`, `PATCH /feeds/{id}`, `DELETE /feeds/{id}` | Feed CRUD |
| `POST /feeds/{id}/toggle`, `POST /feeds/{id}/run` | Enable/disable, run one feed now |
| `POST /feeds/suggest` | AI-generate keywords from a domain CV |
| `GET /feeds/apify-actors` | Live Apify Store search |
| `POST /scanner/run`, `GET /scanner/status` | Run all feeds, scan history |

## Activity — `/api/activity` (read-only)

| Method & path | Purpose |
|---|---|
| `GET /alerts` | Per-email job-alert timeline + saved-job summaries |
| `GET /system` | Scanner runs / Gmail polls / ghosted checks + recent errors |

## Gmail — `/api/gmail`

| Method & path | Purpose |
|---|---|
| `POST /send-application` | Send CV + cover letter (test mode by default) |
| `POST /reply` | Send an approved recruiter reply |
| `POST /poll` | Poll the inbox now |
| `POST /test-connection` | Verify IMAP/SMTP credentials |

## PDFs — `/api/pdfs`

| Method & path | Purpose |
|---|---|
| `GET /master-cv`, `/domain-cv/{id}`, `/tailored-cv/{id}`, `/cover-letter/{id}` | Render to PDF |

## Wallet — `/api/wallet`

| Method & path | Purpose |
|---|---|
| `GET /` | Balance + transactions |

---

[← Back to home](index.html) · [Architecture](architecture.md) · [Features](features.md)
