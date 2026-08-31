from __future__ import annotations

import secrets
from typing import Annotated

from fastapi import Depends, Header

from opsdesk.ai.service import AiWorkflowService
from opsdesk.auth.dependencies import AppSettings, DatabaseSession
from opsdesk.core.errors import AuthenticationError
from opsdesk.observability.dependencies import MetricsDependency, TelemetryDependency


def get_ai_service(
    db: DatabaseSession,
    settings: AppSettings,
    metrics: MetricsDependency,
    telemetry: TelemetryDependency,
) -> AiWorkflowService:
    return AiWorkflowService(db, settings, metrics, telemetry)


AiServiceDependency = Annotated[AiWorkflowService, Depends(get_ai_service)]
AgentTokenHeader = Annotated[
    str, Header(alias="X-OpsDesk-Agent-Token", min_length=1, max_length=512)
]


def require_agent_token(token: AgentTokenHeader, settings: AppSettings) -> None:
    if not settings.ai_enabled or not secrets.compare_digest(
        token, settings.ai_internal_token.get_secret_value()
    ):
        raise AuthenticationError()


AuthenticatedAgent = Annotated[None, Depends(require_agent_token)]
