from django.urls import path
from . import views
from . import recovery_views

app_name = "accounts"

urlpatterns = [
    path("recover/", recovery_views.account_recovery_view, name="account_recovery"),
    path("recover/sent/", recovery_views.account_recovery_done_view, name="account_recovery_done"),
    path("access/<uidb64>/<token>/", recovery_views.AccountAccessConfirmView.as_view(), name="account_access_confirm"),
    path("login/", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),
    path("register/", views.register_view, name="register"),
    path("verify-email/<str:token>/", views.verify_email_view, name="verify_email"),
    path("profile/", views.profile_view, name="profile"),
    path("export-data/", views.export_data_view, name="export_data"),
]
