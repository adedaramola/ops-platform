"""Add categories, tickets, comments, private notes, and activity history."""

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op

revision: str = "0002_ticket_domain"
down_revision: str | None = "0001_core_auth"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    categories = op.create_table(
        "categories",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_categories")),
    )
    op.create_index(op.f("ix_categories_name"), "categories", ["name"], unique=True)
    op.bulk_insert(
        categories,
        [
            {
                "id": uuid.UUID("00000000-0000-0000-0000-000000000001"),
                "name": "General",
                "description": "General support requests",
                "is_active": True,
                "created_at": datetime.now(UTC),
                "updated_at": datetime.now(UTC),
            }
        ],
    )

    op.execute(sa.schema.CreateSequence(sa.Sequence("ticket_number_seq", start=1)))
    op.create_table(
        "tickets",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "ticket_number",
            sa.BigInteger(),
            server_default=sa.text("nextval('ticket_number_seq')"),
            nullable=False,
        ),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("priority", sa.String(length=16), nullable=False),
        sa.Column("category_id", sa.Uuid(), nullable=False),
        sa.Column("requester_id", sa.Uuid(), nullable=False),
        sa.Column("assignee_id", sa.Uuid(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("version > 0", name=op.f("ck_tickets_positive_version")),
        sa.CheckConstraint(
            "priority IN ('low', 'medium', 'high', 'critical')",
            name=op.f("ck_tickets_valid_priority"),
        ),
        sa.CheckConstraint(
            "status IN ('open', 'in_progress', 'waiting_for_user', 'resolved', 'closed')",
            name=op.f("ck_tickets_valid_status"),
        ),
        sa.ForeignKeyConstraint(
            ["assignee_id"],
            ["users.id"],
            name=op.f("fk_tickets_assignee_id_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["category_id"],
            ["categories.id"],
            name=op.f("fk_tickets_category_id_categories"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["requester_id"],
            ["users.id"],
            name=op.f("fk_tickets_requester_id_users"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tickets")),
    )
    op.create_index(op.f("ix_tickets_assignee_id"), "tickets", ["assignee_id"])
    op.create_index(op.f("ix_tickets_category_id"), "tickets", ["category_id"])
    op.create_index(op.f("ix_tickets_requester_id"), "tickets", ["requester_id"])
    op.create_index("ix_tickets_stable_page", "tickets", ["created_at", "id"])
    op.create_index(op.f("ix_tickets_ticket_number"), "tickets", ["ticket_number"], unique=True)

    op.create_table(
        "comments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("ticket_id", sa.Uuid(), nullable=False),
        sa.Column("author_id", sa.Uuid(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["author_id"],
            ["users.id"],
            name=op.f("fk_comments_author_id_users"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["ticket_id"],
            ["tickets.id"],
            name=op.f("fk_comments_ticket_id_tickets"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_comments")),
    )
    op.create_index(op.f("ix_comments_author_id"), "comments", ["author_id"])
    op.create_index(op.f("ix_comments_created_at"), "comments", ["created_at"])
    op.create_index(op.f("ix_comments_ticket_id"), "comments", ["ticket_id"])

    op.create_table(
        "internal_notes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("ticket_id", sa.Uuid(), nullable=False),
        sa.Column("author_id", sa.Uuid(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["author_id"],
            ["users.id"],
            name=op.f("fk_internal_notes_author_id_users"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["ticket_id"],
            ["tickets.id"],
            name=op.f("fk_internal_notes_ticket_id_tickets"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_internal_notes")),
    )
    op.create_index(op.f("ix_internal_notes_author_id"), "internal_notes", ["author_id"])
    op.create_index(op.f("ix_internal_notes_created_at"), "internal_notes", ["created_at"])
    op.create_index(op.f("ix_internal_notes_ticket_id"), "internal_notes", ["ticket_id"])

    op.create_table(
        "ticket_activities",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("ticket_id", sa.Uuid(), nullable=False),
        sa.Column("actor_id", sa.Uuid(), nullable=True),
        sa.Column("event_type", sa.String(length=100), nullable=False),
        sa.Column("event_metadata", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["actor_id"],
            ["users.id"],
            name=op.f("fk_ticket_activities_actor_id_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["ticket_id"],
            ["tickets.id"],
            name=op.f("fk_ticket_activities_ticket_id_tickets"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ticket_activities")),
    )
    op.create_index(op.f("ix_ticket_activities_actor_id"), "ticket_activities", ["actor_id"])
    op.create_index(op.f("ix_ticket_activities_created_at"), "ticket_activities", ["created_at"])
    op.create_index(op.f("ix_ticket_activities_event_type"), "ticket_activities", ["event_type"])
    op.create_index(
        "ix_ticket_activities_history", "ticket_activities", ["ticket_id", "created_at", "id"]
    )
    op.create_index(op.f("ix_ticket_activities_ticket_id"), "ticket_activities", ["ticket_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_ticket_activities_ticket_id"), table_name="ticket_activities")
    op.drop_index("ix_ticket_activities_history", table_name="ticket_activities")
    op.drop_index(op.f("ix_ticket_activities_event_type"), table_name="ticket_activities")
    op.drop_index(op.f("ix_ticket_activities_created_at"), table_name="ticket_activities")
    op.drop_index(op.f("ix_ticket_activities_actor_id"), table_name="ticket_activities")
    op.drop_table("ticket_activities")
    op.drop_index(op.f("ix_internal_notes_ticket_id"), table_name="internal_notes")
    op.drop_index(op.f("ix_internal_notes_created_at"), table_name="internal_notes")
    op.drop_index(op.f("ix_internal_notes_author_id"), table_name="internal_notes")
    op.drop_table("internal_notes")
    op.drop_index(op.f("ix_comments_ticket_id"), table_name="comments")
    op.drop_index(op.f("ix_comments_created_at"), table_name="comments")
    op.drop_index(op.f("ix_comments_author_id"), table_name="comments")
    op.drop_table("comments")
    op.drop_index(op.f("ix_tickets_ticket_number"), table_name="tickets")
    op.drop_index("ix_tickets_stable_page", table_name="tickets")
    op.drop_index(op.f("ix_tickets_requester_id"), table_name="tickets")
    op.drop_index(op.f("ix_tickets_category_id"), table_name="tickets")
    op.drop_index(op.f("ix_tickets_assignee_id"), table_name="tickets")
    op.drop_table("tickets")
    op.execute(sa.schema.DropSequence(sa.Sequence("ticket_number_seq")))
    op.drop_index(op.f("ix_categories_name"), table_name="categories")
    op.drop_table("categories")
