"""Tests for townhall_connector.contrib.django (skipped when Django isn't installed)."""
import unittest
from unittest.mock import MagicMock, patch

try:
    import django
    from django.conf import settings
except ImportError:  # pragma: no cover
    django = None

if django is not None and not settings.configured:
    settings.configure(
        DEBUG=True,
        SECRET_KEY='test',
        ROOT_URLCONF=__name__,
        INSTALLED_APPS=[
            'django.contrib.auth', 'django.contrib.contenttypes', 'django.contrib.sessions',
            'townhall_connector.contrib.django',
        ],
        MIDDLEWARE=[
            'django.contrib.sessions.middleware.SessionMiddleware',
            'django.middleware.csrf.CsrfViewMiddleware',
            'django.contrib.auth.middleware.AuthenticationMiddleware',
        ],
        DATABASES={'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': ':memory:'}},
        CACHES={'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}},
        STATIC_URL='/static/',
        TEMPLATES=[{'BACKEND': 'django.template.backends.django.DjangoTemplates', 'APP_DIRS': True}],
        TOWNHALL_URL='https://townhall.example.org',
        TOWNHALL_API_KEY='th_test',
        TOWNHALL_ROLE_ID=7,
        TOWNHALL_USER_ID='town_hall_id',
        USE_TZ=True,
    )
    django.setup()

if django is not None:
    from django.urls import include, path
    urlpatterns = [path('townhall/', include('townhall_connector.contrib.django.urls'))]


@unittest.skipIf(django is None, 'Django is not installed')
class DjangoIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from django.core.management import call_command
        call_command('migrate', verbosity=0)

    def setUp(self):
        from django.contrib.auth.models import User
        from django.core.cache import cache
        from django.test import Client
        cache.clear()
        User.objects.all().delete()
        self.staff = User.objects.create_user('librarian', password='pw', is_staff=True)
        User.town_hall_id = property(lambda u: '204816' if u.username == 'librarian' else '')
        self.client = Client()
        self.client.force_login(self.staff)
        self.fake = MagicMock()
        patcher = patch('townhall_connector.contrib.django.conf.client', return_value=self.fake)
        patcher.start()
        self.addCleanup(patcher.stop)

    def shift(self, started=False, active=True):
        from datetime import datetime, timezone
        from townhall_connector import Shift
        return Shift(id=1, town_hall_id='204816', person='Olena', role_id=7, role_name='Librarian',
                     start_time=datetime(2026, 11, 8, tzinfo=timezone.utc), end_time=None, active=active, minutes=3,
                     impact_points=None, tracked_by_heartbeat=True, last_heartbeat=None, started=started)

    def test_heartbeat_forwards_to_town_hall(self):
        self.fake.heartbeat.return_value = self.shift(started=True)
        response = self.client.post('/townhall/heartbeat/')
        self.assertEqual(response.json()['shift']['started'], True)
        self.fake.heartbeat.assert_called_once_with('204816', '7')

    def test_heartbeats_are_throttled(self):
        self.fake.heartbeat.return_value = self.shift()
        self.client.post('/townhall/heartbeat/')
        self.assertTrue(self.client.post('/townhall/heartbeat/').json()['throttled'])
        self.assertEqual(self.fake.heartbeat.call_count, 1)

    def test_untracked_users_are_told_to_stop(self):
        from django.contrib.auth.models import User
        other = User.objects.create_user('patron', password='pw', is_staff=True)
        self.client.force_login(other)
        self.assertTrue(self.client.post('/townhall/heartbeat/').json()['stop'])
        self.fake.heartbeat.assert_not_called()

    def test_non_staff_are_not_tracked_by_default(self):
        self.staff.is_staff = False
        self.staff.save()
        self.assertFalse(self.client.post('/townhall/heartbeat/').json()['tracking'])

    def test_permanent_errors_stop_the_page(self):
        from townhall_connector import PermissionDenied, TownHallConnectionError
        self.fake.heartbeat.side_effect = PermissionDenied('no', code='not_assigned', status=403)
        with self.assertLogs('townhall_connector', 'ERROR'):
            body = self.client.post('/townhall/heartbeat/').json()
        self.assertEqual((body['error'], body['stop']), ('not_assigned', True))
        self.fake.heartbeat.side_effect = TownHallConnectionError('down')
        with self.assertLogs('townhall_connector', 'WARNING'):
            self.assertFalse(self.client.post('/townhall/heartbeat/').json()['stop'])

    def test_heartbeat_needs_post_and_csrf(self):
        from django.test import Client
        self.assertEqual(self.client.get('/townhall/heartbeat/').status_code, 405)
        strict = Client(enforce_csrf_checks=True)
        strict.force_login(self.staff)
        self.assertEqual(strict.post('/townhall/heartbeat/').status_code, 403)

    def test_end_and_logout_end_the_shift(self):
        self.fake.end_shift.return_value = self.shift(active=False)
        self.assertTrue(self.client.post('/townhall/end/').json()['ended'])
        self.fake.end_shift.reset_mock()
        self.client.logout()
        self.fake.end_shift.assert_called_once_with('204816', '7')

    def test_template_tag(self):
        from django.template import Context, Template
        from django.test import RequestFactory
        request = RequestFactory().get('/')
        request.user = self.staff
        html = Template('{% load townhall %}{% townhall_heartbeat %}').render(Context({'request': request}))
        self.assertIn('/static/townhall_connector/heartbeat.js', html)
        self.assertIn('data-url="/townhall/heartbeat/"', html)
        self.assertNotIn('th_test', html)  # the key stays on the server
        from django.contrib.auth.models import AnonymousUser
        request.user = AnonymousUser()
        self.assertEqual(Template('{% load townhall %}{% townhall_heartbeat %}').render(Context({'request': request})), '')

    def test_attribute_path_and_callable(self):
        from django.test import override_settings
        from townhall_connector.contrib.django import conf
        self.staff.extra = type('X', (), {'th': ' 111222 '})()
        with override_settings(TOWNHALL_USER_ID='extra.th'):
            self.assertEqual(conf.town_hall_id(self.staff), '111222')
        with override_settings(TOWNHALL_USER_ID='missing.th'):
            self.assertIsNone(conf.town_hall_id(self.staff))
        with override_settings(TOWNHALL_USER_ID=lambda u: 333444):
            self.assertEqual(conf.town_hall_id(self.staff), '333444')


if __name__ == '__main__':
    unittest.main()
