from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from opsdesk.tickets.models import TicketPriority, TicketStatus


class TicketCreate(BaseModel):
    title: str = Field(min_length=3, max_length=200)
    description: str = Field(min_length=1, max_length=20_000)
    category_id: uuid.UUID
    priority: TicketPriority = TicketPriority.MEDIUM


class CommentCreate(BaseModel):
    body: str = Field(min_length=1, max_length=10_000)


class InternalNoteCreate(BaseModel):
    body: str = Field(min_length=1, max_length=10_000)


class AssignmentCommand(BaseModel):
    assignee_id: uuid.UUID | None
    expected_version: int = Field(gt=0)


class StatusCommand(BaseModel):
    status: TicketStatus
    expected_version: int = Field(gt=0)


class PriorityCommand(BaseModel):
    priority: TicketPriority
    expected_version: int = Field(gt=0)


class CategoryCommand(BaseModel):
    category_id: uuid.UUID
    expected_version: int = Field(gt=0)


class TicketResponse(BaseModel):
    id: uuid.UUID
    display_number: str
    title: str
    description: str
    status: str
    priority: str
    category_id: uuid.UUID
    category_name: str
    requester_id: uuid.UUID
    assignee_id: uuid.UUID | None
    version: int
    created_at: datetime
    updated_at: datetime
    resolved_at: datetime | None
    closed_at: datetime | None


class TicketListResponse(BaseModel):
    items: list[TicketResponse]
    page: int
    page_size: int
    total: int


class CommentResponse(BaseModel):
    id: uuid.UUID
    ticket_id: uuid.UUID
    author_id: uuid.UUID
    body: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class InternalNoteResponse(BaseModel):
    id: uuid.UUID
    ticket_id: uuid.UUID
    author_id: uuid.UUID
    body: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ActivityResponse(BaseModel):
    id: uuid.UUID
    ticket_id: uuid.UUID
    actor_id: uuid.UUID | None
    event_type: str
    event_metadata: dict[str, object]
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TicketDetailResponse(BaseModel):
    ticket: TicketResponse
    comments: list[CommentResponse]
    activity: list[ActivityResponse]


class DashboardResponse(BaseModel):
    role: str
    status_counts: dict[str, int]
    total_visible: int
    unassigned: int
    assigned_to_me: int


def ticket_response(ticket: object) -> TicketResponse:
    from opsdesk.tickets.models import Ticket

    if not isinstance(ticket, Ticket):
        raise TypeError("Expected Ticket")
    return TicketResponse(
        id=ticket.id,
        display_number=ticket.display_number,
        title=ticket.title,
        description=ticket.description,
        status=ticket.status,
        priority=ticket.priority,
        category_id=ticket.category_id,
        category_name=ticket.category.name,
        requester_id=ticket.requester_id,
        assignee_id=ticket.assignee_id,
        version=ticket.version,
        created_at=ticket.created_at,
        updated_at=ticket.updated_at,
        resolved_at=ticket.resolved_at,
        closed_at=ticket.closed_at,
    )
