"""
V2 Feed agents — auto-generate feed profiles from domain CVs using Claude.
Each domain CV gets a personalised feed profile with:
- Search keywords generated from CV content
- Domain-specific job boards based on industry vertical
"""
import json
from typing import Optional

from app.utils.usage_logger import log_call

# ── Domain-specific job boards per industry vertical ─────────────────────────

DOMAIN_JOB_BOARDS = {
    "EC": [  # eCommerce & Marketplace
        {"name": "Indeed NL", "type": "rss", "url": "https://nl.indeed.com/rss?q={keywords}&l=Netherlands"},
        {"name": "Indeed AE", "type": "rss", "url": "https://ae.indeed.com/rss?q={keywords}&l=Dubai"},
        {"name": "eCommerce Jobs", "type": "rss", "url": "https://www.ecommercejobs.com/rss?q={keywords}"},
        {"name": "Retail Gazette Jobs", "type": "rss", "url": "https://www.retailgazette.co.uk/jobs/feed/?s={keywords}"},
    ],
    "AI": [  # AI & Data Products
        {"name": "Indeed NL", "type": "rss", "url": "https://nl.indeed.com/rss?q={keywords}&l=Netherlands"},
        {"name": "AI Jobs", "type": "rss", "url": "https://aijobs.net/feed/?search={keywords}"},
        {"name": "MLOps Jobs", "type": "rss", "url": "https://mlops.community/jobs/feed/?s={keywords}"},
        {"name": "LinkedIn AI", "type": "apify", "url": "apify/linkedin-jobs-scraper"},
    ],
    "FP": [  # Fintech & Payments
        {"name": "Indeed NL", "type": "rss", "url": "https://nl.indeed.com/rss?q={keywords}&l=Netherlands"},
        {"name": "eFinancialCareers", "type": "rss", "url": "https://www.efinancialcareers.com/rss/jobs?q={keywords}"},
        {"name": "Fintech Jobs", "type": "rss", "url": "https://fintechjobs.com/feed/?s={keywords}"},
    ],
    "BS": [  # B2B SaaS
        {"name": "Indeed NL", "type": "rss", "url": "https://nl.indeed.com/rss?q={keywords}&l=Netherlands"},
        {"name": "Work at a Startup", "type": "rss", "url": "https://www.workatastartup.com/jobs/feed?q={keywords}"},
        {"name": "Remotive", "type": "rss", "url": "https://remotive.com/remote-jobs/feed/product-management"},
    ],
    "HT": [  # HealthTech
        {"name": "Indeed NL", "type": "rss", "url": "https://nl.indeed.com/rss?q={keywords}&l=Netherlands"},
        {"name": "Healthcare IT News", "type": "rss", "url": "https://www.healthcareitnews.com/jobs/feed?q={keywords}"},
    ],
    "SC": [  # Supply Chain
        {"name": "Indeed NL", "type": "rss", "url": "https://nl.indeed.com/rss?q={keywords}&l=Netherlands"},
        {"name": "Supply Chain Jobs", "type": "rss", "url": "https://www.supplychainjobs.com/rss?q={keywords}"},
    ],
}

# Default boards for any industry
DEFAULT_BOARDS = [
    {"name": "Indeed NL", "type": "rss", "url": "https://nl.indeed.com/rss?q={keywords}&l=Netherlands"},
    {"name": "Indeed AE", "type": "rss", "url": "https://ae.indeed.com/rss?q={keywords}&l=Dubai"},
    {"name": "Indeed SG", "type": "rss", "url": "https://sg.indeed.com/rss?q={keywords}&l=Singapore"},
    {"name": "Jobicy NL", "type": "rss", "url": "https://jobicy.com/feed/job_feed?search_keywords={keywords}&search_region=netherlands"},
    {"name": "LinkedIn Jobs", "type": "apify", "url": "apify/linkedin-jobs-scraper"},
]

