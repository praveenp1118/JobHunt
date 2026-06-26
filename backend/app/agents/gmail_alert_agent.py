"""
V3 Gmail Job Alert Parser agent.

Detects job-alert digest emails (rule-based, no Claude), extracts careers-page
links from the HTML body, cheaply pre-filters by page title (Playwright title
only — saves ~60% of full fetch + Claude calls), then for matching titles does a
full JD fetch + parse + S1 score and saves qualifying jobs to the tracker with
source=gmail_alert, source_email_id=<alert thread>, detected_domain_cv_id=<best>.
"""
import re
import uuid as uuid_module
from typing import Optional

from bs4 import BeautifulSoup
from sqlalchemy import select


# ── Job-alert detection signals (rule-based, 2+ signals = job_alert) ───────────
SENDER_SIGNALS = [
    "jobs@", "careers@", "jobalert@", "alerts@",
    "noreply@linkedin", "jobs-noreply@linkedin", "jobalerts@linkedin",
    "notifications@indeed", "alert@glassdoor",
]
SUBJECT_SIGNALS = [
    "new job", "new jobs for", "job alert", "jobs for you", "matching jobs",
    "recommended jobs", "jobs matching", "new opening", "your search",
    "job opportunity", "positions matching",
]
# Subjects that look alert-ish but are NOT job alerts — hard exclude (overrides
# all signals + the Claude classifier). Fixes e.g. Google "Security alert".
SUBJECT_EXCLUSIONS = [
    "security alert", "password", "verify your", "sign-in attempt",
    "was recovered", "confirm your email", "verification code",
]

# ── Link filter ───────────────────────────────────────────────────────────────
LINK_KEEP = [
    "/job/", "/jobs/", "/career", "/position/", "/opening/",
    "/vacancy/", "/apply/", "/posting/", "lever.co/",
    "greenhouse.io/", "workday.com/", "taleo.net/", "icims.com/",
]
LINK_SKIP = [
    "unsubscribe", "optout", "privacy", "terms", "mailto:",
    "facebook.com", "twitter.com", "instagram.com",
]
# Aggregator domains whose job links are login-gated — fetching them returns a
# sign-in wall (verified for LinkedIn). For these we extract job cards straight
# from the email HTML instead of fetching the URL.
GATED_DOMAINS = ["linkedin.com", "indeed.com", "naukri.com", "glassdoor.com"]


def is_excluded_subject(subject: str) -> bool:
    s = (subject or "").lower()
    return any(x in s for x in SUBJECT_EXCLUSIONS)


# ── "Email to JobHunt": save a job URL by emailing it to your job-search Gmail ──
SAVE_SUBJECT_SIGNALS = [
    "jobhunt", "job hunt", "save job", "save this job",
    "crawl", "track this", "add to tracker",
]
SAVE_SUBJECT_PREFIXES = ("jh:", "jt:")
_URL_RE = re.compile(r"https?://[^\s\"'<>)\]]+", re.I)
# URLs that are never a job posting (footer/social/tracking links).
_URL_SKIP = ["unsubscribe", "optout", "/privacy", "/terms", "mailto:",
             "facebook.com", "twitter.com", "x.com/", "instagram.com",
             "youtube.com", "linkedin.com/company", "google.com/maps"]


def is_save_job_email(subject: str, body_html: str = "") -> bool:
    """True when the user emailed a job to save it ("Email to JobHunt").
    Rule-based, no Claude: subject contains a save signal OR starts with jh:/jt:."""
    s = (subject or "").strip().lower()
    if not s:
        return False
    if s.startswith(SAVE_SUBJECT_PREFIXES):
        return True
    return any(sig in s for sig in SAVE_SUBJECT_SIGNALS)


def extract_first_url(body_html: str, subject: str = "") -> Optional[str]:
    """First real http(s) URL in the email (anchors first, then any text/subject URL),
    skipping unsubscribe/social/tracking links. Returns None if none found."""
    candidates = []
    if body_html:
        try:
            soup = BeautifulSoup(body_html, "html.parser")
            candidates += [a["href"].strip() for a in soup.find_all("a", href=True)]
        except Exception:
            pass
        candidates += _URL_RE.findall(body_html)
    candidates += _URL_RE.findall(subject or "")
    for u in candidates:
        low = u.lower()
        if not low.startswith("http"):
            continue
        if any(sk in low for sk in _URL_SKIP):
            continue
        return u.rstrip(".,);]")
    return None


