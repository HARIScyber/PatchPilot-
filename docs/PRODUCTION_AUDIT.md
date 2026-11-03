# Production integration audit

Audit date: 3 November 2026. Source branch: `main` (use `git rev-parse HEAD` for the current revision). No production dashboard credentials were available.

## Working in source

- React 18, TypeScript, and Vite frontend; FastAPI backend with project, analysis, patches, repair, verification, report, provider, health, public config, and aggregate stats routes.
- Meta adapter uses `https://api.meta.ai/v1/chat/completions`, Bearer `MODEL_API_KEY`, and configured `muse-spark-1.3`; errors do not silently fall back to mock mode. Provider response usage is returned where supplied.
- Python static analysis, bounded repair flow, archive validation, patch validation, human approval, report generation, and database-backed ORM models exist.
- Test execution is disabled by the sandbox (`EXECUTION_UNAVAILABLE`) before it launches a subprocess. No Pyodide/browser runner exists.
- The bundled calculator sample is now under `backend/app/sample_data`, copied into the Render image by `COPY app ./app`; missing sample assets return a structured `SAMPLE_NOT_FOUND` response.
- `/api/health` now returns constant-time process/build status without database, filesystem, or provider checks. `/api/health/deep` reports database and cached provider configuration.
- Unified diff patches now reject test/configuration targets, assertion removal, newly introduced process/network imports, `os.system`, and a simple literal-input special-case pattern.
- Verification parses per-test JUnit results, requires a declared failing reproducer and three stable baseline/patched runs, rejects test-file edits, and records execution trust details in report JSON/Markdown. No actual repository execution is possible yet.
- `/api/public/readiness` reports G1–G8; `PUBLIC_AI_ENABLED` is the master switch and remains blocked unless every gate passes. The landing/workspace explain that live AI is off.
- Render Docker startup binds to `0.0.0.0:$PORT`; Vercel serves static frontend output and rewrites API paths.
- CI runs backend tests, Ruff, frontend contrast/typecheck/build, credential scanning, and a Docker image smoke test. CodeQL is configured separately.
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

- Current deployed Vercel URL returned HTTP 404; Render health check timed out without an HTTP response. No post-push host proof is available, and local Docker is unavailable, so deployment and image smoke are not confirmed.
- No authentication/authorization or user-level data isolation exists. Project and report routes must not be treated as private multi-user storage.
- SQLite is the default, Render local disk is ephemeral, there is no PostgreSQL driver/production DB confirmation, and no Alembic migration versions are present. No production data migration was attempted.
- No durable daily/monthly estimated-cost budget, token-based usage ledger, budget threshold warnings, or monthly budget controls are implemented. Existing call caps are not billing guarantees and can reset with database state.
- No persisted per-artifact provider call trace, durable run events/SSE, private share tokens, feedback storage, retention worker, or browser execution runner exists.
- Live Meta connectivity has not been tested; no live key or billing state is known. Public Meta action kill switch remains off by default.
- CSP/API rewrite source is prepared but Vercel dashboard/project settings and Render env settings remain to be confirmed.
- CI adds Ruff over app and tests, credential scanning, and a Docker smoke job; CodeQL is configured. Hosted workflow results have not been captured.
- Version metadata is generated for the frontend and backend Docker image; the frontend footer and `/api/health` expose the non-secret build revision/date.

## Security findings

- Main safe defaults: upload validation, no host execution, key kept server-side, no CORS wildcards, secret/log/database ignore rules, and backend kill switch.
- Remaining high-impact gaps: no auth, no durable abuse/budget controls, missing user-data isolation, ephemeral DB, incomplete prompt-injection/secret scanning of pasted code, and no secure test executor.
- Health responses no longer return database engine URLs or exception text. The backend status reports execution unavailable honestly.

See [SECURITY.md](SECURITY.md) and [END_TO_END_TEST_REPORT.md](END_TO_END_TEST_REPORT.md).
