import httpx

from nisar_hazard_watch.adapters.nasa.cmr_probe import CmrProbe
from nisar_hazard_watch.constants.health import DependencyName, DependencyState

HEALTH_URL = "https://cmr.example.test/search/health"
HEALTHY_BODY = {"echo": {"ok?": True}, "indexer": {"ok?": True}, "metadata-db": {"ok?": True}}
DEGRADED_BODY = {"echo": {"ok?": True}, "indexer": {"ok?": False}, "metadata-db": {"ok?": False}}


def _probe(transport: httpx.MockTransport) -> CmrProbe:
    return CmrProbe(client=httpx.AsyncClient(transport=transport), health_url=HEALTH_URL)


def _answering(status: int, body: object) -> httpx.MockTransport:
    return httpx.MockTransport(lambda request: httpx.Response(status, json=body))


async def test_a_healthy_cmr_is_ok() -> None:
    # Arrange
    probe = _probe(_answering(200, HEALTHY_BODY))

    # Act
    report = await probe.check()

    # Assert
    assert probe.name is DependencyName.CMR
    assert report.state is DependencyState.OK
    assert report.critical is False
    assert report.latency_ms is not None


async def test_failing_components_are_listed_in_the_detail() -> None:
    # Arrange
    probe = _probe(_answering(200, DEGRADED_BODY))

    # Act
    report = await probe.check()

    # Assert
    assert report.state is DependencyState.DOWN
    assert report.detail == "failing components: indexer, metadata-db"


async def test_an_http_error_is_down() -> None:
    # Arrange
    probe = _probe(_answering(503, {}))

    # Act
    report = await probe.check()

    # Assert
    assert report.state is DependencyState.DOWN
    assert report.detail == "NASA CMR is unreachable"


async def test_a_network_failure_is_down() -> None:
    # Arrange
    def fail(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no route", request=request)

    probe = _probe(httpx.MockTransport(fail))

    # Act
    report = await probe.check()

    # Assert
    assert report.state is DependencyState.DOWN
