"""
API smoke tests — verify core endpoints respond as expected.
Run inside the backend container against the live server:
    docker exec jobhunt_backend pytest tests/test_api_smoke.py
"""


async def test_login_returns_200(client, user_creds):
    """1. POST /api/auth/login returns 200 (with an access token)."""
    r = await client.post(
        "/api/auth/login",
        json={"email": user_creds["email"], "password": user_creds["password"]},
    )
    assert r.status_code == 200, r.text
    assert r.json().get("access_token")


async def test_get_master_cv_returns_200(client, user_creds):
    """2. GET /api/cvs/master returns 200 (null body when no CV exists)."""
    r = await client.get("/api/cvs/master", headers=user_creds["headers"])
    assert r.status_code == 200, r.text


async def test_jobs_stats_returns_200_with_by_domain_cv(client, user_creds):
    """3. GET /api/jobs/stats returns 200 and includes the by_domain_cv field."""
    r = await client.get("/api/jobs/stats", headers=user_creds["headers"])
    assert r.status_code == 200, r.text
    body = r.json()
    assert "by_domain_cv" in body, f"missing by_domain_cv: {body}"


async def test_feeds_returns_200(client, user_creds):
    """4. GET /api/feeds returns 200."""
    r = await client.get("/api/feeds", headers=user_creds["headers"])
    assert r.status_code == 200, r.text


async def test_admin_stats_forbidden_for_non_admin(client, user_creds):
    """5. GET /api/admin/stats returns 403 for a non-admin user."""
    r = await client.get("/api/admin/stats", headers=user_creds["headers"])
    assert r.status_code == 403, r.text


async def test_activity_alerts_returns_200(client, user_creds):
    """6. GET /api/activity/alerts returns 200 (a list)."""
    r = await client.get("/api/activity/alerts", headers=user_creds["headers"])
    assert r.status_code == 200, r.text
    assert isinstance(r.json(), list)


async def test_activity_system_returns_200(client, user_creds):
    """7. GET /api/activity/system returns 200 with the expected sections."""
    r = await client.get("/api/activity/system", headers=user_creds["headers"])
    assert r.status_code == 200, r.text
    body = r.json()
    for key in ("scanner_runs", "gmail_polls", "ghosted_checks", "error_count", "recent_errors"):
        assert key in body, f"missing {key}"
