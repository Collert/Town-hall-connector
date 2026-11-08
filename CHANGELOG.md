# Changelog

## 0.1.0

First release.

- `TownHall` client: `info()`, `start_shift()`, `heartbeat()`, `end_shift()`, `shift_status()` and the `working()` context manager.
- Django integration (`townhall_connector.contrib.django`): heartbeat endpoint, `{% townhall_heartbeat %}` script tag, shift ends on sign-out.
