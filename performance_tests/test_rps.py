import asyncio
import math
import os
import socket
import threading
import time
import uuid
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

import httpx
import pytest
import uvicorn

from expedition_service.back.app import create_app
from expedition_service.back.platform.config import Settings

TEAM_COUNT = int(os.getenv("LOAD_TEAM_COUNT", "40"))
INVITED_MEMBERS_PER_TEAM = int(os.getenv("LOAD_INVITED_MEMBERS_PER_TEAM", "20"))
CONFIRMED_MEMBERS_PER_TEAM = int(os.getenv("LOAD_CONFIRMED_MEMBERS_PER_TEAM", "15"))
HTTP_TIMEOUT_SECONDS = int(os.getenv("LOAD_HTTP_TIMEOUT_SECONDS", "30"))


@dataclass
class ScenarioMetrics:
    status_codes: Counter[int] = field(default_factory=Counter)
    request_latencies_ms: list[float] = field(default_factory=list)
    team_latencies_ms: list[float] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    completed_teams: int = 0

    @property
    def total_http_requests(self) -> int:
        return sum(self.status_codes.values())

    def record_error(self, message: str) -> None:
        self.errors.append(message)


@dataclass(frozen=True)
class ScenarioResult:
    scenario: str
    team_count: int
    invited_members_per_team: int
    confirmed_members_per_team: int
    elapsed_seconds: float
    metrics: ScenarioMetrics

    @property
    def rps(self) -> float:
        if self.elapsed_seconds == 0:
            return 0
        return self.metrics.total_http_requests / self.elapsed_seconds

    @property
    def p95_request_ms(self) -> float:
        return percentile(self.metrics.request_latencies_ms, 95)

    @property
    def p95_team_ms(self) -> float:
        return percentile(self.metrics.team_latencies_ms, 95)

    def summary(self) -> str:
        return (
            f"{self.scenario}: teams={self.team_count}, completed_teams={self.metrics.completed_teams}, "
            f"invited_per_team={self.invited_members_per_team}, confirmed_per_team={self.confirmed_members_per_team}, "
            f"http_requests={self.metrics.total_http_requests}, elapsed={self.elapsed_seconds:.2f}s, "
            f"rps={self.rps:.2f}, p95_request_ms={self.p95_request_ms:.2f}, "
            f"p95_team_ms={self.p95_team_ms:.2f}, statuses={dict(self.metrics.status_codes)}, "
            f"errors={len(self.metrics.errors)}"
        )


