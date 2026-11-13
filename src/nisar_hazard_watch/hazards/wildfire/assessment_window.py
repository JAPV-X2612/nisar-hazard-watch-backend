from datetime import datetime

from nisar_hazard_watch.models.base_model import CamelModel
from nisar_hazard_watch.models.scene import ScenePlan


class AssessmentWindow(CamelModel):
    """From the last baseline pass to the target pass: where a fire could have changed the scene."""

    start: datetime
    end: datetime


def assessment_window(plan: ScenePlan) -> AssessmentWindow | None:
    passes = sorted({scene.acquired_at for scene in plan.scenes})
    if len(passes) < 2:
        return None
    return AssessmentWindow(start=passes[-2], end=passes[-1])