def _is_gated_domain(url: str) -> bool:
    u = (url or "").lower()
    return any(d in u for d in GATED_DOMAINS)


def _is_linkedin_url(url: str) -> bool:
    return "linkedin.com" in (url or "").lower()


async def extract_job_links(body_html: str, max_links: int = 10) -> list:
    """Pull job-looking careers links from an email HTML body (KEEP-list filter,
    SKIP-list exclusions, deduped, capped at max_links)."""
    if not body_html:
        return []
    soup = BeautifulSoup(body_html, "html.parser")
    seen, links = set(), []
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        low = href.lower()
        if not low.startswith("http"):
            continue
        if any(s in low for s in LINK_SKIP):
            continue
        if not any(k in low for k in LINK_KEEP):
            continue
        if href in seen:
            continue
        seen.add(href)
        links.append(href)
        if len(links) >= max_links:
            break
    return links


async def is_job_alert_email(subject: str, sender: str, body_html: str) -> bool:
    """Rule-based classification — no Claude call. 2+ signals => job alert.
    Hard-excluded subjects (security alerts etc.) are never job alerts."""
    if is_excluded_subject(subject):
        return False
    subject_l = (subject or "").lower()
    sender_l = (sender or "").lower()
    signals = 0
    if any(s in sender_l for s in SENDER_SIGNALS):
        signals += 1
    if any(s in subject_l for s in SUBJECT_SIGNALS):
        signals += 1
    # body signal: 3+ job-looking links (scan generously, ignore the save cap)
    if len(await extract_job_links(body_html, max_links=50)) >= 3:
        signals += 1
    return signals >= 2


async def check_title_relevance(url: str, target_keywords: list) -> bool:
    """Cheap pre-filter: fetch ONLY the page <title> via Playwright and match it
    against the user's target role keywords. Returns False on any fetch error
    (skip — conservative, saves a full fetch + Claude call)."""
    if not target_keywords:
        return True  # no filter configured -> let everything through
    try:
        from playwright.async_api import async_playwright
        async with async_playwright() as p:
            browser = await p.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
            try:
                page = await browser.new_page()
                await page.goto(url, wait_until="domcontentloaded", timeout=15000)
                title = (await page.title() or "").lower()
            finally:
                await browser.close()
    except Exception as e:
        print(f"⚠️ title relevance check failed for {url}: {e}")
        return False
    return any(kw.lower() in title for kw in target_keywords if kw)


# Noise segments that aren't part of a job's title/company/location
_CARD_NOISE = re.compile(
    r"^(actively recruiting|promoted|easy apply|view job|see (all|more).*|apply|"
    r"\d+\s+(second|minute|hour|day|week|month)s?\s+ago|be an early applicant.*|"
    r"\d+\s+(applicants?|connections?).*)$",
    re.I,
)


def extract_jobs_from_email_body(body_html: str, max_jobs: int = 10) -> list:
    """Extract structured job cards directly from a job-alert email's HTML —
    used for login-gated sources (LinkedIn/Indeed/etc.) where fetching the URL
    just returns a sign-in wall. Each card: {title, company, location, url, snippet}.

    Each specific job link (…/jobs/view/<id>) is a card. The link wraps several
    text segments (role, then "Company · Location", then status); we read those
    SEPARATE segments (a.stripped_strings) rather than the joined blob, and drop
    noise like "Actively recruiting" / "3 days ago"."""
    if not body_html:
        return []
    soup = BeautifulSoup(body_html, "html.parser")
    jobs, seen = [], set()
    for a in soup.find_all("a", href=True):
        low = a["href"].strip().lower()
        # specific job postings only (skip search/aggregate links)
        if not any(p in low for p in ("/jobs/view/", "/viewjob", "/job/")):
            continue
        m = re.search(r"/(?:jobs/view|viewjob|job)[/=](\d+)", low)
        key = m.group(1) if m else a["href"]
        if key in seen:
            continue

        segs = [s.strip() for s in a.stripped_strings if s.strip() and not _CARD_NOISE.match(s.strip())]
        if not segs or len(segs[0]) < 3:
            continue
        seen.add(key)

        title = segs[0]
        company = location = None
        for s in segs[1:]:
            if "·" in s:  # LinkedIn renders "Company · Location"
                parts = [p.strip() for p in s.split("·")]
                company = parts[0] or None
                location = parts[1] if len(parts) > 1 and parts[1] else None
                break
        if company is None and len(segs) > 1:
            company = segs[1]

        jobs.append({
            "title": title,
            "company": company,
            "location": location,
            "url": a["href"].strip(),
            "snippet": " · ".join(segs[:6])[:500],
        })
        if len(jobs) >= max_jobs:
            break
    return jobs