@pytest.fixture(scope="module")
def live_server(tmp_path_factory: pytest.TempPathFactory) -> str:
    port = get_free_port()
    db_path = tmp_path_factory.mktemp("load-db") / "load.db"
    settings = Settings(
        database_url=f"sqlite+aiosqlite:///{db_path.as_posix()}",
        jwt_secret_key="load-test-secret",
        jwt_algorithm="HS256",
        access_token_expire_minutes=120,
        websocket_cleanup_interval_seconds=30,
    )
    server = uvicorn.Server(
        uvicorn.Config(
            create_app(settings),
            host="127.0.0.1",
            port=port,
            log_level="warning",
            access_log=False,
        )
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{port}"
    wait_until_ready(base_url)

    yield base_url

    server.should_exit = True
    thread.join(timeout=5)


@pytest.mark.performance
def test_expedition_team_flow_rps(live_server: str):
    result = asyncio.run(
        run_team_flow_scenario(
            base_url=live_server,
            team_count=TEAM_COUNT,
            invited_members_per_team=INVITED_MEMBERS_PER_TEAM,
            confirmed_members_per_team=CONFIRMED_MEMBERS_PER_TEAM,
        )
    )

    print(result.summary())
    assert result.metrics.completed_teams == TEAM_COUNT, result.summary()
    assert not result.metrics.errors, "\n".join(result.metrics.errors[:20])
    assert result.metrics.status_codes == expected_status_codes(
        TEAM_COUNT,
        INVITED_MEMBERS_PER_TEAM,
        CONFIRMED_MEMBERS_PER_TEAM,
    )


async def run_team_flow_scenario(
    base_url: str,
    team_count: int,
    invited_members_per_team: int,
    confirmed_members_per_team: int,
) -> ScenarioResult:
    if confirmed_members_per_team > invited_members_per_team:
        raise ValueError("confirmed_members_per_team must be less than or equal to invited_members_per_team")

    metrics = ScenarioMetrics()
    limits = httpx.Limits(
        max_connections=team_count,
        max_keepalive_connections=team_count,
        keepalive_expiry=30,
    )
    started_at = time.perf_counter()
    run_id = uuid.uuid4().hex

    async with httpx.AsyncClient(limits=limits, timeout=HTTP_TIMEOUT_SECONDS) as client:
        await asyncio.gather(
            *(
                run_team_flow(
                    client=client,
                    base_url=base_url,
                    run_id=run_id,
                    team_index=team_index,
                    invited_members_per_team=invited_members_per_team,
                    confirmed_members_per_team=confirmed_members_per_team,
                    metrics=metrics,
                )
                for team_index in range(team_count)
            )
        )

    return ScenarioResult(
        scenario="expedition full team flow",
        team_count=team_count,
        invited_members_per_team=invited_members_per_team,
        confirmed_members_per_team=confirmed_members_per_team,
        elapsed_seconds=time.perf_counter() - started_at,
        metrics=metrics,
    )


async def run_team_flow(
    client: httpx.AsyncClient,
    base_url: str,
    run_id: str,
    team_index: int,
    invited_members_per_team: int,
    confirmed_members_per_team: int,
    metrics: ScenarioMetrics,
) -> None:
    team_started_at = time.perf_counter()
    chief_payload = await register_user(client, base_url, f"team-{run_id}-{team_index}-chief@example.com", "chief", metrics)
    if chief_payload is None:
        return

    expedition_payload = await create_expedition(
        client,
        base_url,
        chief_payload["access_token"],
        f"Team {team_index} Expedition",
        confirmed_members_per_team,
        metrics,
    )
    if expedition_payload is None:
        return

    members: list[dict] = []
    for member_index in range(invited_members_per_team):
        member_payload = await register_user(
            client,
            base_url,
            f"team-{run_id}-{team_index}-member-{member_index}@example.com",
            "member",
            metrics,
        )
        if member_payload is None:
            return
        members.append(member_payload)

    for member_payload in members:
        invite_response = await request(
            metrics,
            client.post(
                f"{base_url}/expeditions/{expedition_payload['id']}/members/invite",
                headers=auth_headers(chief_payload["access_token"]),
                json={"user_id": member_payload["user"]["id"]},
            ),
            expected_status=200,
            context=f"team={team_index} invite member={member_payload['user']['id']}",
        )
        if invite_response is None:
            return

    for member_payload in members[:confirmed_members_per_team]:
        confirm_response = await request(
            metrics,
            client.post(
                f"{base_url}/expeditions/{expedition_payload['id']}/members/confirm",
                headers=auth_headers(member_payload["access_token"]),
            ),
            expected_status=200,
            context=f"team={team_index} confirm member={member_payload['user']['id']}",
        )
        if confirm_response is None:
            return

    for status in ["ready", "active", "finished"]:
        status_response = await request(
            metrics,
            client.patch(
                f"{base_url}/expeditions/{expedition_payload['id']}/status",
                headers=auth_headers(chief_payload["access_token"]),
                json={"status": status},
            ),
            expected_status=200,
            context=f"team={team_index} set status={status}",
        )
        if status_response is None:
            return

    metrics.completed_teams += 1
    metrics.team_latencies_ms.append((time.perf_counter() - team_started_at) * 1000)


async def register_user(
    client: httpx.AsyncClient,
    base_url: str,
    email: str,
    role: str,
    metrics: ScenarioMetrics,
) -> dict | None:
    response = await request(
        metrics,
        client.post(
            f"{base_url}/auth/register",
            json={
                "email": email,
                "name": email.split("@", maxsplit=1)[0],
                "role": role,
            },
        ),
        expected_status=201,
        context=f"register email={email}",
    )
    if response is None:
        return None
    return response.json()


async def create_expedition(
    client: httpx.AsyncClient,
    base_url: str,
    token: str,
    title: str,
    capacity: int,
    metrics: ScenarioMetrics,
) -> dict | None:
    response = await request(
        metrics,
        client.post(
            f"{base_url}/expeditions",
            headers=auth_headers(token),
            json={
                "title": title,
                "description": None,
                "capacity": capacity,
            },
        ),
        expected_status=201,
        context=f"create expedition title={title}",
    )
    if response is None:
        return None
    return response.json()


async def request(
    metrics: ScenarioMetrics,
    response_awaitable,
    expected_status: int,
    context: str,
) -> httpx.Response | None:
    started_at = time.perf_counter()
    try:
        response = await response_awaitable
    except Exception as exc:
        metrics.record_error(f"{context}: {type(exc).__name__}: {exc}")
        return None
    finally:
        metrics.request_latencies_ms.append((time.perf_counter() - started_at) * 1000)

    metrics.status_codes[response.status_code] += 1
    if response.status_code != expected_status:
        metrics.record_error(f"{context}: expected={expected_status}, actual={response.status_code}, body={response.text}")
        return None
    return response


def expected_status_codes(
    team_count: int,
    invited_members_per_team: int,
    confirmed_members_per_team: int,
) -> Counter[int]:
    created_per_team = 1 + invited_members_per_team + 1
    ok_per_team = invited_members_per_team + confirmed_members_per_team + 3
    return Counter(
        {
            201: team_count * created_per_team,
            200: team_count * ok_per_team,
        }
    )


def percentile(values: list[float], percentile_value: int) -> float:
    if not values:
        return 0
    sorted_values = sorted(values)
    index = max(math.ceil(len(sorted_values) * percentile_value / 100) - 1, 0)
    return sorted_values[index]


def get_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def wait_until_ready(base_url: str) -> None:
    deadline = time.perf_counter() + 10
    with httpx.Client(timeout=1) as client:
        while time.perf_counter() < deadline:
            try:
                response = client.get(f"{base_url}/health")
                if response.status_code == 200:
                    return
            except httpx.HTTPError:
                time.sleep(0.05)
    raise RuntimeError("Load test server did not start in time")


def auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}
