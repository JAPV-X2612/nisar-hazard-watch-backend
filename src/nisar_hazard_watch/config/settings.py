import json
from functools import lru_cache
from typing import Annotated

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

from nisar_hazard_watch import __version__
from nisar_hazard_watch.constants.environments import Environment
from nisar_hazard_watch.utils.database_url import to_async_database_url

DEFAULT_DATABASE_URL = "postgresql+asyncpg://postgres:postgres@localhost:5432/nisar_hazard_watch"
DEFAULT_CORS_ORIGINS = ["http://localhost:5173"]
DEFAULT_CMR_HEALTH_URL = "https://cmr.earthdata.nasa.gov/search/health"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    service_name: str = "nisar-hazard-watch-backend"
    version: str = __version__
    environment: Environment = Environment.LOCAL
    log_level: str = "INFO"
    database_url: str = DEFAULT_DATABASE_URL
    cors_allowed_origins: Annotated[list[str], NoDecode] = DEFAULT_CORS_ORIGINS
    cmr_health_url: str = DEFAULT_CMR_HEALTH_URL
    cmr_health_timeout_seconds: float = 5.0
    database_health_timeout_seconds: float = 3.0
    earthdata_token: SecretStr | None = None
    modal_token_id: SecretStr | None = None
    modal_token_secret: SecretStr | None = None

    @field_validator("database_url")
    @classmethod
    def _use_the_async_driver(cls, value: str) -> str:
        return to_async_database_url(value)

    @field_validator("cors_allowed_origins", mode="before")
    @classmethod
    def _split_origins(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        text = value.strip()
        if text.startswith("["):
            return json.loads(text)
        return [origin.strip() for origin in text.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
