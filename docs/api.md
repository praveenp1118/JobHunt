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

## Career — `/api/career`

| Method & path | Purpose |
|---|---|
| `GET /analysis` | Cached gap analysis (or `available: false`) — never auto-charges |
| `POST /analyse` | Run a fresh batch analysis (subscription-gated; returns tokens + cost) |
| `GET/POST /questions` | The 5 sharpening questions |
| `PATCH /roadmap/{id}` | Toggle a roadmap item → updates readiness |
| `GET /community`, `POST /share` | Anonymised role-level insights (≥2 contributors) |

## Usage — `/api/usage`

| Method & path | Purpose |
|---|---|
| `GET /logs` | Token + cost log with summary and category breakdown |
| `GET /export` | CSV export of usage |

## Community — `/api/community`

| Method & path | Purpose |
|---|---|
| `GET /insights` | Aggregated job insights (only at ≥2 contributors) |
| `POST /share/{job_id}`, `GET /my-contributions` | Contribute / list contributions |
| `PATCH /preferences` | Toggle community sharing |

## Billing — `/api/billing` (Stripe)

| Method & path | Purpose |
|---|---|
| `POST /create-checkout-session`, `GET /subscription`, `POST /cancel` | Subscription lifecycle |
| `POST /webhook`, `GET /verify-session` | Stripe event sync + post-checkout activation |

## Chat — `/api/chat`

| Method & path | Purpose |
|---|---|
| `POST /conversations`, `POST /conversations/{id}/messages` | Guest/user chat + FAQ bot |
| `POST /tickets`, `GET/PATCH …` (admin) | Tickets, presence, admin console |
| `WS /ws/chat/{conversation_id}` | Real-time message push |

## Templates — `/api/templates` (CV template)

| Method & path | Purpose |
|---|---|
| `GET/PUT /cv`, `GET /cv/fonts` | Global CV template (aesthetic + content rules); `max_words` = pages × 300 |
| `GET/PUT/DELETE /domain/{id}` | Per-domain-CV overrides (null = inherit global) |

## Privacy — `/api/privacy` (GDPR self-service)

| Method & path | Purpose |
|---|---|
| `GET /summary`, `GET /rate-limits` | Data summary + remaining rate-limit calls |
| `GET /export` | Download all your data as a ZIP (audited) |
| `POST /delete-request`, `POST /cancel-deletion` | Right-to-erasure with a 30-day grace period |

## Governance — `/api/admin/governance` (admin)

| Method & path | Purpose |
|---|---|
| `GET /` | Audit log + security stats (429s, failed logins, exports, hallucination flags, pending deletions) |
| `POST /cancel-deletion/{user_id}` | Admin override to cancel a scheduled deletion |

## Wallet — `/api/wallet`

| Method & path | Purpose |
|---|---|
| `GET /` | Balance + transactions |

---

[← Back to home](index.html) · [Architecture](architecture.md) · [Features](features.md)