def _is_linkedin_alert(sender: str) -> bool:
    """A LinkedIn-sourced alert — its job links are login-gated, so we read the
    job cards straight from the email body instead of fetching the URL."""
    return "linkedin.com" in (sender or "").lower()


def extract_jobs_from_linkedin_email(body_html: str, max_jobs: int = 10) -> list:
    """Extract job cards directly from a LinkedIn alert email's HTML — no Playwright,
    no gated-URL fetch. LinkedIn renders each posting as a `/jobs/view/<id>` link
    wrapping the role, then "Company · Location". Returns
    [{title, company, location, url, snippet}] for LinkedIn job links only."""
    cards = extract_jobs_from_email_body(body_html, max_jobs=50)
    linkedin = [c for c in cards if "linkedin.com" in (c.get("url") or "").lower()]
    return (linkedin or cards)[:max_jobs]


async def _load_domain_cvs_full(session, user_id) -> list:
    """[(domain_cv_id, content_md, 'Industry × Country')] for active domain CVs
    that have content — used to score each job against ALL of them."""
    from app.models.cv import DomainCV, CVStatus
    from app.models.domain import IndustryVertical

    rows = (await session.execute(
        select(DomainCV.id, DomainCV.content_md, IndustryVertical.label, DomainCV.country_code)
        .outerjoin(IndustryVertical, IndustryVertical.id == DomainCV.industry_id)
        .where(DomainCV.user_id == user_id, DomainCV.status == CVStatus.active,
               DomainCV.content_md.isnot(None))
    )).all()
    return [(dcv_id, content, f"{ind or 'Domain'} × {cc or '—'}")
            for dcv_id, content, ind, cc in rows if content]


async def _score_jobs_vs_domain_cvs(job_inputs, domain_cv_list, anthropic_key, model=None) -> dict:
    """Score a batch of jobs against EVERY active domain CV.
    job_inputs: [{id, role, company, location, description}]; domain_cv_list:
    [(id, content, label)]. Returns {job_id: {dcv_id_str: score}}."""
    from app.agents.scanner_agents import batch_score_s1
    out = {}
    for dcv_id, content, _label in domain_cv_list:
        try:
            for s in await batch_score_s1(content, job_inputs, api_key=anthropic_key, model=model):
                out.setdefault(s["id"], {})[str(dcv_id)] = s.get("s1_score")
        except Exception as e:
            print(f"⚠️ domain CV scoring failed: {e}")
    return out


def _best_domain(dscores: dict):
    """{dcv_id_str: score} -> (best_id_str, best_score) or (None, None)."""
    valid = {k: v for k, v in (dscores or {}).items() if v is not None}
    if not valid:
        return None, None
    best = max(valid, key=valid.get)
    return best, valid[best]


