class FireDataUnavailableError(Exception):
    """The fire detections could not be read; never shown to API clients as an error."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason
