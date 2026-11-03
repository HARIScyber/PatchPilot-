"""Create current application tables as a baseline for new or legacy databases."""
from alembic import op

from app import models  # noqa: F401
from app.database import Base

revision = "0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # create_all is idempotent and allows this baseline to adopt pre-Alembic local DBs.
    Base.metadata.create_all(bind=op.get_bind())
    op.get_bind().exec_driver_sql(
        "CREATE TABLE IF NOT EXISTS public_meta_daily_usage ("
        "usage_day VARCHAR(10) PRIMARY KEY, calls INTEGER NOT NULL DEFAULT 0)"
    )


def downgrade() -> None:
    op.get_bind().exec_driver_sql("DROP TABLE IF EXISTS public_meta_daily_usage")
    Base.metadata.drop_all(bind=op.get_bind())
