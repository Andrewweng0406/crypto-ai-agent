# Technical Gap Audit - 2026-08-10

Scope: backend architecture, frontend reliability, persistence, deployment,
security, observability, and test coverage for `crypto-ai-agent`.

Current validation:
- `npm run typecheck` passed.
- `npm run build` passed.
- `./venv/bin/python -m pytest -q` passed: 197 tests.
- Railway production `web` and `frontend` are running commit `86e182d`.
- Railway Postgres is provisioned and connected to `web`; `/api/health`
  reports `database_enabled=true`.

## Executive Verdict

The product is technically usable as a beta, but not production-grade for
larger public usage yet. The strongest parts are strategy-specific backend
tests, honest no-mock UI states, Railway deployment, and basic API health.
The main technical gaps are persistence, worker isolation, data-source health,
automated E2E coverage, observability, and production configuration.

## P0 - Must Fix Before Serious Public Use

### 1. Replace JSONL/memory/localStorage with a database - first phase started

Evidence:
- `database.py` now defines the initial Postgres migration for
  `signal_snapshots`, `trade_history`, `watchlists`, `journal_entries`,
  `risk_settings`, `data_source_health`, and `ingest_events`.
- Railway Postgres is now provisioned, and `web` has `DATABASE_URL` set via a
  Railway service variable reference.
- FastAPI startup now runs the migration when `DATABASE_URL` is configured; the
  production database has migration `1` applied and all 7 core tables present.
- Data-source health is flushed to Postgres every 30 seconds, and local ingest
  endpoints write audit rows into `ingest_events` when Postgres is enabled.
  Production verification showed `data_source_health` and `ingest_events`
  receiving rows.
- `main.py` still stores trade/news logs in JSONL paths and stores a broad state
  snapshot in `logs/state_snapshot.json`.
- `main.py` comments explicitly describe the snapshot as "not a real database".
- `TradeJournal` persists user journal entries only in `localStorage`.

Remaining risk:
- Restart/deploy race can lose or corrupt state.
- Multiple service replicas would diverge.
- Users cannot access the same journal/watchlist across devices.
- Trade history, watchlists, journal entries, risk settings, and snapshots are
  not yet read/written through Postgres.

Next fix:
- Migrate trade history, watchlists, journal entries, and risk settings to use
  Postgres as the primary source of truth.
- Keep JSONL only as optional local debug export, not product state.

### 2. Split background workers from the API process

Evidence:
- FastAPI `lifespan()` starts seven long-running loops with
  `asyncio.create_task`: crypto monitor, US stock ORB, news agent, squeeze,
  options analytics, RSI2, and meme trade.

Risk:
- One heavy worker can degrade API latency.
- Deploying API restarts all scanners.
- Scaling API replicas would duplicate scanners unless explicitly guarded.
- Failures are logged but not centrally observable.

Fix:
- Keep `web` as API-only.
- Add worker services: `crypto-worker`, `stocks-worker`, `options-worker`,
  `news-worker`, `ingest-worker`.
- Use DB row locks/advisory locks or a queue so only one worker owns each job.

### 3. Backend-owned data-source health API - first phase completed

Evidence:
- `/api/data-sources/health` now reports per-source `status`,
  `last_success_at`, `last_error_at`, `last_error`, `stale_after_seconds`,
  `latency_ms`, `records_seen`, and `is_stale`.
- Background loops and local ingest endpoints now update source health.
- The frontend overview trust panel now consumes this backend endpoint, with
  the old inferred labels kept only as a fallback if the health endpoint fails.

Remaining risk:
- The health state is still served from process memory, but it is now flushed to
  Postgres when `DATABASE_URL` is configured.
- Worker split and Postgres persistence are still needed to make this durable
  across replicas and restarts.

Next fix:
- Read initial data-source health from Postgres on boot after Postgres is
  provisioned.
- Add stale-source alerting in Sentry/Telegram after observability is installed.

## P1 - Required For Production Reliability

### 4. Add automated E2E tests

Evidence:
- There is no Playwright/Cypress config or frontend E2E test files.
- Manual screenshots were used for smoke testing.

Risk:
- Mobile overlap, broken tabs, stale fallback states, and API-offline behavior
  can regress without warning.

