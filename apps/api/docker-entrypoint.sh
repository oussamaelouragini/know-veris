#!/bin/sh
# Container entrypoint: bring the schema to head, then hand off to the CMD.
#
# Compose gates this service on `postgres: service_healthy`, so there is no wait
# loop here — a connection failure is a real failure and the container should
# exit loudly rather than retry silently. `restart: unless-stopped` retries it.
#
# `alembic upgrade head` is a no-op once the DB is at head, so this stays cheap
# on every subsequent start. It lives outside /app on purpose: the ./apps/api
# bind mount would otherwise shadow it with the host copy (CRLF on Windows).
set -e

echo "[entrypoint] applying database migrations (alembic upgrade head)"
alembic upgrade head
echo "[entrypoint] schema is at head"

exec "$@"
