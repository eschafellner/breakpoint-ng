from django.urls import path
from . import views

app_name = "courts"

urlpatterns = [
    path("calendar/", views.calendar_view, name="calendar"),
    path("book/", views.book_slot_view, name="book"),
    path("booking/<int:booking_id>/cancel/", views.cancel_booking_view, name="cancel"),
    path("blockings/", views.blockings_view, name="blockings"),
]
