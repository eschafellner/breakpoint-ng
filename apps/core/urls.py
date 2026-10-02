from django.urls import path
from . import views

app_name = "core"

urlpatterns = [
    path("", views.home_view, name="home"),
    path("impressum/", views.imprint_view, name="imprint"),
    path("datenschutz/", views.privacy_view, name="privacy"),
    path("styleguide/", views.styleguide_view, name="styleguide"),
]
