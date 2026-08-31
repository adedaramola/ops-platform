from __future__ import annotations

import json
import time
import uuid
from contextlib import ExitStack
from typing import Annotated, Any

import boto3
import httpx
from pydantic import BaseModel, ConfigDict, Field, SecretStr, ValidationError

from opsdesk.agent.config import AgentSettings
from opsdesk.agent.tools import DeterministicDraftTool, DraftTool, GatewayDraftTool
from opsdesk.ai.schemas import AgentTicketContext


class QueueMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    workflow_id: uuid.UUID
    traceparent: Annotated[
        str | None,
        Field(pattern=r"^00-[0-9a-f]{32}-[0-9a-f]{16}-[0-9a-f]{2}$"),
    ] = None


def _resolve_gateway_api_key(settings: AgentSettings, client: Any) -> SecretStr:
    if settings.llm_gateway_api_key is not None:
        return settings.llm_gateway_api_key
    secret_arn = settings.llm_gateway_api_key_secret_arn
    if not secret_arn:
        raise RuntimeError("LLM gateway credential is not configured")
    response = client.get_secret_value(SecretId=secret_arn)
    raw_secret = response.get("SecretString")
    if not isinstance(raw_secret, str) or not raw_secret:
        raise RuntimeError("LLM gateway credential secret has no SecretString")
    try:
        decoded = json.loads(raw_secret)
    except json.JSONDecodeError:
        return SecretStr(raw_secret)
    if not isinstance(decoded, dict) or not isinstance(decoded.get("api_key"), str):
        raise RuntimeError("LLM gateway credential secret has an invalid format")
    return SecretStr(decoded["api_key"])


def _resolve_rag_api_key(settings: AgentSettings, client: Any) -> SecretStr:
    if settings.rag_api_key is not None:
        return settings.rag_api_key
    secret_arn = settings.rag_api_key_secret_arn
    if not secret_arn:
        raise RuntimeError("RAG credential is not configured")
    response = client.get_secret_value(SecretId=secret_arn)
    raw_secret = response.get("SecretString")
    if not isinstance(raw_secret, str) or not raw_secret:
        raise RuntimeError("RAG credential secret has no SecretString")
    try:
        decoded = json.loads(raw_secret)
    except json.JSONDecodeError:
        return SecretStr(raw_secret)
    if not isinstance(decoded, dict) or not isinstance(decoded.get("api_key"), str):
        raise RuntimeError("RAG credential secret has an invalid format")
    return SecretStr(decoded["api_key"])


class AgentRunner:
    def __init__(
        self,
        settings: AgentSettings,
        client: httpx.Client,
        tool: DraftTool | None = None,
    ) -> None:
        self.settings = settings
        self.client = client
        self.tool = tool or DeterministicDraftTool()

    def process(self, workflow_id: uuid.UUID, traceparent: str | None = None) -> None:
        started = time.monotonic()
        headers = {"X-OpsDesk-Agent-Token": self.settings.service_token.get_secret_value()}
        if traceparent is not None:
            headers["traceparent"] = traceparent
        context_response = self.client.get(
            f"/internal/v1/ai-workflows/{workflow_id}/context", headers=headers
        )
        context_response.raise_for_status()
        context = AgentTicketContext.model_validate(context_response.json())
        if context.cancel_requested:
            return
        if self.settings.max_steps < 1:
            raise RuntimeError("Agent step budget exhausted")
        result = self.tool.run(context)
        if len(result.content.split()) > self.settings.token_budget:
            raise RuntimeError("Agent token budget exceeded")
        if time.monotonic() - started > self.settings.total_deadline_seconds:
            raise TimeoutError("Agent total deadline exceeded")
        result_response = self.client.post(
            f"/internal/v1/ai-workflows/{workflow_id}/result",
            headers=headers,
            json=result.model_dump(mode="json"),
        )
        result_response.raise_for_status()


def _receive(client: Any, settings: AgentSettings) -> dict[str, Any] | None:
    response = client.receive_message(
        QueueUrl=settings.queue_url,
        MaxNumberOfMessages=1,
        WaitTimeSeconds=settings.wait_time_seconds,
        VisibilityTimeout=settings.total_deadline_seconds + 30,
    )
    messages = response.get("Messages", [])
    return dict(messages[0]) if messages else None


def main() -> None:
    settings = AgentSettings()  # pyright: ignore[reportCallIssue]
    sqs = boto3.client("sqs")
    with ExitStack() as stack:
        opsdesk_client = stack.enter_context(
            httpx.Client(
                base_url=str(settings.opsdesk_base_url).rstrip("/"),
                timeout=settings.request_timeout_seconds,
            )
        )
        tool: DraftTool = DeterministicDraftTool()
        if settings.llm_gateway_enabled:
            gateway_url = settings.llm_gateway_base_url
            if gateway_url is None:
                raise RuntimeError("LLM gateway URL is not configured")
            gateway_client = stack.enter_context(
                httpx.Client(
                    base_url=str(gateway_url).rstrip("/"),
                    timeout=settings.request_timeout_seconds,
                )
            )
            secrets_client = boto3.client("secretsmanager")
            gateway_api_key = _resolve_gateway_api_key(settings, secrets_client)
            rag_client: httpx.Client | None = None
            rag_api_key: SecretStr | None = None
            if settings.rag_enabled:
                rag_url = settings.rag_base_url
                if rag_url is None:
                    raise RuntimeError("RAG URL is not configured")
                rag_client = stack.enter_context(
                    httpx.Client(
                        base_url=str(rag_url).rstrip("/"),
                        timeout=settings.request_timeout_seconds,
                    )
                )
                rag_api_key = _resolve_rag_api_key(settings, secrets_client)
            tool = GatewayDraftTool(
                settings,
                gateway_client,
                gateway_api_key,
                rag_client,
                rag_api_key,
            )
        runner = AgentRunner(settings, opsdesk_client, tool)
        while True:
            raw_message = _receive(sqs, settings)
            if raw_message is None:
                continue
            try:
                message = QueueMessage.model_validate(json.loads(str(raw_message["Body"])))
            except (KeyError, json.JSONDecodeError, ValidationError):
                # Invalid messages cannot become valid on retry. The DLQ remains a final guard.
                sqs.delete_message(
                    QueueUrl=settings.queue_url,
                    ReceiptHandle=raw_message["ReceiptHandle"],
                )
                continue
            try:
                runner.process(message.workflow_id, message.traceparent)
            except (httpx.HTTPError, RuntimeError, TimeoutError, ValidationError):
                # Safe retry: no consequential action occurs, and result submission is idempotent.
                continue
            else:
                sqs.delete_message(
                    QueueUrl=settings.queue_url,
                    ReceiptHandle=raw_message["ReceiptHandle"],
                )
