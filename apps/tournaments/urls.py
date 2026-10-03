from django.urls import path
from . import views

app_name = "tournaments"

urlpatterns = [
    path("", views.tournament_list_view, name="list"),
    path("ehrentafel/", views.honor_roll_view, name="honor_roll"),
    path("<slug:slug>/", views.tournament_detail_view, name="detail"),
    path("competition/<int:comp_id>/register/", views.register_view, name="register"),
    path(
        "match/<int:match_id>/result/",
        views.manage_match_result_view,
        name="match_result",
    ),
    path(
        "entry/<int:entry_id>/confirm/",
        views.confirm_partner_view,
        name="confirm_partner",
    ),
    path("entry/<int:entry_id>/withdraw/", views.withdraw_entry_view, name="withdraw"),
    path(
        "match/<int:match_id>/schedule/",
        views.schedule_match_view,
        name="schedule_match",
    ),
]
