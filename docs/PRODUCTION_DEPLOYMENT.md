# Production deployment guide

## Authoritative endpoints

- Frontend: <https://patchpilot-delta.vercel.app/>
- Backend: <https://patchpilot-rurc.onrender.com>
- Render service ID: `srv-dbkd5icipgvc73c80080` (do not create a duplicate)
- GitHub: <https://github.com/HARIScyber/PatchPilot->, branch `main`

The deployment config uses Vercel external-origin rewrites to proxy same-origin `/api/*` requests to the Render backend. The browser client always calls `/api`; local Vite proxies to `127.0.0.1:8000`, production Vercel rewrites to the given Render host. This avoids a production `VITE_API_BASE_URL` and browser CORS dependency while retaining exact CORS for direct-origin requests.

## Source configuration

- `frontend/vercel.json`: SPA fallback, `/api/:path*` rewrite to `https://patchpilot-rurc.onrender.com/api/:path*`, security headers, CSP `connect-src 'self'`, and `Cache-Control: no-store` for API responses.
- `frontend/package.json`: `npm run build` runs TypeScript checking and the Vite production build; Vercel output is `dist`.
- `render.yaml` and `backend/Dockerfile`: existing service name and Docker setup are preserved. The container binds `0.0.0.0` and Render's `$PORT`; health-check path is `/api/health`.
- `ALLOWED_ORIGINS`: local development and the exact production origin `https://patchpilot-delta.vercel.app` are in the safe code default and `.env.example`. On the existing Render service, verify the environment value is exactly that Vercel origin plus only intentionally enabled local/preview origins. Do not use `*`; credentials are not required and CORS credentials are disabled.
- `MODEL_API_KEY`: set only in Render's secret environment. Do not create any `VITE_*` key or put it in Vercel, GitHub, a report, or browser code.

## Render dashboard settings to confirm

Inspect the existing service ID before changing settings. Keep:

```text
APP_MODE=public_demo
DEMO_MODE=false
EXECUTION_BACKEND=none
ENABLE_UPLOAD=false
PUBLIC_DEMO_ENABLED=false
ALLOWED_ORIGINS=https://patchpilot-delta.vercel.app
```

The last value may include localhost only for a deliberate development deployment; production should not include localhost. Leave `MODEL_API_KEY` unset until the account's billing is understood. If live mode is enabled later, use standard (non-Contributor) Meta mode when user code must not be used for model training. Public repair actions remain disabled by the kill switch until cost limits and provider billing have been reviewed.

Vercel project root should be `frontend`; install `npm ci`, build `npm run build`, output `dist`. No frontend API-base environment variable is needed. The settings above must be changed in the service dashboard if they differ; source changes do not prove dashboard state.

## Persistence and migrations

Current SQLAlchemy code defaults to SQLite and creates tables at startup. There is no committed Alembic migration history, PostgreSQL driver, or known production database URL. Render's local filesystem is ephemeral; SQLite and repository workspaces may disappear after restart, redeploy, or spin-down. No live data migration is attempted. Before using this as a multi-user service, provision PostgreSQL, add/test Alembic migrations, take a verified backup, and migrate without deleting the current source data. See [Render Free service storage limits](https://render.com/docs/free).

## Current deployment verification

On 3 November 2026, the supplied Vercel root returned HTTP 404. The Render `/api/health` request timed out after 100 seconds with curl exit code 28 and no HTTP response. These local configuration changes are not deployed until the platforms confirm new deployments. Confirm Git integration, project root, production branch, and the Render service dashboard, then redeploy the existing services (do not create another Render service). Use the commands in [END_TO_END_TEST_REPORT.md](END_TO_END_TEST_REPORT.md) and update the report only with actual results.

The backend Docker image packages the bundled calculator source under `app/sample_data` and generates `app/version.json` during image build. Render documents `RENDER_GIT_COMMIT` and `RENDER_GIT_BRANCH` as runtime variables and translates service variables to Docker build arguments; the image uses only those non-secret identifiers. The API reads build metadata once at startup and includes it in `/api/health`. The frontend generates `version.json` at build time and shows it in the landing-page footer.

For a single capture of direct/proxied health, SPA fallback, headers, elapsed time, and foreign-origin CORS, run `./scripts/check-deploy.ps1` from the repository root. It allows 120 seconds per request and writes local `deploy-proof.json`; the file is gitignored. Review response bodies before sharing it. The precise host-side root cause remains unknown until the Vercel and Render dashboard logs are inspected.

Official hosting facts checked 3 November 2026: Vercel [external rewrites](https://vercel.com/docs/routing/rewrites); Render [Free limits and ephemeral storage](https://render.com/docs/free). Render Free sleeps after 15 minutes idle, may take about a minute to start, and does not persist local SQLite files.
