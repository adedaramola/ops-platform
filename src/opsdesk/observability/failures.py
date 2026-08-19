from __future__ import annotations

import asyncio
from typing import Annotated

from fastapi import APIRouter, Query

from opsdesk.auth.dependencies import AppSettings, CurrentPrincipal
from opsdesk.core.errors import WorkflowError

router = APIRouter(prefix="/api/v1/development/failures", tags=["development"])


@router.get("/slow")
async def controlled_slow_response(
    principal: CurrentPrincipal,
    settings: AppSettings,
    delay_ms: Annotated[int, Query(ge=1)] = 250,
) -> dict[str, int | str]:
    del principal
    if delay_ms > settings.controlled_failure_max_delay_ms:
        raise WorkflowError("Requested delay exceeds the configured development limit")
    await asyncio.sleep(delay_ms / 1_000)
    return {"status": "delayed", "delay_ms": delay_ms}


@router.get("/error")
def controlled_server_error(principal: CurrentPrincipal) -> None:
    del principal
    raise RuntimeError("Controlled development failure")
