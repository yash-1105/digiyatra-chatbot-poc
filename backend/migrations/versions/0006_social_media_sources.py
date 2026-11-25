"""Social media / YouTube / transcript provenance on the official-source registry and records."""

import sqlalchemy as sa
from alembic import op

revision = "0006_social_media_sources"
down_revision = "0005_official_source_sync"
branch_labels = None
depends_on = None

SOURCE = (("platform", sa.String(16)), ("account_id", sa.String(96)), ("ownership_evidence", sa.JSON()),
          ("cursor", sa.String(200)), ("quota_note", sa.String(160)))
RECORD = (("source_kind", sa.String(24)), ("platform", sa.String(16)), ("external_id", sa.String(96)),
          ("account_id", sa.String(96)), ("account_name", sa.String(120)), ("start_s", sa.Integer()),
          ("media", sa.JSON()))


def upgrade():
    with op.batch_alter_table("official_source") as b:
        for name, kind in SOURCE:
            b.add_column(sa.Column(name, kind))
    with op.batch_alter_table("official_record") as b:
        for name, kind in RECORD:
            b.add_column(sa.Column(name, kind))
    op.create_index("ix_official_record_external", "official_record", ["platform", "external_id"])


def downgrade():
    op.drop_index("ix_official_record_external", "official_record")
    with op.batch_alter_table("official_record") as b:
        for name, _ in reversed(RECORD):
            b.drop_column(name)
    with op.batch_alter_table("official_source") as b:
        for name, _ in reversed(SOURCE):
            b.drop_column(name)