MARKET_BOARD_MAP = {
    "NL": ["Indeed NL", "Jobicy NL"],
    "EU": ["Indeed NL", "Jobicy NL"],
    "DU": ["Indeed AE"],
    "Dubai": ["Indeed AE"],
    "SG": ["Indeed SG"],
    "IN": ["Indeed IN"],
}

# Known Apify actors offered in the "Add feed" modal (not free text). The actor_id
# substring (linkedin/google/indeed) is what the scanner uses to pick the right
# input builder + normaliser (see apify_mcp.normalise_job).
KNOWN_APIFY_ACTORS = [
    {"name": "LinkedIn Jobs", "actor_id": "apify/linkedin-jobs-scraper"},
    {"name": "Google Jobs", "actor_id": "apify/google-jobs-scraper"},
    {"name": "Indeed Jobs", "actor_id": "apify/indeed-scraper"},
]


def get_rss_board_options(industry_code: str, country_code: str, keywords: str) -> list:
    """RSS board options for the Add-feed modal: each entry has a ready-to-use
    `url` (keywords substituted) plus the `url_template` so the client can
    re-substitute if the user edits keywords."""
    encoded = (keywords or "").strip().replace(" ", "+")
    options = []
    for board in get_boards_for_domain(industry_code, country_code):
        if board.get("type") != "rss":
            continue
        template = board["url"]
        options.append({
            "name": board["name"],
            "url": template.replace("{keywords}", encoded),
            "url_template": template,
        })
    return options


def get_boards_for_domain(industry_code: str, country_code: str) -> list:
    """Get domain-specific job boards, filtered by market."""
    # Copy — never mutate the shared DOMAIN_JOB_BOARDS / DEFAULT_BOARDS constants
    # (repeated calls would otherwise keep appending duplicate market boards).
    boards = list(DOMAIN_JOB_BOARDS.get(industry_code, DEFAULT_BOARDS))

    # Add market-specific Indeed if not already present
    market_boards = MARKET_BOARD_MAP.get(country_code, [])
    existing_names = {b["name"] for b in boards}
    for board in DEFAULT_BOARDS:
        if board["name"] in market_boards and board["name"] not in existing_names:
            boards.append(board)

    return boards


# Keyword generation is a simple task — Haiku is sufficient (was Sonnet).
FEED_KEYWORDS_MODEL = "claude-haiku-4-5"


async def generate_feed_keywords(
    domain_cv_content: str,
    industry_label: str,
    function_label: str,
    country_code: str,
    api_key: str,
    model: str = FEED_KEYWORDS_MODEL,
    essence: Optional[dict] = None,
) -> dict:
    """
    Use Claude (Haiku) to generate personalised search keywords from a domain CV.
    Prefers the compact CV essence (keywords + domain strengths) over the full CV text
    — much smaller input → cheaper. Returns: { search_keywords: str, feed_name: str }
    """
    from anthropic import Anthropic

    client = Anthropic(api_key=api_key)

    # Compact essence context when available (keywords + domain strengths), else CV excerpt.
    if essence:
        kws = ", ".join(map(str, (essence.get("keywords") or [])[:20]))
        strengths = ", ".join((essence.get("domain_strengths") or {}).keys())
        cv_context = f"Candidate keywords: {kws}\nDomain strengths: {strengths}\n" \
                     f"Identity: {essence.get('core_identity', '')}"
    else:
        cv_context = f"Domain CV excerpt (first 2000 chars):\n{domain_cv_content[:2000]}"

    prompt = f"""You are a job search assistant. Based on this domain CV for a {function_label} professional in {industry_label}, targeting {country_code}, generate optimal job search keywords.

{cv_context}

Generate:
1. A short search query (5-8 words) for job boards like Indeed/LinkedIn
2. A human-readable feed profile name

Rules:
- Keywords should be specific to this domain + function combination
- Include the seniority level (e.g. head, VP, director, lead)
- Include domain-specific terms (e.g. "ecommerce marketplace" for EC, "AI machine learning" for AI)
- Keep it natural for job board search

Respond ONLY with valid JSON, no markdown:
{{"search_keywords": "director financial planning fintech", "feed_name": "Fintech Finance Leadership — NL"}}"""

    response = client.messages.create(
        model=model,
        max_tokens=200,
        messages=[{"role": "user", "content": prompt}],
    )
    await log_call("generate_feed_keywords", "other", response, model)

    text = response.content[0].text.strip()
    # Strip markdown if present
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    text = text.strip()

    result = json.loads(text)
    return result


