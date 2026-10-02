from django.urls import path
from . import views

app_name = "billing"

urlpatterns = [
    path("dashboard/", views.cashier_dashboard_view, name="dashboard"),
    path("charge/<int:charge_id>/pay/", views.record_payment_view, name="record_payment"),
    path("run-fees/", views.run_fees_view, name="run_fees"),
    path("export-csv/", views.export_csv_view, name="export_csv"),
]
