class ServiceError(Exception):
    """A business-rule violation with an HTTP status and a user-facing message."""

    def __init__(self, status_code: int, message: str):
        super().__init__(message)
        self.status_code = status_code
        self.message = message
