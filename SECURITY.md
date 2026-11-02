# Security notes

PatchPilot is a prototype. It has no user authentication and is not multi-user safe. Do not expose the local development server to untrusted users and do not submit secrets, personal data, or proprietary repository content.

## Current safeguards

- `.env`, nested `.env` files, local databases, logs, caches, generated workspaces, and common key/certificate files are excluded by `.gitignore`.
- `.env.example` contains an empty `MODEL_API_KEY` placeholder. Store a real key in `backend/.env` locally or in the backend host's secret manager. Never use `VITE_*` for secrets.
- The ZIP validator rejects unsafe archive paths and symlinks and bounds archive size, member count, and compression ratio.
- Static analysis does not execute repository code. The current sandbox returns `EXECUTION_UNAVAILABLE` before process creation; there is no browser WebAssembly executor.
- Meta errors are sanitized, and the provider key is excluded from API status/config responses.
- Public demo settings include an off-by-default kill switch, disabled upload behavior, input-size checks, exact-origin CORS, and best-effort in-process request limits. The call counter/rate limit is not a durable, multi-instance abuse control.

## Important gaps

- There is no authentication, durable multi-tenant storage, persistent per-IP rate limiter, secret-scanning/masking stage for pasted code, or automatic data-retention worker.
- No signed browser test-result protocol exists; browser-reported results must not be treated as server-verified.
- Model prompts include untrusted project context. Prompt-injection resistance is incomplete; do not treat model output as trusted code.
- A local SQLite database and uploaded workspaces can contain user data. They are ignored by Git and must remain out of public commits.
- A Git commit containing a real credential requires immediate credential revocation/rotation. Removing the file in a later commit does not remove it from Git history.

## Pre-publication audit (2 November 2026)

- High-confidence scans of project text for Meta `LLM_` keys, GitHub access tokens, common cloud tokens, and PEM private-key headers found no matches.
- The local `backend/.env` file exists and contains no non-empty credential value; it remains ignored and must not be published.
- Local backend/frontend log files and SQLite databases exist; all are excluded by the updated ignore rules. Generated `database/workspaces` and `backend/database/workspaces` are excluded.
- Git and GitHub CLI were unavailable in the workspace, so Git index/history scanning and `git check-ignore` could not be run. A clean publication review must run those checks in the Git-enabled environment before commit.
- No dedicated `gitleaks`, `trufflehog`, or `detect-secrets` executable was available. The text scan is not a substitute for a full history scanner.

Report vulnerabilities privately to the project owner before publishing details.
