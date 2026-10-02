from django.shortcuts import render
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
    return render(request, "core/imprint.html", {"title": f"Impressum – {settings_obj.name}"})

def privacy_view(request):
    """Datenschutzerklärung mit Inhalten aus ClubSettings."""
    settings_obj = ClubSettings.get_settings()
    return render(request, "core/privacy.html", {"title": f"Datenschutzerklärung – {settings_obj.name}"})

def styleguide_view(request):
    """Styleguide-Seite mit Farbtokens, Typografie und UI-Komponenten."""
    return render(request, "core/styleguide.html", {"title": "Design Styleguide & Tokens"})
