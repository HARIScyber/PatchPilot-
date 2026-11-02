# Meta API integration audit

## Findings

- `MetaClient.chat_completion` is the only real Meta request adapter. It is called by `RepairPlanner`, `Patcher`, `TestGenerator`, and `RepairLoopOrchestrator` for plan generation, patch generation, regression tests, and retry reasoning. Health checking also sends a genuine one-token Chat Completions request.
- Demo mode is an explicit local simulated completion in `MetaClient._mock_completion`. Planner and test generator also have deterministic demo-only substitutions for malformed mock output; these are logged, but the artifact database does not retain the provider label, so reports cannot trace those artifacts reliably.
- Live mode has no silent provider fallback. However, artifact records do not persist provider/model/request IDs, so historical reports cannot prove which provider call produced an artifact.
- `MODEL_API_KEY` is primary, with `META_API_KEY` retained as legacy fallback. Keys stay on the backend. Provider error bodies and arbitrary exception text must not be exposed.
- Official documentation confirms base URL `https://api.meta.ai/v1`, bearer key `MODEL_API_KEY`, model `muse-spark-1.3`, and `/chat/completions`. Chat Completions remains compatible with the current messages-array design; Responses offers reasoning continuity and is recommended for new agentic workflows. No migration was made.
- Meta integration is implemented but not verified live without valid account credentials and a successful request. No key or account entitlement is inferred from local configuration.

## Feature status

| Feature | Status | Evidence / limitation |
| --- | --- | --- |
| Static analysis and project intake | Implemented | FastAPI project routes and analyzer |
| AI plan, patch, regression test | Implemented with live adapter and explicit demo mode | Provider provenance is not persisted per artifact |
| Patch approval before applying | Implemented | Apply endpoint checks `is_approved` |
| Disposable snapshots | Implemented | Copies project files to temporary directories |
| Secure process isolation | Unavailable | Current runner always returns `EXECUTION_UNAVAILABLE`; there is no host execution override |
| Repair loop | Partial | Bounded retries; cannot claim verified repairs while execution is unavailable |
| Evidence report | Partial | Captures observed execution, but provider attribution is incomplete |
| Benchmark metrics | Withdrawn | Prior evaluation fabricated rates; current script reports `NOT_MEASURED` |
| Genuine live Meta workflow | Unverified | Requires valid key/account and successful end-to-end run |

## Changes in this audit

Provider status errors no longer include provider response bodies; malformed completion payloads are rejected; usage/model/status metadata is recorded in call responses. Host execution now returns `EXECUTION_UNAVAILABLE` by default instead of treating temporary copies as isolation. Health output describes that limitation accurately. Evaluation scores and README performance claims are withdrawn. See the final run record for commands and results.

## End-to-end run and additional defects found (2026-11-01)

The sample workflow exposed two additional correctness bugs: the demo adapter matched `root cause` before classifying the requested artifact, so patch generation returned plan JSON; and the diff validator ignored file-header identity, hunk context, source/output line positions, and hunk counts, allowing malformed/no-op patches to be marked valid. The adapter now routes demo requests by system task; diff validation checks target paths, exact context, line positions, and counts. Approval revalidates the candidate, and apply rejects a target whose hash changed after generation. Workspace containment checks now use resolved path ancestry.

The verification response now includes actual exit codes; when no process starts, the code is `null` and the UI says `NOT RUN` rather than `FAILED`. Evidence reports select the newest patch/test/plan by timestamp and label patches as candidates. The sample workflow test covers intake, analysis, plan, patch, regression test generation, verification, repair loop, and evidence report. It ends at `EXECUTION_UNAVAILABLE` as designed; no repository tests are run or claimed as passed.

Validation on 2026-11-01: `python -m pytest backend/tests -q` â€” 26 passed, 4 warnings; `npm.cmd run build` â€” passed. The backend and frontend were restarted with the audited source, and the end-to-end sample workflow completed through the evidence report over the frontend API proxy. The generated diff was structurally valid; verification and the bounded repair loop correctly ended at `EXECUTION_UNAVAILABLE`, with no test exit codes. Provider status was `DEMO_MODE`. Live Meta API and secure-container tests remain not run.

## Correctness pass (2026-11-02)

- Unified diff handling preserves meaningful whitespace, strictly decodes UTF-8 source, preserves the file's newline style, and locates contextual hunks even when their reported line numbers are stale. Stale context remains rejected. Existing no-newline markers are still unsupported.
- A patch application error is `NOT_VERIFIED`; passing patched tests only count as verified when the baseline failed, since an already-passing baseline does not demonstrate a fix.
- Pytest counts are taken from pytest's JUnit XML report, not parsed from terminal prose or fabricated as a one-test pass. Counts remain unknown when the report is unavailable.
- The retry prompt now includes source context and tells the model to treat repository contents and test output as untrusted data. Its source path is workspace-contained.
- Reports associate evidence with the patch referenced by the latest verification run. Markdown output fences expand around embedded backtick sequences.
- Localization downranks test files. A regression test now makes the repair attempt-limit assertion exercise actual repeated failures rather than an unavailable workspace.

Validation on 2026-11-02: from `backend`, `$env:PYTHONPATH='.'; python -m pytest tests -q` — 38 passed, 2 dependency deprecation warnings; `python -m ruff check app` — passed. Frontend TypeScript typecheck passed during `npm.cmd run build`; Vite/esbuild could not read the workspace under the current filesystem sandbox, so the bundle build did not complete in this run. Live Meta, restricted-container execution, and public deployment remain unverified; no provider key or hosting credentials were present.
