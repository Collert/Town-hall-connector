"""Python connector for the Town Hall volunteer-management API.

Start and end shifts in Town Hall's permanent roles from your own application, and keep
them alive with heartbeats. See https://github.com/Collert/Town-hall-connector.
"""
__version__ = '0.1.0'

from .client import KeyInfo, Role, Shift, TownHall  # noqa: E402
from .exceptions import (  # noqa: E402
    AuthenticationError,
    InvalidRequest,
    NotFound,
    PermissionDenied,
    ShiftConflict,
    TownHallConnectionError,
    TownHallError,
)

__all__ = [
    'TownHall', 'Shift', 'Role', 'KeyInfo',
    'TownHallError', 'TownHallConnectionError', 'AuthenticationError', 'PermissionDenied',
    'NotFound', 'InvalidRequest', 'ShiftConflict',
    '__version__',
]
