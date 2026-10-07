from django.urls import path
from . import views

app_name = "core"

urlpatterns = [
    path("", views.home_view, name="home"),
    path("impressum/", views.imprint_view, name="imprint"),
    path("datenschutz/", views.privacy_view, name="privacy"),
    path("styleguide/", views.styleguide_view, name="styleguide"),
    # PWA endpoints
    path("manifest.webmanifest", views.manifest_view, name="manifest"),
    path("manifest.json", views.manifest_view, name="manifest_json"),
    path("sw.js", views.service_worker_view, name="service_worker"),
    path("offline/", views.offline_view, name="offline"),
]
