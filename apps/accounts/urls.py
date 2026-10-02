from django.urls import path
from . import views

app_name = "accounts"

urlpatterns = [
    path("login/", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),
    path("register/", views.register_view, name="register"),
    path("verify-email/<str:token>/", views.verify_email_view, name="verify_email"),
    path("profile/", views.profile_view, name="profile"),
    path("export-data/", views.export_data_view, name="export_data"),
]
