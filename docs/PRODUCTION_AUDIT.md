# Production integration audit

Audit date: 3 November 2026. Source baseline: commit `00db54e` on `main`; follow-up integration changes are in the current workspace. No production dashboard credentials were available.

## Working in source

- React 18, TypeScript, and Vite frontend; FastAPI backend with project, analysis, patches, repair, verification, report, provider, health, public config, and aggregate stats routes.
- Meta adapter uses `https://api.meta.ai/v1/chat/completions`, Bearer `MODEL_API_KEY`, and configured `muse-spark-1.3`; errors do not silently fall back to mock mode. Provider response usage is returned where supplied.
- Python static analysis, bounded repair flow, archive validation, patch validation, human approval, report generation, and database-backed ORM models exist.
- Test execution is disabled by the sandbox (`EXECUTION_UNAVAILABLE`) before it launches a subprocess. No Pyodide/browser runner exists.
- Render Docker startup binds to `0.0.0.0:$PORT`; Vercel serves static frontend output and rewrites API paths.
- CI runs backend tests and frontend contrast/typecheck/build.
- Health wake retries run with increasing delays; an owner-run deployment probe captures status, elapsed time, headers, body, and foreign-origin CORS behavior without credentials.

## Fixed in this integration pass

- Corrected Vercel rewrite from the old `patchpilot-api.onrender.com` target to the supplied `patchpilot-rurc.onrender.com`; production browser requests now use only same-origin `/api` via the rewrite.
- Added API request timeouts, readable network/timeout errors, and propagation of server request IDs to frontend error messages.
- Configured exact production/local origins, disabled credentialed CORS, and limited CORS methods/headers to the routes the app uses.
- Added response request IDs and safe request logs; stripped database URL/path and exception detail from health responses. Added basic, database, and readiness health routes.
- Production defaults are restrictive: public demo mode, uploads off, model actions off. API docs/OpenAPI are disabled in public mode.
- Public Meta health checks now honor the daily call counter; the Meta shared HTTP client now honors the per-call timeout.
- Increased public repair-loop maximum to 3 attempts (still bounded).

## Broken, missing, or incomplete

- Current deployed Vercel URL returned HTTP 404; Render health check timed out without an HTTP response. The changed source has not yet been confirmed deployed.
- No authentication/authorization or user-level data isolation exists. Project and report routes must not be treated as private multi-user storage.
- SQLite is the default, Render local disk is ephemeral, there is no PostgreSQL driver/production DB confirmation, and no Alembic migration versions are present. No production data migration was attempted.
- No durable daily/monthly estimated-cost budget, token-based usage ledger, budget threshold warnings, or monthly budget controls are implemented. Existing call caps are not billing guarantees and can reset with database state.
- No persisted per-artifact provider call trace, durable run events/SSE, private share tokens, feedback storage, retention worker, or browser execution runner exists.
- Live Meta connectivity has not been tested; no live key or billing state is known. Public Meta action kill switch remains off by default.
- CSP/API rewrite source is prepared but Vercel dashboard/project settings and Render env settings remain to be confirmed.
- Follow-up CI adds Ruff, a workspace credential scan, and CodeQL. CodeQL has not run in hosted CI; local checks are not a substitute for its result.

## Security findings

- Main safe defaults: upload validation, no host execution, key kept server-side, no CORS wildcards, secret/log/database ignore rules, and backend kill switch.
- Remaining high-impact gaps: no auth, no durable abuse/budget controls, missing user-data isolation, ephemeral DB, incomplete prompt-injection/secret scanning of pasted code, and no secure test executor.
- Health responses no longer return database engine URLs or exception text. The backend status reports execution unavailable honestly.

See [SECURITY.md](SECURITY.md) and [END_TO_END_TEST_REPORT.md](END_TO_END_TEST_REPORT.md).
