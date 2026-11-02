# PatchPilot project inventory

Inventory checked 2 November 2026. Local generated databases, logs, caches, dependencies and workspace data are not intended for Git publication.

| Area | Existing implementation | Status / boundary |
|---|---|---|
| Backend API | `backend/app/main.py`, `backend/app/api/` | FastAPI health, project, patch, repair, provider, public config/stats and evaluation routes |
| Meta integration | `backend/app/services/meta_client.py` | Server-side `MODEL_API_KEY`; live connectivity unverified; explicit simulated mode |
| Database | `backend/app/models/`, `backend/app/database/` | SQLAlchemy ORM; SQLite default; schema uses `create_all` and compatibility migration code; no Alembic versions directory |
| Project intake | `backend/app/services/repo_manager.py`, `backend/app/security/zip_validator.py` | Workspace/file and archive handling with path and size checks |
| Analysis | `backend/app/services/static_analyzer.py`, `localization.py` | Python AST inspection and stack-trace localization; no source execution |
| Planning and patching | `repair_planner.py`, `patcher.py`, `backend/app/api/patches.py` | Candidate plans/diffs, validation and human approval before application |
| Regression tests | `test_generator.py` | Generates test candidates; generated tests are not executed in the current environment |
| Repair loop | `repair_loop.py`, `verification_engine.py`, `test_runner.py`, `security/sandbox.py` | Bounded loop and structured result fields exist; sandbox fails closed with `EXECUTION_UNAVAILABLE` |
| Browser execution | Frontend and WebAssembly | No Pyodide or other browser execution runner is implemented |
| Reports and audit | `reporting.py`, audit/verification models | JSON/Markdown evidence and audit events; no private permalink/share-token system |
| Frontend | `frontend/src/`, `frontend/scripts/`, `frontend/public/` | React + TypeScript + Vite; public pages, three themes, existing workspace at `/work` |
| Hosting | `render.yaml`, `backend/Dockerfile`, `frontend/vercel.json` | Deployment configuration prepared; external accounts/deployments not verified |
| CI and tests | `.github/workflows/ci.yml`, `backend/tests/` | Backend test suite plus frontend contrast, typecheck, and production build steps |
| Evaluation/training | `training/`, `sample_projects/` | Small synthetic benchmark; status is `NOT_MEASURED`, no performance claim |
| Documentation | Root Markdown and `docs/` | Setup, architecture, security, deployment, Meta integration audit and contrast output |

## Excluded local state

The workspace contains `backend/.env`, SQLite files, local server logs, generated workspaces, test caches, and frontend dependencies/build artifacts. `.gitignore` excludes these. Confirm the final Git candidate list in a Git-enabled checkout before committing.
