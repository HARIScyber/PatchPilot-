# Optional Gemini development provider

Meta remains PatchPilot's default provider and the only provider accepted by the submission check. Gemini is selected explicitly with `LLM_PROVIDER=gemini`; a provider error is returned as an error and never triggers a Meta request.

## Verified API facts

Verified against the official Google AI for Developers documentation on 2026-11-03:

- Native REST generation uses `POST https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent` and the `x-goog-api-key` request header.
- Model discovery uses `GET https://generativelanguage.googleapis.com/v1beta/models`; configure `GEMINI_MODEL_ID` only from a model returned by that endpoint and enabled for `generateContent`.
- System messages map to `systemInstruction`; user and assistant turns map to `contents` with `user` and `model` roles.
- Structured JSON output uses `generationConfig.responseMimeType=application/json` and `generationConfig.responseSchema`. Gemini supports a documented subset of JSON Schema.
- Candidate finish reasons include safety blocks and token-limit truncation; PatchPilot reports these as blocked or truncated errors instead of empty successful output.

Sources: [Gemini API key authentication](https://ai.google.dev/gemini-api/docs/api-key), [REST text generation](https://ai.google.dev/gemini-api/docs/generate-content/text-generation), [model list](https://ai.google.dev/api/models), [structured outputs](https://ai.google.dev/gemini-api/docs/structured-output).

## Local use

Put a newly generated key in `backend/.env` or a secret manager, set `LLM_PROVIDER=gemini`, and set `GEMINI_MODEL_ID` after inspecting `GET /api/providers/gemini/models` in local mode. `POST /api/providers/test` makes one live minimal generation request. No live call was performed for this implementation because the only supplied key was exposed in chat and must first be revoked and replaced.

## Current limits

The adapter is normalized through the existing `MetaClient` call boundary so current repair services do not need provider-specific branches. Persistent provider-call provenance, Alembic migration, cassette-backed replay, and full tool-call mapping are not implemented. Replay selection therefore fails closed. Public AI remains disabled by the existing launch gates; Gemini must not be used for the Meta hackathon demo or evaluation.
