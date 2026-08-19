from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class AuditEventResponse(BaseModel):
    id: uuid.UUID
    actor_user_id: uuid.UUID | None
    event_type: str
    target_type: str | None
    target_id: str | None
    event_metadata: dict[str, object]
    request_id: str | None
    trace_id: str | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AdminStatisticsResponse(BaseModel):
    users_total: int
    users_active: int
    categories_total: int
    categories_active: int
    tickets_total: int
    tickets_unassigned: int
    status_counts: dict[str, int]
    priority_counts: dict[str, int]
