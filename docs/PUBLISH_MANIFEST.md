# GitHub publish manifest

This workspace is an existing Git repository on `main`, tracking `origin/main` at the GitHub repository supplied by the owner. The current integration changes are intended as a normal additive commit on that branch. No history rewrite or force push is needed.

The repository `.gitignore` excludes local environment files (except `.env.example`), database files, logs, generated workspaces, dependency folders, build artifacts, Python caches, and common private-key/certificate files. Review `git status --short` before staging; never add local secrets.

The production integration pass updates the frontend API rewrite/client, backend safe defaults and health/CORS behavior, regression coverage, and deployment/security documentation. See [the end-to-end report](END_TO_END_TEST_REPORT.md) for the checks run and the status of the public URLs.
