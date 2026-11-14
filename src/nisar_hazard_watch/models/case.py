from datetime import date

from pydantic import ConfigDict, Field, JsonValue

from nisar_hazard_watch.constants.explorations import SCIENTIFIC_STATUS
from nisar_hazard_watch.models.base_model import CamelModel

Bounds = tuple[float, float, float, float]


class CaseGrid(CamelModel):
    crs: str
    bounds: Bounds
    shape: tuple[int, int]
    posting_m: tuple[float, float]


class CaseLayer(CamelModel):
    id: str
    url: str
    bounds: Bounds
    crs: str
    units: str
    colormap: str
    value_range: tuple[float, float] | None = None
    legend: dict[str, str] | None = None


class VisualizationComponent(CamelModel):
    band: str
    label: str
    polarizations: list[str]
    display_db: tuple[float, float]


class CaseVisualization(CamelModel):
    id: str
    recipe: str
    title: str
    dates: list[date]
    interpretation: str
    components: list[VisualizationComponent]
    colormap: str
    supported_cells: int
    total_cells: int
    bounds: Bounds
    crs: str
    url: str


class CaseSource(CamelModel):
    date: date
    title: str
    source: str
    pols: list[str] = Field(default_factory=list)


class CaseEvidence(CamelModel):
    """Only measured, honest fields; anything else the gateway sends is dropped."""

    model_config = ConfigDict(extra="ignore")

    state: str
    radar_support_cells: int | None = None
    threshold_cells: int | None = None
    threshold_policy: dict[str, JsonValue] | None = None
    independent_reference: dict[str, JsonValue] | None = None
    comparison: dict[str, JsonValue] | None = None
    sources: list[CaseSource] = Field(default_factory=list)
    pair: dict[str, JsonValue] | None = None
    common_support: dict[str, JsonValue] | None = None
    corrections_applied: list[str] | None = None


class CaseSummary(CamelModel):
    id: str
    title: str
    point: tuple[float, float]
    status: str
    baseline_dates: list[date]
    assessment_dates: list[date]


class CaseView(CaseSummary):
    grid: CaseGrid
    series_key: str
    evidence: CaseEvidence
    layers: list[CaseLayer]
    visualizations: list[CaseVisualization] = Field(default_factory=list)
    is_demo: bool
    limitations: list[str] = Field(default_factory=list)
    scientific_status: str = SCIENTIFIC_STATUS


class CasesView(CamelModel):
    cases: list[CaseSummary] = Field(default_factory=list)
