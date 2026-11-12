ASYNC_POSTGRES_PREFIX = "postgresql+asyncpg://"
PLAIN_POSTGRES_PREFIXES = ("postgresql://", "postgres://")


def to_async_database_url(url: str) -> str:
    for prefix in PLAIN_POSTGRES_PREFIXES:
        if url.startswith(prefix):
            return ASYNC_POSTGRES_PREFIX + url[len(prefix) :]
    return url
