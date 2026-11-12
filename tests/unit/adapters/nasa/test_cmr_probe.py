import json
from collections.abc import AsyncIterator
from typing import Protocol

import httpx
import pytest

from nisar_hazard_watch.adapters.nasa.cmr_probe import (
    UNEXPECTED_RESPONSE_DETAIL,
    UNREACHABLE_DETAIL,
    CmrProbe,
)
from nisar_hazard_watch.constants.health import DependencyName, DependencyState
from tests.constants import CMR_HEALTH_URL

HEALTHY_BODY = {"echo": {"ok?": True}, "indexer": {"ok?": True}, "metadata-db": {"ok?": True}}
DEGRADED_BODY = {"echo": {"ok?": True}, "indexer": {"ok?": False}, "metadata-db": {"ok?": False}}
UNEXPECTED_BODIES = [{}, {"error": "maintenance"}, {"echo": {"status": "bad"}}, [1], None]


class ProbeFactory(Protocol):
    def __call__(self, transport: httpx.MockTransport) -> CmrProbe: ...


@pytest.fixture
async def make_probe() -> AsyncIterator[ProbeFactory]:
    clients: list[httpx.AsyncClient] = []

    def build(transport: httpx.MockTransport) -> CmrProbe:
        client = httpx.AsyncClient(transport=transport)
        clients.append(client)
        return CmrProbe(client=client, health_url=CMR_HEALTH_URL)

    yield build
    for client in clients:
        await client.aclose()


def _answering(status: int, body: object) -> httpx.MockTransport:
    content = json.dumps(body).encode()
    return httpx.MockTransport(lambda request: httpx.Response(status_code=status, content=content))


async def test_a_healthy_cmr_is_ok(make_probe: ProbeFactory) -> None:
    # Arrange
    probe = make_probe(transport=_answering(status=200, body=HEALTHY_BODY))

    # Act
    report = await probe.check()

    # Assert
    assert probe.name is DependencyName.CMR
    assert report.state is DependencyState.OK
    assert report.critical is False
    assert report.latency_ms is not None


async def test_failing_components_are_listed_in_the_detail(make_probe: ProbeFactory) -> None:
    # Arrange
    probe = make_probe(transport=_answering(status=200, body=DEGRADED_BODY))

    # Act
    report = await probe.check()

    # Assert
    assert report.state is DependencyState.DOWN
    assert report.detail == "failing components: indexer, metadata-db"


@pytest.mark.parametrize(argnames="body", argvalues=UNEXPECTED_BODIES)
async def test_a_payload_without_recognised_components_is_not_reported_as_healthy(
    make_probe: ProbeFactory, body: object
) -> None:
    # Arrange
    probe = make_probe(transport=_answering(status=200, body=body))

    # Act
    report = await probe.check()

    # Assert
    assert report.state is DependencyState.DOWN
    assert report.detail == UNEXPECTED_RESPONSE_DETAIL


async def test_an_http_error_is_down(make_probe: ProbeFactory) -> None:
    # Arrange
    probe = make_probe(transport=_answering(status=503, body={}))

    # Act
    report = await probe.check()

    # Assert
    assert report.state is DependencyState.DOWN
    assert report.detail == UNREACHABLE_DETAIL


async def test_a_network_failure_is_down(make_probe: ProbeFactory) -> None:
    # Arrange
    def fail(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no route", request=request)

    probe = make_probe(transport=httpx.MockTransport(fail))

    # Act
    report = await probe.check()

    # Assert
    assert report.state is DependencyState.DOWN
    assert report.detail == UNREACHABLE_DETAIL