async def _save_gated_cards(cards, user, session, source_email_id, master_cv_md,
                            domain_cv_list, label_map, anthropic_key, min_s1, model=None) -> dict:
    """Save login-gated job cards (LinkedIn etc) extracted from the alert email body.

    Partial-JD cards carry only a ~50-char snippet, so S1 scoring on them is unreliable
    (it produced B=0). We therefore save them UNSCORED — s1/s1d/domain_cv_scores/
    best_domain_cv_id = None, has_partial_jd=True — for the user to review. The full JD is
    fetched + scored later (manual "Fetch full JD" button or background task) from
    portal_url. No Claude tokens are spent here. (master_cv_md / domain_cv_list / label_map /
    anthropic_key / min_s1 / model are accepted for signature stability but unused now.)

    Returns {"saved_ids": [...], "results": [{url, reason, ...}]}."""
    from app.agents.jd_agents import compute_jd_hash, detect_market_from_text, SKIP_WORDS
    from app.models.job import Job, JobSource, JobStatus

    saved_ids, results = [], []
    for c in cards:
        title = c.get("title") or "Unknown"
        company = c.get("company") or "Unknown"
        url = c.get("url")
        snippet = c.get("snippet") or ""
        # Skip cards with no link — a partial-JD job with no portal_url is useless
        # (the user can't open it to read the full JD), and shows as "No link".
        if not url:
            results.append({"url": None, "reason": "no_url", "role": title, "company": company})
            continue
        # Drop clearly non-product roles by title (gated cards have no JD to S1-score,
        # so this is the only filter — e.g. "Head of Surveillance", "Sales Director").
        tl = title.lower()
        if any(sw in tl for sw in SKIP_WORDS):
            results.append({"url": url, "reason": "skipped_non_product", "role": title, "company": company})
            continue
        jd_hash = compute_jd_hash(f"{title} {company} {url}")
        existing = (await session.execute(
            select(Job.id).where(Job.jd_hash == jd_hash, Job.user_id == user.id)
        )).scalars().first()
        if existing:
            results.append({"url": url, "reason": "duplicate", "role": title, "company": company})
            continue
        new_id = uuid_module.uuid4()
        session.add(Job(
            id=new_id,
            user_id=user.id,
            company=company,
            role=title,
            location=c.get("location"),
            market=detect_market_from_text(f"{c.get('location', '')} {snippet}"),
            jd_hash=jd_hash,
            jd_raw=snippet[:50000],
            jd_md=snippet[:50000],
            jd_language="en",
            has_partial_jd=True,   # only the email snippet — full JD is behind portal_url
            portal_url=url,
            source=JobSource.gmail_alert,
            status=JobStatus.new,
            s1=None, s1d=None,     # unscored — snippet too short to score reliably
            domain_cv_scores=None,
            best_domain_cv_id=None,
            source_email_id=source_email_id,
            detected_domain_cv_id=None,
        ))
        saved_ids.append(str(new_id))
        # Auto-queue a background fetch+score ONLY for non-LinkedIn (public ATS) URLs —
        # LinkedIn needs a login, so fetching it just hits a sign-in wall. The countdown
        # gives the caller time to commit the new job before the worker picks it up.
        if _is_linkedin_url(url):
            print(f"⏭️  Skipped auto-fetch — LinkedIn gated: {title}")
        else:
            try:
                from app.tasks.gmail_tasks import fetch_partial_jd
                fetch_partial_jd.apply_async(args=[str(new_id), str(user.id)], countdown=15)
                print(f"🔁 Queued auto-fetch for public URL: {url}")
            except Exception as e:
                print(f"⚠️ could not queue auto-fetch for {url}: {e}")
        results.append({"url": url, "reason": "saved_unscored", "role": title,
                        "company": company, "gated": True, "partial_jd": True})
    return {"saved_ids": saved_ids, "results": results}


