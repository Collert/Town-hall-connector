"""Django integration: clock staff in to Town Hall while they have your site open.

1. ``INSTALLED_APPS += ['townhall_connector.contrib.django']``
2. ``urlpatterns += [path('townhall/', include('townhall_connector.contrib.django.urls'))]``
3. In a template every tracked page uses (e.g. ``admin/base_site.html``)::

       {% load townhall %}
       {% block extrahead %}{{ block.super }}{% townhall_heartbeat %}{% endblock %}

4. Settings (or environment variables of the same name): ``TOWNHALL_URL``,
   ``TOWNHALL_API_KEY``, ``TOWNHALL_ROLE_ID``, and ``TOWNHALL_USER_ID`` (how to find a user's
   Town Hall ID: an attribute path such as ``"profile.town_hall_id"``, or a callable).

The page's script posts to your site about once a minute; your server forwards that to Town
Hall with the API key, so the key never reaches the browser. The first heartbeat starts the
shift. When the heartbeats stop for five minutes (every tab closed, computer asleep, network
gone), Town Hall ends the shift at the last one. Signing out ends it right away.
"""
