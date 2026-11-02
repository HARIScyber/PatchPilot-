# Deployment status

See [the production deployment guide](PRODUCTION_DEPLOYMENT.md) for the current Vercel and Render configuration and the dashboard steps still required.

The source config uses Vercel's same-origin `/api/*` rewrite to `https://patchpilot-rurc.onrender.com`. This does not prove a live deployment is updated. As checked on 3 November 2026, the provided Vercel URL returned HTTP 404 and the Render health request timed out without an HTTP response. See [the end-to-end report](END_TO_END_TEST_REPORT.md).

Render Free services can sleep after 15 minutes and use an ephemeral filesystem. The current project defaults to SQLite and has no production migration history, so production data persistence is not established. Application-level request/call limits are not provider billing caps. Review [the production audit](PRODUCTION_AUDIT.md) and [security notes](SECURITY.md) before enabling public AI actions.
