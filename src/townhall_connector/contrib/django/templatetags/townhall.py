from django import template
from django.middleware.csrf import get_token
from django.templatetags.static import static
from django.urls import reverse
from django.utils.html import format_html

from .. import conf

register = template.Library()


@register.simple_tag(takes_context=True)
def townhall_heartbeat(context):
    """The heartbeat script, for users whose time is tracked; nothing for everyone else."""
    request = context.get('request')
    user = getattr(request, 'user', None)
    if request is None or not conf.tracks(user):
        return ''
    return format_html(
        '<script src="{}" defer data-url="{}" data-end-url="{}" data-csrf="{}" data-interval="{}" data-idle="{}"></script>',
        static('townhall_connector/heartbeat.js'),
        reverse('townhall_connector:heartbeat'),
        reverse('townhall_connector:end'),
        get_token(request),
        max(10, int(conf.get('TOWNHALL_HEARTBEAT_INTERVAL'))),
        max(0, int(conf.get('TOWNHALL_IDLE_MINUTES'))),
    )


@register.simple_tag(takes_context=True)
def townhall_tracked(context):
    """True when the signed-in user's time is sent to Town Hall (for showing a notice)."""
    request = context.get('request')
    return bool(request is not None and conf.tracks(getattr(request, 'user', None)))
