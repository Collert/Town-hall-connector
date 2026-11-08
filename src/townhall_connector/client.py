"""A small client for the Town Hall API (``/api/v1/``).

>>> from townhall_connector import TownHall
>>> th = TownHall("https://townhall.example.org", "th_...")
>>> shift = th.start_shift("204816", 7)       # Town Hall ID, role ID
>>> th.heartbeat("204816", 7)                  # about once a minute while they work
>>> th.end_shift("204816", 7)

Only permanent roles can be used, and only by people assigned to them in Town Hall. If no
heartbeat arrives for five minutes, Town Hall ends the shift at the last heartbeat.
"""
import json
import os
import threading
import urllib.error
import urllib.parse
import urllib.request
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, Iterator, List, Optional, Union

from . import __version__
from .exceptions import TownHallConnectionError, TownHallError, error_for

Id = Union[str, int]


def _parse_time(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    return datetime.fromisoformat(value.replace('Z', '+00:00'))


@dataclass(frozen=True)
class Shift:
    """A shift as Town Hall reports it."""

    id: int
    town_hall_id: str
    person: str
    role_id: int
    role_name: Optional[str]
    start_time: datetime
    end_time: Optional[datetime]
    active: bool
    minutes: float
    impact_points: Optional[int]
    tracked_by_heartbeat: bool
    """False for shifts started somewhere else (e.g. a Town Hall kiosk): they're never timed out."""
    last_heartbeat: Optional[datetime]
    started: bool = False
    """True when this call started the shift."""
    raw: Dict[str, Any] = field(default_factory=dict, repr=False, compare=False)

    @classmethod
    def from_api(cls, data: Dict[str, Any], started: bool = False) -> 'Shift':
        role = data.get('role') or {}
        return cls(
            id=data['id'],
            town_hall_id=data.get('town_hall_id', ''),
            person=data.get('person', ''),
            role_id=role.get('id'),
            role_name=role.get('name'),
            start_time=_parse_time(data['start_time']),
            end_time=_parse_time(data.get('end_time')),
            active=data.get('active', data.get('end_time') is None),
            minutes=data.get('minutes', 0),
            impact_points=data.get('impact_points'),
            tracked_by_heartbeat=data.get('tracked_by_heartbeat', False),
            last_heartbeat=_parse_time(data.get('last_heartbeat')),
            started=started,
            raw=data,
        )


@dataclass(frozen=True)
class Role:
    id: int
    name: str


@dataclass(frozen=True)
class KeyInfo:
    """What :meth:`TownHall.info` returns: the key, the roles it may use and the heartbeat timing."""

    name: str
    prefix: str
    expires_at: Optional[datetime]
    roles: List[Role]
    heartbeat_interval_seconds: int
    heartbeat_timeout_seconds: int


class TownHall:
    """Talks to one Town Hall site with one API key.

    :param base_url: the site's address, e.g. ``https://townhall.example.org``.
    :param api_key: a key from Console > Organization > API (starts with ``th_``).
    :param timeout: seconds to wait for each request.
    """

    def __init__(self, base_url: str, api_key: str, timeout: float = 10.0, user_agent: Optional[str] = None):
        if not base_url:
            raise ValueError('base_url is required, e.g. "https://townhall.example.org"')
        if not api_key:
            raise ValueError('api_key is required (create one at Console > Organization > API)')
        base = base_url.strip().rstrip('/')
        if base.endswith('/api/v1'):
            base = base[:-len('/api/v1')]
        self.base_url = base
        self.api_url = base + '/api/v1/'
        self.api_key = api_key.strip()
        self.timeout = timeout
        self.user_agent = user_agent or f'town-hall-connector/{__version__}'

    def __repr__(self) -> str:
        return f'TownHall({self.base_url!r})'

    @classmethod
    def from_env(cls, **kwargs: Any) -> 'TownHall':
        """Build a client from the ``TOWNHALL_URL`` and ``TOWNHALL_API_KEY`` environment variables."""
        return cls(os.environ.get('TOWNHALL_URL', ''), os.environ.get('TOWNHALL_API_KEY', ''), **kwargs)

    # ------------------------------------------------------------------ requests

    def _request(self, method: str, path: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        url = self.api_url + path
        body = None
        headers = {
            'Authorization': f'Bearer {self.api_key}',
            'Accept': 'application/json',
            'User-Agent': self.user_agent,
        }
        if method == 'GET' and params:
            url += '?' + urllib.parse.urlencode(params)
        elif params is not None:
            body = json.dumps(params).encode()
            headers['Content-Type'] = 'application/json'
        request = urllib.request.Request(url, data=body, method=method, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                status, raw = response.status, response.read()
        except urllib.error.HTTPError as exc:
            status, raw = exc.code, exc.read()
        except (urllib.error.URLError, OSError) as exc:
            reason = getattr(exc, 'reason', exc)
            raise TownHallConnectionError(f'Could not reach Town Hall at {self.base_url}: {reason}') from exc
        try:
            data = json.loads(raw or b'{}')
        except ValueError:
            raise TownHallConnectionError(
                f'Town Hall answered HTTP {status} without JSON. Is {self.base_url} the right address?', status=status)
        if status >= 400:
            error = data.get('error') if isinstance(data, dict) else None
            if isinstance(error, dict):
                raise error_for(status, error.get('code'), error.get('message') or f'HTTP {status}')
            raise TownHallError(f'Town Hall answered HTTP {status}', status=status)
        return data

    @staticmethod
    def _who(town_hall_id: Id, role_id: Id) -> Dict[str, str]:
        return {'town_hall_id': str(town_hall_id).strip(), 'role_id': str(role_id).strip()}

    @staticmethod
    def _shift(data: Dict[str, Any]) -> Optional[Shift]:
        return Shift.from_api(data['shift'], started=data.get('started', False)) if data.get('shift') else None

    # ------------------------------------------------------------------ API

    def info(self) -> KeyInfo:
        """Check the connection and key. Lists the roles this key may start shifts in."""
        data = self._request('GET', '')
        key = data.get('key') or {}
        return KeyInfo(
            name=key.get('name', ''),
            prefix=key.get('prefix', ''),
            expires_at=_parse_time(key.get('expires_at')),
            roles=[Role(r['id'], r['name']) for r in data.get('roles', [])],
            heartbeat_interval_seconds=data.get('heartbeat_interval_seconds', 60),
            heartbeat_timeout_seconds=data.get('heartbeat_timeout_seconds', 300),
        )

    def start_shift(self, town_hall_id: Id, role_id: Id) -> Shift:
        """Start a shift for the person in this permanent role.

        Safe to call again: if they're already on a shift in this role, that shift is
        returned (with ``started=False``). Keep it alive with :meth:`heartbeat`.
        """
        return self._shift(self._request('POST', 'shifts/start', self._who(town_hall_id, role_id)))

    def heartbeat(self, town_hall_id: Id, role_id: Id, start: bool = True) -> Optional[Shift]:
        """Tell Town Hall the person is still working. Send about once a minute.

        With ``start=True`` (the default) a shift is started if they aren't on one, for example
        after the previous one timed out. With ``start=False`` it returns ``None`` instead.
        """
        params = {**self._who(town_hall_id, role_id), 'start': bool(start)}
        return self._shift(self._request('POST', 'shifts/heartbeat', params))

    def end_shift(self, town_hall_id: Id, role_id: Id) -> Optional[Shift]:
        """End the person's shift in this role now. Returns the ended shift, or ``None`` if there wasn't one."""
        return self._shift(self._request('POST', 'shifts/end', self._who(town_hall_id, role_id)))

    def shift_status(self, town_hall_id: Id, role_id: Id) -> Optional[Shift]:
        """The person's running shift in this role, or ``None``."""
        return self._shift(self._request('GET', 'shifts/status', self._who(town_hall_id, role_id)))

    @contextmanager
    def working(self, town_hall_id: Id, role_id: Id, interval: float = 60.0, end: bool = True) -> Iterator[Shift]:
        """Keep a shift running for the duration of a ``with`` block.

        Starts the shift, sends a heartbeat from a background thread every ``interval`` seconds,
        and ends the shift when the block exits (unless ``end=False``). Heartbeat failures are
        retried on the next beat; if they keep failing, Town Hall ends the shift by itself.

        >>> with th.working("204816", 7):
        ...     run_the_front_desk()
        """
        shift = self.start_shift(town_hall_id, role_id)
        stop = threading.Event()

        def beat() -> None:
            while not stop.wait(interval):
                try:
                    self.heartbeat(town_hall_id, role_id)
                except TownHallError:
                    pass

        thread = threading.Thread(target=beat, name='townhall-heartbeat', daemon=True)
        thread.start()
        try:
            yield shift
        finally:
            stop.set()
            thread.join(timeout=self.timeout + 1)
            if end:
                self.end_shift(town_hall_id, role_id)
