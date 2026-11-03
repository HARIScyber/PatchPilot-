"""Robust model JSON extraction, Pydantic validation, and single-attempt repair loop."""
from __future__ import annotations

import json
import logging
import re
from typing import Awaitable, Callable, Optional, Type, TypeVar
from pydantic import BaseModel, ValidationError

from .meta_client import MetaAPIError

logger = logging.getLogger("patchpilot.services.json_parser")
T = TypeVar("T", bound=BaseModel)


def extract_json_candidate(text: str) -> str:
    """Extract candidate JSON substring by stripping markdown fences and preambles/postambles."""
    if not text:
        return ""
    cleaned = text.strip()

    # 1. Check for fenced code blocks
    fence_pattern = re.compile(r"```(?:json)?\s*([\s\S]*?)\s*```", re.IGNORECASE)
    match = fence_pattern.search(cleaned)
    if match:
        cleaned = match.group(1).strip()

    # 2. Strip preamble before the first opening brace or bracket
    first_brace = cleaned.find("{")
    first_bracket = cleaned.find("[")

    start_idx = -1
    if first_brace != -1 and first_bracket != -1:
        start_idx = min(first_brace, first_bracket)
    elif first_brace != -1:
        start_idx = first_brace
    elif first_bracket != -1:
        start_idx = first_bracket

    if start_idx != -1:
        cleaned = cleaned[start_idx:]

    # 3. Strip postamble after the matching closing brace or bracket
    last_brace = cleaned.rfind("}")
    last_bracket = cleaned.rfind("]")
    end_idx = max(last_brace, last_bracket)
    if end_idx != -1:
        cleaned = cleaned[: end_idx + 1]

    # 4. Strip trailing commas before closing braces/brackets (common LLM JSON flaw)
    cleaned = re.sub(r",\s*([\]}])", r"\1", cleaned)
    return cleaned.strip()


def parse_and_validate(raw_text: str, schema_cls: Type[T]) -> T:
    """Parse raw text into candidate JSON and validate with the target Pydantic schema."""
    candidate = extract_json_candidate(raw_text)
    if not candidate:
        raise ValueError("No JSON content found in model response.")
    parsed = json.loads(candidate)
    return schema_cls.model_validate(parsed)


async def robust_model_parse(
    raw_text: str,
    schema_cls: Type[T],
    repair_fn: Optional[Callable[[str, str], Awaitable[str]]] = None,
) -> T:
    """Parse JSON with Pydantic validation, with at most one bounded repair attempt on failure.

    If validation fails after one repair attempt, raises MetaAPIError with MALFORMED_RESPONSE (502).
    Never raises a 500 error.
    """
    first_err: Optional[Exception] = None
    try:
        return parse_and_validate(raw_text, schema_cls)
    except (json.JSONDecodeError, ValidationError, ValueError, TypeError) as exc:
        first_err = exc
        logger.warning("First attempt model JSON validation failed: %s", exc)

    # One bounded repair attempt if repair callback is provided
    if repair_fn is not None:
        try:
            logger.info("Attempting bounded repair of malformed model JSON...")
            err_message = str(first_err)
            repaired_text = await repair_fn(err_message, raw_text)
            return parse_and_validate(repaired_text, schema_cls)
        except Exception as repair_exc:
            logger.error("Bounded JSON repair attempt failed: %s", repair_exc)

    raise MetaAPIError(
        f"Model response was malformed and could not be parsed: {first_err}",
        status_code=502,
        provider_status="MALFORMED_RESPONSE",
    )
