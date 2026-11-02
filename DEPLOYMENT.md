# Deployment guide

The application is prepared for local use. A public deployment has not been created or verified.

## Current status

- Backend container and Render Blueprint exist.
- Vercel static frontend build and `/api/*` rewrite configuration exist under `frontend/`.
- The exact Render service hostname must be verified after account setup; update the Vercel rewrite and CSP if it differs from `patchpilot-api.onrender.com`.
- Do not enable public Meta actions until billing, exact CORS origins, durable usage limits, and the browser execution trust model have been reviewed. Current repository execution is disabled.
- Render Free storage is ephemeral; SQLite/workspace files must not be treated as persistent data.

## Local run

Use the PowerShell commands in [README.md](README.md). Keep local credentials in `backend/.env`; the root `.env.example` is a placeholder template. `MODEL_API_KEY` must never be put in frontend variables or committed.

## Render backend

Create the Blueprint from `render.yaml`. Configure each environment variable in the host dashboard. Start with `APP_MODE=public_demo`, `DEMO_MODE=false`, `EXECUTION_BACKEND=none`, `ENABLE_UPLOAD=false`, `PUBLIC_DEMO_ENABLED=false`, and an exact comma-separated `ALLOWED_ORIGINS`. Keep Meta credentials unset until billing is understood. Render Free's local filesystem is ephemeral and the service can sleep; consult the current [Render Free service limits](https://render.com/docs/free).

## Vercel frontend

Configure the project root as `frontend`, install with `npm ci`, build with `npm run build`, and publish the `dist` output. `frontend/vercel.json` proxies API requests to the Render host and falls back to `index.html`. Before deploying, verify the external Render URL and update both the rewrite destination and CSP `connect-src` origin if needed. Add the exact Vercel production origin to backend CORS settings and redeploy the backend. Preview origins must be allowed explicitly; do not use a wildcard.

Vercel Hobby is limited to personal, non-commercial use under its current [terms](https://vercel.com/legal/terms); choose a plan that fits the intended public use. Hosting research and limitations are recorded in [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md).

## Post-deployment verification

After deploying, record actual outputs for `/api/health`, `/api/public/config`, `/api/public/stats`, hostile-origin CORS, and browser navigation to `/`, `/work`, `/gallery`, `/privacy`, and `/terms`. Test the Meta endpoint only with a configured account and approved billing. Record Lighthouse scores only when measured. No public URL or deployment verification is currently available.
