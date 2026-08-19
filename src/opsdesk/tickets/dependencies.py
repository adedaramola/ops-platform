from typing import Annotated

from fastapi import Depends

from opsdesk.auth.dependencies import DatabaseSession
from opsdesk.tickets.service import TicketService


def get_ticket_service(db: DatabaseSession) -> TicketService:
    return TicketService(db)


TicketServiceDependency = Annotated[TicketService, Depends(get_ticket_service)]
