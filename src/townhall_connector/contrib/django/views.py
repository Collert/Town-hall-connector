"""Endpoints the page's heartbeat script posts to. They forward to Town Hall with the API key."""
import logging

from django.core.cache import cache
from django.http import JsonResponse
from django.views.decorators.http import require_POST

from ...exceptions import AuthenticationError, InvalidRequest, NotFound, PermissionDenied, TownHallError
from . import conf

logger = logging.getLogger('townhall_connector')

# Problems a retry won't fix: the page stops sending heartbeats until it's reloaded
PERMANENT = (AuthenticationError, PermissionDenied, NotFound, InvalidRequest)


def _shift_json(shift):
    if shift is None:
        return None
    return {'active': shift.active, 'started': shift.started, 'minutes': shift.minutes,
            'start_time': shift.start_time.isoformat(), 'role': shift.role_name}


def _not_tracked():
    return JsonResponse({'tracking': False, 'stop': True})


@require_POST
def heartbeat(request):
    user = request.user
    if not conf.tracks(user):
        return _not_tracked()
    # Several open tabs each send heartbeats; Town Hall only needs about one a minute
    interval = max(10, int(conf.get('TOWNHALL_HEARTBEAT_INTERVAL')))
    if not cache.add(f'townhall_connector:beat:{user.pk}', True, interval // 2):
        return JsonResponse({'tracking': True, 'ok': True, 'throttled': True})
    try:
        shift = conf.client().heartbeat(conf.town_hall_id(user), conf.role_id(user))
    except TownHallError as exc:
        cache.delete(f'townhall_connector:beat:{user.pk}')
        permanent = isinstance(exc, PERMANENT)
        log = logger.error if permanent else logger.warning
        log('Town Hall heartbeat for user %s failed: %s', user.pk, exc)
        return JsonResponse({'tracking': True, 'ok': False, 'error': exc.code or 'error', 'stop': permanent})
    if shift and shift.started:
        logger.info('Town Hall shift started for user %s', user.pk)
    return JsonResponse({'tracking': True, 'ok': True, 'shift': _shift_json(shift)})


@require_POST
def end(request):
    """End the user's shift now (for an "End my shift" button)."""
    user = request.user
    if not conf.tracks(user):
        return _not_tracked()
    try:
        shift = conf.client().end_shift(conf.town_hall_id(user), conf.role_id(user))
    except TownHallError as exc:
        logger.warning('Ending the Town Hall shift for user %s failed: %s', user.pk, exc)
        return JsonResponse({'tracking': True, 'ok': False, 'error': exc.code or 'error'}, status=502)
    return JsonResponse({'tracking': True, 'ok': True, 'ended': shift is not None, 'shift': _shift_json(shift), 'stop': True})


def end_on_logout(sender, request, user, **kwargs):
    """user_logged_out receiver (connected in apps.py)."""
    if user is None or not conf.get('TOWNHALL_END_ON_LOGOUT') or not conf.tracks(user):
        return
    try:
        conf.client().end_shift(conf.town_hall_id(user), conf.role_id(user))
    except TownHallError as exc:  # never block signing out; the heartbeat timeout ends it anyway
        logger.warning('Ending the Town Hall shift for user %s at sign-out failed: %s', user.pk, exc)
