"""Phase-1 dedup backfill + duplicate resolution.

DRY-RUN by default (no writes). Pass --apply to actually backfill dedup_key and delete
duplicate loser rows. Sequence:
    Migration A (add jobs.dedup_key)  →  this script --apply  →  Migration B (unique index)

Resolution rules (per (user_id, dedup_key) collision group):
  DEPENDENTS (a row that must NOT be silently deleted): has a tailored CV
    (jobs.tailored_cv_id OR tailored_cvs.job_id), an email thread (email_threads.job_id),
    a community contribution (community_contributions.job_id), or an advanced status
    (anything beyond 'new'/'bookmarked').
  Survivor selection:
    • exactly ONE dependent row      → it survives.
    • TWO+ dependent rows            → BLOCK the group (manual review; never auto-delete).
    • ZERO dependent rows            → prefer has_partial_jd=False, then non-null scores,
                                       then newest created_at, then lowest id.
  Then merge-up: fill NULL fields on the survivor from a loser (portal_url/jd_raw/jd_md/
  recruiter_email/market/best_domain_cv_id/s1/s1d). Delete the (dependent-free) losers.

Phase 1 uses ON CONFLICT DO NOTHING in the save paths. DO-UPDATE-enrich (fill a partial
row from a later full-JD source) is an explicit FAST-FOLLOW — it matters for the
partial→full JD case that Bright Data collect-by-URL enables.

  docker-compose exec backend python -m app.scripts.dedup_resolve            # dry-run
  docker-compose exec backend python -m app.scripts.dedup_resolve --apply    # writes
"""
import asyncio
import sys
from collections import defaultdict

# Single source of truth for the key — same builder the save paths use (no drift).
from app.utils.dedup import build_dedup_key


def _self_test():
    cases = {
        build_dedup_key("X", "Y", "Z",
            "https://www.linkedin.com/comm/jobs/view/4432636617/?trackingId=abc&trk=eml-xyz"): "linkedin:4432636617",
        build_dedup_key("X", "Y", "Z", "https://www.linkedin.com/jobs/view/123"): "linkedin:123",
        build_dedup_key("X", "Y", "Z", "https://nl.indeed.com/viewjob?jk=b661bc2362cab0c6"): "indeed:b661bc2362cab0c6",
        build_dedup_key("X", "Y", "Z", "https://boards.greenhouse.io/acme/jobs/999?utm=x"): "url:boards.greenhouse.io/acme/jobs/999",
        build_dedup_key("Booking.com", "Head of Product", "Amsterdam", None): "crl:booking com|head of product|amsterdam",
    }
    ok = all(got == exp for got, exp in cases.items())
    print("builder self-test:", "PASS ✓" if ok else "FAIL ✗")
    for got, exp in cases.items():
        flag = "" if got == exp else "   ✗ EXPECTED " + exp
        print(f"   {got}{flag}")
    return ok


PROGRESS_STATUSES_EXCLUDED = {"new", "bookmarked"}   # anything else = advanced/progress

MERGE_FIELDS = ["portal_url", "jd_raw", "jd_md", "recruiter_email", "market",
                "best_domain_cv_id", "s1", "s1d"]


