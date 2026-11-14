from datetime import date

from pydantic import ConfigDict, Field, JsonValue

from nisar_hazard_watch.constants.cases import CaseStatus
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
    title: str
    kind: str
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


class CaseComparisonCounts(CamelModel):
    """Agreement with an independent optical product, never ground-truth accuracy."""

    model_config = ConfigDict(extra="ignore")

    comparison_kind: str
    scored_pixels: int
    true_positive_proxy_pixels: int | None = None
    false_positive_proxy_pixels: int | None = None
    false_negative_proxy_pixels: int | None = None
    true_negative_proxy_pixels: int | None = None
    precision_against_proxy: float | None = None
    recall_against_proxy: float | None = None
    intersection_over_union_against_proxy: float | None = None
    reference_stable_nonwater_radar_flag_rate: float | None = None
    reference_stable_open_water_radar_flag_rate: float | None = None
    reference_water_loss_radar_flag_rate: float | None = None
    unscored_reference_or_mixed_pixels: int | None = None
    radar_comparator: str | None = None


class CaseComparison(CaseComparisonCounts):
    last_baseline_sensitivity: CaseComparisonCounts | None = None


class CasePair(CamelModel):
    model_config = ConfigDict(extra="ignore")

    source_id: str
    reference_date: date
    secondary_date: date
    interval_days: int
    selected_component: int | None = None
    coherent_component_fraction: float | None = None
    ionosphere_filled_fraction: float | None = None
    source_sha256: str | None = None
    common_spatial_support_median_coherence: float | None = None
    common_spatial_support_coherence_histogram: list[int] | None = None
    finite_cells: int | None = None
    total_cells: int | None = None
    median_coherence: float | None = None


class RadarSignature(CamelModel):
    state: str
    signature_cells: int
    supported_cells: int
    fraction: float


class RegionalContext(CamelModel):
    """A public bulletin that frames the case; context, not a measurement of ours."""

    source: str
    date: date
    url: str
    scope: str


class CaseEvidence(CamelModel):
    """Only measured, honest fields; anything else the gateway sends is dropped."""

    model_config = ConfigDict(extra="ignore")

    state: str
    radar_support_cells: int | None = None
    threshold_cells: int | None = None
    threshold_policy: dict[str, JsonValue] | None = None
    independent_reference: dict[str, JsonValue] | None = None
    comparison: CaseComparison | None = None
    sources: list[CaseSource] = Field(default_factory=list)
    pair: CasePair | None = None
    common_support: dict[str, JsonValue] | None = None
    corrections_applied: list[str] | None = None
    lens_id: str | None = None
    radar_comparator: str | None = None
    radar_signatures: dict[str, RadarSignature] | None = None
    signature_policy: dict[str, JsonValue] | None = None
    regional_context: RegionalContext | None = None


class CaseSummary(CamelModel):
    id: str
    title: str
    point: tuple[float, float]
    status: str = Field(
        description="Known values: " + ", ".join(CaseStatus) + ". New values are relayed as sent."
    )
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
