#!/usr/bin/env bash
set -Eeuo pipefail
# Read-only checks; never prints environment variable values.
cd "$(dirname "$0")"
if [[ $(uname -m) != aarch64 && $(uname -m) != arm64 ]]; then
  echo "WARNING: current host is not ARM64; OCI pilot target is ARM64" >&2
fi
if ! docker compose version >/dev/null 2>&1; then
  echo "Docker Compose plugin unavailable" >&2
  exit 1
fi
if [[ ! -f .env ]]; then
  echo "Missing deploy/oci/.env. Copy .env.example and fill it on the VM." >&2
  exit 1
fi
if grep -q REPLACE_WITH .env; then
  echo "Replace example password/token before launching containers" >&2
  exit 1
fi
if ! grep -q '^BACKGROUND_WORKERS_ENABLED=false' .env; then
  echo "Refusing pilot start: BACKGROUND_WORKERS_ENABLED must be false" >&2
  exit 1
fi
if ! grep -q '^BTC_QUANT_ENABLED=false' .env; then
  echo "Refusing pilot start: BTC_QUANT_ENABLED must be false" >&2
  exit 1
fi
docker compose config --quiet
echo "Preflight OK: compose is valid, secrets remain local, workers disabled."
