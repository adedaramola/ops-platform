"""Persist bounded W3C trace context for asynchronous AI workflows."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005_workflow_trace_context"
down_revision: str | None = "0004_gateway_usage"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "ai_workflows",
        sa.Column("traceparent", sa.String(length=55), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("ai_workflows", "traceparent")
