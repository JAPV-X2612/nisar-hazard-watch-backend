from pathlib import Path

import pytest

from nisar_hazard_watch.config.settings import Settings
from nisar_hazard_watch.constants.environments import Environment

SQLITE_MEMORY_URL = "sqlite+aiosqlite://"


@pytest.fixture
def settings(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Settings:
    monkeypatch.chdir(tmp_path)  # no .env file is picked up
    return Settings(environment=Environment.TEST, database_url=SQLITE_MEMORY_URL)
