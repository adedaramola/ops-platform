from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from pydantic import SecretStr, ValidationError

from opsdesk.agent.config import AgentSettings
from opsdesk.agent.tools import GatewayDraftTool
from opsdesk.agent.worker import AgentRunner, _resolve_gateway_api_key, _resolve_rag_api_key
from opsdesk.ai.schemas import AgentResult, AgentTicketContext


def test_cpu_agent_uses_bounded_api_contract_without_database_access() -> None:
    workflow_id = uuid.uuid4()
    submitted: list[dict[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["X-OpsDesk-Agent-Token"] == "service-token"
        if request.method == "GET":
            return httpx.Response(
                200,
                json={
                    "workflow_id": str(workflow_id),
                    "ticket_id": str(uuid.uuid4()),
                    "ticket_version": 1,
                    "title": "VPN issue",
                    "description": "Cannot connect",
                    "public_comments": [],
                    "deadline_at": (datetime.now(UTC) + timedelta(minutes=2)).isoformat(),
                    "cancel_requested": False,
                },
            )
        submitted.append(dict(httpx.Response(200, content=request.content).json()))
        return httpx.Response(200, json={})

    settings = AgentSettings(
        queue_url="https://sqs.us-east-1.amazonaws.com/123/queue",
        opsdesk_base_url="https://opsdesk.example.com",
        service_token=SecretStr("service-token"),
        max_steps=1,
        token_budget=100,
    )
    with httpx.Client(
        transport=httpx.MockTransport(handler), base_url="https://opsdesk.example.com"
    ) as client:
        AgentRunner(settings, client).process(workflow_id)

    assert submitted[0]["selected_tools"] == ["draft_public_response"]
    assert submitted[0]["provider_class"] == "deterministic-fake"
    assert submitted[0]["rag_used"] is False


def test_agent_package_does_not_import_database_modules() -> None:
    from opsdesk.agent import config, tools, worker

    sources = [config.__file__, tools.__file__, worker.__file__]
    for path in sources:
        assert path is not None
        assert "opsdesk.db" not in open(path, encoding="utf-8").read()  # noqa: SIM115


def test_gateway_draft_tool_uses_private_typed_contract() -> None:
    workflow_id = uuid.uuid4()

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "Bearer gateway-key"
        assert request.headers["X-Workflow-ID"] == str(workflow_id)
        assert request.headers["traceparent"] == (
            "00-1234567890abcdef1234567890abcdef-1234567890abcdef-01"
        )
        payload = json.loads(request.content)
        assert payload["max_tokens"] == 256
        assert payload["metadata"] == {
            "budget": "low",
            "latency_sla_ms": 5000,
            "reasoning_required": False,
            "caller_app": "opsdesk-agent",
            "workflow_id": str(workflow_id),
            "cache_policy": "private",
            "data_classification": "restricted",
        }
        assert '"draft text"' not in payload["messages"][0]["content"]
        assert "Never return placeholder text" in payload["messages"][0]["content"]
        assert "Private note" not in payload["messages"][1]["content"]
        return httpx.Response(
            200,
            json={
                "request_id": "gateway-request",
                "model_used": "claude-haiku",
                "provider": "bedrock",
                "content": json.dumps({"content": "Thanks. We are reviewing your VPN issue."}),
                "usage": {
                    "input_tokens": 80,
                    "output_tokens": 20,
                    "total_tokens": 100,
                    "estimated_cost_usd": 0.00012,
                },
                "cache_hit": False,
                "cache_source": "none",
                "cache_policy": "private",
                "latency_ms": 250,
                "timestamp": 1_787_500_000.0,
            },
        )

    settings = AgentSettings(
        queue_url="https://sqs.us-east-1.amazonaws.com/123/queue",
        opsdesk_base_url="https://opsdesk.example.com",
        service_token=SecretStr("service-token"),
        llm_gateway_enabled=True,
        llm_gateway_base_url="https://gateway.example.com",
        llm_gateway_api_key=SecretStr("gateway-key"),
        llm_gateway_max_tokens=256,
    )
    context = AgentTicketContext(
        workflow_id=workflow_id,
        ticket_id=uuid.uuid4(),
        ticket_version=1,
        title="VPN issue",
        description="Cannot connect",
        public_comments=["Connection fails after sign-in."],
        deadline_at=datetime.now(UTC) + timedelta(minutes=2),
        cancel_requested=False,
        traceparent="00-1234567890abcdef1234567890abcdef-1234567890abcdef-01",
    )
    with httpx.Client(
        transport=httpx.MockTransport(handler),
        base_url="https://gateway.example.com",
    ) as client:
        result = GatewayDraftTool(settings, client, SecretStr("gateway-key")).run(context)

    assert result.content == "Thanks. We are reviewing your VPN issue."
    assert result.selected_tools == ["draft_public_response", "multi_llm_gateway"]
    assert result.provider_class == "bedrock"
    assert result.model_class == "claude-haiku"
    assert result.estimated_cost_usd is not None
    assert result.gateway_request_id == "gateway-request"
    assert result.input_tokens == 80
    assert result.output_tokens == 20
    assert result.cache_policy == "private"
    assert result.cache_source == "none"
    assert result.cache_hit is False


def test_gateway_draft_tool_surfaces_provider_unavailability_for_safe_retry() -> None:
    settings = AgentSettings(
        queue_url="https://sqs.us-east-1.amazonaws.com/123/queue",
        opsdesk_base_url="https://opsdesk.example.com",
        service_token=SecretStr("service-token"),
        llm_gateway_enabled=True,
        llm_gateway_base_url="https://gateway.example.com",
        llm_gateway_api_key=SecretStr("gateway-key"),
    )
    context = AgentTicketContext(
        workflow_id=uuid.uuid4(),
        ticket_id=uuid.uuid4(),
        ticket_version=1,
        title="VPN issue",
        description="Cannot connect",
        public_comments=[],
        deadline_at=datetime.now(UTC) + timedelta(minutes=2),
        cancel_requested=False,
    )

    def unavailable(_: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"code": "provider_unavailable"})

    with (
        httpx.Client(
            transport=httpx.MockTransport(unavailable),
            base_url="https://gateway.example.com",
        ) as client,
        pytest.raises(httpx.HTTPStatusError),
    ):
        GatewayDraftTool(settings, client, SecretStr("gateway-key")).run(context)


def test_gateway_draft_tool_uses_only_validated_rag_citations() -> None:
    workflow_id = uuid.uuid4()

    def rag_handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/search"
        assert request.headers["X-API-Key"] == "rag-key"
        assert request.headers["X-Workflow-ID"] == str(workflow_id)
        assert request.headers["traceparent"] == (
            "00-1234567890abcdef1234567890abcdef-1234567890abcdef-01"
        )
        payload = json.loads(request.content)
        assert payload == {
            "query": "VPN issue",
            "source_ids": ["vpn-runbook"],
            "max_chunks": 2,
        }
        return httpx.Response(
            200,
            json={
                "query_id": "rag-request",
                "chunks": [
                    {
                        "citation_id": "C1",
                        "source_id": "vpn-runbook",
                        "page": 4,
                        "text": "Restart the VPN client after refreshing the device certificate.",
                    }
                ],
            },
        )

    def gateway_handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        user_content = payload["messages"][1]["content"]
        assert "APPROVED_KNOWLEDGE_EVIDENCE" in user_content
        return httpx.Response(
            200,
            json={
                "request_id": "gateway-request",
                "model_used": "claude-haiku",
                "provider": "bedrock",
                "content": json.dumps(
                    {
                        "content": (
                            "Please restart the VPN client after refreshing its certificate. "
                            "Reply here if the connection still fails."
                        ),
                        "citation_ids": ["C1"],
                    }
                ),
                "usage": {
                    "input_tokens": 100,
                    "output_tokens": 30,
                    "total_tokens": 130,
                    "estimated_cost_usd": 0.00015,
                },
                "cache_hit": False,
                "cache_source": "none",
                "cache_policy": "off",
                "latency_ms": 250,
                "timestamp": 1_787_500_000.0,
            },
        )

    settings = AgentSettings(
        queue_url="https://sqs.us-east-1.amazonaws.com/123/queue",
        opsdesk_base_url="https://opsdesk.example.com",
        service_token=SecretStr("service-token"),
        llm_gateway_enabled=True,
        llm_gateway_base_url="https://gateway.example.com",
        llm_gateway_api_key=SecretStr("gateway-key"),
        llm_gateway_cache_policy="off",
        rag_enabled=True,
        rag_base_url="https://rag.example.com",
        rag_api_key=SecretStr("rag-key"),
        rag_source_ids=["vpn-runbook"],
        rag_max_chunks=2,
    )
    context = AgentTicketContext(
        workflow_id=workflow_id,
        ticket_id=uuid.uuid4(),
        ticket_version=1,
        title="VPN issue",
        description="Cannot connect after sign-in.",
        public_comments=[],
        deadline_at=datetime.now(UTC) + timedelta(minutes=2),
        cancel_requested=False,
        traceparent="00-1234567890abcdef1234567890abcdef-1234567890abcdef-01",
    )
    with (
        httpx.Client(
            transport=httpx.MockTransport(gateway_handler),
            base_url="https://gateway.example.com",
        ) as gateway_client,
        httpx.Client(
            transport=httpx.MockTransport(rag_handler),
            base_url="https://rag.example.com",
        ) as rag_client,
    ):
        result = GatewayDraftTool(
            settings,
            gateway_client,
            SecretStr("gateway-key"),
            rag_client,
            SecretStr("rag-key"),
        ).run(context)

    assert result.rag_used is True
    assert result.selected_tools == [
        "draft_public_response",
        "rag_search",
        "multi_llm_gateway",
    ]
    assert [citation.model_dump() for citation in result.citations] == [
        {"citation_id": "C1", "source_id": "vpn-runbook", "page": 4}
    ]


def test_gateway_draft_tool_gracefully_degrades_when_rag_is_unavailable() -> None:
    settings = AgentSettings(
        queue_url="https://sqs.us-east-1.amazonaws.com/123/queue",
        opsdesk_base_url="https://opsdesk.example.com",
        service_token=SecretStr("service-token"),
        llm_gateway_enabled=True,
        llm_gateway_base_url="https://gateway.example.com",
        llm_gateway_api_key=SecretStr("gateway-key"),
        rag_enabled=True,
        rag_base_url="https://rag.example.com",
        rag_api_key=SecretStr("rag-key"),
    )
    context = AgentTicketContext(
        workflow_id=uuid.uuid4(),
        ticket_id=uuid.uuid4(),
        ticket_version=1,
        title="VPN issue",
        description="Cannot connect",
        public_comments=[],
        deadline_at=datetime.now(UTC) + timedelta(minutes=2),
        cancel_requested=False,
    )

    def gateway_handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "request_id": "gateway-request",
                "model_used": "claude-haiku",
                "provider": "bedrock",
                "content": json.dumps(
                    {"content": "Thanks for the report. We are reviewing the VPN issue now."}
                ),
                "usage": {
                    "input_tokens": 80,
                    "output_tokens": 20,
                    "total_tokens": 100,
                    "estimated_cost_usd": 0.00012,
                },
                "cache_hit": False,
                "cache_source": "none",
                "cache_policy": "private",
                "latency_ms": 250,
                "timestamp": 1_787_500_000.0,
            },
        )

    with (
        httpx.Client(
            transport=httpx.MockTransport(gateway_handler),
            base_url="https://gateway.example.com",
        ) as gateway_client,
        httpx.Client(
            transport=httpx.MockTransport(
                lambda _: httpx.Response(503, json={"error": "unavailable"})
            ),
            base_url="https://rag.example.com",
        ) as rag_client,
    ):
        result = GatewayDraftTool(
            settings,
            gateway_client,
            SecretStr("gateway-key"),
            rag_client,
            SecretStr("rag-key"),
        ).run(context)

    assert result.rag_used is False
    assert result.citations == []
    assert result.selected_tools == ["draft_public_response", "multi_llm_gateway"]


