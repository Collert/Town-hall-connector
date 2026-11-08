import json
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

from townhall_connector import (
    AuthenticationError,
    InvalidRequest,
    NotFound,
    PermissionDenied,
    ShiftConflict,
    TownHall,
    TownHallConnectionError,
)

KEY = 'th_test'


def shift_json(active=True, started_role=7):
    return {
        'id': 1, 'town_hall_id': '204816', 'person': 'Olena', 'role': {'id': started_role, 'name': 'Librarian'},
        'start_time': '2026-11-08T09:00:00+00:00', 'end_time': None if active else '2026-11-08T11:00:00+00:00',
        'active': active, 'minutes': 12.0, 'impact_points': None if active else 20,
        'tracked_by_heartbeat': active, 'last_heartbeat': '2026-11-08T09:12:00+00:00' if active else None,
    }


class FakeTownHall(BaseHTTPRequestHandler):
    """Answers like Town Hall's /api/v1/ and records what it was sent."""

    calls = []
    errors = {}  # path -> (status, code)
    html = False

    def log_message(self, *args):
        pass

    def _send(self, status, body):
        raw = json.dumps(body).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _handle(self, method):
        url = urlparse(self.path)
        if method == 'GET':
            params = {k: v[0] for k, v in parse_qs(url.query).items()}
        else:
            params = json.loads(self.rfile.read(int(self.headers.get('Content-Length', 0))) or b'{}')
        FakeTownHall.calls.append((method, url.path, params, dict(self.headers)))
        if FakeTownHall.html:
            raw = b'<html>not found</html>'
            self.send_response(404)
            self.send_header('Content-Length', str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)
            return
        if self.headers.get('Authorization') != f'Bearer {KEY}':
            return self._send(401, {'error': {'code': 'invalid_api_key', 'message': 'Bad key.'}})
        if url.path in FakeTownHall.errors:
            status, code = FakeTownHall.errors[url.path]
            return self._send(status, {'error': {'code': code, 'message': 'Nope.'}})
        path = url.path
        if path == '/api/v1/':
            return self._send(200, {'api_version': 1, 'key': {'name': 'Library', 'prefix': 'th_abc', 'expires_at': None},
                                    'roles': [{'id': 7, 'name': 'Librarian'}],
                                    'heartbeat_interval_seconds': 60, 'heartbeat_timeout_seconds': 300})
        if path == '/api/v1/shifts/start':
            return self._send(201, {'started': True, 'shift': shift_json()})
        if path == '/api/v1/shifts/heartbeat':
            if params.get('start') is False:
                return self._send(200, {'started': False, 'shift': None})
            return self._send(200, {'started': False, 'shift': shift_json()})
        if path == '/api/v1/shifts/end':
            return self._send(200, {'ended': True, 'shift': shift_json(active=False)})
        if path == '/api/v1/shifts/status':
            return self._send(200, {'shift': shift_json()})
        return self._send(404, {'error': {'code': 'not_found', 'message': 'No route.'}})

    def do_GET(self):
        self._handle('GET')

    def do_POST(self):
        self._handle('POST')


class ClientTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = HTTPServer(('127.0.0.1', 0), FakeTownHall)
        cls.url = f'http://127.0.0.1:{cls.server.server_port}'
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()

    def setUp(self):
        FakeTownHall.calls = []
        FakeTownHall.errors = {}
        FakeTownHall.html = False
        self.th = TownHall(self.url + '/', KEY)

    def test_needs_url_and_key(self):
        with self.assertRaises(ValueError):
            TownHall('', KEY)
        with self.assertRaises(ValueError):
            TownHall(self.url, '')

    def test_accepts_api_url(self):
        self.assertEqual(TownHall(self.url + '/api/v1/', KEY).api_url, self.url + '/api/v1/')

    def test_info(self):
        info = self.th.info()
        self.assertEqual(info.name, 'Library')
        self.assertEqual(info.roles[0].id, 7)
        self.assertEqual(info.heartbeat_timeout_seconds, 300)

    def test_start_shift_sends_ids_and_key(self):
        shift = self.th.start_shift(204816, 7)
        method, path, params, headers = FakeTownHall.calls[-1]
        self.assertEqual((method, path), ('POST', '/api/v1/shifts/start'))
        self.assertEqual(params, {'town_hall_id': '204816', 'role_id': '7'})
        self.assertTrue(headers['User-Agent'].startswith('town-hall-connector/'))
        self.assertTrue(shift.started)
        self.assertTrue(shift.active)
        self.assertEqual(shift.role_id, 7)
        self.assertEqual(shift.start_time.hour, 9)

    def test_heartbeat(self):
        self.assertFalse(self.th.heartbeat('204816', 7).started)
        self.assertIs(FakeTownHall.calls[-1][2]['start'], True)
        self.assertIsNone(self.th.heartbeat('204816', 7, start=False))

    def test_end_and_status(self):
        ended = self.th.end_shift('204816', 7)
        self.assertFalse(ended.active)
        self.assertEqual(ended.impact_points, 20)
        self.assertTrue(self.th.shift_status('204816', 7).active)
        self.assertEqual(FakeTownHall.calls[-1][:2], ('GET', '/api/v1/shifts/status'))

    def test_errors_map_to_exceptions(self):
        with self.assertRaises(AuthenticationError):
            TownHall(self.url, 'th_wrong').start_shift('1', 1)
        for status, code, exc in [(403, 'not_assigned', PermissionDenied), (404, 'person_not_found', NotFound),
                                  (400, 'role_not_permanent', InvalidRequest), (409, 'other_shift_in_progress', ShiftConflict)]:
            FakeTownHall.errors = {'/api/v1/shifts/start': (status, code)}
            with self.assertRaises(exc) as caught:
                self.th.start_shift('204816', 7)
            self.assertEqual(caught.exception.code, code)
            self.assertEqual(caught.exception.status, status)

    def test_non_json_answer(self):
        FakeTownHall.html = True
        with self.assertRaises(TownHallConnectionError):
            self.th.info()

    def test_unreachable(self):
        with self.assertRaises(TownHallConnectionError):
            TownHall('http://127.0.0.1:9', KEY, timeout=1).info()

    def test_working_beats_and_ends(self):
        with self.th.working('204816', 7, interval=0.05) as shift:
            self.assertTrue(shift.active)
            time.sleep(0.2)
        paths = [call[1] for call in FakeTownHall.calls]
        self.assertEqual(paths[0], '/api/v1/shifts/start')
        self.assertIn('/api/v1/shifts/heartbeat', paths)
        self.assertEqual(paths[-1], '/api/v1/shifts/end')

    def test_from_env(self):
        import os
        from unittest.mock import patch
        with patch.dict(os.environ, {'TOWNHALL_URL': self.url, 'TOWNHALL_API_KEY': KEY}):
            self.assertEqual(TownHall.from_env().info().name, 'Library')


if __name__ == '__main__':
    unittest.main()
