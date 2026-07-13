# Database conventions — apply to ALL models + queries

## Migrations
- Every model change needs an alembic migration
- Migration naming: v3_{feature_name}.py
- Always run: alembic upgrade head after creating
- Never edit existing migrations — create new ones
- Current head: v7_dedup_key_unique

## Model conventions
- All PKs: UUID (not integer)
- All tables: created_at + updated_at timestamps
- Soft deletes: use is_active=False not DELETE
  (except for GDPR deletion — that's hard delete)
- All FKs: include CASCADE on delete where appropriate

## Query patterns
- Always use async SQLAlchemy (await session.execute)
- Always filter by user_id first in WHERE clause
- Use .scalars().first() not .scalar_one_or_none()
  (avoids MultipleResultsFound errors)
- Batch inserts over individual saves for performance

## JSONB fields
- score_components: {ats: {...}, pursuit: {...}}
- essence_json: CV essence schema
- domain_cv_scores: {domain_cv_id: score}
- Never store PII in JSONB fields

## Indexes
- Always index: user_id + created_at (most queries)
- Index foreign keys used in JOINs
- Index fields used in WHERE filters
