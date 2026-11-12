from nisar_hazard_watch.constants.errors import ReasonCode


class AppError(Exception):
    status_code: int = 500
    reason_code: ReasonCode = ReasonCode.INTERNAL_ERROR
    title: str = "Internal Server Error"

    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail
