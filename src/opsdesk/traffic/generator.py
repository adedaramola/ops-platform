from __future__ import annotations

import asyncio
import uuid
from collections.abc import Awaitable
from contextlib import suppress
from dataclasses import dataclass
from typing import Any

import httpx

from opsdesk.core.config import Settings
from opsdesk.observability.logging import get_logger

DEMO_USER_EMAIL = "demo-user@opsdesk.example.com"
DEMO_AGENT_EMAIL = "demo-agent@opsdesk.example.com"


@dataclass(slots=True)
class TrafficSummary:
    attempted: int = 0
    succeeded: int = 0
    failed: int = 0
    cancelled: bool = False


class TrafficGenerator:
    def __init__(
        self,
        settings: Settings,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        if not settings.traffic_enabled:
            raise ValueError("Demo traffic is disabled; set OPS_TRAFFIC_ENABLED=true explicitly")
        if settings.environment == "production":
            raise ValueError("Demo traffic cannot run in production")
        if settings.seed_user_password is None or settings.seed_agent_password is None:
            raise ValueError("Designated demo user and agent passwords are required")
        self.settings = settings
        self.transport = transport
        self.user_password = settings.seed_user_password.get_secret_value()
        self.agent_password = settings.seed_agent_password.get_secret_value()
        self._cancel = asyncio.Event()

    def cancel(self) -> None:
        self._cancel.set()

    async def run(self) -> TrafficSummary:
        summary = TrafficSummary()
        loop = asyncio.get_running_loop()
        deadline = loop.time() + self.settings.traffic_duration_seconds
        interval = 1.0 / self.settings.traffic_rate_per_second
        tasks: set[asyncio.Task[bool]] = set()
        scenario_number = 0

        while loop.time() < deadline and not self._cancel.is_set():
            if len(tasks) >= self.settings.traffic_concurrency:
                cancel_waiter = asyncio.create_task(self._cancel.wait())
                done, _pending = await asyncio.wait(
                    {*tasks, cancel_waiter}, return_when=asyncio.FIRST_COMPLETED
                )
                if cancel_waiter in done:
                    break
                cancel_waiter.cancel()
                await asyncio.gather(cancel_waiter, return_exceptions=True)
                completed = {task for task in done if task is not cancel_waiter}
                tasks.difference_update(completed)
                self._record_results(completed, summary)
                continue

            task = asyncio.create_task(self._run_safely(scenario_number))
            tasks.add(task)
            summary.attempted += 1
            scenario_number += 1

            remaining = deadline - loop.time()
            if remaining <= 0:
                break
            with suppress(TimeoutError):
                await asyncio.wait_for(self._cancel.wait(), timeout=min(interval, remaining))

        if self._cancel.is_set():
            summary.cancelled = True
            for task in tasks:
                task.cancel()
        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for result in results:
                if result is True:
                    summary.succeeded += 1
                elif not isinstance(result, asyncio.CancelledError):
                    summary.failed += 1
        return summary

    @staticmethod
    def _record_results(done: set[asyncio.Task[bool]], summary: TrafficSummary) -> None:
        for task in done:
            if task.cancelled():
                continue
            if task.exception() is None and task.result():
                summary.succeeded += 1
            else:
                summary.failed += 1

    async def _run_safely(self, scenario_number: int) -> bool:
        try:
            await self.run_scenario(scenario_number)
        except asyncio.CancelledError:
            raise
        except Exception as error:
            get_logger().warning(
                "traffic.scenario_failed",
                event_name="traffic.scenario_failed",
                error_type=type(error).__name__,
                scenario_number=scenario_number,
                traffic_source="demo",
            )
            return False
        get_logger().info(
            "traffic.scenario_completed",
            event_name="traffic.scenario_completed",
            scenario_number=scenario_number,
            traffic_source="demo",
        )
        return True

    async def run_scenario(self, scenario_number: int) -> None:
        headers = {"X-Traffic-Source": "demo"}
        client_options: dict[str, Any] = {
            "base_url": self.settings.traffic_base_url.rstrip("/"),
            "headers": headers,
            "timeout": self.settings.traffic_request_timeout_seconds,
            "transport": self.transport,
        }
        async with (
            httpx.AsyncClient(**client_options) as user,
            httpx.AsyncClient(**client_options) as agent,
        ):
            await self._login(
                user,
                DEMO_USER_EMAIL,
                self.user_password,
            )
            agent_identity = await self._login(
                agent,
                DEMO_AGENT_EMAIL,
                self.agent_password,
            )
            categories = self._json_list(await self._expect(user.get("/api/v1/categories"), 200))
            category_id = str(categories[0]["id"])
            ticket = await self._mutate(
                user,
                "/api/v1/tickets",
                {
                    "title": f"Demo observability scenario {scenario_number}",
                    "description": (
                        "Synthetic support activity generated for observability testing."
                    ),
                    "category_id": category_id,
                    "priority": "medium",
                },
                201,
            )
            ticket_id = str(ticket["id"])
            await self._expect(
                user.get("/api/v1/tickets", params={"query": ticket["display_number"]}),
                200,
            )
            await self._mutate(
                user,
                f"/api/v1/tickets/{ticket_id}/comments",
                {"body": "Synthetic requester follow-up."},
                201,
            )
            claimed = await self._mutate(
                agent,
                f"/api/v1/tickets/{ticket_id}/assignment",
                {"assignee_id": agent_identity["user"]["id"], "expected_version": 1},
                200,
            )
            prioritized = await self._mutate(
                agent,
                f"/api/v1/tickets/{ticket_id}/priority",
                {"priority": "high", "expected_version": claimed["version"]},
                200,
            )
            active = await self._mutate(
                agent,
                f"/api/v1/tickets/{ticket_id}/status",
                {"status": "in_progress", "expected_version": prioritized["version"]},
                200,
            )
            resolved = await self._mutate(
                agent,
                f"/api/v1/tickets/{ticket_id}/status",
                {"status": "resolved", "expected_version": active["version"]},
                200,
            )
            if self.settings.traffic_controlled_outcomes and scenario_number == 0:
                await self._controlled_outcomes(user, agent, ticket_id, resolved)

    async def _controlled_outcomes(
        self,
        user: httpx.AsyncClient,
        agent: httpx.AsyncClient,
        ticket_id: str,
        ticket: dict[str, Any],
    ) -> None:
        async with httpx.AsyncClient(
            base_url=self.settings.traffic_base_url.rstrip("/"),
            headers={"X-Traffic-Source": "demo"},
            timeout=self.settings.traffic_request_timeout_seconds,
            transport=self.transport,
        ) as anonymous:
            await self._expect(anonymous.get("/api/v1/tickets"), 401)
            await self._generate_rate_limit(anonymous)
        await self._expect(user.get(f"/api/v1/tickets/{ticket_id}/internal-notes"), 403)
        await self._expect(user.get(f"/api/v1/tickets/{uuid.uuid4()}"), 404)
        await self._mutate(
            agent,
            f"/api/v1/tickets/{ticket_id}/priority",
            {"priority": "critical", "expected_version": 1},
            409,
        )
        await self._mutate(
            user,
            "/api/v1/tickets",
            {"title": "x", "description": "invalid", "category_id": ticket["category_id"]},
            422,
        )
        if self.settings.traffic_controlled_failures:
            await self._expect(
                user.get("/api/v1/development/failures/slow", params={"delay_ms": 100}),
                200,
            )
            await self._expect(user.get("/api/v1/development/failures/error"), 500)

    async def _generate_rate_limit(self, client: httpx.AsyncClient) -> None:
        for _attempt in range(self.settings.login_max_failures + 1):
            token = await self._csrf(client)
            response = await client.post(
                "/api/v1/auth/login",
                headers={"X-CSRF-Token": token},
                json={
                    "email": "demo-rate-limit@opsdesk.example.com",
                    "password": "Deliberately-Wrong-99!",
                },
            )
            if response.status_code == 429:
                return
            if response.status_code != 401:
                response.raise_for_status()
        raise RuntimeError("Controlled rate-limit outcome was not produced")

    async def _login(self, client: httpx.AsyncClient, email: str, password: str) -> dict[str, Any]:
        token = await self._csrf(client)
        response = await client.post(
            "/api/v1/auth/login",
            headers={"X-CSRF-Token": token},
            json={"email": email, "password": password},
        )
        return self._json_object(await self._expect(response, 200))

    async def _mutate(
        self,
        client: httpx.AsyncClient,
        path: str,
        payload: dict[str, Any],
        expected_status: int,
    ) -> dict[str, Any]:
        token = await self._csrf(client)
        response = await client.post(
            path,
            headers={"X-CSRF-Token": token},
            json=payload,
        )
        return self._json_object(await self._expect(response, expected_status))

    @staticmethod
    async def _csrf(client: httpx.AsyncClient) -> str:
        response = await TrafficGenerator._expect(client.get("/api/v1/auth/csrf"), 200)
        return str(response.json()["csrf_token"])

    @staticmethod
    async def _expect(
        response_awaitable: Awaitable[httpx.Response] | httpx.Response,
        expected_status: int,
    ) -> httpx.Response:
        response = (
            response_awaitable
            if isinstance(response_awaitable, httpx.Response)
            else await response_awaitable
        )
        if response.status_code != expected_status:
            raise RuntimeError(f"Expected HTTP {expected_status}, received {response.status_code}")
        return response

    @staticmethod
    def _json_object(response: httpx.Response) -> dict[str, Any]:
        payload = response.json()
        if not isinstance(payload, dict):
            raise RuntimeError("Expected a JSON object")
        return payload

    @staticmethod
    def _json_list(response: httpx.Response) -> list[dict[str, Any]]:
        payload = response.json()
        if not isinstance(payload, list) or not all(isinstance(item, dict) for item in payload):
            raise RuntimeError("Expected a JSON object list")
        return payload
