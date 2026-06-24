"""
Tailor agents — job-specific CV tailoring.

Key optimisation: tailor + cover letter + email draft + S2 score
are all computed in ONE Claude call. This saves 3 round trips
vs doing them separately.

S3 is recomputed AFTER user approves the change log (not during generation).
"""
import json
import re
from typing import Optional

from app.config import settings


def _get_client(user_anthropic_key: Optional[str] = None):
    from anthropic import Anthropic
    api_key = user_anthropic_key or settings.platform_anthropic_api_key or settings.anthropic_api_key
    if not api_key:
        raise ValueError("No Anthropic API key configured")
    return Anthropic(api_key=api_key)


def _parse_json_safe(text: str):
    text = re.sub(r"```json\s*", "", text)
    text = re.sub(r"```\s*", "", text)
    return json.loads(text.strip())


# ── Cheap JD-only highlights (Tailor page left panel) ─────────────────────────

async def extract_jd_highlights(
    jd_text: str,
    model: Optional[str] = None,
    user_anthropic_key: Optional[str] = None,
) -> dict:
    """Cheap JD-only analysis (no CV needed) for the Tailor page's left panel.
    Returns {"matches": [...], "gaps": [...]} — key requirements a senior product
    leader would meet, plus nice-to-haves / potential gaps."""
    if not jd_text or len(jd_text.strip()) < 50:
        return {"matches": [], "gaps": []}
    client = _get_client(user_anthropic_key)
    prompt = f"""Analyse this job description for a SENIOR PRODUCT LEADER candidate
(Head of Product / VP Product / CPO / AI Product Lead).

Extract:
1. "matches" — 4-6 key requirements the JD emphasises that a strong senior product
   leader would meet. Short phrases, e.g. "8+ years product leadership",
   "API platform experience", "Multi-geography delivery".
2. "gaps" — 1-3 requirements that are nice-to-have or a possible gap, e.g.
   "Dutch language (not required)".

JOB DESCRIPTION:
{jd_text[:4000]}

Return ONLY JSON: {{"matches": ["..."], "gaps": ["..."]}}"""
    try:
        response = client.messages.create(
            model=model or settings.anthropic_model,
            max_tokens=600,
            messages=[{"role": "user", "content": prompt}],
        )
        data = _parse_json_safe(response.content[0].text)
        return {"matches": (data.get("matches") or [])[:6], "gaps": (data.get("gaps") or [])[:3]}
    except Exception as e:
        print(f"⚠️ JD highlights extraction failed: {e}")
        return {"matches": [], "gaps": []}


# ── Main agent: tailor + CL + email + S2 in ONE call ─────────────────────────

