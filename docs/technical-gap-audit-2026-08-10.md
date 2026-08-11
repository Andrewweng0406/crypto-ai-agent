# Technical Gap Audit - 2026-08-10

Scope: backend architecture, frontend reliability, persistence, deployment,
security, observability, and test coverage for `crypto-ai-agent`.

Current validation:
- `npm run typecheck` passed.
- `npm run build` passed.
- `npm run e2e` passed: 6 Playwright checks across desktop and mobile.
- `npm audit --audit-level=high` passed: 0 vulnerabilities after upgrading
  Next.js to `16.3.0`.
- `python -m pip_audit -r requirements.txt --strict` passed: 0 known
  vulnerabilities after upgrading FastAPI to `0.141.1` / Starlette to `1.6.0`.
- `./venv/bin/python -m pytest -q` passed: 219 tests.
- Railway production `web` and `frontend` should be smoke-tested after each
  pushed commit; the latest local validation includes the checks above.
- Railway Postgres is provisioned and connected to `web`; `/api/health`
  reports `database_enabled=true`.

## Executive Verdict

The product is technically usable as a beta, but not production-grade for
larger public usage yet. The strongest parts are strategy-specific backend
tests, honest no-mock UI states, Railway deployment, and basic API health.
The main technical gaps are worker isolation, observability, production
configuration, backend dependency auditing, and broader E2E coverage.

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
- Watchlists now seed/read/write/delete through Postgres when `DATABASE_URL`
  is enabled, with JSON snapshot retained as fallback.
- Trade journal now has backend API routes and writes to Postgres in production;
  localStorage is retained only as an offline cache/fallback.
- Closed trade history now writes to Postgres for main crypto/scan signals,
  US stock ORB, RSI2 mean reversion, and meme trade. The four history APIs read
  Postgres first when `DATABASE_URL` is enabled, with memory fallback only if
  the database read fails.
- Startup seeds existing JSON snapshot trade history into Postgres with
  duplicate protection, so the migration does not hide already accumulated
  real records.
- Risk settings now have backend API routes and use Postgres as the production
  source of truth. The frontend risk calculator loads/saves through the backend
  and treats localStorage only as offline cache.
- `main.py` still stores trade/news logs in JSONL paths and stores a broad state
  snapshot in `logs/state_snapshot.json`.
- `main.py` comments explicitly describe the snapshot as "not a real database".

Remaining risk:
- Restart/deploy race can lose or corrupt state.
- Multiple service replicas would diverge.
- Broad process snapshots are not yet fully decomposed into Postgres-owned
  state domains.

Next fix:
- Reduce the broad JSON state snapshot to a fallback/debug artifact after the
  remaining state domains have DB hydration.
- Keep JSONL only as optional local debug export, not product state.

### 2. Split background workers from the API process - first phase started

Evidence:
- FastAPI `lifespan()` starts seven long-running loops with
  `asyncio.create_task`: crypto monitor, US stock ORB, news agent, squeeze,
  options analytics, RSI2, and meme trade.
- Runtime bootstrapping is now factored into reusable helpers:
  `initialize_runtime()`, `start_background_tasks()`, `shutdown_runtime()`, and
  `run_background_workers()`.
- `BACKGROUND_WORKERS_ENABLED=false` lets the API process start without scanner
  loops, while `worker.py` can run the scanner loops as a standalone process.
- `Procfile` now defines both `web` and `worker` process types.
- Migration `2` adds `job_leases`, and each scanner loop now acquires a
  Postgres-backed lease before running a cycle. This prevents duplicate scan
  cycles when multiple worker/API processes are alive.
- Lease TTLs have a 120-second minimum to avoid false expired states on
  short-interval scanners during deploys or transient upstream slowness.
- `/api/background-jobs/health` and the overview trust panel expose lease
  status, so expired scanner ownership is visible without manual database access.

Risk:
- Production Railway still runs the existing single-service behavior by default,
  so one heavy worker can still degrade API latency until a separate worker
  service is created and `BACKGROUND_WORKERS_ENABLED=false` is set on web.