async def main(apply):
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine
    from app.config import settings

    if not _self_test():
        print("✖ builder self-test failed — aborting.")
        return

    eng = create_async_engine(settings.database_url)
    async with eng.connect() as c:
        rows = (await c.execute(text(
            "SELECT id, user_id, company, role, location, portal_url, source, created_at, "
            "status, has_partial_jd, s1, s1d, tailored_cv_id, jd_raw, jd_md, recruiter_email, "
            "market, best_domain_cv_id FROM jobs ORDER BY created_at, id"
        ))).fetchall()
        # dependency sets (job_ids referenced by children)
        tailored = {r[0] for r in (await c.execute(text("SELECT DISTINCT job_id FROM tailored_cvs"))).fetchall()}
        emailed = {r[0] for r in (await c.execute(text(
            "SELECT DISTINCT job_id FROM email_threads WHERE job_id IS NOT NULL"))).fetchall()}
        community = {r[0] for r in (await c.execute(text(
            "SELECT DISTINCT job_id FROM community_contributions"))).fetchall()}

    def deps(r):
        d = []
        if r.id in tailored or r.tailored_cv_id is not None:
            d.append("tailoredCV")
        if r.id in emailed:
            d.append("emailThread")
        if r.id in community:
            d.append("community")
        if (r.status or "") not in PROGRESS_STATUSES_EXCLUDED:
            d.append(f"status={r.status}")
        return d

    groups = defaultdict(list)
    for r in rows:
        key = build_dedup_key(r.company, r.role, r.location, r.portal_url)
        groups[(r.user_id, key)].append(r)
    collisions = {k: v for k, v in groups.items() if len(v) > 1}

    print(f"\ntotal jobs {len(rows)} · distinct keys {len(groups)} · collision groups {len(collisions)}")
    print("=" * 78)

    to_delete, blocked, losers_with_deps, merge_ops = [], [], [], 0

    for (uid, key), members in sorted(collisions.items(), key=lambda kv: -len(kv[1])):
        dep_rows = [(r, deps(r)) for r in members]
        with_dep = [(r, d) for r, d in dep_rows if d]

        if len(with_dep) >= 2:
            blocked.append((key, with_dep))
            print(f"\n⛔ BLOCK  key={key[:60]!r}  ×{len(members)} — {len(with_dep)} rows have dependents:")
            for r, d in dep_rows:
                mark = "  <dep>" if d else ""
                print(f"     {str(r.id)[:8]}  {str(r.created_at)[:19]}  {r.source:11.11} {str(r.role)[:30]:30.30}{mark} {d or ''}")
            continue

        if len(with_dep) == 1:
            survivor = with_dep[0][0]
            reason = "has-dependents"
        else:
            survivor = sorted(members, key=lambda r: (
                r.has_partial_jd,                         # False (full) first
                r.s1 is None and r.s1d is None,           # scored first
                -(r.created_at.timestamp()),              # newest first
                str(r.id),                                # stable
            ))[0]
            reason = "no-deps: full/scored/newest"

        losers = [r for r in members if r.id != survivor.id]
        # merge-up preview
        merged = []
        for f in MERGE_FIELDS:
            if getattr(survivor, f) in (None, "",):
                for l in losers:
                    if getattr(l, f) not in (None, ""):
                        merged.append(f)
                        merge_ops += 1
                        break

        print(f"\n✓ key={key[:56]!r}  ×{len(members)}  survivor={str(survivor.id)[:8]} ({reason})")
        print(f"     KEEP   {str(survivor.id)[:8]}  {str(survivor.created_at)[:19]}  {survivor.source:11.11} "
              f"partial={survivor.has_partial_jd} s1={survivor.s1} status={survivor.status} deps={deps(survivor) or '-'}")
        for l in losers:
            d = deps(l)
            if d:
                losers_with_deps.append((key, str(l.id), d))
            print(f"     DELETE {str(l.id)[:8]}  {str(l.created_at)[:19]}  {l.source:11.11} "
                  f"partial={l.has_partial_jd} s1={l.s1} status={l.status} deps={d or '-'}")
            to_delete.append(l.id)
        if merged:
            print(f"     MERGE-UP into survivor: {merged}")

    print("\n" + "=" * 78)
    print(f"SUMMARY  collision groups {len(collisions)} · survivors {len(collisions) - len(blocked)} · "
          f"rows to delete {len(to_delete)} · merge-up field-fills {merge_ops}")
    print(f"BLOCKED groups (2+ dependents, NOT auto-resolved): {len(blocked)}")
    print(f"LOSERS flagged with dependents (MUST be 0 before any delete): {len(losers_with_deps)}")
    if losers_with_deps:
        for key, lid, d in losers_with_deps:
            print(f"   ✖ loser {lid} in {key[:40]!r} has {d}")

    if not apply:
        print("\nDRY-RUN — no writes. Re-run with --apply after review (and after Migration A).")
        await eng.dispose()
        return

    # ── APPLY ────────────────────────────────────────────────────────────────────
    if losers_with_deps or blocked:
        print("\n✖ REFUSING to apply: dependent losers or blocked groups present. Resolve manually first.")
        await eng.dispose()
        return
    async with eng.begin() as c:
        # backfill dedup_key for ALL rows (requires Migration A: jobs.dedup_key exists)
        for r in rows:
            key = build_dedup_key(r.company, r.role, r.location, r.portal_url)
            await c.execute(text("UPDATE jobs SET dedup_key=:k WHERE id=:i"), {"k": key, "i": r.id})
        # merge-up + delete losers per group
        for (uid, key), members in collisions.items():
            with_dep = [r for r in members if deps(r)]
            survivor = with_dep[0] if len(with_dep) == 1 else sorted(members, key=lambda r: (
                r.has_partial_jd, r.s1 is None and r.s1d is None, -(r.created_at.timestamp()), str(r.id)))[0]
            losers = [r for r in members if r.id != survivor.id]
            for f in MERGE_FIELDS:
                if getattr(survivor, f) in (None, ""):
                    for l in losers:
                        v = getattr(l, f)
                        if v not in (None, ""):
                            await c.execute(text(f"UPDATE jobs SET {f}=:v WHERE id=:i AND {f} IS NULL"),
                                            {"v": v, "i": survivor.id})
                            break
            for l in losers:
                await c.execute(text("DELETE FROM jobs WHERE id=:i"), {"i": l.id})
    print(f"\n✓ APPLIED: backfilled {len(rows)} dedup_keys, deleted {len(to_delete)} duplicate rows.")
    await eng.dispose()


if __name__ == "__main__":
    asyncio.run(main(apply="--apply" in sys.argv))
