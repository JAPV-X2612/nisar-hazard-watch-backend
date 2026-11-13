from datetime import date

from nisar_hazard_watch.constants.sar import Direction
from nisar_hazard_watch.models.base_model import CamelModel


class InsarPair(CamelModel):
    pair_id: str
    series_key: str
    track: int
    direction: Direction
    frame: int
    reference_date: date
    secondary_date: date
    temporal_baseline_days: int
