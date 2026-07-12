# Testing rules — apply after EVERY feature build

## Requirements
- Write tests AFTER every feature
- Test count must NEVER decrease
- Run full suite before every commit:
  docker-compose exec backend pytest tests/ -v
- Current count: 168 tests (165 pass + 3 skip) — must stay ≥ 168

## Test patterns
- Use conftest.py fixtures (client, user_creds)
- Every new endpoint needs at least 1 test
- New agent functions need unit tests
- Use monkeypatch for Anthropic API calls
  (never make real API calls in tests)

## What to test
- Happy path (200 response)
- Auth required (401 without token)
- User isolation (can't access other user's data)
- Edge cases (null scores, missing CV, etc)

## Naming
- test_{feature}_{what_it_does}
- Example: test_ats_score_applies_dealbreaker_cap
