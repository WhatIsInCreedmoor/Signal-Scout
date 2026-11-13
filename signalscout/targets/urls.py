from django.urls import path, re_path
from django.views.static import serve
from django.conf import settings
import os
from . import views

urlpatterns = [
    path('', views.map_view, name='map_view'),
    path('api/definitions/', views.get_definitions, name='get_definitions'),
    path('api/ingest/', views.ingest_target, name='ingest_target'),
    path('api/targets/', views.get_targets, name='get_targets'),
    path('api/heartbeat/', views.heartbeat, name='heartbeat'),
    path('firmware/<path:path>', views.serve_firmware, name='serve_firmware'),
]
