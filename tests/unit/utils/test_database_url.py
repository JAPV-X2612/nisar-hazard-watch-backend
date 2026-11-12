import pytest

from nisar_hazard_watch.utils.database_url import to_async_database_url

ASYNC_URL = "postgresql+asyncpg://user:secret@host:5432/db"


@pytest.mark.parametrize(
    "url",
    ["postgresql://user:secret@host:5432/db", "postgres://user:secret@host:5432/db"],
)
def test_plain_postgres_urls_get_the_asyncpg_driver(url: str) -> None:
    # Arrange / Act
    result = to_async_database_url(url)

    # Assert
    assert result == ASYNC_URL


@pytest.mark.parametrize("url", [ASYNC_URL, "sqlite+aiosqlite://"])
def test_urls_with_an_explicit_driver_are_left_alone(url: str) -> None:
    # Arrange / Act
    result = to_async_database_url(url)

    # Assert
    assert result == url