async def create_feed_profile_for_domain_cv(
    domain_cv_id: str,
    user_id: str,
    session,
    api_key: str,
    model: str = "claude-sonnet-4-5",
) -> Optional[dict]:
    """
    Auto-create a feed profile when a domain CV is generated.
    Called from cv_agents.py after domain CV is applied.
    """
    from sqlalchemy import select
    from app.models.cv import DomainCV
    from app.models.domain import UserFeed, IndustryVertical, FunctionalDiscipline
    import uuid as uuid_module

    # Load domain CV with industry + function labels
    cv_result = await session.execute(
        select(DomainCV).where(DomainCV.id == domain_cv_id)
    )
    cv = cv_result.scalar_one_or_none()
    if not cv or not cv.content_md:
        return None

    # Load industry + function labels
    industry_label = "Product"
    function_label = "Product Management"
    industry_code = "GN"  # generic

    if cv.industry_id:
        ind_result = await session.execute(
            select(IndustryVertical).where(IndustryVertical.id == cv.industry_id)
        )
        ind = ind_result.scalar_one_or_none()
        if ind:
            industry_label = ind.label
            industry_code = ind.code

    if cv.function_id:
        fn_result = await session.execute(
            select(FunctionalDiscipline).where(FunctionalDiscipline.id == cv.function_id)
        )
        fn = fn_result.scalar_one_or_none()
        if fn:
            function_label = fn.label

    # Check if feed profile already exists for this domain CV
    existing = await session.execute(
        select(UserFeed).where(
            UserFeed.user_id == user_id,
            UserFeed.domain_cv_id == domain_cv_id,
            UserFeed.is_auto_generated == True,
        )
    )
    if existing.scalar_one_or_none():
        return None  # already exists

    # Generate keywords with Claude
    try:
        result = await generate_feed_keywords(
            domain_cv_content=cv.content_md,
            industry_label=industry_label,
            function_label=function_label,
            country_code=cv.country_code or "NL",
            api_key=api_key,
            essence=cv.essence_json,
        )
        search_keywords = result.get("search_keywords", f"head of product {industry_label.lower()}")
        feed_name = result.get("feed_name", f"{industry_label} × {function_label}")
    except Exception as e:
        print(f"Keyword generation failed: {e}, using defaults")
        search_keywords = f"head of product {industry_label.lower()}"
        feed_name = f"{industry_label} × {function_label}"

    # Get domain-specific boards
    boards = get_boards_for_domain(industry_code, cv.country_code or "NL")
    boards_json = json.dumps(boards)

    # Create the primary feed entry (RSS-based, using first relevant board URL)
    primary_board = boards[0] if boards else DEFAULT_BOARDS[0]
    feed_url = primary_board["url"].replace("{keywords}", search_keywords.replace(" ", "+"))

    feed = UserFeed(
        id=uuid_module.uuid4(),
        user_id=user_id,
        feed_type=primary_board["type"],
        name=feed_name,
        url_or_actor=feed_url,
        is_active=True,
        is_platform=False,
        keywords=search_keywords,
        domain_cv_id=domain_cv_id,
        search_keywords=search_keywords,
        job_boards=boards_json,
        is_auto_generated=True,
    )
    session.add(feed)
    await session.flush()

    return {
        "feed_id": str(feed.id),
        "feed_name": feed_name,
        "search_keywords": search_keywords,
        "boards_count": len(boards),
    }
