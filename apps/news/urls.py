from django.urls import path
from . import views
from .feeds import LatestNewsFeed

app_name = "news"

urlpatterns = [
    path("", views.article_list_view, name="list"),
    path("feed/", LatestNewsFeed(), name="feed"),
    path("<slug:slug>/", views.article_detail_view, name="detail"),
]
