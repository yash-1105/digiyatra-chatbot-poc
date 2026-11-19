"""Privacy-safe provider usage accounting; existing analytics and accounts are unchanged."""

import sqlalchemy as sa
from alembic import op

revision = "0002_ai_usage"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "ai_usage",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("occurred_at", sa.DateTime(), nullable=False),
        sa.Column("provider", sa.String(12), nullable=False),
        sa.Column("model", sa.String(40), nullable=False),
        sa.Column("status", sa.String(12), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=False),
        sa.Column("output_tokens", sa.Integer(), nullable=False),
        sa.Column("cache_read_tokens", sa.Integer(), nullable=False),
        sa.Column("cache_write_tokens", sa.Integer(), nullable=False),
        sa.Column("tokens_estimated", sa.Boolean(), nullable=False),
        sa.Column("estimated_usd", sa.Float(), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
    )
    op.create_index("ix_ai_usage_occurred_at", "ai_usage", ["occurred_at"])


def downgrade():
    op.drop_index("ix_ai_usage_occurred_at", table_name="ai_usage")
    op.drop_table("ai_usage")
