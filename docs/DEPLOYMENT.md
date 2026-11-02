# Deployment status and launch checklist

Hosting facts checked **2 November 2026** against official documentation. This repository is prepared for deployment; no Vercel or Render account was linked, no deployment was run, and there is no public URL yet.

## Decision: Option A

Host the static React frontend on Vercel and keep FastAPI on the existing Render Blueprint. Vercel documents external-origin rewrites, so `/api/*` is proxied through the frontend origin. Vercel Hobby currently limits function duration to 300 seconds, but this design does not put FastAPI in a Vercel function. Vercel Hobby is restricted to personal, non-commercial use; the current Terms of Service (updated 19 October 2026) must be checked against the intended public hackathon use before deploying. See [Vercel rewrites](https://vercel.com/docs/routing/rewrites), [Vercel function limits](https://vercel.com/docs/functions/limitations), [Hobby plan](https://vercel.com/docs/plans/hobby), and [Terms](https://vercel.com/legal/terms).

The Vercel config currently proxies to `https://patchpilot-api.onrender.com`. Render documents that a service's public `onrender.com` hostname includes its service name, but account availability can alter the final hostname. Confirm the actual Render URL after creating the Blueprint; if it differs, update both `frontend/vercel.json` (rewrite and CSP `connect-src`) and `frontend/public/_headers` before deploying. Render Free services sleep after 15 minutes idle, take about one minute to wake, have ephemeral filesystems, and receive 750 workspace instance hours per month. SQLite and project files can disappear after restarts, spin-downs, or deploys. See [Render Free services](https://render.com/docs/free) and [Render web services](https://render.com/docs/web-services).

Meta Model API is pay-as-you-go. Current standard Muse Spark pricing is $1.25 per million input tokens and $4.25 per million output tokens. Contributor mode permits Meta to use submitted prompts, code, files, context and responses to train future models; this project must use standard mode for submitted user material. Billing and quota for the owner's account are unknown. No Meta key is committed or configured here. See [Meta pricing and rate limits](https://dev.meta.ai/docs/pricing-rate-limits) and [Meta API overview](https://dev.meta.ai/docs/overview).

Vercel Python Functions allow 500 MB uncompressed bundles, but Option B is rejected: this app uses SQLite, local workspace files, synchronous repair flows and process-local controls, and does not have a durable external store or step-based run controller. See [Vercel Python runtime](https://vercel.com/docs/functions/runtimes/python). This launch setup does not move FastAPI to Vercel.

## Current public capability gate

- A real Meta request has **not** been confirmed (`POST /api/providers/meta/test` not run against a configured account).
- The backend records model IDs on generated patches and evidence reports, but there is no public live-call trace stream.
- Verification records have baseline/patched fields and status logic, but the execution backend is deliberately disabled (`EXECUTION_BACKEND=none`). The public UI calls out `EXECUTION_UNAVAILABLE`; it does not label generated output as a verified fix.
- There is no browser WebAssembly runner, repair-run state machine, persisted event feed/SSE, private share link, feedback store, approved gallery records, or seven-day deletion job.
- `GET /api/public/stats` returns aggregate project and verification row counts from the configured database. It does not claim users, unique viewers, or successful public repairs.
- Existing in-process rate limits and SQLite Meta call caps are not durable abuse controls. Do not expose live Meta actions publicly until durable budgets/rate controls and provider billing are configured.

Accordingly, the deployment is **not ready for public Paste and Fix**. The Vercel site can host the honest prototype landing/workspace, but public repair execution, reports with share tokens, and real-time collaboration remain unavailable.

## Vercel setup (PowerShell)

After verifying the Terms and the real Render URL, configure the backend first. Keep `PUBLIC_DEMO_ENABLED=false`, `EXECUTION_BACKEND=none`, uploads disabled, and `MODEL_API_KEY` only in the Render secret manager. Set `ALLOWED_ORIGINS` to the exact Vercel production origin; add each preview origin explicitly when needed. Do not use a wildcard.

```powershell
npm i -g vercel
vercel login
Set-Location frontend
vercel link
vercel env add VITE_APP_MODE production
vercel --prod
```

Vercel project root is `frontend`; build command is `npm run build`, output directory is `dist`, install command is `npm ci`. The project has `/api/*` external-origin rewrite, SPA fallback, security headers, no-store API response headers, and a CSP limited to the app and configured Render origin. This is a static frontend deployment: no `MODEL_API_KEY` belongs in Vercel. Vercel external rewrite configuration is documented at [Rewrites](https://vercel.com/docs/routing/rewrites); header configuration is in [vercel.json](https://vercel.com/docs/project-configuration/vercel-json).

Vercel preview deployments and GitHub CI are supported by the existing workflow. Preview frontend requests will be rejected by backend CORS until their exact origins are added to `ALLOWED_ORIGINS` and the backend redeployed. Avoid wildcard origins.

## Local checks and deployment verification

The build and tests must be run before deployment. After an actual deployment, run the health, config, provider test, hostile-origin CORS, and browser checks in the launch brief. None has been run against a public site; no Lighthouse score, stream check, or production browser run is available. The contrast-check output is recorded in [contrast-check-output.txt](contrast-check-output.txt).

No hardcoded URLs in the final report should imply a deployment exists. Update this document with the actual Vercel and Render URLs, real command output, Lighthouse scores, provider status and browser findings only after running them.

## Rollback and limitations

Disable public AI actions with `PUBLIC_DEMO_ENABLED=false` in Render and redeploy. Revert the Vercel deployment from its dashboard. Free Render restarts can erase SQLite/workspaces; no auth, persistent public storage, browser test runner, share links, SSE, feedback collection or retention automation currently exists. Treat this as a hackathon prototype, without warranty, and use only non-sensitive sample material.
