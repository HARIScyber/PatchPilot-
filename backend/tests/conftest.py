"""Isolated test configuration; do not read developer .env or write repository DBs."""
import os
import shutil
import tempfile
from pathlib import Path


_old_environment = {key: os.environ.get(key) for key in (
    "APP_MODE", "APP_ENV", "DEMO_MODE", "MODEL_API_KEY", "DATABASE_URL",
    "EXECUTION_BACKEND", "SESSION_SIGNING_SECRET", "LLM_PROVIDER", "GEMINI_API_KEY")}
_test_root = Path(tempfile.mkdtemp(prefix="patchpilot-tests-"))
os.environ.update({
    "APP_MODE": "local",
    "DEMO_MODE": "true",
    "MODEL_API_KEY": "",
    "DATABASE_URL": f"sqlite:///{_test_root / 'patchpilot-test.db'}",
    "EXECUTION_BACKEND": "none",
    "APP_ENV": "test",
    "SESSION_SIGNING_SECRET": "test-only-session-signing-secret-32-bytes-minimum",
    "LLM_PROVIDER": "meta",
    "GEMINI_API_KEY": "",
})

# Run alembic migrations once on the temporary test database to match release startup
from app.database import run_alembic_upgrade_head  # noqa: E402
run_alembic_upgrade_head()


def pytest_unconfigure(config):
    try:
        from app.database import engine
        engine.dispose()
    except Exception:
        pass
    shutil.rmtree(_test_root, ignore_errors=True)
    for key, value in _old_environment.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value
