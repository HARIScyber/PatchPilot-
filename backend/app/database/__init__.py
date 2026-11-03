"""Database engine, session, and Base setup for SQLAlchemy."""
from __future__ import annotations

import re
from pathlib import Path
from fastapi import Request, Response
from sqlalchemy import Column, String, create_engine, text, event
from sqlalchemy.engine import make_url
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker, with_loader_criteria

from ..core.config import get_settings


def normalize_database_url(url: str) -> str:
    """Normalize database connection URLs to SQLAlchemy's expected driver schemes.

    Converts 'postgres://' or 'postgresql://' to 'postgresql+psycopg://' for the
    installed psycopg 3 driver while preserving credentials, host, port, path, and options.
    Leaves other URLs (SQLite, file, memory) intact.
    """
    if not url:
        return url
    if url.startswith("postgres://"):
        return "postgresql+psycopg://" + url[len("postgres://"):]
    if url.startswith("postgresql://"):
        return "postgresql+psycopg://" + url[len("postgresql://"):]
    return url


def render_safe_url(url: str) -> str:
    """Return a masked URL string with passwords and credentials safely redacted.

    Guarantees that sensitive passwords never appear in logs, diagnostics, or error strings.
    """
    if not url:
        return ""
    try:
        return make_url(url).render_as_string(hide_password=True)
    except Exception:
        return re.sub(r"://([^:@]+):([^@]+)@", r"://\1:***@", url)


class OwnerScoped:
    """Mixin for rows protected by the current anonymous session owner."""
    owner_id = Column(String(64), nullable=False, index=True)


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""
    pass


def _build_engine():
    settings = get_settings()
    database_url = normalize_database_url(settings.DATABASE_URL)
    connect_args = {}
    if database_url.startswith("sqlite"):
        connect_args["check_same_thread"] = False
        db_path_str = database_url.replace("sqlite:///", "")
        if db_path_str and not db_path_str.startswith(":memory:"):
            db_file = Path(db_path_str)
            db_file.parent.mkdir(parents=True, exist_ok=True)
    return create_engine(database_url, connect_args=connect_args, pool_pre_ping=True)


