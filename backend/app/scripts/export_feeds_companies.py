#!/usr/bin/env python3
"""
Export a user's feed configs + target companies from the LOCAL database into a single
portable .sql file, for applying on PROD (where the same user has a DIFFERENT id).

Reads LOCAL only. Writes NOTHING to any database. Emits INSERT..SELECT statements that:
  - resolve user_id on PROD via `(SELECT id FROM users WHERE email = '<email>')` subquery,
  - use fresh UUIDs (no PK collision),
  - set domain_cv_id = NULL (feeds keep their own search_keywords; re-link later),
  - dedup with `NOT EXISTS` on a natural key so re-applying is safe (never overwrites).

Tables: user_feeds, user_target_companies. Nothing else (no jobs, CVs, credentials).

Run (inside the backend container, against LOCAL):
    docker-compose exec -T backend python app/scripts/export_feeds_companies.py \
        --email praveenp.1118@gmail.com --out app/scripts/feeds_companies_export.sql

Apply on the server (inside the prod db container):
    docker-compose -f docker-compose.prod.yml exec -T db \
        psql -U jobhunt -d jobhunt < feeds_companies_export.sql
"""
import argparse
import asyncio
import os
import uuid

import asyncpg

FEED_COLS = ["feed_type", "name", "url_or_actor", "actor_name", "is_active", "is_platform",
             "keywords", "location", "date_range_days", "search_keywords", "job_boards",
             "is_auto_generated"]
COMPANY_COLS = ["company_name", "career_page_url", "market", "is_active", "is_platform"]


def _dsn() -> str:
    dsn = os.environ.get("DATABASE_URL") or os.environ["DATABASE_URL"]
    return dsn.replace("+asyncpg", "")  # asyncpg wants a plain libpq DSN


def lit(v) -> str:
    """Render a Python value as a SQL literal."""
    if v is None:
        return "NULL"
    if isinstance(v, bool):
        return "TRUE" if v else "FALSE"
    if isinstance(v, (int, float)):
        return str(v)
    return "'" + str(v).replace("'", "''") + "'"   # escape single quotes


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--email", required=True, help="account email (same on local + prod)")
    ap.add_argument("--out", required=True, help="output .sql path")
    args = ap.parse_args()
    email_lit = lit(args.email)

    conn = await asyncpg.connect(_dsn())
    try:
        urow = await conn.fetchrow("SELECT id FROM users WHERE email = $1", args.email)
        if not urow:
            raise SystemExit(f"No local user with email {args.email!r}")
        luid = urow["id"]
        feeds = await conn.fetch(
            f"SELECT {', '.join(FEED_COLS)} FROM user_feeds WHERE user_id = $1 ORDER BY name", luid)
        comps = await conn.fetch(
            f"SELECT {', '.join(COMPANY_COLS)} FROM user_target_companies WHERE user_id = $1 "
            f"ORDER BY company_name", luid)
    finally:
        await conn.close()

    out = []
    w = out.append
    w("-- ============================================================================")
    w(f"-- Feed configs + target companies export for {args.email}")
    w("-- Generated from LOCAL. Reads only; safe to review before applying.")
    w("-- Apply on PROD (inside the prod db container):")
    w("--   docker-compose -f docker-compose.prod.yml exec -T db \\")
    w("--       psql -U jobhunt -d jobhunt < feeds_companies_export.sql")
    w("--")
    w("-- Safe + idempotent: user_id resolved by email subquery, fresh uuids,")
    w("-- domain_cv_id = NULL, INSERT..WHERE NOT EXISTS dedup (never overwrites).")
    w(f"-- Rows: {len(feeds)} feeds, {len(comps)} target companies.")
    w("-- PREREQ: the prod user must exist (logged in at least once); otherwise the")
    w("-- email subquery returns 0 rows and NOTHING is inserted (still safe).")
    w("-- ============================================================================")
    w("")
    w("BEGIN;")
    w("")

    # ---- user_feeds ----
    w(f"-- === user_feeds ({len(feeds)}) — domain_cv_id forced NULL; dedup on (user_id, name, url_or_actor) ===")
    fcols = ["id", "user_id", "domain_cv_id"] + FEED_COLS
    for r in feeds:
        new_id = f"'{uuid.uuid4()}'::uuid"
        sel = [new_id, "u.id", "NULL"] + [lit(r[c]) for c in FEED_COLS]
        w(f"INSERT INTO user_feeds ({', '.join(fcols)})")
        w(f"SELECT {', '.join(sel)}")
        w("FROM users u")
        w(f"WHERE u.email = {email_lit}")
        w("  AND NOT EXISTS (SELECT 1 FROM user_feeds f WHERE f.user_id = u.id"
          f" AND f.name = {lit(r['name'])} AND f.url_or_actor = {lit(r['url_or_actor'])});")
        w("")

    # ---- user_target_companies ----
    w(f"-- === user_target_companies ({len(comps)}) — dedup on (user_id, lower(company_name)) ===")
    ccols = ["id", "user_id"] + COMPANY_COLS
    for r in comps:
        new_id = f"'{uuid.uuid4()}'::uuid"
        sel = [new_id, "u.id"] + [lit(r[c]) for c in COMPANY_COLS]
        w(f"INSERT INTO user_target_companies ({', '.join(ccols)})")
        w(f"SELECT {', '.join(sel)}")
        w("FROM users u")
        w(f"WHERE u.email = {email_lit}")
        w("  AND NOT EXISTS (SELECT 1 FROM user_target_companies c WHERE c.user_id = u.id"
          f" AND lower(c.company_name) = lower({lit(r['company_name'])}));")
        w("")

    w("COMMIT;")
    w("")
    w("-- Verify after apply:")
    w(f"--   SELECT count(*) FROM user_feeds f JOIN users u ON u.id=f.user_id WHERE u.email={email_lit};")
    w(f"--   SELECT count(*) FROM user_target_companies c JOIN users u ON u.id=c.user_id WHERE u.email={email_lit};")
    w("")

    with open(args.out, "w", encoding="utf-8") as fh:
        fh.write("\n".join(out))
    print(f"Wrote {args.out}: {len(feeds)} feeds + {len(comps)} companies "
          f"({len(out)} lines). Read-only; nothing was written to any DB.")


if __name__ == "__main__":
    asyncio.run(main())
