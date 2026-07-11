#!/bin/sh
# Backend entrypoint — migrate the DB to head, THEN start the app.
#
# Wired as the entrypoint for the BACKEND service ONLY (see docker-compose*.yml),
# so exactly one process ever runs migrations. The Celery worker and beat run their
# OWN commands (no entrypoint override) and therefore never migrate; they wait for
# the backend to become healthy — which only happens AFTER this migration finishes.
#
# `set -e`: if `alembic upgrade head` fails, this script exits non-zero and the app
# is NEVER started against a bad schema — the container fails loudly (the error is
# visible in `docker compose logs backend`).
#
# Idempotent: `alembic upgrade head` only applies revisions newer than the DB's
# current `alembic_version`; when already at head it is a no-op that exits 0. Safe
# to run on every boot.
set -e

echo "[entrypoint] Applying database migrations (alembic upgrade head)…"
alembic upgrade head
echo "[entrypoint] Database schema is at head. Starting app: $*"
exec "$@"
