"""Automated test suite for Phase 6: Evidence reporting, audit trails, and secret redaction."""
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.database import init_db
from app.services.reporting import EvidenceReporter


@pytest.fixture(autouse=True)
def setup_database():
    init_db()


@pytest.fixture
def client():
    return TestClient(app)


def test_evidence_report_lifecycle(client):
    """Verify evidence report generation, Markdown export, and audit timeline."""
    # 1. Load sample
    sample_resp = client.post("/api/projects/load-sample")
    assert sample_resp.status_code == 200
    proj_id = sample_resp.json()["id"]

    # 2. Run analysis
    client.post(f"/api/projects/{proj_id}/analyze")

    # 3. Generate plan
    plan_resp = client.post(f"/api/projects/{proj_id}/repair-plan", json={})
    plan_id = plan_resp.json()["id"]

    # 4. Generate patch
    patch_resp = client.post(f"/api/projects/{proj_id}/patches/generate", json={"plan_id": plan_id})
    patch_id = patch_resp.json()["id"]

    # 5. Verify patch
    client.post(f"/api/patches/{patch_id}/verify", json={})

    # 6. Fetch JSON Report
    report_resp = client.get(f"/api/projects/{proj_id}/report")
    assert report_resp.status_code == 200
    report = report_resp.json()
    assert report["project"]["id"] == proj_id
    assert "verification_evidence" in report
    assert "timeline" in report

    # 7. Check Secret Redaction in Report
    report_text = report_resp.text
    assert "META_API_KEY" not in report_text
    assert "LLM_" not in report_text

    # 8. Fetch Markdown Report
    md_resp = client.get(f"/api/projects/{proj_id}/report?format=markdown")
    assert md_resp.status_code == 200
    assert "# PatchPilot Verification Report" in md_resp.text

    # 9. Fetch Audit Timeline
    timeline_resp = client.get(f"/api/projects/{proj_id}/timeline")
    assert timeline_resp.status_code == 200
    events = timeline_resp.json()
    assert len(events) >= 3
