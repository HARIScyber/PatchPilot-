"""Context windowing and token budget enforcement for LLM requests."""
from __future__ import annotations

import logging
from typing import Optional

from .meta_client import MetaAPIError

logger = logging.getLogger("patchpilot.services.context_budget")

# Hard cap on estimated tokens for context sent to LLM
MAX_CONTEXT_TOKENS_DEFAULT = 2048


def estimate_tokens(text: str) -> int:
    """Fast rough token estimator (~4 characters per token)."""
    if not text:
        return 0
    return max(1, (len(text) + 3) // 4)


def extract_windowed_context(
    content: str,
    line_number: Optional[int] = None,
    window_lines: int = 50,
) -> str:
    """Extract a window of lines around the suspect line number with explicit line numbers.

    Avoids sending whole files when only a local region is needed for analysis or repair.
    """
    if not content:
        return ""
    lines = content.splitlines()
    if not lines:
        return ""

    total = len(lines)
    if line_number is None or line_number < 1:
        start_idx = 0
        end_idx = min(total, window_lines)
    else:
        half = window_lines // 2
        start_idx = max(0, (line_number - 1) - half)
        end_idx = min(total, start_idx + window_lines)
        if end_idx - start_idx < window_lines and start_idx > 0:
            start_idx = max(0, end_idx - window_lines)

    numbered = [
        f"{idx + 1:4d} | {lines[idx]}"
        for idx in range(start_idx, end_idx)
    ]
    return "\n".join(numbered)


def check_context_budget(
    prompt_content: str,
    system_prompt: str = "",
    hard_cap: int = MAX_CONTEXT_TOKENS_DEFAULT,
) -> int:
    """Enforce a hard cap on prompt context tokens; raises MetaAPIError with CONTEXT_TOO_LARGE if exceeded."""
    total_tokens = estimate_tokens(prompt_content) + estimate_tokens(system_prompt)
    if total_tokens > hard_cap:
        logger.warning(
            "Context size %d tokens exceeds budget hard cap %d tokens.",
            total_tokens,
            hard_cap,
        )
        raise MetaAPIError(
            f"Context budget exceeded: estimated {total_tokens} tokens > cap of {hard_cap}.",
            status_code=413,
            provider_status="CONTEXT_TOO_LARGE",
        )
    return total_tokens
