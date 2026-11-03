"""Create provider_calls ledger and provider_budget_counters tables.

Revision ID: 0003_provider_calls
Revises: 0002_owner_scoping
Create Date: 2026-11-03
"""
from alembic import op
import sqlalchemy as sa

revision = "0003_provider_calls"
down_revision = "0002_owner_scoping"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if "provider_budget_counters" not in tables:
        op.create_table(
            "provider_budget_counters",
            sa.Column("budget_key", sa.String(length=128), primary_key=True),
            sa.Column("calls", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("tokens", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index("ix_provider_budget_counters_budget_key", "provider_budget_counters", ["budget_key"])

    if "provider_calls" not in tables:
        op.create_table(
            "provider_calls",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("owner_id", sa.String(length=64), nullable=False),
            sa.Column("provider", sa.String(), nullable=False),
            sa.Column("stage", sa.String(), nullable=False),
            sa.Column("model", sa.String(), nullable=True),
            sa.Column("prompt_hash", sa.String(length=64), nullable=True),
            sa.Column("response_hash", sa.String(length=64), nullable=True),
            sa.Column("latency_ms", sa.Integer(), nullable=True),
            sa.Column("status", sa.String(), nullable=False, server_default="success"),
            sa.Column("tokens", sa.Integer(), nullable=True),
            sa.Column("plan_id", sa.String(), sa.ForeignKey("repair_plans.id", ondelete="SET NULL"), nullable=True),
            sa.Column("patch_id", sa.String(), sa.ForeignKey("patches.id", ondelete="SET NULL"), nullable=True),
            sa.Column("generated_test_id", sa.String(), sa.ForeignKey("generated_tests.id", ondelete="SET NULL"), nullable=True),
            sa.Column("attempt", sa.Integer(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index("ix_provider_calls_id", "provider_calls", ["id"])
        op.create_index("ix_provider_calls_owner_id", "provider_calls", ["owner_id"])
        op.create_index("ix_provider_calls_provider", "provider_calls", ["provider"])
        op.create_index("ix_provider_calls_stage", "provider_calls", ["stage"])
        op.create_index("ix_provider_calls_plan_id", "provider_calls", ["plan_id"])
        op.create_index("ix_provider_calls_patch_id", "provider_calls", ["patch_id"])
        op.create_index("ix_provider_calls_generated_test_id", "provider_calls", ["generated_test_id"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if "provider_calls" in tables:
        op.drop_table("provider_calls")
    if "provider_budget_counters" in tables:
        op.drop_table("provider_budget_counters")
