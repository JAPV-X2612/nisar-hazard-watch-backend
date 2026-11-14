from typing import Any

from pydantic import Field

from nisar_hazard_watch.models.base_model import CamelModel


class PublishedAsset(CamelModel):
    name: str
    url: str
    media_type: str
    bytes: int
    sha256: str


class SciencePreview(CamelModel):
    name: str
    title: str
    interpretation: str
    legend: dict[str, Any] | None = None


class RadarComponent(CamelModel):
    band: str
    label: str
    polarizations: list[str]
    display_db: tuple[float, float]


class RadarVisualization(CamelModel):
    id: str
    recipe: str
    title: str
    dates: list[str]
    interpretation: str
    components: list[RadarComponent]
    colormap: str
    supported_cells: int
    total_cells: int
    grid: dict[str, Any]
    bounds: tuple[float, float, float, float]
    crs: str
    png: str
    cog: str | None = None


class RegionalAnalysis(CamelModel):
    point: tuple[float, float] | None = None
    observations: dict[str, Any] = Field(default_factory=dict)
    capabilities: dict[str, Any] = Field(default_factory=dict)
    series: dict[str, list[dict[str, str | float | None]]] = Field(default_factory=dict)
    limitations: list[str] = Field(default_factory=list)


class ScienceProducts(CamelModel):
    visualizations: list[RadarVisualization] = Field(default_factory=list)
    assets: list[PublishedAsset] = Field(default_factory=list)
    previews: list[SciencePreview] = Field(default_factory=list)
    analysis: RegionalAnalysis | None = None
