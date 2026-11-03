"""Add owner columns to pre-existing tables and quarantine pre-session rows."""
import sqlalchemy as sa
from alembic import op

revision = "0002_owner_scoping"
down_revision = "0001_initial_schema"
branch_labels = None
depends_on = None

OWNED_TABLES = ("projects", "repairs", "findings", "repair_plans", "patches",
                "generated_tests", "verification_runs", "audit_events")


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = set(inspector.get_table_names())
    for table in OWNED_TABLES:
        if table not in existing_tables:
            continue
        columns = {column["name"] for column in inspector.get_columns(table)}
        if "owner_id" not in columns:
            op.add_column(table, sa.Column("owner_id", sa.String(length=64), nullable=False,
                                            server_default="legacy-unclaimed"))
        indexes = {index["name"] for index in sa.inspect(bind).get_indexes(table)}
        index_name = f"ix_{table}_owner_id"
        if index_name not in indexes:
            op.create_index(index_name, table, ["owner_id"], unique=False)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    for table in reversed(OWNED_TABLES):
        if table not in inspector.get_table_names():
            continue
        indexes = {index["name"] for index in sa.inspect(bind).get_indexes(table)}
        index_name = f"ix_{table}_owner_id"
        if index_name in indexes:
            op.drop_index(index_name, table_name=table)
        if "owner_id" in {column["name"] for column in sa.inspect(bind).get_columns(table)}:
            with op.batch_alter_table(table) as batch:
                batch.drop_column("owner_id")