async def process_job_alert_email(
    email_thread,
    body_html: str,
    user,
    session,
    anthropic_key: Optional[str],
    model: Optional[str],
    prefs,
    poll_run_id=None,
) -> dict:
    """Orchestrate one job-alert email: gated sources (LinkedIn/Indeed) → read job
    cards from the email body; public ATS links → title pre-filter + fetch + parse
    + S1 score. Saves qualifying jobs, updates the thread counters, and writes an
    EmailAlertLog capturing exactly what happened. The caller owns the commit.

    NOTE: body_html is passed explicitly because EmailThread only persists a
    500-char body_preview, not the full HTML needed for link extraction.
    """
    from app.agents.jd_agents import (
        compute_jd_hash, parse_and_score_jd, fetch_url_content,
        detect_market_from_text, TARGET_TITLE_KEYWORDS,
    )
    from app.models.job import Job, JobSource, JobStatus
    from app.models.cv import MasterCV
    from app.models.admin import EmailAlertLog

    max_links = getattr(prefs, "job_alert_max_links", 10) or 10
    min_s1 = getattr(prefs, "s1_min_threshold", 65) or 65
    title_filter = getattr(prefs, "job_alert_title_filter", True)

    links = await extract_job_links(body_html, max_links)
    public_links = [l for l in links if not _is_gated_domain(l)]
    gated_present = any(_is_gated_domain(l) for l in links)
    links_found = len(links)
    links_gated = sum(1 for l in links if _is_gated_domain(l))
    links_public = len(public_links)

    # Login-gated sources (LinkedIn/Indeed/…): read job cards from the email HTML
    # instead of fetching the sign-in-walled URL. Always do this for LinkedIn-sent
    # alerts (their cards live in the body even if link detection is conservative).
    is_linkedin = _is_linkedin_alert(getattr(email_thread, "from_email", "") or "")
    cards = extract_jobs_from_email_body(body_html, max_links) if (gated_present or is_linkedin) else []

    def _log(saved_ids, results):
        below = sum(1 for r in results if r.get("reason") == "below_threshold")
        dup = sum(1 for r in results if r.get("reason") == "duplicate")
        email_thread.jobs_extracted = len(public_links) + len(cards)
        email_thread.jobs_saved = len(saved_ids)
        session.add(EmailAlertLog(
            poll_run_id=poll_run_id,
            user_id=user.id,
            email_subject=email_thread.subject,
            sender=email_thread.from_email,
            received_at=email_thread.received_at,
            links_found=links_found,
            links_gated=links_gated,
            links_public=links_public,
            links_below_threshold=below,
            links_duplicate=dup,
            jobs_saved=len(saved_ids),
            saved_job_ids=saved_ids or None,
            skip_reasons=results or None,
        ))
        return {"extracted": len(public_links) + len(cards), "saved": len(saved_ids)}

    if not public_links and not cards:
        return _log([], [])

    # Target keywords for the cheap title pre-filter: canonical set + user roles
    target_keywords = list(TARGET_TITLE_KEYWORDS)
    if getattr(prefs, "target_roles", None):
        target_keywords += [r.strip().lower() for r in prefs.target_roles.split(",") if r.strip()]

    # Master CV for S1 scoring; domain CVs for best-match tagging
    master = (await session.execute(
        select(MasterCV).where(MasterCV.user_id == user.id, MasterCV.is_active == True)
    )).scalars().first()
    master_cv_md = master.content_md if master else ""
    # Hybrid-RAG Stage 1 keyword filter (free) for the public-URL path.
    _essence_kw = [str(k).lower() for k in ((master.essence_json or {}).get("keywords") or [])] if master else []
    _kw_threshold = 0
    if _essence_kw:
        try:
            from app.models.user import UserPreferences
            from app.agents.rag_scorer import config_from_prefs
            _p = (await session.execute(
                select(UserPreferences).where(UserPreferences.user_id == user.id))).scalars().first()
            _kw_threshold = config_from_prefs(_p)["keyword_match_threshold"]
        except Exception:
            _kw_threshold = 3
    # ALL active domain CVs (id, content, label) — each job is scored against every one.
    domain_cv_list = await _load_domain_cvs_full(session, user.id)
    label_map = {str(dcv_id): label for dcv_id, _content, label in domain_cv_list}

    def _labelled(d):
        return {label_map.get(k, k): v for k, v in (d or {}).items()}

    saved_ids, results = [], []

    # ── Gated path: lightweight S1 score from the email card (no fetch) ──────
    if cards:
        try:
            gated = await _save_gated_cards(
                cards, user, session, email_thread.id,
                master_cv_md, domain_cv_list, label_map, anthropic_key, min_s1, model)
            saved_ids += gated["saved_ids"]
            results += gated["results"]
        except Exception as e:
            print(f"⚠️ job alert: gated card path failed: {e}")

    # ── Public ATS path: title pre-filter -> fetch -> full parse + S1 score ──
    for url in public_links:
        try:
            if title_filter and not await check_title_relevance(url, target_keywords):
                results.append({"url": url, "reason": "title_skip"})
                continue

            content = await fetch_url_content(url)
            if not content or len(content) < 100:
                results.append({"url": url, "reason": "fetch_failed"})
                continue

            # RAG Stage 1 (free): skip public jobs with low keyword overlap vs the master essence.
            if _essence_kw and _kw_threshold:
                _m = sum(1 for k in _essence_kw if k in content.lower())
                if _m < _kw_threshold:
                    results.append({"url": url, "reason": f"stage1_keyword_{_m}/{_kw_threshold}"})
                    continue

            jd_hash = compute_jd_hash(content)
            existing = (await session.execute(
                select(Job.id).where(Job.jd_hash == jd_hash, Job.user_id == user.id)
            )).scalars().first()
            if existing:
                results.append({"url": url, "reason": "duplicate"})
                continue

            result = await parse_and_score_jd(content, master_cv_md, anthropic_key, model=model)
            s1 = result.get("s1_score", 0) or 0
            parsed = result.get("parsed", {})
            company = parsed.get("company") or "Unknown"
            role = parsed.get("role") or "Unknown"

            # Score this job against ALL active domain CVs; the best one drives the
            # threshold decision (best S1d when domain CVs exist, else S1).
            job_input = [{"id": "j", "role": role, "company": company,
                          "location": parsed.get("location") or "", "description": content[:500]}]
            dscores = (await _score_jobs_vs_domain_cvs(
                job_input, domain_cv_list, anthropic_key, model)).get("j", {})
            best_id, best_s1d = _best_domain(dscores)
            has_domain = best_s1d is not None
            decision = best_s1d if has_domain else s1
            if decision < min_s1:
                results.append({"url": url, "reason": "below_threshold", "s1": s1, "s1d": best_s1d,
                                "domain_scores": _labelled(dscores), "best_domain_cv": label_map.get(best_id),
                                "role": role, "company": company})
                continue

            new_id = uuid_module.uuid4()
            session.add(Job(
                id=new_id,
                user_id=user.id,
                company=company,
                role=role,
                location=parsed.get("location"),
                market=parsed.get("market") or detect_market_from_text(content),
                jd_hash=jd_hash,
                jd_raw=content[:50000],
                jd_md=content[:50000],
                jd_language=parsed.get("jd_language") or "en",
                portal_url=url,
                source=JobSource.gmail_alert,
                status=JobStatus.new,
                s1=s1,
                s1d=best_s1d,
                domain_cv_scores=(dscores or None),
                best_domain_cv_id=(uuid_module.UUID(best_id) if best_id else None),
                source_email_id=email_thread.id,
                detected_domain_cv_id=(uuid_module.UUID(best_id) if best_id else None),
            ))
            saved_ids.append(str(new_id))
            results.append({"url": url, "reason": "saved", "s1": s1, "s1d": best_s1d,
                            "domain_scores": _labelled(dscores), "best_domain_cv": label_map.get(best_id),
                            "decision": "s1d" if has_domain else "s1",
                            "role": role, "company": company})
        except Exception as e:
            print(f"⚠️ job alert: failed to process {url}: {e}")
            results.append({"url": url, "reason": "error"})
            continue

    return _log(saved_ids, results)