async def generate_tailor_package(
    domain_cv_md: str,
    master_cv_md: str,
    jd_text: str,
    company: str,
    role: str,
    market: str,
    country_rules: dict,
    cl_tone: str = "professional",
    cl_template: str = "story_led",
    user_name: str = "Candidate",
    user_email: str = "",
    user_linkedin: str = "",
    user_anthropic_key: Optional[str] = None,
    model: Optional[str] = None,
) -> dict:
    """
    Single optimised call that produces:
    1. Change log (bounded edits to domain CV for this specific JD)
    2. Cover letter draft
    3. Application email draft (5 lines max)
    4. S2 score (domain CV vs JD — before tailoring changes applied)

    Returns:
    {
        "changelog": [...],
        "cover_letter_md": "...",
        "email_draft": "...",
        "s2_score": 82.5,
        "s2_key_matches": [...],
    }
    """
    client = _get_client(user_anthropic_key)

    # Cover letter template instructions
    cl_templates = {
        "hook_first": "Open with a bold, specific statement about what you'd bring to this role.",
        "story_led": "Open with a brief, relevant achievement story that connects directly to the role.",
        "problem_solver": "Open by identifying a key challenge the company faces and how you'd solve it.",
        "concise": "Be extremely concise — 3 short paragraphs, no fluff.",
        "random": "Choose whichever opening style feels most compelling for this specific role.",
    }
    cl_instruction = cl_templates.get(cl_template, cl_templates["story_led"])

    cl_tones = {
        "formal": "formal and traditional",
        "professional": "professional but warm",
        "conversational": "conversational and direct",
        "concise": "brief and punchy",
    }
    tone_desc = cl_tones.get(cl_tone, cl_tones["professional"])

    country_adaptations = []
    if not country_rules.get("phone_on_cv", True):
        country_adaptations.append("CV header: phone number removed")
    if country_rules.get("relocation_note"):
        country_adaptations.append(f"Add to CV: '{country_rules['relocation_note']}'")

    prompt = f"""You are a senior career coach and copywriter. Complete four tasks for one job application.

━━━ CANDIDATE ━━━
Name: {user_name}
Email: {user_email}
LinkedIn: {user_linkedin}

━━━ TARGET ROLE ━━━
Company: {company}
Role: {role}
Market: {market}

━━━ DOMAIN CV (starting point for tailoring) ━━━
{domain_cv_md[:3000]}

━━━ JOB DESCRIPTION ━━━
{jd_text[:2500]}

━━━ TASK 1: CHANGE LOG ━━━
Propose bounded edits to tailor the domain CV for THIS specific JD.

GOLDEN RULES:
- NEVER invent content. Only reorder, rephrase verb openers, inject JD keywords, or deselect.
- Every change must trace back to the domain CV
- Maximum 6 changes
- Country adaptations: {', '.join(country_adaptations) if country_adaptations else 'none needed'}

━━━ TASK 2: COVER LETTER ━━━
Write a cover letter. Tone: {tone_desc}. {cl_instruction}
- 3-4 paragraphs, 200-280 words
- Reference specific things from the JD
- Close with a concrete call to action

━━━ TASK 3: APPLICATION EMAIL ━━━
Write the email body (NOT the subject line). Maximum 5 lines.
- Line 1: why you're writing
- Line 2-3: your most relevant credential (one specific thing)
- Line 4: brief forward reference
- Line 5: sign-off

━━━ TASK 4: S2 SCORE ━━━
Score how well the DOMAIN CV (before tailoring) matches this JD.
Score 0-100. Focus on: seniority match, domain relevance, required skills coverage.

━━━ OUTPUT FORMAT ━━━
Return ONLY JSON:

{{
  "changelog": [
    {{
      "change_type": "rephrase|keyword_injection|reorder|deselect",
      "section": "section name",
      "original_text": "exact text from domain CV",
      "proposed_text": "your proposed change",
      "reason": "why this helps for this specific role"
    }}
  ],
  "cover_letter_md": "full cover letter text",
  "email_draft": "email body only (no subject), max 5 lines",
  "s2_score": <number 0-100>,
  "s2_key_matches": ["top 3 matching points"]
}}"""

    response = client.messages.create(
        model=model or settings.anthropic_model,
        max_tokens=3000,
        messages=[{"role": "user", "content": prompt}],
    )

    try:
        result = _parse_json_safe(response.content[0].text)
        return {
            "changelog": result.get("changelog", []),
            "cover_letter_md": result.get("cover_letter_md", ""),
            "email_draft": result.get("email_draft", ""),
            "s2_score": float(result.get("s2_score", 0)),
            "s2_key_matches": result.get("s2_key_matches", []),
        }
    except Exception as e:
        print(f"⚠️ Tailor package parse error: {e}\nRaw: {response.content[0].text[:300]}")
        return {
            "changelog": [],
            "cover_letter_md": "",
            "email_draft": "",
            "s2_score": 0.0,
            "s2_key_matches": [],
        }


# ── Apply tailor changes to produce final tailored CV ────────────────────────

