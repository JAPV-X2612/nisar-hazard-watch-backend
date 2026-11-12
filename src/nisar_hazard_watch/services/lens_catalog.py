from nisar_hazard_watch.constants.explorations import OPTICAL_LENSES, Lens
from nisar_hazard_watch.constants.sar import MIN_IMAGES
from nisar_hazard_watch.models.exploration import LensInfo

_DESCRIPTIONS = {
    Lens.FLOOD_WETLAND: (
        "Flood and wetland",
        "Dual-polarization darkening and brightening of the latest scene against the area's own "
        "earlier measurements, diagnostic of open-water and wet-surface change.",
    ),
    Lens.VEGETATION_DISTURBANCE: (
        "Vegetation disturbance",
        "Departures of cross-polarized backscatter from the observed baseline, diagnostic of "
        "canopy or biomass change.",
    ),
    Lens.WILDFIRE: (
        "Wildfire",
        "Cross-polarization decline history against a three-date baseline, diagnostic of burn-"
        "related change; fire context is not provided.",
    ),
    Lens.AGRICULTURE: (
        "Agriculture",
        "Backscatter step and population comparisons across the measured dates, descriptive of "
        "field-scale change.",
    ),
}


def list_lenses() -> list[LensInfo]:
    return [
        LensInfo(
            id=lens,
            title=title,
            description=description,
            optical_evidence=lens in OPTICAL_LENSES,
            minimum_dates=MIN_IMAGES,
        )
        for lens, (title, description) in _DESCRIPTIONS.items()
    ]