async def process_save_job_email(
    email_thread,
    body_html: str,
    subject: str,
    user,
    session,
    anthropic_key: Optional[str],
    model: Optional[str],
    prefs,
    poll_run_id=None,
) -> dict:
    """"Email to JobHunt": the user emailed a job URL to their job-search Gmail.
    Extract the first URL, fetch + parse + score it (full RAG: S1 vs master + S1d vs
    all domain CVs — NO threshold gate, the user explicitly asked to save it), and save
    it to the tracker with source=manual, status=new, portal_url=<url>. Writes an
    EmailAlertLog (reason="email_to_jobhunt") for the Activity timeline and returns the
    outcome dict (the caller sends the confirmation email + owns the commit).

    Returns {saved, action: saved|duplicate|no_url|fetch_failed, company?, role?, s1?,
    s1d?, job_id?, url?}."""
    from app.agents.jd_agents import (
        compute_jd_hash, parse_and_score_jd, fetch_url_content, detect_market_from_text,
    )
    from app.models.job import Job, JobSource, JobStatus
    from app.models.cv import MasterCV
    from app.models.admin import EmailAlertLog

    url = extract_first_url(body_html, subject)

    def _log(saved_ids, entry):
        email_thread.jobs_extracted = 1 if url else 0
        email_thread.jobs_saved = len(saved_ids)
        session.add(EmailAlertLog(
            poll_run_id=poll_run_id,
            user_id=user.id,
            email_subject=email_thread.subject,
            sender=email_thread.from_email,
            received_at=email_thread.received_at,
            links_found=1 if url else 0,
            links_public=1 if url else 0,
            jobs_saved=len(saved_ids),
            saved_job_ids=saved_ids or None,
            skip_reasons=[entry],
        ))
        return {"saved": len(saved_ids), **entry}

    if not url:
        # Phase 2 (not implemented): subject like "jh: Head of Product at Adyen" with no URL
        # → search Apify/Google for the role+company and save the best match.
        return _log([], {"reason": "email_to_jobhunt", "action": "no_url", "subject": subject})

    # Already tracked from the same URL? Don't duplicate.
    existing = (await session.execute(
        select(Job).where(Job.user_id == user.id, Job.portal_url == url)
    )).scalars().first()
    if existing:
        return _log([], {"reason": "email_to_jobhunt", "action": "duplicate", "url": url,
                         "company": existing.company, "role": existing.role,
                         "job_id": str(existing.id)})

    try:
        content = await fetch_url_content(url)
    except Exception as e:
        print(f"⚠️ email-to-jobhunt: fetch failed for {url}: {e}")
        content = ""
    if not content or len(content) < 100:
        return _log([], {"reason": "email_to_jobhunt", "action": "fetch_failed", "url": url})

    master = (await session.execute(
        select(MasterCV).where(MasterCV.user_id == user.id, MasterCV.is_active == True)
    )).scalars().first()
    master_cv_md = master.content_md if master else ""

    result = await parse_and_score_jd(content, master_cv_md, anthropic_key, model=model)
    s1 = result.get("s1_score", 0) or 0
    parsed = result.get("parsed", {})
    company = parsed.get("company") or "Unknown"
    role = parsed.get("role") or "Unknown"

    domain_cv_list = await _load_domain_cvs_full(session, user.id)
    job_input = [{"id": "j", "role": role, "company": company,
                  "location": parsed.get("location") or "", "description": content[:500]}]
    dscores = (await _score_jobs_vs_domain_cvs(
        job_input, domain_cv_list, anthropic_key, model)).get("j", {})
    best_id, best_s1d = _best_domain(dscores)

    new_id = uuid_module.uuid4()
    session.add(Job(
        id=new_id,
        user_id=user.id,
        company=company,
        role=role,
        location=parsed.get("location"),
        market=parsed.get("market") or detect_market_from_text(content),
        jd_hash=compute_jd_hash(content),
        jd_raw=content[:50000],
        jd_md=content[:50000],
        jd_language=parsed.get("jd_language") or "en",
        portal_url=url,
        source=JobSource.manual,          # user-initiated
        status=JobStatus.new,
        s1=s1,
        s1d=best_s1d,
        domain_cv_scores=(dscores or None),
        best_domain_cv_id=(uuid_module.UUID(best_id) if best_id else None),
        source_email_id=email_thread.id,
        detected_domain_cv_id=(uuid_module.UUID(best_id) if best_id else None),
    ))
    return _log([str(new_id)], {"reason": "email_to_jobhunt", "action": "saved", "url": url,
                                "company": company, "role": role, "s1": s1, "s1d": best_s1d,
                                "job_id": str(new_id)})


