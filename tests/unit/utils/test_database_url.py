import pytest

from nisar_hazard_watch.utils.database_url import to_async_database_url

ASYNC_URL = "postgresql+asyncpg://user:secret@host:5432/db"
SQLITE_URL = "sqlite+aiosqlite://"


@pytest.mark.parametrize(
    argnames="url",
    argvalues=[
        "postgresql://user:secret@host:5432/db",
        "postgres://user:secret@host:5432/db",
    ],
)
def test_plain_postgres_urls_get_the_asyncpg_driver(url: str) -> None:
    # Arrange
    plain_url = url

    # Act
    result = to_async_database_url(url=plain_url)

    # Assert
    assert result == ASYNC_URL


@pytest.mark.parametrize(argnames="url", argvalues=[ASYNC_URL, SQLITE_URL])
def test_urls_with_an_explicit_driver_are_left_alone(url: str) -> None:
    # Arrange
    explicit_url = url

    # Act
    result = to_async_database_url(url=explicit_url)

    # Assert
    assert result == explicit_url
