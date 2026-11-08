from django.apps import AppConfig


class TownHallConnectorConfig(AppConfig):
    name = 'townhall_connector.contrib.django'
    label = 'townhall_connector'
    verbose_name = 'Town Hall connector'

    def ready(self):
        from django.contrib.auth.signals import user_logged_out

        from .views import end_on_logout
        user_logged_out.connect(end_on_logout, dispatch_uid='townhall_connector_end_on_logout')
