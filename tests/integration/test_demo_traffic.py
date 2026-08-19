from __future__ import annotations

import asyncio

import httpx
import pytest
from pydantic import SecretStr
from sqlalchemy import func, select

from opsdesk.auth.security import get_password_service
from opsdesk.core.config import Settings
from opsdesk.db.models import User
from opsdesk.db.session import get_session_factory
from opsdesk.main import create_app
from opsdesk.tickets.models import Comment, Ticket
from opsdesk.traffic.generator import DEMO_AGENT_EMAIL, DEMO_USER_EMAIL, TrafficGenerator

DEMO_USER_PASSWORD = "Demo-User-Only-99!"
DEMO_AGENT_PASSWORD = "Demo-Agent-Only-99!"


def test_demo_generator_executes_real_workflow_and_controlled_outcomes(
    capsys: pytest.CaptureFixture[str],
) -> None:
    passwords = get_password_service()
    with get_session_factory()() as session:
        session.add_all(
            [
                User(
                    email=DEMO_USER_EMAIL,
                    password_hash=passwords.hash(DEMO_USER_PASSWORD),
                    role_key="user",
                    is_active=True,
                ),
                User(
                    email=DEMO_AGENT_EMAIL,
                    password_hash=passwords.hash(DEMO_AGENT_PASSWORD),
                    role_key="agent",
                    is_active=True,
                ),
            ]
        )
        session.commit()

    settings = Settings(
        environment="test",
        traffic_enabled=True,
        traffic_base_url="http://testserver",
        traffic_controlled_outcomes=True,
        seed_user_password=SecretStr(DEMO_USER_PASSWORD),
        seed_agent_password=SecretStr(DEMO_AGENT_PASSWORD),
    )
    app = create_app(settings)
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    generator = TrafficGenerator(settings, transport=transport)

    asyncio.run(generator.run_scenario(0))

    with get_session_factory()() as session:
        ticket = session.scalar(select(Ticket))
        assert ticket is not None
        assert ticket.status == "resolved"
        assert ticket.priority == "high"
        assert ticket.assignee_id is not None
        assert session.scalar(select(func.count()).select_from(Comment)) == 1

    metrics, _content_type = app.state.metrics.render()
    metric_text = metrics.decode()
    for status_class in ("2xx", "4xx", "5xx"):
        if status_class != "5xx":
            assert f'status_class="{status_class}"' in metric_text
    assert 'outcome="rate_limited"' in metric_text
    output = capsys.readouterr().out
    assert '"traffic_source": "demo"' in output
    for sensitive_value in (
        DEMO_USER_EMAIL,
        DEMO_AGENT_EMAIL,
        DEMO_USER_PASSWORD,
        DEMO_AGENT_PASSWORD,
        "Synthetic requester follow-up.",
    ):
        assert sensitive_value not in output
