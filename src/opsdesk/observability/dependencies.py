from __future__ import annotations

from typing import Annotated, cast

from fastapi import Depends, Request

from opsdesk.observability.metrics import OpsMetrics
from opsdesk.observability.tracing import Telemetry


def get_metrics(request: Request) -> OpsMetrics:
    return cast(OpsMetrics, request.app.state.metrics)


def get_telemetry(request: Request) -> Telemetry:
    return cast(Telemetry, request.app.state.telemetry)


MetricsDependency = Annotated[OpsMetrics, Depends(get_metrics)]
TelemetryDependency = Annotated[Telemetry, Depends(get_telemetry)]
