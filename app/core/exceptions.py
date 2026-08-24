class DomainError(Exception):
    """Base exception for expected business rule violations."""

    status_code = 400

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


class NotFoundError(DomainError):
    status_code = 404


class ConflictError(DomainError):
    status_code = 409


class ForbiddenError(DomainError):
    status_code = 403


class InsufficientStockError(DomainError):
    status_code = 422
