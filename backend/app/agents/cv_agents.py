"""
CV agents — all Claude-powered operations on CVs.
Optimised: batched where possible, single calls where context allows.

Agents in this module:
1. text_to_markdown_cv      — convert raw extracted text to clean .md CV
2. generate_domain_changelog — propose bounded changes for a domain CV
3. apply_changes             — apply approved changes + country rules to produce final CV
4. compute_s3_score         — factual integrity score (vs master)
"""
import json
import re
from typing import Optional

from anthropic import Anthropic
from app.config import settings
from app.utils.usage_logger import log_call


# ── Client helper ─────────────────────────────────────────────────────────────

def _get_client(user_anthropic_key: Optional[str] = None) -> Anthropic:
    """
    Use user's own key (Default plan) or platform key (Wallet plan).
    Falls back to platform key if no user key is set.
    """
    api_key = user_anthropic_key or settings.platform_anthropic_api_key or settings.anthropic_api_key
    if not api_key:
        raise ValueError("No Anthropic API key configured. Add your key in Settings → Plan & Keys.")
    return Anthropic(api_key=api_key)


def _parse_json(text: str) -> dict | list:
    """Safely parse JSON from Claude response, stripping markdown fences."""
    text = re.sub(r"```json\s*", "", text)
    text = re.sub(r"```\s*", "", text)
    return json.loads(text.strip())


# ── Agent 1: text → markdown CV ───────────────────────────────────────────────

async def text_to_markdown_cv(raw_text: str, user_anthropic_key: Optional[str] = None,
    model: Optional[str] = None) -> str:
    """
    Convert raw extracted text (from PDF/DOCX) into a clean, structured markdown CV.
    Preserves ALL content — never invents, summarises, or drops information.
    """
    client = _get_client(user_anthropic_key)

    prompt = f"""Convert this raw CV text into clean, well-structured Markdown.

RULES:
- Preserve ALL content exactly — do not invent, summarise, or drop any information
- Use ## for section headings (EXPERIENCE, EDUCATION, SKILLS, etc.)
- Use **Company · Role · Dates** format for job headers
- Use bullet points (- ) for achievements and responsibilities
- Keep all numbers, metrics, and specific details exactly as given
- Remove duplicate whitespace and formatting artifacts from PDF extraction
- Do NOT add any commentary or explanation — output ONLY the markdown CV

RAW TEXT:
{raw_text}"""

    response = client.messages.create(
        model=model or settings.anthropic_model,
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}],
    )
    await log_call("text_to_markdown_cv", "other", response, model or settings.anthropic_model)
    return response.content[0].text.strip()


# ── Agent 2: generate domain CV change log ────────────────────────────────────

async def generate_domain_changelog(
    master_cv_md: str,
    industry_label: str,
    industry_keywords: str,
    industry_emphasis: str,
    function_label: str,
    function_keywords: str,
    country_code: str,
    country_rules: dict,
    user_anthropic_key: Optional[str] = None,
    model: Optional[str] = None,
) -> list[dict]:
    """
    Generate a bounded change log to tailor a master CV for a specific domain.

    Returns a list of change objects:
    [
      {
        "change_type": "rephrase|keyword_injection|reorder|deselect",
        "section": "Experience — Company X",
        "original_text": "...",
        "proposed_text": "...",
        "reason": "..."
      }
    ]

    GOLDEN RULE: Only reorder, rephrase, inject keywords, or deselect.
    Never invent content.
    """
    client = _get_client(user_anthropic_key)

    country_rule_text = f"""
Country: {country_rules.get('country_name', country_code)}
- Phone on CV: {'Yes' if country_rules.get('phone_on_cv', True) else 'Remove phone number'}
- Remove photo line: {'Yes' if country_rules.get('remove_photo') else 'No'}
- Remove DOB: {'Yes' if country_rules.get('remove_dob') else 'No'}
- Relocation note to add: {country_rules.get('relocation_note', 'None')}
- GDPR lines: {country_rules.get('lines_to_add', '[]')}
""".strip()

    prompt = f"""You are a senior CV consultant specialising in product management roles.
Your task is to propose a BOUNDED change log to tailor this CV for a specific domain.

━━━ GOLDEN RULES (NEVER BREAK THESE) ━━━
1. NEVER invent experiences, metrics, skills, companies, or achievements
2. ONLY allowed operations: reorder bullets, rephrase verb openers, inject domain keywords into existing phrases, deselect irrelevant bullets
3. Every proposed change must be traceable to the original CV
4. Maximum 8 changes — quality over quantity
5. If a bullet is already strong for this domain, leave it alone

━━━ TARGET DOMAIN ━━━
Industry: {industry_label}
Domain keywords: {industry_keywords}
Emphasis: {industry_emphasis or 'General product leadership'}

Function: {function_label}
Function keywords: {function_keywords}

━━━ COUNTRY ADAPTATION ({country_code}) ━━━
{country_rule_text}

━━━ MASTER CV ━━━
{master_cv_md}

━━━ OUTPUT FORMAT ━━━
Return ONLY a JSON array. No explanation, no markdown fences.

[
  {{
    "change_type": "rephrase",
    "section": "Experience — [Company]",
    "original_text": "exact text from CV",
    "proposed_text": "your proposed change",
    "reason": "why this helps for {industry_label} roles"
  }}
]

change_type must be one of: rephrase, keyword_injection, reorder, deselect
For country adaptations (remove phone, add relocation note), include those as separate change items."""

    response = client.messages.create(
        model=model or settings.anthropic_model,
        max_tokens=2048,
        messages=[{"role": "user", "content": prompt}],
    )
    await log_call("generate_domain_changelog", "domain_cv", response, model or settings.anthropic_model)

    try:
        changes = _parse_json(response.content[0].text)
        if not isinstance(changes, list):
            changes = []
        return changes
    except Exception as e:
        print(f"⚠️ Failed to parse changelog JSON: {e}")
        print(f"Raw response: {response.content[0].text[:500]}")
        return []