engine = _build_engine()
if engine.dialect.name == "sqlite":
    @event.listens_for(engine, "connect")
    def _enable_sqlite_foreign_keys(dbapi_connection, _connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@event.listens_for(Session, "do_orm_execute")
def _scope_owned_orm_operations(execute_state):
    owner_id = execute_state.session.info.get("owner_id")
    if not owner_id:
        return
    if execute_state.is_select:
        execute_state.statement = execute_state.statement.options(
            with_loader_criteria(OwnerScoped, lambda row: row.owner_id == owner_id, include_aliases=True)
        )
    elif execute_state.is_update or execute_state.is_delete:
        mapper = execute_state.bind_mapper
        if mapper is not None and issubclass(mapper.class_, OwnerScoped):
            execute_state.statement = execute_state.statement.where(mapper.class_.owner_id == owner_id)


@event.listens_for(Session, "before_flush")
def _assign_and_protect_owner(session, _flush_context, _instances):
    owner_id = session.info.get("owner_id")
    if not owner_id:
        return
    for record in session.new:
        if isinstance(record, OwnerScoped):
            if record.owner_id not in (None, owner_id):
                raise ValueError("Cannot create a record for another owner.")
            record.owner_id = owner_id
    for record in session.dirty:
        if isinstance(record, OwnerScoped) and record.owner_id != owner_id:
            raise ValueError("Cannot change record ownership.")


def get_db(request: Request, response: Response):
    """Yield an owner-scoped database session and issue a signed anonymous session cookie."""
    from ..security.owner_session import get_or_create_owner_id
    owner_id, signed_cookie = get_or_create_owner_id(request.cookies.get("patchpilot_session"))
    settings = get_settings()
    response.set_cookie("patchpilot_session", signed_cookie, max_age=7 * 24 * 60 * 60,
        httponly=True, secure=(settings.APP_ENV.lower() == "production" or request.url.scheme == "https"),
        samesite="lax", path="/")
    db = SessionLocal(info={"owner_id": owner_id})
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Development/test helper that creates tables and keeps legacy SQLite fixtures usable."""
    from .. import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    # Lightweight development migration for databases created before sample tagging.
    # create_all() does not alter existing SQLite tables.
    if engine.dialect.name == "sqlite":
        # Remove the historical fabricated patch model default while preserving rows.
        with engine.connect() as connection:
            patch_columns = connection.execute(text("PRAGMA table_info(patches)")).fetchall()
        model_column = next((column for column in patch_columns if column[1] == "model_id"), None)
        if model_column and model_column[3]:
            with engine.connect() as connection:
                connection.execute(text("PRAGMA foreign_keys=OFF"))
                connection.commit()
            with engine.begin() as connection:
                connection.execute(text("""CREATE TABLE patches_new (
                    id VARCHAR PRIMARY KEY, project_id VARCHAR NOT NULL, plan_id VARCHAR,
                    finding_id VARCHAR, target_file VARCHAR NOT NULL, original_file_hash VARCHAR,
                    diff_content TEXT NOT NULL, model_id VARCHAR, validation_status VARCHAR NOT NULL,
                    validation_error TEXT, is_approved BOOLEAN NOT NULL DEFAULT 0,
                    is_applied BOOLEAN NOT NULL DEFAULT 0, created_at DATETIME NOT NULL,
                    FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE,
                    FOREIGN KEY(plan_id) REFERENCES repair_plans(id) ON DELETE SET NULL,
                    FOREIGN KEY(finding_id) REFERENCES findings(id) ON DELETE SET NULL)"""))
                connection.execute(text("""INSERT INTO patches_new
                    (id, project_id, plan_id, finding_id, target_file, original_file_hash,
                     diff_content, model_id, validation_status, validation_error, is_approved,
                     is_applied, created_at)
                    SELECT id, project_id, plan_id, finding_id, target_file, original_file_hash,
                           diff_content, NULL, validation_status, validation_error, is_approved,
                           is_applied, created_at FROM patches"""))
                connection.execute(text("DROP TABLE patches"))
                connection.execute(text("ALTER TABLE patches_new RENAME TO patches"))
                connection.execute(text("CREATE INDEX IF NOT EXISTS ix_patches_id ON patches(id)"))
                connection.execute(text("CREATE INDEX IF NOT EXISTS ix_patches_project_id ON patches(project_id)"))
            with engine.connect() as connection:
                connection.execute(text("PRAGMA foreign_keys=ON"))
                connection.commit()
        with engine.begin() as connection:
            connection.execute(text("""CREATE TABLE IF NOT EXISTS public_meta_daily_usage (
                usage_day TEXT PRIMARY KEY, calls INTEGER NOT NULL DEFAULT 0)"""))
            columns = {row[1] for row in connection.execute(text("PRAGMA table_info(projects)"))}
            if columns and "is_sample" not in columns:
                connection.execute(text("ALTER TABLE projects ADD COLUMN is_sample BOOLEAN NOT NULL DEFAULT 0"))


def run_alembic_upgrade_head() -> None:
    """Run Alembic migrations programmatically to head revision."""
    from alembic import command
    from alembic.config import Config

    config_path = Path(__file__).resolve().parents[2] / "alembic.ini"
    alembic_cfg = Config(str(config_path))
    alembic_cfg.set_main_option("script_location", str(config_path.parent / "migrations"))
    command.upgrade(alembic_cfg, "head")


def ensure_schema_current() -> None:
    """Fail startup if production database migrations have not reached the code's head."""
    from alembic.config import Config
    from alembic.runtime.migration import MigrationContext
    from alembic.script import ScriptDirectory

    config_path = Path(__file__).resolve().parents[2] / "alembic.ini"
    config = Config(str(config_path))
    config.set_main_option("script_location", str(config_path.parent / "migrations"))
    scripts = ScriptDirectory.from_config(config)
    with engine.connect() as connection:
        current = set(MigrationContext.configure(connection).get_current_heads())
    expected = set(scripts.get_heads())
    if current != expected:
        raise RuntimeError(
            f"Database schema is behind or uninitialized (current={sorted(current)}, expected={sorted(expected)}). "
            "Run `alembic upgrade head` as the release migration step before starting the API."
        )


def check_db_health() -> dict:
    """Return a simple health-check dict for the database with secrets masked."""
    try:
        with Session(engine) as session:
            session.execute(text("SELECT 1"))
        return {"status": "ok", "engine": render_safe_url(str(engine.url))}
    except Exception as exc:
        return {"status": "error", "detail": render_safe_url(str(exc))}
