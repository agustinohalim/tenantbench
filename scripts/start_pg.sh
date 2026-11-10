#!/usr/bin/env bash
# Start the oracle database: PostgreSQL 17 in Docker, bound to localhost only.
# The password is local throwaway; the container holds only public BIRD data.
set -euo pipefail
NAME=tenantbench-pg
if docker ps -a --format '{{.Names}}' | grep -qx "$NAME"; then
  docker start "$NAME" >/dev/null
else
  docker run -d --name "$NAME" -p 127.0.0.1:55432:5432 \
    -e POSTGRES_PASSWORD=tenantbench -e POSTGRES_DB=tenantbench \
    postgres:17-alpine >/dev/null
fi
# pg_isready can answer during the image's init phase, before the final restart; retry a real query.
until docker exec "$NAME" psql -U postgres -tAc "SELECT version()" 2>/dev/null; do sleep 1; done
echo "conninfo: postgresql://postgres:tenantbench@127.0.0.1:55432/tenantbench"