# ── Agent 3: apply approved changes to produce final CV ───────────────────────

async def apply_changes(
    master_cv_md: str,
    approved_changes: list[dict],
    country_rules: dict,
    user_anthropic_key: Optional[str] = None,
    model: Optional[str] = None,
) -> str:
    """
    Apply a list of approved changes to the master CV to produce the domain CV.
    Also applies country rules (remove phone, add relocation note, etc.).

    Returns the final domain CV as markdown.
    """
    if not approved_changes:
        return master_cv_md

    client = _get_client(user_anthropic_key)

    changes_json = json.dumps(approved_changes, indent=2)

    country_rule_text = ""
    if not country_rules.get("phone_on_cv", True):
        country_rule_text += "- Remove phone number from header\n"
    if country_rules.get("remove_photo"):
        country_rule_text += "- Remove any photo or 'Photo: ...' line\n"
    if country_rules.get("remove_dob"):
        country_rule_text += "- Remove date of birth if present\n"
    if country_rules.get("relocation_note"):
        country_rule_text += f"- Add to header: '{country_rules['relocation_note']}'\n"
    lines_to_add = country_rules.get("lines_to_add", "[]")
    try:
        extra_lines = json.loads(lines_to_add) if isinstance(lines_to_add, str) else lines_to_add
        for line in extra_lines:
            country_rule_text += f"- Add at footer: '{line}'\n"
    except Exception:
        pass

    prompt = f"""Apply these approved changes to the CV exactly as specified.

━━━ RULES ━━━
1. Apply ONLY the changes listed — do not make any other modifications
2. Apply country rules exactly as specified
3. Keep all content not mentioned in changes exactly as-is
4. Return ONLY the final CV markdown — no explanation

━━━ MASTER CV ━━━
{master_cv_md}

━━━ APPROVED CHANGES TO APPLY ━━━
{changes_json}

━━━ COUNTRY RULES TO APPLY ━━━
{country_rule_text or 'None — keep CV as-is for this country'}

Apply all changes and return the final CV markdown."""

    response = client.messages.create(
        model=model or settings.anthropic_model,
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}],
    )
    await log_call("apply_changes", "domain_cv", response, model or settings.anthropic_model)
    return response.content[0].text.strip()


# ── Agent 4: compute S3 score ─────────────────────────────────────────────────

async def compute_s3_score(
    domain_cv_md: str,
    master_cv_md: str,
    user_anthropic_key: Optional[str] = None,
    model: Optional[str] = None,
) -> dict:
    """
    Compute S3 factual integrity score.
    
    Returns:
    {
        "s3_score": 94.5,   # 0-100, % of domain CV traceable to master
        "flags": [          # items that could not be traced back
            "X years experience in payments (original says Y)"
        ]
    }
    
    Thresholds:
    - >= 90: green (safe to use)
    - 85-89: amber (review before sending)
    - < 85: red (blocked)
    """
    client = _get_client(user_anthropic_key)

    prompt = f"""You are a CV integrity auditor. Score how much of the DOMAIN CV is traceable to the MASTER CV.

━━━ SCORING RULES ━━━
- Bullet/sentence verbatim in master: 100% traceable
- Bullet rephrased but same meaning: 90-100% traceable
- Bullet with keywords added to existing content: 85-95% traceable  
- Bullet reordered from master: 100% traceable
- Bullet REMOVED from master: not counted (deselection is allowed)
- Content NOT in master (invented metrics, companies, skills, experiences): 0% traceable — FLAG IT

S3 = average traceability across all bullets/sentences in the domain CV.

━━━ MASTER CV ━━━
{master_cv_md}

━━━ DOMAIN CV TO SCORE ━━━
{domain_cv_md}

Return ONLY JSON, no explanation:
{{
  "s3_score": <number 0-100>,
  "flags": [<list of strings describing any invented/untraceable content>]
}}"""

    response = client.messages.create(
        model=model or settings.anthropic_model,
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    )
    await log_call("compute_s3_score", "domain_cv", response, model or settings.anthropic_model)

    try:
        result = _parse_json(response.content[0].text)
        return {
            "s3_score": float(result.get("s3_score", 0)),
            "flags": result.get("flags", []),
        }
    except Exception as e:
        print(f"⚠️ S3 parse error: {e}")
        return {"s3_score": 0.0, "flags": ["Failed to compute S3 score"]}
