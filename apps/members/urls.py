from django.urls import path
from . import views

app_name = "members"

urlpatterns = [
    path("directory/", views.directory_view, name="directory"),
    path("applications/", views.applications_list_view, name="applications"),
    path("applications/<int:pk>/approve/", views.approve_application_view, name="approve_application"),
    path("applications/<int:pk>/reject/", views.reject_application_view, name="reject_application"),
    path("import-csv/", views.csv_import_view, name="csv_import"),
]
