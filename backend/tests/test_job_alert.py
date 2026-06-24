"""V3 Gmail job-alert parser — unit tests for the rule-based classifier and
link extraction. These are pure functions (no Claude / network / DB), so they
run fast and deterministically alongside the API smoke tests."""
from app.agents.gmail_alert_agent import (
    is_job_alert_email, extract_job_links, extract_jobs_from_email_body,
    is_excluded_subject,
)


# Mirrors real LinkedIn job-alert markup: each /jobs/view/ link wraps separate
# segments (role, then "Company · Location", then status), plus an aggregate
# /jobs/search link that must be ignored.
LINKEDIN_ALERT_HTML = """
<table>
  <tr><td>
    <a href="https://www.linkedin.com/comm/jobs/view/4412119266/?trackingId=x">
      <span>VP Research &amp; Development Engineering EMEA</span>
      <span>Eaton · Amsterdam, Netherlands (Hybrid)</span>
      <span>Actively recruiting</span>
    </a>
  </td></tr>
  <tr><td>
    <a href="https://www.linkedin.com/comm/jobs/view/4430379131/?trackingId=y">
      <span>Senior Project Manager</span>
      <span>COWI · Rotterdam, Netherlands</span>
      <span>3 days ago</span>
    </a>
  </td></tr>
  <tr><td>
    <a href="https://www.linkedin.com/comm/jobs/search?keywords=foo">See all jobs</a>
  </td></tr>
</table>
"""

ALERT_HTML = """
<html><body>
  <a href="https://careers.underarmour.com/jobs/123-vp-product">VP Product</a>
  <a href="https://boards.greenhouse.io/acme/jobs/678">Head of Product</a>
  <a href="https://jobs.lever.co/acme/abc">Director Product</a>
  <a href="https://acme.com/unsubscribe">unsubscribe</a>
  <a href="https://facebook.com/acme">fb</a>
  <a href="mailto:jobs@acme.com">email</a>
  <a href="https://acme.com/about">about us</a>
</body></html>
"""


async def test_extract_job_links_keeps_careers_drops_junk():
    links = await extract_job_links(ALERT_HTML, max_links=10)
    # keeps the 3 careers links; drops unsubscribe / facebook / mailto / about
    assert len(links) == 3
    assert all(
        not any(bad in l for bad in ("unsubscribe", "facebook", "mailto", "/about"))
        for l in links
    )


async def test_extract_job_links_respects_cap():
    assert len(await extract_job_links(ALERT_HTML, max_links=2)) == 2


async def test_is_job_alert_true_for_digest():
    # sender (jobs@) + subject (matching) + 3 links = 3 signals -> alert
    assert await is_job_alert_email(
        "New jobs matching your search", "jobs@underarmour.com", ALERT_HTML
    ) is True


async def test_is_job_alert_needs_two_signals():
    # job-looking links only (neutral sender + subject) = 1 signal -> not an alert
    assert await is_job_alert_email("hello there", "friend@gmail.com", ALERT_HTML) is False


async def test_is_job_alert_false_for_normal_email():
    assert await is_job_alert_email("lunch tomorrow?", "bob@gmail.com", "<p>hi</p>") is False


def test_extract_jobs_from_email_body_linkedin_cards():
    jobs = extract_jobs_from_email_body(LINKEDIN_ALERT_HTML, max_jobs=10)
    # 2 specific job cards; the /jobs/search aggregate link is ignored
    assert len(jobs) == 2
    assert jobs[0]["title"] == "VP Research & Development Engineering EMEA"
    assert jobs[0]["company"] == "Eaton"
    assert jobs[0]["location"] == "Amsterdam, Netherlands (Hybrid)"
    assert "/jobs/view/4412119266" in jobs[0]["url"]
    assert jobs[1]["title"] == "Senior Project Manager"
    assert jobs[1]["company"] == "COWI"
    assert jobs[1]["location"] == "Rotterdam, Netherlands"


def test_subject_exclusion_blocks_security_alert():
    assert is_excluded_subject("Security alert") is True
    assert is_excluded_subject("New jobs matching your search") is False


async def test_is_job_alert_excludes_security_alert():
    # even from an alerts-y sender with job-looking links, excluded subjects are not alerts
    assert await is_job_alert_email("Security alert", "no-reply@accounts.google.com", LINKEDIN_ALERT_HTML) is False
