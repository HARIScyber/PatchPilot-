"""Regression test generator using Meta AI to produce verifiable pytest test cases."""
from __future__ import annotations

import ast
import logging
import re
from typing import Optional

from .meta_client import MetaClient

logger = logging.getLogger("patchpilot.services.test_generator")


class RegressionTestGenerator:
    """Generates targeted pytest regression tests for patched code."""

    def __init__(self):
        self.meta_client = MetaClient()

    async def generate_regression_test(
        self,
        bug_description: str,
        target_file: str,
        patch_diff: str,
        existing_test_context: Optional[str] = None,
    ) -> str:
        """Prompt Meta AI to write high-signal regression tests."""
        system_prompt = (
            "You are PatchPilot, an expert AI test engineer. Write targeted pytest test cases that verify "
            "the bug is resolved and prevent regressions. "
            "Ensure tests contain explicit assert statements with informative failure messages. "
            "Output only executable Python code wrapped in ```python ... ``` without conversational commentary."
        )

        user_content = (
            f"Bug Description:\n{bug_description}\n\n"
            f"Target File: {target_file}\n"
            f"Patch Diff:\n{patch_diff}\n\n"
        )
        if existing_test_context:
            user_content += f"Existing Test Context:\n{existing_test_context}\n\n"

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ]

        resp = await self.meta_client.chat_completion(messages, temperature=0.1)
        raw_code = resp["choices"][0]["message"]["content"].strip()

        # Extract code from markdown block
        match = re.search(r"```(?:python)?\s*([\s\S]*?)```", raw_code)
        test_code = match.group(1).strip() if match else raw_code

        # Validate Python syntax
        try:
            ast.parse(test_code)
        except SyntaxError as syn_err:
            if not self.meta_client.settings.DEMO_MODE:
                logger.error("Meta Model generated invalid Python syntax for regression test: %s", syn_err)
                raise ValueError(f"Model generated invalid Python code: {syn_err.msg} (line {syn_err.lineno})")

            logger.warning("DEMO_MODE active: Using verified demo regression test.")
            test_code = (
                "import pytest\n"
                "from core.calculator import compute_cumulative_total\n\n"
                "def test_cumulative_total_boundary_verified():\n"
                '    """Regression test ensuring all elements including the boundary element are summed."""\n'
                "    assert compute_cumulative_total([10.0, 20.0, 30.0]) == 60.0\n"
            )

        return test_code


TestGenerator = RegressionTestGenerator
TestGenerator.__test__ = False
