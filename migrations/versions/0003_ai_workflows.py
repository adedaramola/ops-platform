"""Add bounded AI workflows, suggestions, reviews, and durable outbox."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003_ai_workflows"
down_revision: str | None = "0002_ticket_domain"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ai_workflows",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("ticket_id", sa.Uuid(), nullable=False),
        sa.Column("requested_by_id", sa.Uuid(), nullable=False),
        sa.Column("workflow_type", sa.String(length=50), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("ticket_version", sa.Integer(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=True),
        sa.Column("cancel_requested", sa.Boolean(), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("failure_code", sa.String(length=100), nullable=True),
        sa.Column("decision_summary", sa.String(length=500), nullable=True),
        sa.Column("selected_tools", sa.JSON(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deadline_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "attempt_count >= 0", name=op.f("ck_ai_workflows_nonnegative_attempt_count")
        ),
        sa.CheckConstraint(
            "ticket_version > 0", name=op.f("ck_ai_workflows_positive_ticket_version")
        ),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'succeeded', 'failed', 'cancelled')",
            name=op.f("ck_ai_workflows_valid_status"),
        ),
        sa.ForeignKeyConstraint(
            ["requested_by_id"],
            ["users.id"],
            name=op.f("fk_ai_workflows_requested_by_id_users"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["ticket_id"],
            ["tickets.id"],
            name=op.f("fk_ai_workflows_ticket_id_tickets"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ai_workflows")),
        sa.UniqueConstraint(
            "requested_by_id", "idempotency_key", name="uq_ai_workflows_request_idempotency"
        ),
    )
    op.create_index(op.f("ix_ai_workflows_requested_by_id"), "ai_workflows", ["requested_by_id"])
    op.create_index(op.f("ix_ai_workflows_status"), "ai_workflows", ["status"])
    op.create_index(op.f("ix_ai_workflows_ticket_id"), "ai_workflows", ["ticket_id"])
    op.create_index(
        "ix_ai_workflows_ticket_history", "ai_workflows", ["ticket_id", "created_at", "id"]
    )

    op.create_table(
        "ai_suggestions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workflow_id", sa.Uuid(), nullable=False),
        sa.Column("ticket_id", sa.Uuid(), nullable=False),
        sa.Column("suggestion_type", sa.String(length=50), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("approval_state", sa.String(length=20), nullable=False),
        sa.Column("citations", sa.JSON(), nullable=False),
        sa.Column("rag_used", sa.Boolean(), nullable=False),
        sa.Column("provider_class", sa.String(length=100), nullable=False),
        sa.Column("model_class", sa.String(length=100), nullable=False),
        sa.Column("generation_ms", sa.Integer(), nullable=False),
        sa.Column("estimated_cost_usd", sa.Numeric(precision=12, scale=6), nullable=True),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reviewed_by_id", sa.Uuid(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("applied_comment_id", sa.Uuid(), nullable=True),
        sa.CheckConstraint(
            "approval_state IN ('pending', 'approved', 'rejected', 'applied')",
            name=op.f("ck_ai_suggestions_valid_approval_state"),
        ),
        sa.CheckConstraint(
            "generation_ms >= 0", name=op.f("ck_ai_suggestions_nonnegative_generation_ms")
        ),
        sa.ForeignKeyConstraint(
            ["applied_comment_id"],
            ["comments.id"],
            name=op.f("fk_ai_suggestions_applied_comment_id_comments"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["reviewed_by_id"],
            ["users.id"],
            name=op.f("fk_ai_suggestions_reviewed_by_id_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["ticket_id"],
            ["tickets.id"],
            name=op.f("fk_ai_suggestions_ticket_id_tickets"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["workflow_id"],
            ["ai_workflows.id"],
            name=op.f("fk_ai_suggestions_workflow_id_ai_workflows"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ai_suggestions")),
    )
    op.create_index(op.f("ix_ai_suggestions_approval_state"), "ai_suggestions", ["approval_state"])
    op.create_index(op.f("ix_ai_suggestions_ticket_id"), "ai_suggestions", ["ticket_id"])
    op.create_index(
        op.f("ix_ai_suggestions_workflow_id"), "ai_suggestions", ["workflow_id"], unique=True
    )

    op.create_table(
        "ai_review_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("suggestion_id", sa.Uuid(), nullable=False),
        sa.Column("actor_id", sa.Uuid(), nullable=False),
        sa.Column("action", sa.String(length=20), nullable=False),
        sa.Column("ticket_version", sa.Integer(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("content_snapshot", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "action IN ('edited', 'approved', 'rejected', 'applied')",
            name=op.f("ck_ai_review_events_valid_action"),
        ),
        sa.ForeignKeyConstraint(
            ["actor_id"],
            ["users.id"],
            name=op.f("fk_ai_review_events_actor_id_users"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["suggestion_id"],
            ["ai_suggestions.id"],
            name=op.f("fk_ai_review_events_suggestion_id_ai_suggestions"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ai_review_events")),
    )
    op.create_index(op.f("ix_ai_review_events_actor_id"), "ai_review_events", ["actor_id"])
    op.create_index(op.f("ix_ai_review_events_created_at"), "ai_review_events", ["created_at"])
    op.create_index(
        "ix_ai_review_events_history", "ai_review_events", ["suggestion_id", "created_at", "id"]
    )
    op.create_index(
        op.f("ix_ai_review_events_suggestion_id"), "ai_review_events", ["suggestion_id"]
    )

    op.create_table(
        "ai_outbox_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workflow_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.String(length=300), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("attempts >= 0", name=op.f("ck_ai_outbox_events_nonnegative_attempts")),
        sa.CheckConstraint(
            "status IN ('pending', 'published')", name=op.f("ck_ai_outbox_events_valid_status")
        ),
        sa.ForeignKeyConstraint(
            ["workflow_id"],
            ["ai_workflows.id"],
            name=op.f("fk_ai_outbox_events_workflow_id_ai_workflows"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ai_outbox_events")),
    )
    op.create_index(op.f("ix_ai_outbox_events_available_at"), "ai_outbox_events", ["available_at"])
    op.create_index(op.f("ix_ai_outbox_events_status"), "ai_outbox_events", ["status"])
    op.create_index(
        op.f("ix_ai_outbox_events_workflow_id"), "ai_outbox_events", ["workflow_id"], unique=True
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_ai_outbox_events_workflow_id"), table_name="ai_outbox_events")
    op.drop_index(op.f("ix_ai_outbox_events_status"), table_name="ai_outbox_events")
    op.drop_index(op.f("ix_ai_outbox_events_available_at"), table_name="ai_outbox_events")
    op.drop_table("ai_outbox_events")
    op.drop_index(op.f("ix_ai_review_events_suggestion_id"), table_name="ai_review_events")
    op.drop_index("ix_ai_review_events_history", table_name="ai_review_events")
    op.drop_index(op.f("ix_ai_review_events_created_at"), table_name="ai_review_events")
    op.drop_index(op.f("ix_ai_review_events_actor_id"), table_name="ai_review_events")
    op.drop_table("ai_review_events")
    op.drop_index(op.f("ix_ai_suggestions_workflow_id"), table_name="ai_suggestions")
    op.drop_index(op.f("ix_ai_suggestions_ticket_id"), table_name="ai_suggestions")
    op.drop_index(op.f("ix_ai_suggestions_approval_state"), table_name="ai_suggestions")
    op.drop_table("ai_suggestions")
    op.drop_index("ix_ai_workflows_ticket_history", table_name="ai_workflows")
    op.drop_index(op.f("ix_ai_workflows_ticket_id"), table_name="ai_workflows")
    op.drop_index(op.f("ix_ai_workflows_status"), table_name="ai_workflows")
    op.drop_index(op.f("ix_ai_workflows_requested_by_id"), table_name="ai_workflows")
    op.drop_table("ai_workflows")
