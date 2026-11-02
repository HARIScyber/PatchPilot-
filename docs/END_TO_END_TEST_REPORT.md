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
