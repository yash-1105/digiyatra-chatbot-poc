"""Add versioned supplemental evidence and aggregate gap candidates."""

import sqlalchemy as sa
from alembic import op

revision = "0004_supplemental_knowledge"
down_revision = "0003_faq_telemetry"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "knowledge_revision",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("topic", sa.String(40), nullable=False),
        sa.Column("source_id", sa.String(64), nullable=False),
        sa.Column("digest", sa.String(64), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("risk", sa.String(16), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("retrieved_at", sa.DateTime(), nullable=False),
        sa.Column("reviewed_at", sa.DateTime()),
        sa.Column("reviewer", sa.String(80)),
        sa.UniqueConstraint("source_id", "digest"),
    )
    op.create_index("ix_knowledge_revision_topic", "knowledge_revision", ["topic"])
    current = sa.text("status = 'published'")
    op.create_index("uq_knowledge_published_topic", "knowledge_revision", ["topic"], unique=True,
                    sqlite_where=current, postgresql_where=current)
    op.create_table(
        "knowledge_gap",
        sa.Column("topic", sa.String(40), primary_key=True),
        sa.Column("observations", sa.Integer(), nullable=False),
        sa.Column("last_seen", sa.DateTime(), nullable=False),
    )


def downgrade():
    op.drop_table("knowledge_gap")
    op.drop_table("knowledge_revision")