async def apply_tailor_changes(
    domain_cv_md: str,
    approved_changes: list[dict],
    country_rules: dict,
    user_anthropic_key: Optional[str] = None,
    model: Optional[str] = None,
) -> str:
    """
    Apply approved tailor changes to the domain CV to produce the tailored CV.
    Also applies any remaining country rule adaptations.
    Returns the final tailored CV as markdown.
    """
    if not approved_changes:
        return domain_cv_md

    client = _get_client(user_anthropic_key)
    changes_json = json.dumps(approved_changes, indent=2)

    country_text = ""
    if not country_rules.get("phone_on_cv", True):
        country_text += "- Remove phone number from header\n"
    if country_rules.get("relocation_note"):
        country_text += f"- Ensure this line appears in header: '{country_rules['relocation_note']}'\n"

    prompt = f"""Apply these approved changes to the CV exactly as specified.

RULES:
- Apply ONLY the listed changes — no other modifications
- Keep all content not mentioned in changes exactly as-is
- Return ONLY the final CV markdown

━━━ DOMAIN CV ━━━
{domain_cv_md}

━━━ APPROVED CHANGES ━━━
{changes_json}

━━━ COUNTRY RULES ━━━
{country_text or 'None'}

Return the final tailored CV markdown."""

    response = client.messages.create(
        model=model or settings.anthropic_model,
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text.strip()


# ── Regenerate cover letter with different template ───────────────────────────

async def regenerate_cover_letter(
    tailored_cv_md: str,
    jd_text: str,
    company: str,
    role: str,
    user_name: str,
    cl_tone: str = "professional",
    cl_template: str = "random",
    exclude_template: Optional[str] = None,
    user_anthropic_key: Optional[str] = None,
    model: Optional[str] = None,
) -> str:
    """
    Regenerate cover letter with a different template.
    Called when user clicks 'Regenerate with different template'.
    """
    client = _get_client(user_anthropic_key)

    templates = ["hook_first", "story_led", "problem_solver", "concise"]
    if exclude_template and exclude_template in templates:
        templates.remove(exclude_template)

    import random
    chosen = random.choice(templates) if cl_template == "random" else cl_template

    instructions = {
        "hook_first": "Open with a bold, specific statement about what you'd bring.",
        "story_led": "Open with a brief, relevant achievement story.",
        "problem_solver": "Open by identifying a challenge and how you'd solve it.",
        "concise": "3 short paragraphs, no fluff, under 200 words.",
    }

    tones = {
        "formal": "formal", "professional": "professional but warm",
        "conversational": "conversational", "concise": "brief and punchy",
    }

    prompt = f"""Write a cover letter for this job application.

Tone: {tones.get(cl_tone, 'professional')}
Style: {instructions.get(chosen, instructions['story_led'])}
Length: 3-4 paragraphs, 200-280 words

Candidate: {user_name}
Role: {role} at {company}

TAILORED CV:
{tailored_cv_md[:2000]}

JOB DESCRIPTION:
{jd_text[:1500]}

Return ONLY the cover letter text (no subject, no metadata)."""

    response = client.messages.create(
        model=model or settings.anthropic_model,
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text.strip(), chosen


# ── Follow-up email draft ─────────────────────────────────────────────────────

async def generate_followup_email(
    company: str,
    role: str,
    applied_at: str,
    user_name: str,
    context: Optional[str] = None,
    user_anthropic_key: Optional[str] = None,
    model: Optional[str] = None,
) -> str:
    """Draft a follow-up email after no response."""
    client = _get_client(user_anthropic_key)

    prompt = f"""Write a brief, professional follow-up email.

Context:
- Applied for: {role} at {company}
- Applied on: {applied_at}
- Additional context: {context or 'None'}
- Sender: {user_name}

Requirements:
- 3-4 sentences max
- Polite, not pushy
- Re-states interest and fit briefly
- Asks about next steps
- No subject line — just the email body

Return ONLY the email body."""

    response = client.messages.create(
        model=model or settings.anthropic_model,
        max_tokens=300,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text.strip()