Fix:
- Add Playwright tests for homepage, tab switching, mobile viewport, risk
  calculator, journal local persistence, API offline state, and no fake history.

### 5. Add CI - first phase completed

Evidence:
- `.github/workflows/ci.yml` now runs backend tests and frontend
  typecheck/build on `push` to `main` and on pull requests.
- GitHub Actions run `31363773215` completed successfully for commit
  `f866153d1e8e2717ed7162ac4ca241a8fa247fb8`.

Remaining risk:
- Railway still deploys directly from GitHub pushes; deployment is not yet
  blocked on CI success.
- E2E/browser tests and dependency audits are not yet part of CI.

Next fix:
- Add Playwright E2E.
- Add dependency audit jobs.
- Make Railway deploy only after CI passes, if possible.

### 6. Add observability and alerting

Evidence:
- No Sentry/Logfire/OpenTelemetry integration found.
- Logs are plain process logs plus Telegram notifications for some loop
  failures.

Risk:
- Frontend runtime errors, backend exceptions, slow API calls, and data-source
  failures may go unnoticed until a user reports them.

Fix:
- Add Sentry to Next.js and FastAPI.
- Add structured JSON logs with request IDs.
- Add alerts for API 5xx, worker failure streaks, and stale data sources.

### 7. Harden public write and expensive endpoints

Evidence:
- Watchlist and backtest have in-memory IP rate limits.
- Chat route also uses in-memory rate limits.
- Ingest endpoints use a shared `WHALE_SWEEP_API_KEY`.

Risk:
- In-memory limits reset on deploy and do not work globally across replicas.
- Shared ingest key increases blast radius.
- Public watchlist writes mutate global product state, not per-user state.

Fix:
- Move rate limits to Redis/Postgres.
- Use separate ingest keys per source with rotation.
- Require user/session ownership before mutating watchlists.

## P2 - Important Product-Quality Work

### 8. Put Railway configuration in the repo

Evidence:
- Railway status shows service settings, but no `railway.json`,
  `nixpacks.toml`, or explicit service config exists in the repo.
- Railway healthcheck path is not configured in service manifest.

Risk:
- Production behavior is hard to reproduce from Git alone.
- New environment setup depends on dashboard state.

Fix:
- Add explicit Railway configuration for backend and frontend.
- Configure backend healthcheck path `/api/health`.
- Document required env vars for both services.

### 9. API contract tests between backend and frontend

Evidence:
- Backend has Pydantic response models.
- Frontend has manually maintained TypeScript interfaces/adapters.

Risk:
- Backend schema changes can silently break frontend adapters.

Fix:
- Generate OpenAPI schema in CI.
- Add snapshot tests for critical responses.
- Consider generating TypeScript types from OpenAPI.

### 10. Improve risk model rigor

Evidence:
- `lib/risk.ts` currently uses fixed heuristic thresholds for leverage and
  stop-loss distance.

Risk:
- Risk labels are useful but not yet calibrated per asset class, volatility,
  strategy, or user risk profile.

Fix:
- Move risk scoring to backend.
- Include asset volatility, strategy sample size, stale data status, and user
  max-risk settings.
- Add tests for every risk band.

## P3 - Cleanup

### 11. Clean working tree hygiene

Evidence:
- Several untracked research scripts and PDFs are present locally.

Risk:
- Accidental commits/deploys of local research artifacts.

Fix:
- Decide whether each file should be committed, archived, or ignored.
- Keep generated reports and local research scripts out of deploy scope unless
  intentionally productized.

### 12. Dependency/security audit

Evidence:
- No automated `npm audit`, `pip-audit`, or Dependabot workflow found.

Risk:
- Vulnerable dependencies may remain unnoticed.

Fix:
- Add Dependabot.
- Add `npm audit --audit-level=high` and `pip-audit` to CI.

## Recommended Build Order

1. Add Postgres persistence and migrate watchlists/history/journal.
2. Add data-source health table and `/api/data-sources/health`.
3. Add Playwright E2E tests and GitHub Actions CI.
4. Add Sentry/structured logging/alerts.
5. Split workers from API service.
6. Add repo-managed Railway config and healthchecks.
7. Add OpenAPI contract tests and generated frontend types.
8. Harden global rate limiting and per-source ingest auth.
