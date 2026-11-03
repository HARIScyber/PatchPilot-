"""Tests for edit blocks diff building, JSON parser robustness, context budgets, and provider ledger."""
import pytest
from pathlib import Path
from pydantic import BaseModel

from app.services.patcher import Patcher, PatchValidationError
from app.services.context_budget import extract_windowed_context, check_context_budget
from app.services.json_parser import extract_json_candidate, robust_model_parse
from app.services.provider_ledger import enforce_atomic_budget, record_provider_call
from app.services.runner import DockerRunner, BrowserWasmRunner
from app.services.meta_client import MetaAPIError


class SampleModel(BaseModel):
    name: str
    count: int


def test_build_diffs_from_edit_blocks(tmp_path: Path):
    target = tmp_path / "module.py"
    target.write_text("def run():\n    x = 1\n    return x\n", encoding="utf-8")
    patcher = Patcher()

    edits = [{
        "path": "module.py",
        "old_text": "    x = 1",
        "new_text": "    x = 2",
    }]
    diffs = patcher.build_diffs_from_edit_blocks(tmp_path, edits)
    assert "module.py" in diffs
    assert "-    x = 1" in diffs["module.py"]
    assert "+    x = 2" in diffs["module.py"]


def test_build_diffs_rejects_test_files(tmp_path: Path):
    t_file = tmp_path / "tests" / "test_foo.py"
    t_file.parent.mkdir(parents=True)
    t_file.write_text("assert True\n", encoding="utf-8")
    patcher = Patcher()

    edits = [{"path": "tests/test_foo.py", "old_text": "assert True", "new_text": "assert False"}]
    with pytest.raises(PatchValidationError, match="test files"):
        patcher.build_diffs_from_edit_blocks(tmp_path, edits)


def test_build_diffs_rejects_deleted_assertions(tmp_path: Path):
    target = tmp_path / "mod.py"
    target.write_text("assert x > 0\nx = 1\n", encoding="utf-8")
    patcher = Patcher()

    edits = [{"path": "mod.py", "old_text": "assert x > 0\nx = 1", "new_text": "x = 1"}]
    with pytest.raises(PatchValidationError, match="assertions"):
        patcher.build_diffs_from_edit_blocks(tmp_path, edits)


def test_build_diffs_rejects_literal_special_casing(tmp_path: Path):
    target = tmp_path / "mod.py"
    target.write_text("def check(value):\n    return True\n", encoding="utf-8")
    patcher = Patcher()

    edits = [{"path": "mod.py", "old_text": "    return True", "new_text": "    if value == 'special': return False\n    return True"}]
    with pytest.raises(PatchValidationError, match="special-casing"):
        patcher.build_diffs_from_edit_blocks(tmp_path, edits)


def test_robust_json_extraction_with_fences_and_preamble():
    raw = "Sure! Here is the JSON:\n```json\n{\"name\": \"test\", \"count\": 42}\n```\nHope that helps!"
    candidate = extract_json_candidate(raw)
    assert candidate == '{"name": "test", "count": 42}'


@pytest.mark.asyncio
async def test_robust_model_parse_with_bounded_repair():
    raw_invalid = "Here is the response: {\"name\": \"broken\""  # missing closing brace and count field

    async def mock_repair(err: str, text: str):
        return "{\"name\": \"fixed\", \"count\": 10}"

    result = await robust_model_parse(raw_invalid, SampleModel, repair_fn=mock_repair)
    assert result.name == "fixed"
    assert result.count == 10


@pytest.mark.asyncio
async def test_robust_model_parse_fails_to_502_malformed_response():
    raw_invalid = "Not JSON at all"

    async def failing_repair(err: str, text: str):
        return "Still not JSON"

    with pytest.raises(MetaAPIError) as exc_info:
        await robust_model_parse(raw_invalid, SampleModel, repair_fn=failing_repair)
    assert exc_info.value.provider_status == "MALFORMED_RESPONSE"
    assert exc_info.value.status_code == 502


def test_context_windowing_and_budget_cap():
    content = "\n".join(f"line_{i} = {i}" for i in range(1, 101))
    window = extract_windowed_context(content, line_number=50, window_lines=10)
    assert "50 | line_50 = 50" in window
    assert len(window.splitlines()) == 10

    # Test exceeding context hard cap
    with pytest.raises(MetaAPIError) as exc_info:
        check_context_budget("x" * 20000, hard_cap=500)
    assert exc_info.value.provider_status == "CONTEXT_TOO_LARGE"
    assert exc_info.value.status_code == 413


def test_docker_runner_selector_validation(tmp_path: Path):
    runner = DockerRunner()
    # Selector starting with '-' must be rejected
    with pytest.raises(ValueError, match="leading '-'"):
        runner.validate_selector(tmp_path, "-s -v")

    # Selector escaping snapshot workspace must be rejected
    with pytest.raises(ValueError, match="escapes"):
        runner.validate_selector(tmp_path, "../../etc/passwd")


def test_browser_wasm_signed_token_lifecycle():
    wasm_runner = BrowserWasmRunner(signing_secret="a" * 32)
    token = wasm_runner.generate_signed_run_token("proj-1", "patch-1", expires_in_seconds=60)
    ok, payload = wasm_runner.verify_run_token(token)
    assert ok is True
    assert payload["project_id"] == "proj-1"
    assert payload["patch_id"] == "patch-1"

    # Tampered token fails
    ok_bad, _ = wasm_runner.verify_run_token(token + "bad")
    assert ok_bad is False


def test_provider_ledger_and_budget_enforcement():
    call_id = record_provider_call(
        owner_id="test-owner",
        provider="demo",
        stage="patch",
        model="muse-spark-1.3",
        prompt="prompt text",
        response_text="diff text",
        latency_ms=120,
        tokens=50,
    )
    assert call_id is not None
    # Enforce atomic budget
    enforce_atomic_budget(owner_id="test-owner", ip_address="127.0.0.1", estimated_tokens=10)