async def fetch_and_rescore_partial_job(job_id, user, session, anthropic_key, model=None) -> dict:
    """Fetch the full JD for a partial-JD (gmail_alert) job from its portal_url and
    re-score it properly.

    On success (page > 500 chars): stores the full JD and computes S1 (master CV) +
    S1d (all active domain CVs) + best_domain_cv_id, then clears has_partial_jd.
    On a login wall / thin page: leaves has_partial_jd=True ("Login-gated, cannot fetch").

    Returns {"status": "scored"|"gated"|"not_found"|"no_url", ...}."""
    from app.agents.jd_agents import fetch_url_content, parse_and_score_jd
    from app.models.job import Job
    from app.models.cv import MasterCV

    job = (await session.execute(
        select(Job).where(Job.id == job_id, Job.user_id == user.id)
    )).scalar_one_or_none()
    if not job:
        return {"status": "not_found"}
    if not job.portal_url:
        return {"status": "no_url", "message": "No portal URL to fetch"}

    try:
        content = await fetch_url_content(job.portal_url)
    except Exception as e:
        print(f"⚠️ fetch_and_rescore: fetch failed for {job.portal_url}: {e}")
        content = ""

    if not content or len(content) < 500:
        print(f"ℹ️ fetch_and_rescore: login-gated / thin page, cannot fetch full JD ({job.portal_url})")
        return {"status": "gated", "message": "Login-gated, cannot fetch"}

    master = (await session.execute(
        select(MasterCV).where(MasterCV.user_id == user.id, MasterCV.is_active == True)
    )).scalars().first()
    master_cv_md = master.content_md if master else ""

    result = await parse_and_score_jd(content, master_cv_md, anthropic_key, model=model)
    s1 = result.get("s1_score", 0) or 0
    parsed = result.get("parsed", {})

    # Score against every active domain CV; best one drives S1d / best_domain_cv_id.
    domain_cv_list = await _load_domain_cvs_full(session, user.id)
    job_input = [{"id": "j",
                  "role": job.role or parsed.get("role") or "",
                  "company": job.company or parsed.get("company") or "",
                  "location": job.location or parsed.get("location") or "",
                  "description": content[:500]}]
    dscores = (await _score_jobs_vs_domain_cvs(
        job_input, domain_cv_list, anthropic_key, model)).get("j", {})
    best_id, best_s1d = _best_domain(dscores)

    job.jd_raw = content[:50000]
    job.jd_md = content[:50000]
    job.s1 = s1
    job.s1d = best_s1d
    job.domain_cv_scores = (dscores or None)
    job.best_domain_cv_id = (uuid_module.UUID(best_id) if best_id else None)
    if best_id:
        job.detected_domain_cv_id = uuid_module.UUID(best_id)
    if parsed.get("market"):
        job.market = parsed.get("market")
    job.has_partial_jd = False
    await session.commit()
    return {"status": "scored", "s1": s1, "s1d": best_s1d,
            "best_domain_cv_id": best_id, "job_id": str(job_id)}


