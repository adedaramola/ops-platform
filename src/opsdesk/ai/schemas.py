from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class AiSuggestionRequest(BaseModel):
    suggestion_type: Literal["draft_public_response"] = "draft_public_response"
    idempotency_key: Annotated[str | None, Field(min_length=8, max_length=128)] = None


class AiSuggestionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    suggestion_type: str
    content: str
    approval_state: str
    citations: list[dict[str, object]]
    rag_used: bool
    provider_class: str
    model_class: str
    generation_ms: int
    estimated_cost_usd: Decimal | None
    gateway_request_id: str | None
    input_tokens: int
    output_tokens: int
    cache_policy: str
    cache_source: str
    cache_hit: bool
    generated_at: datetime
    applied_comment_id: uuid.UUID | None


class AiWorkflowResponse(BaseModel):
    id: uuid.UUID
    ticket_id: uuid.UUID
    workflow_type: str
    status: str
    ticket_version: int
    cancel_requested: bool
    failure_code: str | None
    decision_summary: str | None
    selected_tools: list[str]
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    deadline_at: datetime
    suggestion: AiSuggestionResponse | None = None


class AgentTicketContext(BaseModel):
    workflow_id: uuid.UUID
    ticket_id: uuid.UUID
    ticket_version: int
    title: Annotated[str, Field(max_length=200)]
    description: Annotated[str, Field(max_length=20_000)]
    public_comments: Annotated[list[str], Field(max_length=100)]
    deadline_at: datetime
    cancel_requested: bool


class AgentResult(BaseModel):
    suggestion_type: Literal["draft_public_response"]
    content: Annotated[str, Field(min_length=1, max_length=10_000)]
    decision_summary: Annotated[str, Field(min_length=1, max_length=500)]
    selected_tools: Annotated[
        list[Literal["draft_public_response", "multi_llm_gateway"]],
        Field(min_length=1, max_length=3),
    ]
    provider_class: Annotated[str, Field(min_length=1, max_length=100)]
    model_class: Annotated[str, Field(min_length=1, max_length=100)]
    generation_ms: Annotated[int, Field(ge=0, le=300_000)]
    estimated_cost_usd: Annotated[Decimal | None, Field(ge=0)] = None
    gateway_request_id: Annotated[str | None, Field(max_length=100)] = None
    input_tokens: Annotated[int, Field(ge=0)] = 0
    output_tokens: Annotated[int, Field(ge=0)] = 0
    cache_policy: Literal["not_applicable", "off", "private", "shared"] = "not_applicable"
    cache_source: Literal["not_applicable", "none", "exact", "semantic"] = "not_applicable"
    cache_hit: bool = False
    rag_used: Literal[False] = False
    citations: Annotated[list[dict[str, object]], Field(max_length=0)] = []

    @model_validator(mode="after")
    def validate_cache_metadata(self) -> AgentResult:
        if self.cache_policy == "not_applicable":
            if self.cache_source != "not_applicable" or self.cache_hit:
                raise ValueError("Non-gateway results require neutral cache metadata")
        elif self.cache_policy == "off":
            if self.cache_source != "none" or self.cache_hit:
                raise ValueError("Cache-off results cannot report a cache hit")
        elif self.cache_source == "not_applicable":
            raise ValueError("Gateway results require an applicable cache source")
        if self.cache_hit and self.cache_source not in {"exact", "semantic"}:
            raise ValueError("Cache hits require an exact or semantic source")
        return self


class ApprovalCommand(BaseModel):
    content: Annotated[str | None, Field(min_length=1, max_length=10_000)] = None


class ApplyResponse(BaseModel):
    suggestion_id: uuid.UUID
    approval_state: Literal["applied"]
    comment_id: uuid.UUID
