from django.urls import path

from . import views

app_name = 'townhall_connector'

urlpatterns = [
    path('heartbeat/', views.heartbeat, name='heartbeat'),
    path('end/', views.end, name='end'),
]
