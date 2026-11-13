from nisar_hazard_watch.models.base_model import CamelModel


class InsarSummary(CamelModel):
    """What one wrapped GUNW pair measured at the point; displacement is never reported."""

    pair_id: str
    status: str
    reason: str | None = None
    polarization: str | None = None
    median_coherence: float | None = None
    coherence_threshold: float
    coherent_cells: int | None = None
    phase_cells: int | None = None
    window_cells: int | None = None
    point_coherence: float | None = None
    point_wrapped_phase_rad: float | None = None
    phase_reference: str | None = None
    corrections_applied: list[str]
    los_displacement_cm: None = None
