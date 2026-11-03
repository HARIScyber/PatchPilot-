"""Unit tests for database URL normalization, secret redaction, and schema utilities."""
from app.database import normalize_database_url, render_safe_url, check_db_health


def test_normalize_database_url_converts_postgres_schemes():
    raw_postgres = "postgres://patchpilot_user:my_secret_pass@db.example.com:5432/patchpilot_db"
    normalized = normalize_database_url(raw_postgres)
    assert normalized == "postgresql+psycopg://patchpilot_user:my_secret_pass@db.example.com:5432/patchpilot_db"

    raw_postgresql = "postgresql://patchpilot_user:my_secret_pass@db.example.com:5432/patchpilot_db"
    assert normalize_database_url(raw_postgresql) == "postgresql+psycopg://patchpilot_user:my_secret_pass@db.example.com:5432/patchpilot_db"


def test_normalize_database_url_user_pw_host_db():
    raw = "postgres://user:pw@host/db"
    normalized = normalize_database_url(raw)
    assert normalized == "postgresql+psycopg://user:pw@host/db"

    raw_pg = "postgresql://user:pw@host/db"
    assert normalize_database_url(raw_pg) == "postgresql+psycopg://user:pw@host/db"

    # Verify password never appears in safe representations, logs, or error strings
    safe = render_safe_url(normalized)
    assert "pw" not in safe
    assert "user" in safe
    assert "***" in safe

    # Test error string sanitization
    err_text = "Connection failure at postgresql+psycopg://user:pw@host/db: timeout"
    safe_err = render_safe_url(err_text)
    assert "pw" not in safe_err
    assert "***" in safe_err


def test_normalize_database_url_preserves_sqlite_and_psycopg_schemes():
    sqlite_url = "sqlite:///backend/database/patchpilot.db"
    assert normalize_database_url(sqlite_url) == sqlite_url

    psycopg_url = "postgresql+psycopg://u:p@localhost/db"
    assert normalize_database_url(psycopg_url) == psycopg_url


def test_render_safe_url_masks_passwords():
    raw = "postgresql+psycopg://app_user:super_secret_password_123@db.example.com:5432/prod_db"
    safe = render_safe_url(raw)
    assert "super_secret_password_123" not in safe
    assert "app_user" in safe
    assert "***" in safe


def test_check_db_health_masks_credentials():
    health = check_db_health()
    assert health.get("status") == "ok"
    if "engine" in health:
        assert "password" not in health["engine"].lower() or "***" in health["engine"]
