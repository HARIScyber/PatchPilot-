# End-to-end verification report

Checked 3 November 2026. This report records observed results only; tests were not run against a local substitute for the production URLs.

| Check | URL/command | Expected | Actual | Result |
|---|---|---|---|---|
| GitHub main exists | `git ls-remote --heads origin main` | Remote main SHA matches source | `352d0004f60b92e57ef227a89e91df1cb1c0ec80` | PASS |
| Local branch/status | `git status --short --branch`; `git branch -vv` | Clean main tracking origin/main before edits | Clean at start, `main` tracking `origin/main` | PASS |
| Vercel frontend | `GET https://patchpilot-delta.vercel.app/` | HTTP 200 and PatchPilot page | HTTP 404, Vercel `NOT_FOUND` response | FAIL |
| Render health | `GET https://patchpilot-rurc.onrender.com/api/health` | Sanitized health JSON | curl exit 28 after 100 seconds; no HTTP response | BLOCKED |
| Render config/stats/provider status | Render `/api/public/config`, `/api/public/stats`, `/api/providers/meta/status` | JSON response | Not reached after health endpoint timed out | BLOCKED |
| Render CORS preflight | OPTIONS `/api/health` from exact Vercel origin | 200 and exact allow-origin | Not run because Render did not respond | BLOCKED |
| Hostile-origin CORS | GET `/api/health` from `https://evil.example` | No allow-origin header | Not run against deployed host | BLOCKED |
| Live Meta provider call | POST `/api/providers/meta/test` | `LIVE_CONNECTED` only with configured key | Not run; Render did not respond and account billing/key are unknown | NOT RUN |
| Real repository analysis | Vercel UI -> Render API | Actual project/analysis response | Not run; frontend URL is 404 | BLOCKED |
| Browser console/CORS display | Browser visit to Vercel site | No console errors and API state displayed | Not run; no browser session available and Vercel returns 404 | BLOCKED |
| Production bundle secret scan | Built frontend assets | No API credential | No credential-like key or server-only API key found in built assets | PASS |
| Local backend tests | `python -m pytest tests -q` from `backend` | All tests pass | 41 passed, 2 third-party deprecation warnings | PASS |
| Frontend checks | `node scripts/contrast-check.mjs`; `npm.cmd run typecheck`; `npm.cmd run build` | All pass | Contrast checks passed for all 3 themes; typecheck passed; Vite production build succeeded | PASS |

## Follow-up integration checks

These checks were run in the follow-up integration pass after the previous GitHub source update:

| Check | Command | Actual | Result |
|---|---|---|---|
| Backend regression suite | `python -m pytest tests -q` from `backend` | 41 passed, 2 third-party deprecation warnings | PASS |
| Frontend contrast/typecheck/build | `node scripts/contrast-check.mjs`; `npm.cmd run typecheck`; `npm.cmd run build` | All three themes pass; TypeScript passes; Vite build succeeds | PASS |
| Ruff | `python -m ruff check backend/app` | All checks passed | PASS |
| Credential scan | `python scripts/credential-scan.py` | No configured credential patterns found | PASS |
| Deploy probe script syntax | PowerShell parser on `scripts/check-deploy.ps1` | Parse succeeded | PASS |
| Deployment HTTP evidence | `./scripts/check-deploy.ps1` | Not run here because outbound network access is unavailable; owner must run it to create `deploy-proof.json` | NOT RUN |
| CodeQL | GitHub Actions workflow | Workflow added; no hosted workflow result available in this environment | NOT RUN |
| Live Meta, repository execution, proof-bundle verification, benchmark, deployed Playwright | Requires a live provider key, isolated runner, reachable deployment, and/or hosted CI | No output captured; no result claimed | NOT RUN |

The probe script writes `deploy-proof.json` locally; it is gitignored because it can contain full HTTP response bodies. The script sends no credentials. Review the evidence file before sharing it.

The first post-push live probes were blocked by outbound network connectivity in this environment. No post-push HTTP result is available; the earlier Vercel 404 and Render timeout remain the last actual HTTP responses.

## Deployment changes

The source now targets the provided Render hostname and uses a same-origin `/api` client. Local backend/frontend checks pass. No Vercel or Render dashboard deployment has been confirmed; the observed public endpoints remain unavailable as recorded above. A GitHub push does not prove the platform deployment succeeded.

## Commands for the next live verification

```powershell
$site = "https://patchpilot-delta.vercel.app"
Invoke-RestMethod "$site/api/health"
Invoke-RestMethod "$site/api/public/config"
Invoke-RestMethod "$site/api/public/stats"
curl.exe -i -X OPTIONS "$site/api/health" -H "Origin: https://patchpilot-delta.vercel.app" -H "Access-Control-Request-Method: GET" -H "Access-Control-Request-Headers: content-type"
curl.exe -i "$site/api/health" -H "Origin: https://evil.example"
```

Call `POST /api/providers/meta/test` only after the service owner confirms a valid Render-side key and acceptable billing. A one-token connectivity ping still may incur token charges.
