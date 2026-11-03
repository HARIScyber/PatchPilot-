# Deployment diagnosis and owner checklist

## What the available evidence says

On 3 November 2026, the supplied Vercel production URL returned HTTP 404 (`NOT_FOUND`) and the supplied Render `/api/health` request timed out without an HTTP response. After the subsequent GitHub push, the local environment could not reach either host, so no post-push deployment result was captured. The hosting root cause is **not confirmed**: there is no access to the Vercel or Render project dashboard, deployment logs, or current service environment.

The source-side routing issue that was confirmed has been corrected: `frontend/vercel.json` now sends `/api/*` to `https://patchpilot-rurc.onrender.com/api/*`, with the SPA fallback after that rewrite. This does not establish that Vercel's production project builds from this configuration. A Vercel 404 may indicate a project root/build/output/domain issue, but that is a hypothesis until its deployment settings and build log are inspected.

## Vercel project settings to verify

In the existing Vercel project, check the production deployment and build log, then confirm:

- Root Directory: `frontend`.
- Framework Preset: `Vite`.
- Install Command: `npm ci` (or the detected equivalent).
- Build Command: `npm run build`.
- Output Directory: `dist`.
- The successful deployment is the one assigned to `patchpilot-delta.vercel.app`.
- `frontend/vercel.json` is at that configured root. Its API rewrite targets the complete Render HTTPS origin and precedes the SPA fallback.
- The deployment log shows a supported Node version and no failed install/build step.

No dashboard setting has been changed or verified from this workspace. If the current project uses the repository root, set the Root Directory to `frontend`, redeploy, and capture the successful build log. That is the first setting to verify because there is no root `index.html`, but it is not yet proven to be the 404 cause.

## Render service settings to verify

Inspect the existing service `srv-dbkd5icipgvc73c80080` (do not create a duplicate) and capture the build/start log. The repository Dockerfile starts Uvicorn on `0.0.0.0:${PORT:-8000}`; the configured Render health path is `/api/health`. Production now requires PostgreSQL in `DATABASE_URL`, a 32-character-or-longer `SESSION_SIGNING_SECRET`, and the current Alembic schema. Run `alembic upgrade head` as a release pre-deploy command before startup. Confirm the Docker image built, the service started with Render's assigned `PORT`, and required variable **names** are present. Never copy secret values into logs or this repository.

`/api/health` is constant-time and does not access the database, filesystem, or Meta. `/api/health/deep` separately checks database connectivity and cached provider configuration. A free instance may need time to wake, so the owner-run probe allows 120 seconds. The SQLite database directory is `/app/database` in the container and is writable by the non-root app user, but Render Free storage is ephemeral; no persistent disk or durable production database has been established. Sample data is loaded through the explicit sample-project action, not silently seeded at startup.

The Docker build context is `./backend`. The sample source now lives under `backend/app/sample_data`, which is included by `COPY app ./app`. The SQLAlchemy database package also lives under `backend/app/database`; a broad ignore pattern previously omitted it from Git and has now been narrowed. The CI smoke-test workflow builds this exact context and POSTs `/api/projects/load-sample`.

The frontend retries health requests with increasing delays and keeps start actions disabled until the backend responds. An external keep-warm monitor is optional; configure one only if you accept the plan's availability and usage implications. A keep-warm ping does not make ephemeral storage durable.

## Capture deployment evidence

From PowerShell at the repository root, run:

```powershell
./scripts/check-deploy.ps1
```

It probes direct Render health (up to 120 seconds), Vercel root, a deep SPA route, Vercel-proxied health, and direct Render CORS from a foreign origin. It writes timestamped status, elapsed time, headers, response bodies, and the CORS decision to `deploy-proof.json` without sending credentials. Review the generated file before sharing it. It is local evidence and is intentionally not committed by default.

Run `./scripts/launch-check.ps1` to save `launch-proof.json` from `/api/public/readiness`. It exits successfully for Launch 0 only when G1 and G2 pass. A successful Launch 0 check does not turn on AI; `PUBLIC_AI_ENABLED` stays ineffective until every gate passes. Current readiness is blocked because no deployed proof or Docker image smoke result is available, and gates G3–G7 remain unimplemented/unverified.

Acceptance requires HTTP 200 from direct Render health, Vercel `/`, a deep Vercel route, and Vercel `/api/health`, plus no `Access-Control-Allow-Origin` for the foreign origin. If any check fails, inspect the corresponding Vercel deployment log or Render service log and record the exact log line and setting changed here. Do not label a guessed cause as the fix.

See the [production deployment guide](PRODUCTION_DEPLOYMENT.md), [end-to-end report](END_TO_END_TEST_REPORT.md), and [production audit](PRODUCTION_AUDIT.md). The public deployment remains unverified until fresh proof is captured after a successful deployment.
