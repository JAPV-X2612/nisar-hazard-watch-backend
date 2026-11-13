from nisar_hazard_watch.models.base_model import CamelModel


class PlaceView(CamelModel):
    id: str
    name: str
    display_name: str
    kind: str
    # [longitude, latitude]
    point: tuple[float, float]
    # [west, south, east, north]; absent when the provider has no box for the place
    bbox: tuple[float, float, float, float] | None = None
    importance: float = 0.0


class PlacesView(CamelModel):
    places: list[PlaceView]
    attribution: str
