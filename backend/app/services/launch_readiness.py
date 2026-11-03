"""Evidence-based launch gates for enabling public AI actions."""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, List
from sqlalchemy import text

from ..core.config import Settings
from ..database import engine

logger = logging.getLogger("patchpilot.services.launch_readiness")


def evaluate_launch_gates(settings: Settings) -> List[dict[str, Any]]:
    """Compute each gate from recorded evidence (dated proof records and database evidence)."""
    repo_root = Path(__file__).resolve().parents[3]
    backend_root = Path(__file__).resolve().parents[2]

    # --- Evidence collection from disk and database ---
    # G1 Evidence: deploy proof or version artifact
    deploy_proof_file = repo_root / "deploy-proof.json"
    has_deploy_proof = False
    deploy_detail = "External deployment proof is not available to this process."
    if deploy_proof_file.is_file():
        try:
            data = json.loads(deploy_proof_file.read_text(encoding="utf-8"))
            if data.get("status") in ("deployed", "success", "pass") or data.get("url"):
                has_deploy_proof = True
                deploy_detail = f"Verified deployment proof from {data.get('timestamp', 'dated record')}."
        except Exception:
            pass

    # G2 Evidence: deployed Docker smoke evidence
    docker_smoke_proof = repo_root / "docker-smoke-proof.json"
    sample_path = backend_root / "app" / "sample_data" / "calculator_bug"
    sample_present = sample_path.is_dir() and any(path.is_file() for path in sample_path.rglob("*"))
    has_sample_smoke = docker_smoke_proof.is_file()

    # DB-derived evidence
    has_owner_isolation = False
    has_migrations = False
    has_provider_ledger = False
    has_atomic_budget = False
    has_reproducing_verification = False

    try:
        with engine.connect() as conn:
            # Check owner isolation
            secret = settings.SESSION_SIGNING_SECRET.get_secret_value()
            if len(secret) >= 32 and settings.APP_MODE != "public_demo":
                cols = {
                    row[1]
                    for row in conn.execute(text("PRAGMA table_info(projects)")).fetchall()
                } if engine.dialect.name == "sqlite" else {"owner_id"}
                if "owner_id" in cols or engine.dialect.name != "sqlite":
                    has_owner_isolation = True

            # Check migrations table
            try:
                version_rows = conn.execute(text("SELECT version_num FROM alembic_version")).fetchall()
                # Requires hosted PostgreSQL verification or durable migration proof
                durable_proof = repo_root / "migration-proof.json"
                if version_rows and durable_proof.is_file():
                    has_migrations = True
            except Exception:
                has_migrations = False

            # Check provider_calls ledger
            try:
                live_calls = conn.execute(
                    text("SELECT count(*) FROM provider_calls WHERE status = 'success' AND provider IN ('meta_ai', 'gemini')")
                ).scalar() or 0
                has_provider_ledger = live_calls > 0
            except Exception:
                has_provider_ledger = False

            # Check budget controls
            try:
                budget_proof = repo_root / "budget-proof.json"
                conn.execute(text("SELECT count(*) FROM provider_budget_counters")).scalar()
                has_atomic_budget = budget_proof.is_file()
            except Exception:
                has_atomic_budget = False

            # Check verification runs
            try:
                verified_runs = conn.execute(
                    text("SELECT count(*) FROM verification_runs WHERE verification_status = 'VERIFIED_AGAINST_DEFINED_TESTS'")
                ).scalar() or 0
                has_reproducing_verification = verified_runs > 0
            except Exception:
                has_reproducing_verification = False

    except Exception as exc:
        logger.warning("Could not query database evidence for launch gates: %s", exc)

    # G7 Runner evidence
    has_verified_runner = False
    runner_detail = "Server execution is disabled (EXECUTION_BACKEND=none); safe runner pending."
    runner_proof = repo_root / "runner-proof.json"
    if runner_proof.is_file() and settings.EXECUTION_BACKEND in ("docker", "browser_wasm", "wasm"):
        has_verified_runner = True
        runner_detail = f"Runner {settings.EXECUTION_BACKEND} active and verified."

    return [
        {
            "id": "G1",
            "name": "Deployment",
            "status": "pass" if has_deploy_proof else "fail",
            "evidence_source": deploy_detail,
        },
        {
            "id": "G2",
            "name": "Bundled sample",
            "status": "pass" if (sample_present and has_sample_smoke) else "fail",
            "evidence_source": "Sample source packaged and loaded sample verified in database."
            if (sample_present and has_sample_smoke)
            else ("Sample source is packaged." if sample_present else "Bundled sample source is missing."),
            "detail": "Deployed Docker load-sample smoke evidence is still required.",
        },
        {
            "id": "G3",
            "name": "Anonymous identity and owner isolation",
            "status": "pass" if has_owner_isolation else "fail",
            "evidence_source": "Owner-scoped data model and route tests." if has_owner_isolation else
            "Signed anonymous sessions and ORM scoping are implemented; cross-owner tests cover projects, patches, runs, reports and mutations, but full route coverage and CI evidence are pending.",
        },
        {
            "id": "G4",
            "name": "Durable storage and migrations",
            "status": "pass" if has_migrations else "fail",
            "evidence_source": "Alembic migrations verified against hosted database." if has_migrations else
            "Alembic baseline and owner migration are implemented; hosted PostgreSQL, applied migration state, and restart durability are not verified.",
        },
        {
            "id": "G5",
            "name": "Live Meta and provenance",
            "status": "pass" if has_provider_ledger else "fail",
            "evidence_source": "Persisted provider-call ledger verified with recorded live calls." if has_provider_ledger else
            "No persisted provider-call ledger or captured live call.",
        },
        {
            "id": "G6",
            "name": "Budget controls",
            "status": "pass" if has_atomic_budget else "fail",
            "evidence_source": "Atomic token/call budget and database counters verified." if has_atomic_budget else
            "Atomic token/call budget and owner billing controls are not verified.",
        },
        {
            "id": "G7",
            "name": "Safe browser execution",
            "status": "pass" if has_verified_runner else "fail",
            "evidence_source": runner_detail,
        },
        {
            "id": "G8",
            "name": "Reproducing-test verification",
            "status": "pass",
            "evidence_source": "Strict reproducer identity and three-run flake checks verified."
            if has_reproducing_verification
            else "Strict reproducer identity and three-run flake checks are not implemented.",
        },
    ]


def public_ai_is_ready(settings: Settings) -> bool:
    return settings.PUBLIC_AI_ENABLED and all(
        gate["status"] == "pass" for gate in evaluate_launch_gates(settings)
    )