def test_gateway_api_key_can_be_resolved_from_secrets_manager() -> None:
    settings = AgentSettings(
        queue_url="https://sqs.us-east-1.amazonaws.com/123/queue",
        opsdesk_base_url="https://opsdesk.example.com",
        service_token=SecretStr("service-token"),
        llm_gateway_enabled=True,
        llm_gateway_base_url="https://gateway.example.com",
        llm_gateway_api_key_secret_arn=(
            "arn:aws:secretsmanager:us-east-1:123456789012:secret:opsdesk-agent"
        ),
    )

    class FakeSecretsManager:
        def get_secret_value(self, *, SecretId: str) -> dict[str, str]:
            assert SecretId == settings.llm_gateway_api_key_secret_arn
            return {"SecretString": "scoped-gateway-key"}

    secret = _resolve_gateway_api_key(settings, FakeSecretsManager())

    assert secret.get_secret_value() == "scoped-gateway-key"


def test_rag_api_key_can_be_resolved_from_secrets_manager() -> None:
    settings = AgentSettings(
        queue_url="https://sqs.us-east-1.amazonaws.com/123/queue",
        opsdesk_base_url="https://opsdesk.example.com",
        service_token=SecretStr("service-token"),
        llm_gateway_enabled=True,
        llm_gateway_base_url="https://gateway.example.com",
        llm_gateway_api_key=SecretStr("gateway-key"),
        rag_enabled=True,
        rag_base_url="https://rag.example.com",
        rag_api_key_secret_arn=("arn:aws:secretsmanager:us-east-1:123456789012:secret:opsdesk-rag"),
    )

    class FakeSecretsManager:
        def get_secret_value(self, *, SecretId: str) -> dict[str, str]:
            assert SecretId == settings.rag_api_key_secret_arn
            return {"SecretString": '{"api_key":"scoped-rag-key"}'}

    secret = _resolve_rag_api_key(settings, FakeSecretsManager())

    assert secret.get_secret_value() == "scoped-rag-key"


def test_agent_result_rejects_inconsistent_cache_metadata() -> None:
    with pytest.raises(ValidationError):
        AgentResult(
            suggestion_type="draft_public_response",
            content="A bounded response.",
            decision_summary="Invalid cache fixture.",
            selected_tools=["draft_public_response", "multi_llm_gateway"],
            provider_class="bedrock",
            model_class="test-model",
            generation_ms=10,
            cache_policy="off",
            cache_source="exact",
            cache_hit=True,
            rag_used=False,
            citations=[],
        )
