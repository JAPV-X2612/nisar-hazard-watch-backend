import json
from collections.abc import Callable, Iterator
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from nisar_hazard_watch.api.app import create_app
from nisar_hazard_watch.config.settings import Settings
from nisar_hazard_watch.constants.errors import ReasonCode
from nisar_hazard_watch.constants.places import GEOCODER_USER_AGENT, PLACES_ATTRIBUTION

FIXTURE = Path(__file__).parents[4] / "fixtures" / "nominatim_qadirabad.json"
URL = "/api/v1/places"
EDGE_HOP = "100.64.0.1"


@pytest.fixture
def start_api(make_settings: Callable[..., Settings]) -> Iterator[Callable[..., TestClient]]:
    clients: list[TestClient] = []

    def start(
        geocoder: httpx.MockTransport | None = None, **setting_overrides: object
    ) -> TestClient:
        settings = make_settings(**{"rate_limit_per_minute": 1000, **setting_overrides})
        transport = geocoder or httpx.MockTransport(
            lambda request: httpx.Response(status_code=200, json=json.loads(FIXTURE.read_text()))
        )
        client = TestClient(create_app(settings=settings, geocoder_transport=transport))
        client.__enter__()
        clients.append(client)
        return client

    yield start
    for client in clients:
        client.__exit__(None, None, None)


def test_a_search_answers_the_places_in_camel_case_with_attribution(
    start_api: Callable[..., TestClient],
) -> None:
    # Arrange
    client = start_api()

    # Act
    response = client.get(url=URL, params={"q": "Qadirabad"})

    # Assert
    body = response.json()
    assert response.status_code == 200
    assert body["attribution"] == PLACES_ATTRIBUTION
    first = body["places"][0]
    assert first["displayName"].startswith("Qadirabad, Phalia Tehsil")
    assert first["point"] == [73.5025289, 32.297263]
    assert first["bbox"] == [73.4625289, 32.257263, 73.5425289, 32.337263]


def test_the_provider_is_called_with_the_projects_user_agent_and_the_chosen_limit(
    start_api: Callable[..., TestClient], make_settings: Callable[..., Settings]
) -> None:
    # Arrange
    sent: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(request)
        return httpx.Response(status_code=200, json=[])

    client = start_api(geocoder=httpx.MockTransport(handler))

    # Act
    client.get(url=URL, params={"q": "Qadirabad", "limit": 3})

    # Assert
    assert sent[0].headers["user-agent"] == GEOCODER_USER_AGENT.format(
        version=make_settings().version
    )
    assert sent[0].url.params["limit"] == "3"


def test_no_match_is_a_200_with_an_empty_list(start_api: Callable[..., TestClient]) -> None:
    # Arrange
    client = start_api(
        geocoder=httpx.MockTransport(lambda request: httpx.Response(status_code=200, json=[]))
    )

    # Act
    response = client.get(url=URL, params={"q": "Nowhereville"})

    # Assert
    assert response.status_code == 200
    assert response.json()["places"] == []


@pytest.mark.parametrize(
    argnames="params",
    argvalues=[{}, {"q": ""}, {"q": "x"}, {"q": "a" * 201}, {"q": "Qadirabad", "limit": 0}],
    ids=["missing", "empty", "one-character", "too-long", "limit-zero"],
)
def test_a_bad_search_is_a_422_problem(
    start_api: Callable[..., TestClient], params: dict[str, str | int]
) -> None:
    # Arrange
    client = start_api()

    # Act
    response = client.get(url=URL, params=params)

    # Assert
    assert response.status_code == 422
    assert response.headers["content-type"].startswith("application/problem+json")


def test_a_failing_provider_is_a_502_with_its_reason(
    start_api: Callable[..., TestClient],
) -> None:
    # Arrange
    client = start_api(
        geocoder=httpx.MockTransport(lambda request: httpx.Response(status_code=503))
    )

    # Act
    response = client.get(url=URL, params={"q": "Qadirabad"})

    # Assert
    assert response.status_code == 502
    assert response.json()["reasonCode"] == ReasonCode.UPSTREAM_GEOCODER_ERROR


def test_each_client_is_limited_on_its_own_and_gets_a_429(
    start_api: Callable[..., TestClient],
) -> None:
    # Arrange
    client = start_api(rate_limit_per_minute=1)
    first_client = {"X-Forwarded-For": f"203.0.113.7, {EDGE_HOP}"}
    other_client = {"X-Forwarded-For": f"198.51.100.9, {EDGE_HOP}"}

    # Act
    allowed = client.get(url=URL, params={"q": "Qadirabad"}, headers=first_client)
    limited = client.get(url=URL, params={"q": "Qadirabad"}, headers=first_client)
    other = client.get(url=URL, params={"q": "Qadirabad"}, headers=other_client)

    # Assert
    assert allowed.status_code == 200
    assert limited.status_code == 429
    assert other.status_code == 200
