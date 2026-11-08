"""Errors raised by the Town Hall client.

Every error Town Hall reports has a machine-readable ``code`` (for example ``not_assigned``)
and the HTTP ``status`` it came with. Network problems raise :class:`TownHallConnectionError`.
"""
from typing import Optional


class TownHallError(Exception):
    """Base class for every error this package raises."""

    def __init__(self, message: str, code: Optional[str] = None, status: Optional[int] = None):
        super().__init__(message)
        self.message = message
        self.code = code
        self.status = status

    def __str__(self) -> str:
        return f'{self.message} ({self.code})' if self.code else self.message


class TownHallConnectionError(TownHallError):
    """Town Hall couldn't be reached, timed out, or didn't answer with JSON."""


class AuthenticationError(TownHallError):
    """The API key is missing, wrong, revoked or expired (HTTP 401)."""


class PermissionDenied(TownHallError):
    """The key may not use this role, or the person isn't assigned to it (HTTP 403).

    ``code`` is ``role_not_allowed`` or ``not_assigned``.
    """


class NotFound(TownHallError):
    """No active person has that Town Hall ID, or no role has that ID (HTTP 404).

    ``code`` is ``person_not_found`` or ``role_not_found``.
    """


class InvalidRequest(TownHallError):
    """A parameter is missing or wrong, e.g. the role isn't permanent (HTTP 400)."""


class ShiftConflict(TownHallError):
    """The person is already on a shift in another role (HTTP 409, ``other_shift_in_progress``)."""


_BY_STATUS = {
    400: InvalidRequest,
    401: AuthenticationError,
    403: PermissionDenied,
    404: NotFound,
    409: ShiftConflict,
}


def error_for(status: int, code: Optional[str], message: str) -> TownHallError:
    return _BY_STATUS.get(status, TownHallError)(message, code=code, status=status)
