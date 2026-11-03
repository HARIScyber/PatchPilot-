"""Anonymous owner cookie and ORM query scoping regressions."""
from fastapi.testclient import TestClient

from app.main import app
from app.database import SessionLocal
from app.models.patch import Patch
from app.models.project import Project
from app.models.verification_run import VerificationRun
from uuid import uuid4


def test_signed_session_cookie_is_stable_and_tampering_rotates_owner():
    with TestClient(app) as client:
        first = client.get("/api/projects/")
        signed = client.cookies.get("patchpilot_session")
        assert first.status_code == 200
        assert signed and len(signed.split(".")) == 3
        owner_id = signed.split(".")[0]
        client.get("/api/projects/")
        assert client.cookies.get("patchpilot_session").split(".")[0] == owner_id

        client.cookies.set("patchpilot_session", "tampered.owner", domain="testserver.local", path="/")
        client.get("/api/projects/")
        assert client.cookies.get("patchpilot_session") != "tampered.owner"


def test_project_records_are_hidden_from_another_anonymous_owner():
    with TestClient(app) as owner_a, TestClient(app) as owner_b:
        created = owner_a.post("/api/projects/", json={"name": "owner-a"})
        assert created.status_code == 200
        project_id = created.json()["id"]

        other = owner_b.get(f"/api/projects/{project_id}")
        assert other.status_code == 404
        assert owner_b.delete(f"/api/projects/{project_id}").status_code == 404
        assert all(item["id"] != project_id for item in owner_b.get("/api/projects/").json())


def test_orm_queries_and_new_records_are_owner_scoped():
    first = SessionLocal(info={"owner_id": "owner-a"})
    second = SessionLocal(info={"owner_id": "owner-b"})
    try:
        record = Project(id="owner-scope-unit", owner_id="owner-a", name="private project")
        first.add(record)
        first.commit()
        assert first.query(Project).filter(Project.id == record.id).one_or_none() is not None
        assert second.query(Project).filter(Project.id == record.id).one_or_none() is None
        automatic = Project(id="owner-assigned-unit", name="new project")
        second.add(automatic)
        second.flush()
        assert automatic.owner_id == "owner-b"
        second.rollback()
        first.delete(record)
        first.commit()
    finally:
        first.close()
        second.close()


def test_cross_owner_patch_run_report_timeline_and_mutations_return_not_found():
    project_id, patch_id, run_id = (str(uuid4()) for _ in range(3))
    owner_session = SessionLocal(info={"owner_id": "owner-a"})
    try:
        project = Project(id=project_id, name="private", owner_id="owner-a", is_sample=False)
        patch = Patch(id=patch_id, project_id=project_id, owner_id="owner-a", target_file="core/a.py",
                      diff_content="", validation_status="pending")
        run = VerificationRun(id=run_id, project_id=project_id, patch_id=patch_id, owner_id="owner-a",
                              status="completed", verification_status="NOT_VERIFIED")
        owner_session.add(project)
        owner_session.flush()
        owner_session.add(patch)
        owner_session.flush()
        owner_session.add(run)
        owner_session.commit()
    finally:
        owner_session.close()

    with TestClient(app) as another_owner:
        for path in (f"/api/patches/{patch_id}", f"/api/verification-runs/{run_id}",
                     f"/api/projects/{project_id}/patches", f"/api/patches/{patch_id}/verification-history",
                     f"/api/projects/{project_id}/report", f"/api/projects/{project_id}/timeline"):
            assert another_owner.get(path).status_code == 404, path
        for action in ("validate", "approve", "reject", "apply", "verify", "repair-loop", "generate-tests"):
            assert another_owner.post(f"/api/patches/{patch_id}/{action}").status_code == 404, action


def test_project_share_flow_opt_in_expiry_and_revocation():
    with TestClient(app) as owner_client, TestClient(app) as visitor_client:
        created = owner_client.post("/api/projects/", json={"name": "Shareable Project"})
        assert created.status_code == 200
        project_id = created.json()["id"]

        # Initially, visitor cannot access the project
        assert visitor_client.get(f"/api/projects/{project_id}").status_code == 404

        # Owner generates an opt-in share token
        share_res = owner_client.post(f"/api/projects/{project_id}/share", json={"expires_in_hours": 12})
        assert share_res.status_code == 200
        share_data = share_res.json()
        share_token = share_data["share_token"]
        share_id = share_data["share_id"]

        # Visitor accesses via the share token
        public_res = visitor_client.get(f"/api/projects/shared/{share_token}")
        assert public_res.status_code == 200
        assert public_res.json()["project"]["id"] == project_id
        assert public_res.json()["project"]["name"] == "Shareable Project"
        # No owner_id leaked in the public shared response
        assert "owner_id" not in public_res.json()["project"]

        # Owner revokes the share grant
        revoke_res = owner_client.delete(f"/api/projects/{project_id}/shares/{share_id}")
        assert revoke_res.status_code == 200

        # Now visitor gets 404
        revoked_res = visitor_client.get(f"/api/projects/shared/{share_token}")
        assert revoked_res.status_code == 404
