"""Settings for the Django integration. Each is read from Django settings first, then from an
environment variable with the same name."""
import os
from functools import lru_cache
from typing import Any, Optional

from django.conf import settings

from ...client import TownHall

DEFAULTS = {
    'TOWNHALL_URL': '',
    'TOWNHALL_API_KEY': '',
    'TOWNHALL_ROLE_ID': '',
    # How to get a user's Town Hall ID: an attribute path ("profile.town_hall_id") or a callable(user)
    'TOWNHALL_USER_ID': 'town_hall_id',
    # Only staff users (is_staff) are tracked unless this is False
    'TOWNHALL_STAFF_ONLY': True,
    # Seconds between heartbeats from the page
    'TOWNHALL_HEARTBEAT_INTERVAL': 60,
    # Minutes without mouse or keyboard activity after which the page stops sending heartbeats
    # (so the shift ends 5 minutes later). 0 means an open tab is enough.
    'TOWNHALL_IDLE_MINUTES': 0,
    # End the shift as soon as the user signs out
    'TOWNHALL_END_ON_LOGOUT': True,
    # Seconds to wait for Town Hall on each request
    'TOWNHALL_TIMEOUT': 5,
}

_FALSE = ('0', 'false', 'no', 'off', '')


def get(name: str) -> Any:
    if hasattr(settings, name):
        return getattr(settings, name)
    default = DEFAULTS[name]
    value = os.environ.get(name)
    if value is None:
        return default
    if isinstance(default, bool):
        return value.strip().lower() not in _FALSE
    if isinstance(default, int):
        try:
            return int(value)
        except ValueError:
            return default
    return value


def is_configured() -> bool:
    return bool(get('TOWNHALL_URL') and get('TOWNHALL_API_KEY') and get('TOWNHALL_ROLE_ID'))


@lru_cache(maxsize=4)
def _client(url: str, key: str, timeout: float) -> TownHall:
    return TownHall(url, key, timeout=timeout)


def client() -> TownHall:
    return _client(get('TOWNHALL_URL'), get('TOWNHALL_API_KEY'), float(get('TOWNHALL_TIMEOUT')))


def _resolve(obj: Any, path: str) -> Any:
    for part in path.split('.'):
        if obj is None:
            return None
        try:
            obj = getattr(obj, part)
        except Exception:  # e.g. RelatedObjectDoesNotExist for a missing one-to-one
            return None
    return obj() if callable(obj) else obj


def town_hall_id(user) -> Optional[str]:
    """The user's Town Hall ID, or None when they have none."""
    getter = get('TOWNHALL_USER_ID')
    value = getter(user) if callable(getter) else _resolve(user, str(getter))
    value = str(value).strip() if value is not None else ''
    return value or None


def role_id(user) -> Optional[str]:
    value = get('TOWNHALL_ROLE_ID')
    value = value(user) if callable(value) else value
    value = str(value).strip() if value is not None else ''
    return value or None


def tracks(user) -> bool:
    """Whether this user's time is sent to Town Hall."""
    if not is_configured() or not getattr(user, 'is_authenticated', False):
        return False
    if get('TOWNHALL_STAFF_ONLY') and not getattr(user, 'is_staff', False):
        return False
    return bool(town_hall_id(user) and role_id(user))
