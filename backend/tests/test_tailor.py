"""V3 Tailor page — country-rules display (pure) + jd-highlights endpoint guard."""
import uuid
from types import SimpleNamespace

from app.routers.tailor import _country_rule_display


def test_country_rule_display():
    country = SimpleNamespace(
        phone_on_cv=False, remove_photo=True, remove_dob=True,
        remove_marital_status=False, relocation_note="Open to relocation",
        privacy_law="GDPR",
    )
    rules = _country_rule_display(country)
    texts = [(r["text"], r["applied"]) for r in rules]
    assert ("Phone removed", False) in texts
    assert ("Photo line removed", False) in texts
    assert ("DOB removed", False) in texts
    assert ("Marital status removed", False) not in texts  # flag was False
    assert ("Relocation note added", True) in texts
    assert ("GDPR-compliant format", True) in texts
    # no country → empty
    assert _country_rule_display(None) == []


async def test_jd_highlights_404_for_unknown_job(client, user_creds):
    r = await client.post(
        "/api/tailor/jd-highlights",
        json={"job_id": str(uuid.uuid4()), "domain_cv_id": str(uuid.uuid4())},
        headers=user_creds["headers"],
    )
    assert r.status_code == 404
