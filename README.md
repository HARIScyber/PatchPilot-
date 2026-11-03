# PatchPilot

**Patches that carry their own proof.**

[![CI](https://github.com/HARIScyber/PatchPilot-/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/HARIScyber/PatchPilot-/actions/workflows/ci.yml)

PatchPilot is a prototype for inspecting Python repositories, generating repair proposals, and recording verification evidence. Static analysis, Meta-assisted plans/patches, approval before applying patches, regression-test generation, reports, and a bounded repair loop are implemented. Repository code execution currently fails closed as `EXECUTION_UNAVAILABLE`; generated patches are not proof of a fix.

## Public endpoints

- Frontend: https://patchpilot-delta.vercel.app/
- Backend: https://patchpilot-rurc.onrender.com
- Source: https://github.com/HARIScyber/PatchPilot- (`main`)

These are the owner-provided production URLs. As of 3 November 2026, the frontend root returned HTTP 404 and the backend health request timed out without an HTTP response. The latest local source has not been confirmed deployed. See [the live test report](docs/END_TO_END_TEST_REPORT.md).

## Features

- React workspace for repository intake, static analysis, repair plans, candidate patches, generated tests, evidence reports, and evaluation status.
- FastAPI project, patch, repair, health, provider, and report APIs.
- Meta remains the default and hackathon submission provider. An explicitly selected Gemini development adapter is available through `LLM_PROVIDER=gemini`; provider failures never switch providers automatically. Demo is explicit, and replay is unavailable until cassettes are implemented.
- ZIP path/size checks and patch validation; human approval is required before applying a patch.
- Evidence/report records distinguish model proposals from actual test results.

Not implemented: authentication, multi-user data isolation, browser/Pyodide test execution, real-time run streaming, durable share links, feedback storage, automatic retention, or durable daily/monthly token-cost budgets. SQLite is the default and is not durable on Render Free. Do not submit private, proprietary, or confidential repositories.

## Architecture and stack

The browser calls same-origin `/api`. Vite proxies `/api` to FastAPI during local development; Vercel rewrites `/api/*` to Render in production. FastAPI uses SQLAlchemy models and SQLite by default. The Meta key stays on the backend. The test runner currently fails closed before starting any repository subprocess.

Technologies: Python 3.11, FastAPI, Pydantic Settings, SQLAlchemy, SQLite, React 18, TypeScript, Vite, Tailwind CSS, and Meta Model API.

See [ARCHITECTURE.md](ARCHITECTURE.md), [the project inventory](docs/PROJECT_INVENTORY.md), and [the production audit](docs/PRODUCTION_AUDIT.md).

Public AI is controlled by the `PUBLIC_AI_ENABLED` master switch and remains disabled until all eight launch-readiness gates pass. See [the launch gates](docs/DEPLOYMENT.md). The public demo is not currently launch-ready: hosting and Docker image checks still need owner-side evidence.

## Local installation

Requirements: Python 3.11+, Node.js 18+. From the repository root in PowerShell:

```powershell
py -3.11 -m venv backend/.venv
backend/.venv/Scripts/python.exe -m pip install -r backend/requirements.txt
Copy-Item .env.example backend/.env
```

The example is for local development: it has no API key, uses `APP_MODE=local`, and sets the public kill switch off. Do not commit `backend/.env`.

## Run locally

Start the backend from the repository root:

```powershell
$env:PYTHONPATH = "backend"
backend/.venv/Scripts/python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --app-dir backend
```

Start the frontend in another terminal:

```powershell
Set-Location frontend
npm.cmd ci
npm.cmd run dev
```

Open the Vite URL (normally `http://localhost:3000`). The development Vite server proxies `/api` to `http://127.0.0.1:8000`. API docs are at `http://127.0.0.1:8000/docs` in local mode. Public mode disables the interactive docs/OpenAPI routes.

## Environment configuration

The root [`.env.example`](.env.example) lists supported backend values. Important settings:

- `MODEL_API_KEY`: secret bearer key; server-side only.
- `LLM_PROVIDER`: `meta` by default, or explicitly `gemini`, `demo`, or `replay`.
- `GEMINI_API_KEY`, `GEMINI_MODEL_ID`, `GEMINI_API_BASE_URL`: optional server-side Gemini development settings. Set the model ID only after checking the credential's available models.
- `ALLOW_DEV_PROVIDER`: permits selecting a non-Meta provider in public-mode configuration; public AI still remains blocked by the launch gates.
- `META_MODEL_ID`, `META_API_BASE_URL`, `META_API_TIMEOUT`, `META_MAX_RETRIES`: provider model and request behavior.
- `APP_MODE`, `DEMO_MODE`, `PUBLIC_DEMO_ENABLED`: runtime mode and public action kill switch.
- `EXECUTION_BACKEND`, `ENABLE_UPLOAD`, `ALLOWED_ORIGINS`: execution, uploads, and explicit CORS origins.
- `DATABASE_URL`: SQLAlchemy database URL; SQLite is the default.
- `MAX_REPAIR_ATTEMPTS` and `PUBLIC_MAX_ATTEMPTS`: bounded repair-loop settings.

Frontend calls use `/api`; no production `VITE_API_BASE_URL` is needed. Production API routing is in [`frontend/vercel.json`](frontend/vercel.json).

## Provider setup

Set `MODEL_API_KEY` in `backend/.env` for local use or in Render's secret environment for production. The official endpoint/model are `https://api.meta.ai/v1` and `muse-spark-1.3`. A missing/rejected key produces a clear provider error; it does not become simulated output unless `DEMO_MODE=true`. A provider test is a real API request and may be billable. Live status and account billing were not verified in this audit.

Meta is the required demo and submission provider (`LLM_PROVIDER=meta`). For optional local Gemini work, create a fresh Gemini API key, store it only in the backend environment, select `LLM_PROVIDER=gemini`, and set `GEMINI_MODEL_ID` to an ID returned by `GET /api/providers/gemini/models`. `POST /api/providers/test` makes one real minimal request and can consume quota. The `GEMINI_API_KEY` pasted into a prior chat was exposed; revoke it and use a newly generated key. This repository does not contain that pasted value. Do not set Gemini as the public submission provider.

## Testing

From the repository root:

```powershell
$env:PYTHONPATH = "backend"
python -m pytest backend/tests -q
Set-Location frontend
node scripts/contrast-check.mjs
npm.cmd run typecheck
npm.cmd run build
```

The suite verifies local behavior with test doubles. It does not prove public connectivity, live Meta access, or isolated execution of uploaded code. The synthetic evaluation dataset is not a measured benchmark (`NOT_MEASURED`).

## Deployment

See [DEPLOYMENT.md](DEPLOYMENT.md), [docs/PRODUCTION_DEPLOYMENT.md](docs/PRODUCTION_DEPLOYMENT.md), and [docs/PRODUCTION_AUDIT.md](docs/PRODUCTION_AUDIT.md). Render uses the existing service ID `srv-dbkd5icipgvc73c80080`; do not create a duplicate. Vercel project root is `frontend`, output `dist`. Render dashboard configuration and deployment confirmation are still required.

## Security and limitations

This is a prototype without authentication. Do not submit secrets or proprietary code. There is no server/browser sandbox for running uploaded code; test execution remains unavailable. Render Free uses ephemeral local storage, so SQLite/workspaces can be lost. CORS credentials are disabled and origins are explicit. Review [SECURITY.md](SECURITY.md) and [docs/SECURITY.md](docs/SECURITY.md).

Current public-check results and exact blockers are in [docs/END_TO_END_TEST_REPORT.md](docs/END_TO_END_TEST_REPORT.md).
