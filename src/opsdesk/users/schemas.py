from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict


class UserAdminResponse(BaseModel):
    id: uuid.UUID
    email: str
    role_key: str
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class UserRoleUpdate(BaseModel):
    role: Literal["user", "agent", "admin"]


class UserActivationUpdate(BaseModel):
    is_active: bool
