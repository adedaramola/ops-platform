"""Persist multi-LLM request, token, cost, and cache metadata."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004_gateway_usage"
down_revision: str | None = "0003_ai_workflows"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "ai_suggestions",
        sa.Column("gateway_request_id", sa.String(length=100), nullable=True),
    )
    op.add_column(
        "ai_suggestions",
        sa.Column("input_tokens", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column(
        "ai_suggestions",
        sa.Column("output_tokens", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column(
        "ai_suggestions",
        sa.Column(
            "cache_policy",
            sa.String(length=20),
            server_default="not_applicable",
            nullable=False,
        ),
    )
    op.add_column(
        "ai_suggestions",
        sa.Column(
            "cache_source",
            sa.String(length=20),
            server_default="not_applicable",
            nullable=False,
        ),
    )
    op.add_column(
        "ai_suggestions",
        sa.Column("cache_hit", sa.Boolean(), server_default=sa.false(), nullable=False),
    )
    op.create_check_constraint(
        op.f("ck_ai_suggestions_nonnegative_input_tokens"),
        "ai_suggestions",
        "input_tokens >= 0",
    )
    op.create_check_constraint(
        op.f("ck_ai_suggestions_nonnegative_output_tokens"),
        "ai_suggestions",
        "output_tokens >= 0",
    )
    op.create_check_constraint(
        op.f("ck_ai_suggestions_valid_cache_policy"),
        "ai_suggestions",
        "cache_policy IN ('not_applicable', 'off', 'private', 'shared')",
    )
    op.create_check_constraint(
        op.f("ck_ai_suggestions_valid_cache_source"),
        "ai_suggestions",
        "cache_source IN ('not_applicable', 'none', 'exact', 'semantic')",
    )
    op.create_check_constraint(
        op.f("ck_ai_suggestions_cache_hit_requires_enabled_policy"),
        "ai_suggestions",
        "NOT cache_hit OR cache_policy IN ('private', 'shared')",
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("ck_ai_suggestions_cache_hit_requires_enabled_policy"),
        "ai_suggestions",
        type_="check",
    )
    op.drop_constraint(
        op.f("ck_ai_suggestions_valid_cache_source"),
        "ai_suggestions",
        type_="check",
    )
    op.drop_constraint(
        op.f("ck_ai_suggestions_valid_cache_policy"),
        "ai_suggestions",
        type_="check",
    )
    op.drop_constraint(
        op.f("ck_ai_suggestions_nonnegative_output_tokens"),
        "ai_suggestions",
        type_="check",
    )
    op.drop_constraint(
        op.f("ck_ai_suggestions_nonnegative_input_tokens"),
        "ai_suggestions",
        type_="check",
    )
    op.drop_column("ai_suggestions", "cache_hit")
    op.drop_column("ai_suggestions", "cache_source")
    op.drop_column("ai_suggestions", "cache_policy")
    op.drop_column("ai_suggestions", "output_tokens")
    op.drop_column("ai_suggestions", "input_tokens")
    op.drop_column("ai_suggestions", "gateway_request_id")
