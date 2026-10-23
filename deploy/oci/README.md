# Oracle Always Free ARM64 pilot

Staging only. No Oracle VM has been provisioned and no production Railway
services have been stopped. This uses verified crypto-ai-agent source.

## Safety

- Confirm VM.Standard.A1.Flex / Ubuntu ARM64 in the account's **home region**,
  marked Always Free-eligible. Keep free resource quotas and disk in budget.
- This pilot disables background tasks via BACKGROUND_WORKERS_ENABLED=false and
  BTC_QUANT_ENABLED=false to prevent duplicate alerts/scans/trade logs.
- Dashboard is bound only to localhost:3000; PostgreSQL is private.
  Do not expose the dashboard publicly without authentication and HTTPS.
- Rotate cloud and AI API secrets, particularly after Railway's October 2026
  security alert. Never commit .env, backups, SSH keys or credentials.
- Verify packages, builds and market-data provider access on actual ARM64 VM.

## Deploy

Install Docker Engine and Docker Compose plugin on Oracle Ubuntu ARM64.
Clone repository and check out this branch. In deploy/oci:

    cp .env.example .env
    chmod 600 .env
    nano .env

Generate a database password with openssl rand -hex 24. Preserve Railway
PostgreSQL 18 and the /data volume independently; test both backups.

    docker compose up -d postgres

Restore a verified pg_dump -Fc backup into the fresh database **before**
starting the backend:

    docker compose exec -T postgres sh -c 'pg_restore --no-owner --no-acl -U "$POSTGRES_USER" -d "$POSTGRES_DB"' < backup.dump
    docker compose up -d --build backend frontend
    docker compose ps
    docker compose logs --tail=100 backend frontend

On your laptop, open a private dashboard SSH tunnel:

    ssh -i /path/to/your/private_key -L 3000:127.0.0.1:3000 ubuntu@VM_PUBLIC_IP

Then browse http://localhost:3000.

Verify historic PostgreSQL rows, /data state, API endpoints, and provider
connectivity. Configure secure public domain/HTTPS before switching webhook
clients such as liquidation and whale-sweep senders.

Only after everything is verified, stop the old worker, enable exactly one
new background worker, switch clients, and then cancel Railway Hobby after
all necessary services have migrated. Previously accrued charges remain payable.
