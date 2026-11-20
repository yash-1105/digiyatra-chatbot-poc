"""Add reviewed public FAQ storage and privacy-safe usage dimensions."""

import sqlalchemy as sa
from alembic import op

revision = "0003_faq_telemetry"
down_revision = "0002_ai_usage"
branch_labels = None
depends_on = None

USAGE_COLUMNS = (
    ("locale", sa.String(2)), ("reasoning_tokens", sa.Integer()),
    ("cache_write_1h_tokens", sa.Integer()), ("retrieval_tokens_estimated", sa.Integer()),
    ("priced_amount", sa.Float()), ("pricing_version", sa.String(24)),
    ("error_kind", sa.String(24)), ("optimized_context", sa.Boolean()),
)


def upgrade():
    op.create_table(
        "approved_faq",
        sa.Column("key", sa.String(120), primary_key=True),
        sa.Column("locale", sa.String(2), primary_key=True),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("signature", sa.String(64), nullable=False),
        sa.Column("revoked", sa.Boolean(), nullable=False),
    )
    op.create_table(
        "faq_usage",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("occurred_at", sa.DateTime(), nullable=False),
        sa.Column("provider", sa.String(12), nullable=False),
        sa.Column("locale", sa.String(2), nullable=False),
        sa.Column("outcome", sa.String(24), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
    )
    op.create_index("ix_faq_usage_occurred_at", "faq_usage", ["occurred_at"])
    for name, kind in USAGE_COLUMNS:
        op.add_column("ai_usage", sa.Column(name, kind))


def downgrade():
    for name, _ in reversed(USAGE_COLUMNS):
        op.drop_column("ai_usage", name)
    op.drop_table("faq_usage")
    op.drop_table("approved_faq")
