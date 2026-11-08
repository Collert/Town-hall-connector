# Town Hall Connector

A small Python library for the [Town Hall](https://github.com/Collert/town_hall) volunteer-management API.
Use it to clock people in and out of **permanent roles** from your own application, for example a
library's admin site that starts a librarian's shift when they open it and ends it when they leave.

- No dependencies for the client (standard library only).
- Optional Django add-on: a heartbeat script for your pages, so shifts start and end on their own.

```bash
pip install town-hall-connector
```

## What you need from Town Hall

1. **An API key.** In Town Hall, open **Console > Organization > API** and create a key. Pick the
   permanent roles it may use (or leave them all unticked for every permanent role). The key is
   shown once, so copy it straight into your application's environment.
2. **The role ID.** The same page lists every permanent role with its ID.
3. **Each person's Town Hall ID.** That's their 6-digit kiosk ID, shown on their page in the
   Volunteer Pool. They must be **assigned** to the role (Volunteer Pool > person > Roles).

## Quick start

```python
from townhall_connector import TownHall

th = TownHall("https://townhall.example.org", "th_...")   # or TownHall.from_env()

shift = th.start_shift("204816", 7)    # Town Hall ID, role ID
print(shift.started, shift.start_time)

th.heartbeat("204816", 7)              # about once a minute while they work

ended = th.end_shift("204816", 7)
print(ended.minutes, ended.impact_points)
```

`TownHall.from_env()` reads `TOWNHALL_URL` and `TOWNHALL_API_KEY`.

### How shifts work

- **`start_shift(town_hall_id, role_id)`** starts a shift. Calling it again while the shift is
  running returns the same shift with `started=False`, so it is safe to call on every page load.
- **`heartbeat(town_hall_id, role_id)`** says "still working". Send one about every minute.
  If the person has no running shift (for example the last one timed out), it starts a new one;
  pass `start=False` to only refresh an existing shift.
- **If no heartbeat arrives for 5 minutes, Town Hall ends the shift by itself**, at the time of
  the last heartbeat, so the idle minutes aren't counted. A one-minute network blip is harmless.
- **`end_shift(town_hall_id, role_id)`** ends it now. Returns `None` if there was no shift.
- **`shift_status(town_hall_id, role_id)`** returns the running shift, or `None`.
- **`info()`** checks the key and lists the roles it may use.

Shifts started somewhere else, such as at a Town Hall kiosk, are reported (with
`tracked_by_heartbeat=False`) but never timed out.

### Scripts and desktop apps

`working()` keeps a shift alive from a background thread for as long as a `with` block runs:

```python
with th.working("204816", 7):
    run_the_front_desk()
```

### Errors

Every error is a `TownHallError` with a `code` and HTTP `status`:

| Exception | When | `code` |
| --- | --- | --- |
| `AuthenticationError` | The key is wrong, revoked or expired | `invalid_api_key` |
| `PermissionDenied` | The key may not use the role, or the person isn't assigned to it | `role_not_allowed`, `not_assigned` |
| `NotFound` | No active person has that Town Hall ID, or no role has that ID | `person_not_found`, `role_not_found` |
| `InvalidRequest` | A parameter is missing, or the role isn't permanent | `missing_parameter`, `role_not_permanent` |
| `ShiftConflict` | The person is already on a shift in another role | `other_shift_in_progress` |
| `TownHallConnectionError` | Town Hall couldn't be reached or didn't answer with JSON | |

## Django: clock staff in while they use your site

The add-on puts a small script on your pages. While a staff member has a page open, the script
posts to **your** server once a minute, and your server forwards it to Town Hall with the API key
(the key never reaches the browser). The first heartbeat starts their shift. When they close every
tab, their computer sleeps or the network drops for 5 minutes, Town Hall ends the shift at the last
heartbeat. Signing out ends it right away.

```bash
pip install "town-hall-connector[django]"
```

**settings.py**

```python
INSTALLED_APPS = [
    # ...
    "django.contrib.staticfiles",
    "townhall_connector.contrib.django",
]

# Each of these can also be an environment variable with the same name.
TOWNHALL_URL = "https://townhall.example.org"
TOWNHALL_API_KEY = "th_..."
TOWNHALL_ROLE_ID = 7
# How to find a user's Town Hall ID: an attribute path, or a callable taking the user.
TOWNHALL_USER_ID = "profile.town_hall_id"
```

**urls.py**

```python
urlpatterns = [
    # ...
    path("townhall/", include("townhall_connector.contrib.django.urls")),
]
```

**A template on every tracked page**, e.g. `templates/admin/base_site.html` for the Django admin:

```django
{% extends "admin/base.html" %}
{% load townhall %}

{% block extrahead %}{{ block.super }}{% townhall_heartbeat %}{% endblock %}
```

The tag renders nothing for people who aren't tracked: anonymous visitors, non-staff users, and
staff without a Town Hall ID.

### Settings

| Setting | Default | |
| --- | --- | --- |
| `TOWNHALL_URL` | | Town Hall's address |
| `TOWNHALL_API_KEY` | | API key from Console > Organization > API |
| `TOWNHALL_ROLE_ID` | | The permanent role to clock people into (or a callable taking the user) |
| `TOWNHALL_USER_ID` | `"town_hall_id"` | Attribute path on the user (`"profile.town_hall_id"`) or a callable |
| `TOWNHALL_STAFF_ONLY` | `True` | Track only users with `is_staff` |
| `TOWNHALL_HEARTBEAT_INTERVAL` | `60` | Seconds between heartbeats |
| `TOWNHALL_IDLE_MINUTES` | `0` | Stop sending heartbeats after this many minutes without mouse or keyboard activity (0: an open tab is enough) |
| `TOWNHALL_END_ON_LOGOUT` | `True` | End the shift when the user signs out |
| `TOWNHALL_TIMEOUT` | `5` | Seconds to wait for Town Hall |

### In the browser

`window.TownHallHeartbeat.endShift()` ends the shift now (for an "End my shift" button), and every
answer is dispatched as a `townhall:heartbeat` event on `window`:

```js
window.addEventListener("townhall:heartbeat", (e) => console.log(e.detail));
```

Problems are logged to the `townhall_connector` logger. Errors a retry can't fix (wrong key,
person not assigned to the role) stop the script until the page is reloaded.

## The HTTP API

If you aren't using Python, call the API directly. Send the key as `Authorization: Bearer <key>`.
Bodies may be JSON or form-encoded.

| Method | Path | Parameters |
| --- | --- | --- |
| `GET` | `/api/v1/` | |
| `POST` | `/api/v1/shifts/start` | `town_hall_id`, `role_id` |
| `POST` | `/api/v1/shifts/heartbeat` | `town_hall_id`, `role_id`, `start` (default `true`) |
| `POST` | `/api/v1/shifts/end` | `town_hall_id`, `role_id` |
| `GET` | `/api/v1/shifts/status` | `town_hall_id`, `role_id` |

Errors look like `{"error": {"code": "not_assigned", "message": "..."}}`.

## Development

```bash
pip install -e ".[django]" pytest
pytest
```

## License

MIT