- Deploying API still restarts scanners until the worker service is split out.
- Lease ownership now protects scan cycles from duplicate execution, but scaling
  API replicas still wastes resources unless the web service is configured with
  `BACKGROUND_WORKERS_ENABLED=false`.
- Failures are logged but not centrally observable.

Fix:
- Configure Railway `web` with `BACKGROUND_WORKERS_ENABLED=false`.
- Add at least one Railway worker service running `python worker.py`; later split
  into domain-specific workers if resource contention remains high.
- Add external alerts for expired leases so operators are notified without
  keeping the dashboard open.

### 3. Backend-owned data-source health API - first phase completed

Evidence:
- `/api/data-sources/health` now reports per-source `status`,
  `last_success_at`, `last_error_at`, `last_error`, `stale_after_seconds`,
  `latency_ms`, `records_seen`, and `is_stale`.
- Background loops and local ingest endpoints now update source health.
- The frontend overview trust panel now consumes this backend endpoint, with
  the old inferred labels kept only as a fallback if the health endpoint fails.
- Runtime startup now hydrates data-source health from Postgres when
  `DATABASE_URL` is configured, preserving stale calculations from the original
  `last_success_at` timestamp.
- `/api/data-sources/health` now prefers Postgres rows when available and falls
  back to in-process defaults for sources not yet present in the table.

Remaining risk:
- Worker split still needs a separate worker service plus ownership/locking.

Next fix:
- Add stale-source alerting in Sentry/Telegram after observability is installed.

## P1 - Required For Production Reliability

### 4. Add automated E2E tests - first phase completed

Evidence:
- Playwright is now installed and configured.
- `tests/e2e/dashboard.spec.ts` covers overview rendering, no mock/demo
  placeholders, risk settings backend persistence, tab switching, and mobile
  horizontal overflow.
- CI now installs Chromium and runs `npm run e2e`.
- Next.js has been upgraded to `16.3.0`, clearing the high-severity frontend
  advisories reported by npm audit.

Remaining risk:
- E2E uses deterministic mocked API responses; production smoke tests are still
  needed after Railway deploys.
- Backtest, chatbot streaming, watchlist mutation, journal delete, stock
  overview, and options strategy workflows need dedicated browser coverage.

Next fix:
- Add Playwright coverage for watchlist mutation, journal delete, backend
  offline/local cache states, option strategy cards, and backtest validation.

### 5. Add CI - first phase completed

Evidence:
- `.github/workflows/ci.yml` now runs backend tests and frontend
  dependency audit/typecheck/build/E2E on `push` to `main` and on pull requests.
- The backend job now also runs `pip-audit` against `requirements.txt`, and the
  current backend dependency set reports 0 known vulnerabilities.
- Dependabot now checks backend Python dependencies, frontend npm dependencies,
  and GitHub Actions weekly.
- GitHub Actions should complete successfully for each pushed commit before
  treating the deployment as verified.

Remaining risk:
- Railway still deploys directly from GitHub pushes; deployment is not yet
  blocked on CI success.
- Dependency audit coverage and automated dependency update PRs are now present.

Next fix:
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
- CI now runs `npm audit --audit-level=high` for the frontend and `pip-audit`
  for backend `requirements.txt`.
- Dependabot is configured for pip, npm, and GitHub Actions.

Risk:
- Vulnerable dependencies should now fail CI once committed, and routine update
  PRs should surface available patches automatically.

Fix:
- Review and merge Dependabot PRs only after CI passes.

## Recommended Build Order

1. Add Postgres persistence and migrate watchlists/history/journal.
2. Add data-source health table and `/api/data-sources/health`.
3. Add Playwright E2E tests and GitHub Actions CI.
4. Add Sentry/structured logging/alerts.
5. Split workers from API service.
6. Add repo-managed Railway config and healthchecks.
7. Add OpenAPI contract tests and generated frontend types.
8. Harden global rate limiting and per-source ingest auth.
