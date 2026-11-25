"""Official-source registry, versioned records, sync history, publications and job lease."""

import sqlalchemy as sa
from alembic import op

revision = "0005_official_source_sync"
down_revision = "0004_supplemental_knowledge"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "official_source",
        sa.Column("source_id", sa.String(96), primary_key=True),
        sa.Column("parent_id", sa.String(96)),
        sa.Column("canonical_url", sa.String(600), nullable=False, unique=True),
        sa.Column("organization", sa.String(80), nullable=False),
        sa.Column("source_type", sa.String(24), nullable=False),
        sa.Column("language", sa.String(8), nullable=False),
        sa.Column("trust", sa.String(32), nullable=False),
        sa.Column("topic", sa.String(48), nullable=False),
        sa.Column("risk", sa.String(8), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("refresh_days", sa.Integer(), nullable=False),
        sa.Column("last_attempt_at", sa.DateTime()),
        sa.Column("last_success_at", sa.DateTime()),
        sa.Column("next_due_at", sa.DateTime(), nullable=False),
        sa.Column("http_status", sa.Integer()),
        sa.Column("etag", sa.String(200)),
        sa.Column("last_modified", sa.String(64)),
        sa.Column("content_hash", sa.String(64)),
        sa.Column("content_version", sa.Integer(), nullable=False),
        sa.Column("verification_status", sa.String(24), nullable=False),
        sa.Column("consecutive_failures", sa.Integer(), nullable=False),
        sa.Column("failure_reason", sa.String(160)),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_official_source_parent_id", "official_source", ["parent_id"])
    op.create_index("ix_official_source_next_due_at", "official_source", ["next_due_at"])
    op.create_table(
        "official_record",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source_id", sa.String(96), nullable=False),
        sa.Column("record_key", sa.String(64), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("record_type", sa.String(16), nullable=False),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("category", sa.String(200)),
        sa.Column("question", sa.String(600)),
        sa.Column("body", sa.String(20000), nullable=False),
        sa.Column("url", sa.String(700), nullable=False),
        sa.Column("anchor", sa.String(120)),
        sa.Column("organization", sa.String(80), nullable=False),
        sa.Column("language", sa.String(8), nullable=False),
        sa.Column("authority", sa.String(32), nullable=False),
        sa.Column("topic", sa.String(48), nullable=False),
        sa.Column("risk", sa.String(8), nullable=False),
        sa.Column("published_on", sa.String(10)),
        sa.Column("updated_on", sa.String(10)),
        sa.Column("effective_from", sa.String(10)),
        sa.Column("expires_on", sa.String(10)),
        sa.Column("extracted_at", sa.DateTime(), nullable=False),
        sa.Column("review_reason", sa.String(300)),
        sa.Column("reviewer", sa.String(80)),
        sa.Column("reviewed_at", sa.DateTime()),
        sa.UniqueConstraint("source_id", "record_key", "content_hash"),
    )
    op.create_index("ix_official_record_source_id", "official_record", ["source_id"])
    op.create_index("ix_official_record_status", "official_record", ["status"])
    op.create_index("ix_official_record_key", "official_record", ["source_id", "record_key"])
    op.create_table(
        "sync_run",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("finished_at", sa.DateTime()),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("trigger", sa.String(24), nullable=False),
        sa.Column("stats", sa.JSON(), nullable=False),
    )
    op.create_index("ix_sync_run_started_at", "sync_run", ["started_at"])
    op.create_table(
        "knowledge_publication",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("status", sa.String(12), nullable=False),
        sa.Column("digest", sa.String(64), nullable=False),
        sa.Column("record_ids", sa.JSON(), nullable=False),
        sa.Column("record_count", sa.Integer(), nullable=False),
        sa.Column("run_id", sa.Integer()),
    )
    active = sa.text("status = 'active'")
    op.create_index("uq_knowledge_publication_active", "knowledge_publication", ["status"], unique=True,
                    sqlite_where=active, postgresql_where=active)
    op.create_table(
        "job_lease",
        sa.Column("name", sa.String(40), primary_key=True),
        sa.Column("holder", sa.String(64), nullable=False),
        sa.Column("acquired_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
    )


def downgrade():
    op.drop_table("job_lease")
    op.drop_table("knowledge_publication")
    op.drop_table("sync_run")
    op.drop_table("official_record")
    op.drop_table("official_source")
