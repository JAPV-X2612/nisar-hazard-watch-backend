from datetime import date

from pydantic import Field

from nisar_hazard_watch.models.base_model import CamelModel
from nisar_hazard_watch.models.insar_pair import InsarPair


class InsarPairsView(CamelModel):
    window_start: date
    window_end: date
    pairs: list[InsarPair] = Field(default_factory=list)
