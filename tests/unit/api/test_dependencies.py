import pytest
from starlette.requests import Request

from nisar_hazard_watch.api.dependencies import client_key
from nisar_hazard_watch.constants.routes import UNKNOWN_CLIENT

PEER = "10.1.1.1"
CLIENT = "203.0.113.7"
SPOOFED = "192.0.2.1"
FORWARDED_FOR = b"x-forwarded-for"


def _request(forwarded: str | None, peer: str | None = PEER) -> Request:
    headers = [(FORWARDED_FOR, forwarded.encode())] if forwarded is not None else []
    return Request(
        scope={
            "type": "http",
            "headers": headers,
            "client": (peer, 40000) if peer else None,
        }
    )


@pytest.mark.parametrize(
    argnames=("forwarded", "hops", "expected"),
    argvalues=[
        (CLIENT, 1, CLIENT),
        (f"{SPOOFED}, {CLIENT}", 1, CLIENT),
        (f"{SPOOFED}, {CLIENT}, 10.0.0.9", 2, CLIENT),
        (f" {CLIENT} ,", 1, CLIENT),
        (None, 1, PEER),
        ("", 1, PEER),
        (CLIENT, 2, PEER),
        (CLIENT, 0, PEER),
    ],
    ids=[
        "single-hop",
        "spoofed-prefix-is-ignored",
        "two-hops",
        "whitespace-and-trailing-comma",
        "no-header",
        "empty-header",
        "fewer-addresses-than-hops",
        "no-trusted-proxy",
    ],
)
def test_the_client_is_the_address_the_trusted_proxy_saw(
    forwarded: str | None, hops: int, expected: str
) -> None:
    # Arrange
    request = _request(forwarded=forwarded)

    # Act
    key = client_key(request=request, trusted_hops=hops)

    # Assert
    assert key == expected


def test_a_request_without_a_peer_or_header_is_one_unknown_client() -> None:
    # Arrange
    request = _request(forwarded=None, peer=None)

    # Act
    key = client_key(request=request, trusted_hops=1)

    # Assert
    assert key == UNKNOWN_CLIENT
