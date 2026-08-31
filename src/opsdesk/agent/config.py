from __future__ import annotations

from typing import Literal

from pydantic import Field, HttpUrl, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class AgentSettings(BaseSettings):
    queue_url: str
    opsdesk_base_url: HttpUrl
    service_token: SecretStr
    request_timeout_seconds: float = 5.0
    total_deadline_seconds: int = 120
    max_steps: int = 3
    token_budget: int = 2_000
    wait_time_seconds: int = 20
    llm_gateway_enabled: bool = False
    llm_gateway_base_url: HttpUrl | None = None
    llm_gateway_api_key: SecretStr | None = None
    llm_gateway_api_key_secret_arn: str | None = None
    llm_gateway_cache_policy: Literal["off", "private"] = "private"
    llm_gateway_max_tokens: int = 512
    llm_gateway_temperature: float = 0.2
    rag_enabled: bool = False
    rag_base_url: HttpUrl | None = None
    rag_api_key: SecretStr | None = None
    rag_api_key_secret_arn: str | None = None
    rag_source_ids: list[str] = Field(default_factory=list, max_length=20)
    rag_max_chunks: int = 5

    model_config = SettingsConfigDict(env_prefix="OPS_AGENT_", extra="ignore")

    @model_validator(mode="after")
    def validate_bounds(self) -> AgentSettings:
        if not 1 <= self.max_steps <= 10:
            raise ValueError("Agent max steps must be between 1 and 10")
        if not 100 <= self.token_budget <= 20_000:
            raise ValueError("Agent token budget must be between 100 and 20000")
        if not 0.5 <= self.request_timeout_seconds <= 30:
            raise ValueError("Agent request timeout must be between 0.5 and 30 seconds")
        if not 10 <= self.total_deadline_seconds <= 900:
            raise ValueError("Agent deadline must be between 10 and 900 seconds")
        if not 0 <= self.wait_time_seconds <= 20:
            raise ValueError("SQS wait time must be between 0 and 20 seconds")
        if self.llm_gateway_enabled and self.llm_gateway_base_url is None:
            raise ValueError("LLM gateway URL is required when gateway integration is enabled")
        if self.llm_gateway_enabled and not (
            self.llm_gateway_api_key or self.llm_gateway_api_key_secret_arn
        ):
            raise ValueError(
                "LLM gateway API key or Secrets Manager ARN is required when integration is enabled"
            )
        if not 32 <= self.llm_gateway_max_tokens <= 2_000:
            raise ValueError("LLM gateway max tokens must be between 32 and 2000")
        if not 0 <= self.llm_gateway_temperature <= 1:
            raise ValueError("LLM gateway temperature must be between 0 and 1")
        if self.rag_enabled and not self.llm_gateway_enabled:
            raise ValueError("RAG requires the LLM gateway integration")
        if self.rag_enabled and self.rag_base_url is None:
            raise ValueError("RAG URL is required when retrieval integration is enabled")
        if self.rag_enabled and not (self.rag_api_key or self.rag_api_key_secret_arn):
            raise ValueError(
                "RAG API key or Secrets Manager ARN is required when retrieval is enabled"
            )
        if not 1 <= self.rag_max_chunks <= 8:
            raise ValueError("RAG max chunks must be between 1 and 8")
        if any(not source_id.strip() or len(source_id) > 200 for source_id in self.rag_source_ids):
            raise ValueError("RAG source IDs must contain between 1 and 200 characters")
        return self
