from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from opsdesk.db.base import Base, TimestampMixin, utc_now


class AiWorkflowStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class SuggestionType(StrEnum):
    DRAFT_PUBLIC_RESPONSE = "draft_public_response"


class ApprovalState(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    APPLIED = "applied"


class ReviewAction(StrEnum):
    EDITED = "edited"
    APPROVED = "approved"
    REJECTED = "rejected"
    APPLIED = "applied"


class OutboxStatus(StrEnum):
    PENDING = "pending"
    PUBLISHED = "published"


class AiWorkflow(TimestampMixin, Base):
    __tablename__ = "ai_workflows"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    ticket_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tickets.id", ondelete="CASCADE"), index=True, nullable=False
    )
    requested_by_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    workflow_type: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), default=AiWorkflowStatus.QUEUED, index=True, nullable=False
    )
    ticket_version: Mapped[int] = mapped_column(Integer, nullable=False)
    idempotency_key: Mapped[str | None] = mapped_column(String(128))
    cancel_requested: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    failure_code: Mapped[str | None] = mapped_column(String(100))
    decision_summary: Mapped[str | None] = mapped_column(String(500))
    selected_tools: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deadline_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        CheckConstraint("ticket_version > 0", name="positive_ticket_version"),
        CheckConstraint("attempt_count >= 0", name="nonnegative_attempt_count"),
        CheckConstraint(
            "status IN ('queued', 'running', 'succeeded', 'failed', 'cancelled')",
            name="valid_status",
        ),
        UniqueConstraint(
            "requested_by_id", "idempotency_key", name="uq_ai_workflows_request_idempotency"
        ),
        Index("ix_ai_workflows_ticket_history", "ticket_id", "created_at", "id"),
    )


class AiSuggestion(Base):
    __tablename__ = "ai_suggestions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    workflow_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("ai_workflows.id", ondelete="CASCADE"), unique=True, index=True, nullable=False
    )
    ticket_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tickets.id", ondelete="CASCADE"), index=True, nullable=False
    )
    suggestion_type: Mapped[str] = mapped_column(String(50), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    approval_state: Mapped[str] = mapped_column(
        String(20), default=ApprovalState.PENDING, index=True, nullable=False
    )
    citations: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list, nullable=False)
    rag_used: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    provider_class: Mapped[str] = mapped_column(String(100), nullable=False)
    model_class: Mapped[str] = mapped_column(String(100), nullable=False)
    generation_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    estimated_cost_usd: Mapped[float | None] = mapped_column(Numeric(12, 6))
    gateway_request_id: Mapped[str | None] = mapped_column(String(100))
    input_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    cache_policy: Mapped[str] = mapped_column(String(20), default="not_applicable", nullable=False)
    cache_source: Mapped[str] = mapped_column(String(20), default="not_applicable", nullable=False)
    cache_hit: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    reviewed_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    applied_comment_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("comments.id", ondelete="SET NULL")
    )

    __table_args__ = (
        CheckConstraint("generation_ms >= 0", name="nonnegative_generation_ms"),
        CheckConstraint("input_tokens >= 0", name="nonnegative_input_tokens"),
        CheckConstraint("output_tokens >= 0", name="nonnegative_output_tokens"),
        CheckConstraint(
            "cache_policy IN ('not_applicable', 'off', 'private', 'shared')",
            name="valid_cache_policy",
        ),
        CheckConstraint(
            "cache_source IN ('not_applicable', 'none', 'exact', 'semantic')",
            name="valid_cache_source",
        ),
        CheckConstraint(
            "NOT cache_hit OR cache_policy IN ('private', 'shared')",
            name="cache_hit_requires_enabled_policy",
        ),
        CheckConstraint(
            "approval_state IN ('pending', 'approved', 'rejected', 'applied')",
            name="valid_approval_state",
        ),
    )


class AiReviewEvent(Base):
    __tablename__ = "ai_review_events"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    suggestion_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("ai_suggestions.id", ondelete="CASCADE"), index=True, nullable=False
    )
    actor_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    action: Mapped[str] = mapped_column(String(20), nullable=False)
    ticket_version: Mapped[int] = mapped_column(Integer, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    content_snapshot: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, index=True, nullable=False
    )

    __table_args__ = (
        CheckConstraint(
            "action IN ('edited', 'approved', 'rejected', 'applied')", name="valid_action"
        ),
        Index("ix_ai_review_events_history", "suggestion_id", "created_at", "id"),
    )


class AiOutboxEvent(Base):
    __tablename__ = "ai_outbox_events"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    workflow_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("ai_workflows.id", ondelete="CASCADE"), unique=True, index=True, nullable=False
    )
    status: Mapped[str] = mapped_column(
        String(20), default=OutboxStatus.PENDING, index=True, nullable=False
    )
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    available_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, index=True, nullable=False
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(String(300))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    __table_args__ = (
        CheckConstraint("attempts >= 0", name="nonnegative_attempts"),
        CheckConstraint("status IN ('pending', 'published')", name="valid_status"),
    )
