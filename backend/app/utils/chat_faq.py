"""Rule-based support FAQ — keyword matching, NO Claude/AI.

Used by the chat router when no admin is online: match the user's message to a
canned answer, or fall back to suggesting a ticket.
"""
from typing import Optional

FAQ_RULES = [
    {
        "id": "anthropic_key",
        "keywords": ["anthropic", "claude api", "api key", "anthropic key",
                     "claude key", "get key", "where key"],
        "category": "api_keys",
        "answer": """To get your Anthropic API key:
1. Go to console.anthropic.com
2. Sign up or login
3. Click "API Keys" in the left sidebar
4. Click "Create Key"
5. Copy and paste into Settings → Plan & Keys

💡 New accounts get $5 free credit — enough for weeks of job searching.""",
        "links": [{"text": "Open Anthropic Console", "url": "https://console.anthropic.com"}],
    },
    {
        "id": "apify_token",
        "keywords": ["apify", "apify token", "linkedin scraper", "google scraper",
                     "apify key", "scraping", "scanner not working"],
        "category": "api_keys",
        "answer": """To get your Apify token:
1. Go to apify.com
2. Sign up (free — $5 credit included)
3. Click your profile → Settings
4. Go to "Integrations" tab
5. Copy "Personal API token"
6. Paste into Settings → Plan & Keys

💡 Free tier is enough for weeks of scanning.""",
        "links": [{"text": "Open Apify", "url": "https://apify.com"}],
    },
    {
        "id": "gmail_password",
        "keywords": ["gmail", "app password", "gmail password", "email not working",
                     "gmail not connecting", "imap", "smtp"],
        "category": "api_keys",
        "answer": """To get your Gmail App Password:
1. Go to myaccount.google.com
2. Security → enable 2-Step Verification (required)
3. Search "App passwords" in the search bar
4. Select app: Mail, Device: Other → type "AIJobsHunt"
5. Copy the 16-character password
6. Paste into Settings → Gmail

💡 Use a dedicated job search Gmail account, not your personal one.""",
        "links": [{"text": "Open Google Account", "url": "https://myaccount.google.com/apppasswords"}],
    },
    {
        "id": "pricing",
        "keywords": ["price", "cost", "pricing", "how much", "subscription",
                     "₹500", "plan", "fee", "charge"],
        "category": "billing",
        "answer": """AIJobsHunt Pro costs ₹500/month.

Includes:
✅ Full access to all features
✅ CV tailoring with AI
✅ Job scanning (RSS + LinkedIn + Google)
✅ Gmail integration
✅ Activity dashboard

You bring your own Anthropic + Apify API keys.
Cancel anytime from Settings → Plan & Keys.""",
    },
    {
        "id": "cancel",
        "keywords": ["cancel", "unsubscribe", "stop subscription", "end plan"],
        "category": "billing",
        "answer": """To cancel your subscription:
1. Go to Settings → Plan & Keys
2. Click "Cancel plan"
3. Your access continues until the end of the billing period
4. No automatic refunds for partial months

Need help? Create a ticket and we'll assist you.""",
    },
    {
        "id": "scores",
        "keywords": ["score", "s1", "s2", "s3", "b score", "best fit",
                     "what does score mean", "scoring", "fit score"],
        "category": "features",
        "answer": """AIJobsHunt uses 4 scores for each job:

B (S1): Base fit — your master CV vs job description
Best (S1d): Domain fit — your best domain CV vs JD
T (S2): Tailored fit — after CV tailoring is applied
F (S3): Factual integrity — 100% means nothing was invented

Aim for Best Fit ≥ 80 before applying.
T and F only appear after you tailor the CV.""",
    },
    {
        "id": "tailoring",
        "keywords": ["tailor", "tailoring", "cv tailor", "customize cv",
                     "modify cv", "how tailor works", "change cv"],
        "category": "features",
        "answer": """CV Tailoring works like this:
1. Click "Tailor →" on any job
2. AIJobsHunt suggests changes (reorder, rephrase, keywords)
3. You approve or reject each change
4. Click "Generate tailored CV + cover letter"
5. Review and send application

Golden rule: AIJobsHunt NEVER invents experience.
It only changes HOW things are presented, not WHAT you've done.""",
    },
    {
        "id": "domain_cvs",
        "keywords": ["domain cv", "domain cvs", "what is domain",
                     "industry cv", "multiple cv"],
        "category": "features",
        "answer": """Domain CVs are specialised versions of your master CV.

Example: you might have:
- AI Products × Netherlands
- eCommerce × Dubai
- Fintech × Singapore

Each domain CV is scored against jobs separately.
The "Best Fit" score shows which domain CV fits best.
AIJobsHunt auto-selects the best domain CV when tailoring.""",
    },
    {
        "id": "scanner",
        "keywords": ["scanner", "scan", "no jobs", "not finding jobs",
                     "feeds", "rss", "linkedin jobs", "job search"],
        "category": "features",
        "answer": """If the scanner isn't finding jobs:

1. Check Settings → Feeds & Scanning
   → Are feeds toggled ON?

2. Check Settings → Plan & Keys
   → Is Apify token connected? (needed for LinkedIn/Google)

3. Check Activity → System → expand latest scan
   → See exactly which feeds ran and why jobs were rejected

RSS feeds work without Apify.
LinkedIn + Google Jobs require an Apify token.""",
    },
    {
        "id": "gmail_alerts",
        "keywords": ["gmail alert", "job alert", "alert not working",
                     "email alert", "linkedin alert", "partial jd"],
        "category": "features",
        "answer": """For Gmail job alerts:

1. Settings → Gmail → Test connection (confirm connected)
2. Settings → Gmail → "Parse job alert emails" must be ON
3. Activity → Job Alerts → see what was processed

LinkedIn alert jobs show "Partial JD" badge because
LinkedIn requires login to view full job descriptions.
Click "Fetch full JD" button on those jobs to try fetching.""",
    },
    {
        "id": "add_job",
        "keywords": ["add job", "manual job", "paste job", "upload job",
                     "how to add", "new job"],
        "category": "features",
        "answer": """To add a job manually:
1. Go to Jobs page
2. Click "+ Add job" button
3. Choose: paste URL, paste JD text, or upload PDF
4. AIJobsHunt parses and scores automatically
5. Job appears in your tracker""",
    },
    {
        "id": "privacy",
        "keywords": ["privacy", "data", "safe", "secure", "gdpr",
                     "my data", "stored"],
        "category": "general",
        "answer": """Your data security:

✅ CV and job data stored in your local Docker instance
✅ API keys encrypted with AES-256
✅ We never share data with third parties
✅ GDPR-compliant for EU job applications

You own and control all your data.""",
    },
]


def match_faq(message: str) -> Optional[dict]:
    """Match a user message to an FAQ rule. Returns the rule dict or None."""
    message_lower = (message or "").lower()
    for rule in FAQ_RULES:
        if any(kw in message_lower for kw in rule["keywords"]):
            return rule
    return None


def get_no_match_response() -> str:
    return """I don't have a specific answer for that in my knowledge base.

Your options:
- Create a support ticket — we'll respond within 24 hours
- If admin is online, they'll join this chat shortly

What would you like to do?"""
