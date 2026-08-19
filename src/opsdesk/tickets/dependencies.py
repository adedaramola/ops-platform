from typing import Annotated

from fastapi import Depends

from opsdesk.auth.dependencies import DatabaseSession
from opsdesk.observability.dependencies import MetricsDependency, TelemetryDependency
from opsdesk.tickets.service import TicketService


def get_ticket_service(
    db: DatabaseSession,
    metrics: MetricsDependency,
    telemetry: TelemetryDependency,
) -> TicketService:
    return TicketService(db, metrics, telemetry)


TicketServiceDependency = Annotated[TicketService, Depends(get_ticket_service)]
