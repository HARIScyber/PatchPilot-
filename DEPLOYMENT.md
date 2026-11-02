# Deployment guide

See [the production deployment guide](docs/PRODUCTION_DEPLOYMENT.md) for the current configuration and limitations.

As checked on 3 November 2026, the supplied Vercel URL returned HTTP 404 and the Render health endpoint timed out without an HTTP response. Source configuration has been updated to use the supplied Render hostname, but a successful live deployment has not been confirmed. See [the end-to-end report](docs/END_TO_END_TEST_REPORT.md) and [the production audit](docs/PRODUCTION_AUDIT.md).

For local setup, follow [README.md](README.md). Never commit `MODEL_API_KEY` or put it in frontend variables.
