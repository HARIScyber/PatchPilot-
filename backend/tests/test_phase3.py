"""Automated test suite for Phase 3: Repository intake, security, AST analysis, and localization."""
import zipfile
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.database import init_db
from app.security.zip_validator import validate_and_extract_zip, ZipSecurityError
from app.services.static_analyzer import analyze_python_file
from app.services.localization import BugLocalizer


@pytest.fixture(autouse=True)
def setup_database():
    init_db()


@pytest.fixture
def client():
    return TestClient(app)


def test_malicious_zip_path_traversal(tmp_path):
    """Verify that ZIP files containing '../' paths are strictly rejected."""
    malicious_zip = tmp_path / "evil.zip"
    with zipfile.ZipFile(malicious_zip, "w") as zf:
        zf.writestr("../../etc/passwd", "root:x:0:0:")

    target_dir = tmp_path / "extracted"
    with pytest.raises(ZipSecurityError, match="path traversal attempt"):
        validate_and_extract_zip(malicious_zip, target_dir)


def test_safe_zip_extraction(tmp_path):
    """Verify that legitimate ZIP files unpack accurately into target directory."""
    valid_zip = tmp_path / "valid.zip"
    with zipfile.ZipFile(valid_zip, "w") as zf:
        zf.writestr("module/main.py", "print('hello')\n")
        zf.writestr("tests/test_main.py", "def test_ok(): pass\n")

    target_dir = tmp_path / "extracted"
    files = validate_and_extract_zip(valid_zip, target_dir)
    assert len(files) == 2
    assert (target_dir / "module" / "main.py").exists()


def test_bundled_sample_loader_returns_structured_error_when_missing(client, monkeypatch, tmp_path):
    from app.api import projects

    monkeypatch.setattr(projects, "SAMPLE_PROJECT_DIRECTORY", tmp_path / "missing-sample")
    response = client.post("/api/projects/load-sample")

    assert response.status_code == 503
    assert response.json()["detail"]["error_code"] == "SAMPLE_NOT_FOUND"


def test_ast_mutable_default_detection(tmp_path):
    """Verify that AST static analyzer identifies mutable default arguments."""
    code = "def append_item(val, container=[]):\n    container.append(val)\n    return container\n"
    fpath = tmp_path / "defect.py"
    fpath.write_text(code, encoding="utf-8")

    findings = analyze_python_file(fpath, "defect.py")
    types = [f["finding_type"] for f in findings]
    assert "mutable_default" in types
    mut_finding = next(f for f in findings if f["finding_type"] == "mutable_default")
    assert mut_finding["severity"] == "high"
    assert "container" in mut_finding["description"]


def test_ast_silenced_exception_detection(tmp_path):
    """Verify that AST analyzer flags bare or broad silenced exceptions."""
    code = "def risky():\n    try:\n        1 / 0\n    except Exception:\n        pass\n"
    fpath = tmp_path / "risky.py"
    fpath.write_text(code, encoding="utf-8")

    findings = analyze_python_file(fpath, "risky.py")
    types = [f["finding_type"] for f in findings]
    assert "suspicious_exception" in types


def test_bug_localization_stack_trace(tmp_path):
    """Verify bug localization extracts and weights locations from stack traces."""
    code_dir = tmp_path / "pkg"
    code_dir.mkdir()
    (code_dir / "calc.py").write_text("def add(): pass\n", encoding="utf-8")

    localizer = BugLocalizer(tmp_path)
    stack_trace = (
        'Traceback (most recent call last):\n'
        '  File "pkg/calc.py", line 42, in add\n'
        'ZeroDivisionError: division by zero'
    )
    candidates = localizer.rank_candidates(stack_trace=stack_trace)
    assert len(candidates) > 0
    top = candidates[0]
    assert "calc.py" in top["file_path"]
    assert top["line_number"] == 42


def test_project_api_lifecycle(client):
    """Verify project creation, sample loading, file inspection, and static analysis via API."""
    # 1. Load sample project
    resp = client.post("/api/projects/load-sample")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    project_id = data["id"]
    assert "Calculator" in data["name"]
    assert data["file_count"] >= 3

    # 2. Get file tree
    files_resp = client.get(f"/api/projects/{project_id}/files")
    assert files_resp.status_code == 200
    files = files_resp.json()
    file_paths = [f["path"] for f in files]
    assert any("calculator.py" in p for p in file_paths)
    assert any("test_calculator.py" in p for p in file_paths)

    # 3. Read file content
    content_resp = client.get(f"/api/projects/{project_id}/files/content?path=core/calculator.py")
    assert content_resp.status_code == 200
    assert "compute_cumulative_total" in content_resp.json()["content"]

    # 4. Trigger static analysis
    analyze_resp = client.post(f"/api/projects/{project_id}/analyze")
    assert analyze_resp.status_code == 200
    findings_data = analyze_resp.json()
    assert findings_data["status"] == "success"
    assert findings_data["findings_count"] > 0

    # 5. Get findings
    get_findings_resp = client.get(f"/api/projects/{project_id}/findings")
    assert get_findings_resp.status_code == 200
    findings = get_findings_resp.json()
    assert len(findings) > 0
