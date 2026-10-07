import os
from django.conf import settings
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render
from django.template.loader import render_to_string
from django.utils import timezone
from django.views.decorators.http import require_GET
from .models import ClubSettings


def home_view(request):
    """Startseite mit Hero, Kennzahlen, neuesten News und Platz-CTA."""
    settings_obj = ClubSettings.get_settings()

    # We will import selectors from news, courts, tournaments conditionally or safely
    news_articles = []
    try:
        from apps.news.selectors import get_published_articles

        news_articles = get_published_articles(user=request.user)[:5]
    except Exception:
        pass

    context = {
        "title": f"{settings_obj.name} – Startseite",
        "articles": news_articles,
    }
    return render(request, "core/home.html", context)


def imprint_view(request):
    """Impressum-Seite mit Inhalten aus ClubSettings."""
    settings_obj = ClubSettings.get_settings()
    return render(
        request, "core/imprint.html", {"title": f"Impressum – {settings_obj.name}"}
    )


def privacy_view(request):
    """Datenschutzerklärung mit Inhalten aus ClubSettings."""
    settings_obj = ClubSettings.get_settings()
    return render(
        request,
        "core/privacy.html",
        {"title": f"Datenschutzerklärung – {settings_obj.name}"},
    )


def styleguide_view(request):
    """Styleguide-Seite mit Farbtokens, Typografie und UI-Komponenten."""
    return render(
        request, "core/styleguide.html", {"title": "Design Styleguide & Tokens"}
    )


@require_GET
def manifest_view(request):
    """Dynamic Web App Manifest generated from ClubSettings."""
    settings_obj = ClubSettings.get_settings()
    club_name = settings_obj.name if settings_obj and settings_obj.name else "Breakpoint-NG"
    short_name = (
        settings_obj.short_name
        if settings_obj and settings_obj.short_name
        else (club_name[:12] if len(club_name) > 12 else club_name)
    )
    tagline = (
        settings_obj.tagline
        if settings_obj and settings_obj.tagline
        else "Tennisverein CMS & Buchungssystem"
    )

    # Breakpoint-Dunkelgrün: #1E3B2F
    court_green = "#1E3B2F"

    manifest_data = {
        "name": club_name,
        "short_name": short_name,
        "description": tagline,
        "start_url": "/",
        "scope": "/",
        "display": "standalone",
        "orientation": "portrait-primary",
        "background_color": court_green,
        "theme_color": court_green,
        "lang": "de",
        "categories": ["sports", "fitness"],
        "icons": [
            {
                "src": "/static/icons/icon-192x192.png",
                "sizes": "192x192",
                "type": "image/png",
                "purpose": "any",
            },
            {
                "src": "/static/icons/icon-512x512.png",
                "sizes": "512x512",
                "type": "image/png",
                "purpose": "any",
            },
            {
                "src": "/static/icons/icon-maskable-512x512.png",
                "sizes": "512x512",
                "type": "image/png",
                "purpose": "maskable",
            },
            {
                "src": "/static/icons/icon.svg",
                "sizes": "any",
                "type": "image/svg+xml",
                "purpose": "any",
            },
        ],
        "shortcuts": [
            {
                "name": "Platz buchen",
                "short_name": "Buchen",
                "description": "Plätze einsehen und reservieren",
                "url": "/courts/calendar/",
                "icons": [{"src": "/static/icons/icon-192x192.png", "sizes": "192x192"}],
            },
            {
                "name": "Aktuelle News",
                "short_name": "News",
                "description": "Neuigkeiten des Vereins",
                "url": "/news/",
                "icons": [{"src": "/static/icons/icon-192x192.png", "sizes": "192x192"}],
            },
            {
                "name": "Mein Profil",
                "short_name": "Profil",
                "description": "Eigene Buchungen und Mitgliedsdaten",
                "url": "/accounts/profile/",
                "icons": [{"src": "/static/icons/icon-192x192.png", "sizes": "192x192"}],
            },
        ],
    }

    response = JsonResponse(
        manifest_data, json_dumps_params={"ensure_ascii": False, "indent": 2}
    )
    response["Content-Type"] = "application/manifest+json"
    response["Cache-Control"] = "public, max-age=3600"
    return response


@require_GET
def service_worker_view(request):
    """Serve sw.js with root scope permission header and no-cache control."""
    sw_file_path = os.path.join(settings.BASE_DIR, "static", "js", "sw.js")
    try:
        with open(sw_file_path, "r", encoding="utf-8") as f:
            content = f.read()
    except OSError:
        content = "// Service worker file missing"

    response = HttpResponse(content, content_type="application/javascript; charset=utf-8")
    response["Service-Worker-Allowed"] = "/"
    response["Cache-Control"] = "no-cache, no-store, must-revalidate"
    return response


def offline_view(request):
    """Offline emergency page when device has no network connection."""
    settings_obj = ClubSettings.get_settings()
    # No request/context processors: never put session or role data in this page.
    content = render_to_string("core/offline.html", {
        "club_settings": settings_obj, "updated_at": timezone.localtime(),
    })
    response = HttpResponse(content)
    response["X-Breakpoint-Offline"] = "public"
    response["Cache-Control"] = "public, max-age=0, must-revalidate"
    return response
