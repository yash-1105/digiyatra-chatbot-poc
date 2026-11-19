"""Initial schema: admin auth, anonymous conversations, interaction events, topics, feedback.

Revision ID: 0001_initial
Revises:
Create Date: 2026-11-19
"""

import sqlalchemy as sa
from alembic import op

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None

TOPICS = [
    ("aadhaar_registration", "Aadhaar registration", 10),
    ("digilocker_verification", "DigiLocker verification", 20),
    ("boarding_pass_upload", "Boarding pass upload", 30),
    ("airport_availability", "Airport availability", 40),
    ("airport_journey", "Airport journey & e-gates", 50),
    ("privacy_deletion", "Privacy & data deletion", 60),
    ("app_errors", "App errors & login", 70),
    ("international_travel", "International travel", 80),
    ("minors_family", "Children & family", 90),
    ("contact_support", "Contact & support", 100),
    ("general_information", "General information", 110),
    ("greeting", "Greeting / small talk", 900),
    ("other", "Other / unknown", 999),
]


def upgrade() -> None:
    op.create_table(
        "admin_users",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("email", sa.String(254), nullable=False, unique=True),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("password_changed_at", sa.DateTime, nullable=False),
        sa.Column("last_login_at", sa.DateTime),
    )
    op.create_table(
        "admin_sessions",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("csrf_hash", sa.String(64), nullable=False),
        sa.Column("admin_id", sa.Integer, sa.ForeignKey("admin_users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("last_seen_at", sa.DateTime, nullable=False),
        sa.Column("expires_at", sa.DateTime, nullable=False),
        sa.Column("revoked_at", sa.DateTime),
    )
    topics = op.create_table(
        "question_topics",
        sa.Column("slug", sa.String(40), primary_key=True),
        sa.Column("label", sa.String(80), nullable=False),
        sa.Column("sort_order", sa.Integer, nullable=False, server_default="0"),
    )
    op.bulk_insert(topics, [{"slug": s, "label": label, "sort_order": o} for s, label, o in TOPICS])
    op.create_table(
        "conversations",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("conversation_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("started_at", sa.DateTime, nullable=False),
        sa.Column("last_activity_at", sa.DateTime, nullable=False),
        sa.Column("question_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("primary_topic", sa.String(40), sa.ForeignKey("question_topics.slug")),
        sa.Column("resolution_status", sa.String(12), nullable=False, server_default="unconfirmed"),
        sa.Column("feedback_at", sa.DateTime),
        sa.Column("resolved_at", sa.DateTime),
        sa.Column("resolution_seconds", sa.Float),
    )
    op.create_index("ix_conversations_started_at", "conversations", ["started_at"])
    op.create_index("ix_conversations_status", "conversations", ["resolution_status"])
    op.create_table(
        "interaction_events",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("message_id", sa.String(64), nullable=False, unique=True),
        sa.Column("conversation_id", sa.Integer, sa.ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("asked_at", sa.DateTime, nullable=False),
        sa.Column("topic", sa.String(40), sa.ForeignKey("question_topics.slug"), nullable=False),
        sa.Column("keywords", sa.String(200)),
        sa.Column("answer_status", sa.String(24), nullable=False),
        sa.Column("source_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("pii_detected", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("latency_ms", sa.Integer),
    )
    op.create_index("ix_events_asked_at", "interaction_events", ["asked_at"])
    op.create_index("ix_events_conversation", "interaction_events", ["conversation_id"])
    op.create_table(
        "resolution_feedback",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("conversation_id", sa.Integer, sa.ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("message_id", sa.String(64), sa.ForeignKey("interaction_events.message_id"), nullable=False),
        sa.Column("resolved", sa.Boolean, nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.UniqueConstraint("message_id", name="uq_feedback_message"),
    )


def downgrade() -> None:
    op.drop_table("resolution_feedback")
    op.drop_index("ix_events_conversation", table_name="interaction_events")
    op.drop_index("ix_events_asked_at", table_name="interaction_events")
    op.drop_table("interaction_events")
    op.drop_index("ix_conversations_status", table_name="conversations")
    op.drop_index("ix_conversations_started_at", table_name="conversations")
    op.drop_table("conversations")
    op.drop_table("question_topics")
    op.drop_table("admin_sessions")
    op.drop_table("admin_users")