async def rescore_partial_job_from_text(job_id, user, session, anthropic_key, model=None) -> dict:
    """Score a partial-JD job from the JD text the user pasted (already saved to job.jd_raw —
    no fetch, no login wall). Computes S1 (master CV) + S1d (all active domain CVs) +
    best_domain_cv_id and clears has_partial_jd. Returns {"status": "scored"|...}."""
    from app.agents.jd_agents import parse_and_score_jd
    from app.models.job import Job
    from app.models.cv import MasterCV

    job = (await session.execute(
        select(Job).where(Job.id == job_id, Job.user_id == user.id)
    )).scalar_one_or_none()
    if not job:
        return {"status": "not_found"}
    content = (job.jd_raw or "").strip()
    if len(content) < 100:
        return {"status": "too_short", "message": "Pasted JD is too short to score"}

    master = (await session.execute(
        select(MasterCV).where(MasterCV.user_id == user.id, MasterCV.is_active == True)
    )).scalars().first()
    master_cv_md = master.content_md if master else ""

    result = await parse_and_score_jd(content, master_cv_md, anthropic_key, model=model)
    s1 = result.get("s1_score", 0) or 0
    parsed = result.get("parsed", {})

    domain_cv_list = await _load_domain_cvs_full(session, user.id)
    job_input = [{"id": "j",
                  "role": job.role or parsed.get("role") or "",
                  "company": job.company or parsed.get("company") or "",
                  "location": job.location or parsed.get("location") or "",
                  "description": content[:500]}]
    dscores = (await _score_jobs_vs_domain_cvs(
        job_input, domain_cv_list, anthropic_key, model)).get("j", {})
    best_id, best_s1d = _best_domain(dscores)

    job.s1 = s1
    job.s1d = best_s1d
    job.domain_cv_scores = (dscores or None)
    job.best_domain_cv_id = (uuid_module.UUID(best_id) if best_id else None)
    if best_id:
        job.detected_domain_cv_id = uuid_module.UUID(best_id)
    if parsed.get("market"):
        job.market = parsed.get("market")
    job.has_partial_jd = False
    await session.commit()
    return {"status": "scored", "s1": s1, "s1d": best_s1d,
            "best_domain_cv_id": best_id, "job_id": str(job_id)}
