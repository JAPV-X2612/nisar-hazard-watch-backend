from datetime import datetime

from pydantic import Field

from nisar_hazard_watch.constants.sar import Configuration, Direction, Maturity, PlanStatus
from nisar_hazard_watch.models.base_model import CamelModel
from nisar_hazard_watch.models.geometry import Aoi


class SceneIdentity(CamelModel):
    granule_id: str
    acquired_at: datetime
    cycle: int
    track: int
    direction: Direction
    frame: int
    mode: str
    polarizations: list[str]
    maturity: Maturity
    configuration: Configuration
    crid: str
    version: int
    url: str


class Scene(SceneIdentity):
    coverage: float


class SceneGroup(CamelModel):
    track: int
    direction: Direction
    frame: int


class ScenePlan(CamelModel):
    status: PlanStatus
    aoi: Aoi
    window_start: datetime
    window_end: datetime
    group: SceneGroup | None = None
    scenes: list[Scene] = Field(default_factory=list)
    maturity_mixed: bool = False
    notes: list[str] = Field(default_factory=list)
