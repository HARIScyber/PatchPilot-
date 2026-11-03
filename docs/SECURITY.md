# Production security notes

This is a prototype, not a multi-user production repair service. It has no authentication or per-user project ownership. Do not put confidential source code, credentials, personal data, private or proprietary repositories into it.

## Safe behavior

- `MODEL_API_KEY` and `GEMINI_API_KEY` are server-side only. Browser code uses same-origin `/api`; no frontend API credential is configured. The Gemini key pasted in chat must be revoked and replaced before use.
- CORS uses explicit origins and methods; credentialed CORS is disabled.
- Database-backed API routes receive a signed random anonymous owner ID in an HttpOnly, SameSite=Lax cookie. Production cookies are Secure; the signing secret must be at least 32 characters and is stored only in the host secret settings. ORM reads, updates, and deletes are owner-scoped; a foreign-owner ID resolves as not found. This is session isolation, not account authentication or recovery.
- Alembic migrations add non-null indexed ownership fields. Legacy rows are assigned the inaccessible `legacy-unclaimed` owner rather than being exposed to a new anonymous session. Production refuses SQLite and refuses startup when the schema is behind.
- Production defaults disable repository uploads and public Meta actions. `APP_MODE=public_demo`, `PUBLIC_AI_ENABLED=false`, `PUBLIC_DEMO_ENABLED=false`, and `EXECUTION_BACKEND=none` are the intended safe values. Public AI also stays blocked unless all eight launch gates pass.
- Public-mode API documentation/OpenAPI are disabled. Health routes return status only and do not expose database URLs, file paths, or exception details.
- Each API response carries an `X-Request-ID`; request logs include ID, method, path, status, and duration, not request bodies/prompts.
- Archive validation checks paths, symlinks, member count, sizes, and compression ratios. Source analysis is static.
- Unified diff validation blocks test/configuration changes, assertion removal, new process/network imports, `os.system`, and simple literal input special-cases.
- The sandbox returns `EXECUTION_UNAVAILABLE` before starting a subprocess. Do not label a generated patch as verified.
- `.gitignore` excludes `.env` files (except `.env.example`), SQLite files, logs, caches, build artifacts, generated workspaces, and common private key/certificate files.

## Unresolved risks

- No authentication means any enabled API actions and records are not safely isolated across users.
- Public IP rate limits and call caps are best-effort/in-process or SQLite backed. There is no durable budget ledger, daily/monthly token-cost cap, or provider-side spend cap.
- User code is not checked by a secret scanner before it could be sent to Meta. Do not submit secrets or proprietary repositories.
- Automatic seven-day data deletion, private share tokens, and disposable workspace rebuild/object storage are not implemented. PostgreSQL has not been provisioned or verified by the owner; SQLite/local workspaces are not durable on Render Free.
- Generated patches/tests are untrusted data. There is no hardened server sandbox or Pyodide runner.

## Secret audit

The previously committed initial tree excludes local `.env`, SQLite databases, logs, and generated workspaces. A local high-confidence scan found no Meta API key, GitHub token, common cloud token, or PEM private-key marker in the text files scanned. This is not a scan of every historical Git object, a provider's secret scanner, or a substitute for rotating any credential that may have been exposed elsewhere.

Never place secrets in Vercel `VITE_*` variables, source code, reports, browser logs, or GitHub commits. Store provider keys in host secret settings. Follow the project's private vulnerability-reporting route before publishing sensitive reports.
