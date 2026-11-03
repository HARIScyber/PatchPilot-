"""Fail-closed launch gates for enabling public AI actions."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from ..core.config import Settings


def evaluate_launch_gates(settings: Settings) -> list[dict[str, Any]]:
    sample_path = Path(__file__).resolve().parents[1] / "sample_data" / "calculator_bug"
    sample_present = sample_path.is_dir() and any(path.is_file() for path in sample_path.rglob("*"))
    # These remain explicitly false until their implementation and evidence ship.
    has_owner_isolation = False
    has_provider_ledger = False
    has_atomic_budget = False
    has_verified_runner = False
    has_strict_verification = True
    has_migrations = False

    return [
        {"id": "G1", "name": "Deployment", "status": "fail",
         "evidence_source": "External deployment proof is not available to this process."},
        {"id": "G2", "name": "Bundled sample", "status": "fail",
         "evidence_source": "Sample source is packaged." if sample_present else "Bundled sample source is missing.",
         "detail": "Deployed Docker load-sample smoke evidence is still required."},
        {"id": "G3", "name": "Anonymous identity and owner isolation",
         "status": "pass" if has_owner_isolation else "fail",
         "evidence_source": "Owner-scoped data model and route tests." if has_owner_isolation else "Owner-scoped identity is not implemented."},
        {"id": "G4", "name": "Durable storage and migrations",
         "status": "pass" if has_migrations else "fail",
         "evidence_source": "Hosted database and current migration state are not verified."},
        {"id": "G5", "name": "Live Meta and provenance",
         "status": "pass" if has_provider_ledger else "fail",
         "evidence_source": "No persisted provider-call ledger or captured live call."},
        {"id": "G6", "name": "Budget controls",
         "status": "pass" if has_atomic_budget else "fail",
         "evidence_source": "Atomic token/call budget and owner billing controls are not verified."},
        {"id": "G7", "name": "Safe browser execution",
         "status": "pass" if has_verified_runner else "fail",
         "evidence_source": "No browser runner is implemented; server execution is disabled."},
        {"id": "G8", "name": "Reproducing-test verification",
         "status": "pass" if has_strict_verification else "fail",
         "evidence_source": "Strict reproducer identity and three-run flake checks are not implemented."},
    ]


def public_ai_is_ready(settings: Settings) -> bool:
    return settings.PUBLIC_AI_ENABLED and all(
        gate["status"] == "pass" for gate in evaluate_launch_gates(settings)
    )
