from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from apps.core.deployment_views import health_view, media_view

urlpatterns = [
    path("healthz/", health_view, name="health"),
    path("media/<path:path>", media_view, name="media"),
    path("admin/", admin.site.urls),
    path("", include("apps.core.urls")),
    path("accounts/", include("apps.accounts.urls")),
    path("members/", include("apps.members.urls")),
    path("billing/", include("apps.billing.urls")),
    path("news/", include("apps.news.urls")),
    path("courts/", include("apps.courts.urls")),
    path("tournaments/", include("apps.tournaments.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
