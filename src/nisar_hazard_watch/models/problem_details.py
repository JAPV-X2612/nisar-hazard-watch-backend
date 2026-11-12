from nisar_hazard_watch.constants.errors import ReasonCode
from nisar_hazard_watch.models.base_model import CamelModel


class ProblemDetails(CamelModel):
    type: str = "about:blank"
    title: str
    status: int
    detail: str
    reason_code: ReasonCode
    request_id: str | None = None
