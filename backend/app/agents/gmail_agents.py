"""
Gmail classifier agent.
Classifies emails as: auto_confirmation, auto_rejection, genuine_recruiter,
interview_invite, offer, unclear, job_alert.

Optimisation: batch up to 10 emails per Claude call.
"""
import json
import re
from typing import Optional

from app.config import settings
from app.utils.usage_logger import log_call


def _get_client(user_anthropic_key: Optional[str] = None):
    from anthropic import Anthropic
    api_key = user_anthropic_key or settings.platform_anthropic_api_key or settings.anthropic_api_key
    if not api_key:
        raise ValueError("No Anthropic API key configured")
    return Anthropic(api_key=api_key)


# ── Rule-based pre-classifier (zero Claude cost) ──────────────────────────────

AUTO_CONFIRM_SIGNALS = [
    "thank you for applying", "thanks for applying", "application received",
    "we received your application", "your application has been received",
    "application confirmation", "thank you for your interest",
    "application submitted", "we have received your",
]

AUTO_REJECT_SIGNALS = [
    "we regret", "we will not be moving forward", "not moving forward",
    "decided to move forward with other candidates", "unfortunately",
    "position has been filled", "we have decided not to",
    "will not be proceeding", "not selected",
]

JOB_ALERT_SENDERS = [
    "jobs-noreply@linkedin.com", "jobalerts-noreply@linkedin.com",
    "no-reply@indeed.com", "noreply@glassdoor.com",
    "jobs@", "jobalert@", "careers@", "noreply@",
    "donotreply@", "no-reply@",
]

NOREPLY_PATTERNS = ["noreply", "no-reply", "donotreply", "do-not-reply", "mailer-daemon"]


def quick_classify(from_email: str, subject: str, body_preview: str) -> Optional[str]:
    """
    Rule-based quick classification. Returns classification or None if unsure.
    No Claude call needed for clear cases.
    """
    from_lower = from_email.lower()
    subject_lower = subject.lower()
    body_lower = body_preview.lower()

    # Job alert senders
    if any(sig in from_lower for sig in JOB_ALERT_SENDERS):
        return "job_alert"

    # No-reply senders
    if any(p in from_lower for p in NOREPLY_PATTERNS):
        # Could be auto confirm or auto reject
        if any(sig in body_lower or sig in subject_lower for sig in AUTO_REJECT_SIGNALS):
            return "auto_rejection"
        if any(sig in body_lower or sig in subject_lower for sig in AUTO_CONFIRM_SIGNALS):
            return "auto_confirmation"
        return "auto_confirmation"  # default for no-reply

    # Auto confirmation signals
    if any(sig in body_lower for sig in AUTO_CONFIRM_SIGNALS):
        return "auto_confirmation"

    # Auto rejection signals
    if any(sig in body_lower for sig in AUTO_REJECT_SIGNALS):
        return "auto_rejection"

    return None  # needs Claude


async def classify_emails_batch(
    emails: list[dict],
    user_anthropic_key: Optional[str] = None,
) -> list[dict]:
    """
    Classify a batch of emails using Claude (one call for up to 10 emails).
    Each email dict: {id, from_email, subject, body_preview}
    Returns: list of {id, classification, confidence, needs_hitl, summary}

    Classifications:
    - auto_confirmation: portal/ATS ack
    - auto_rejection: standard rejection
    - genuine_recruiter: real person, needs HITL
    - interview_invite: scheduling/calendar request
    - offer: offer letter or compensation discussion
    - job_alert: LinkedIn/Indeed alert
    - unclear: low confidence
    """
    # First pass: rule-based (free)
    results = []
    needs_claude = []

    for email_data in emails:
        quick = quick_classify(
            email_data.get("from_email", ""),
            email_data.get("subject", ""),
            email_data.get("body_preview", ""),
        )
        if quick:
            results.append({
                "id": email_data["id"],
                "classification": quick,
                "confidence": "high",
                "needs_hitl": False,
                "summary": f"Auto-classified as {quick}",
            })
        else:
            needs_claude.append(email_data)

    # Second pass: Claude for unclear emails (batched)
    if needs_claude:
        claude_results = await _classify_with_claude(needs_claude, user_anthropic_key)
        results.extend(claude_results)

    return results


async def _classify_with_claude(
    emails: list[dict],
    user_anthropic_key: Optional[str] = None,
) -> list[dict]:
    """Classify unclear emails using Claude (batched)."""
    client = _get_client(user_anthropic_key)

    emails_text = ""
    for i, e in enumerate(emails):
        emails_text += f"""
Email {i+1}:
ID: {e['id']}
From: {e.get('from_email', '')}
Subject: {e.get('subject', '')}
Preview: {e.get('body_preview', '')[:300]}
---"""

    prompt = f"""Classify each email in the context of a job search.

Classifications:
- auto_confirmation: ATS/portal ack ("thanks for applying", "we received your application")
- auto_rejection: template rejection ("we regret", "not moving forward")
- genuine_recruiter: real person asking a question, wanting to connect, or sharing details
- interview_invite: scheduling request, calendar invite, availability ask
- offer: offer letter, compensation discussion, contract
- job_alert: automated job listing email from LinkedIn/Indeed/etc.
- unclear: ambiguous, could be anything

{emails_text}

Return ONLY JSON array, one entry per email:
[
  {{
    "id": "...",
    "classification": "...",
    "confidence": "high|medium|low",
    "needs_hitl": true|false,
    "summary": "one line: what this email is about"
  }}
]

needs_hitl = true for: genuine_recruiter, interview_invite, offer"""

    try:
        response = client.messages.create(
            model=settings.anthropic_model,
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )
        await log_call("classify_emails_batch", "gmail", response, settings.anthropic_model)
        text = response.content[0].text
        text = re.sub(r"```json\s*", "", text)
        text = re.sub(r"```\s*", "", text)
        return json.loads(text.strip())
    except Exception as e:
        print(f"⚠️ Email classification error: {e}")
        # Return unclear for all
        return [
            {
                "id": e["id"],
                "classification": "unclear",
                "confidence": "low",
                "needs_hitl": True,
                "summary": "Classification failed — review manually",
            }
            for e in emails
        ]


async def match_email_to_job(
    from_email: str,
    subject: str,
    body_preview: str,
    jobs: list[dict],
) -> Optional[str]:
    """
    Try to match an incoming email to a known job.
    Returns job_id string or None.

    Matching priority:
    1. Exact sender email match to job.recruiter_email
    2. Company name in subject/from
    3. Domain match
    """
    from_lower = from_email.lower()
    subject_lower = subject.lower()
    combined = f"{from_lower} {subject_lower} {body_preview.lower()}"

    for job in jobs:
        # Exact recruiter email match
        if job.get("recruiter_email") and job["recruiter_email"].lower() == from_lower:
            return job["id"]

        # Company name in email/subject
        company_lower = job.get("company", "").lower()
        if company_lower and len(company_lower) > 2:
            if company_lower in combined:
                return job["id"]

        # Domain match (e.g. @adyen.com matches Adyen job)
        if "@" in from_lower:
            sender_domain = from_lower.split("@")[1].split(".")[0]
            if sender_domain in company_lower or company_lower in sender_domain:
                return job["id"]

    return None
