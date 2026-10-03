from django.core.paginator import Paginator
from django.http import Http404
from django.shortcuts import render
from .selectors import get_published_articles, get_article_by_slug, get_categories


def article_list_view(request):
    """Archivseite mit Paginierung und Filter nach Kategorie (N-6)."""
    category_slug = request.GET.get("kategorie")
    articles_qs = get_published_articles(user=request.user, category_slug=category_slug)
    categories = get_categories(user=request.user)

    paginator = Paginator(articles_qs, 9)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    return render(
        request,
        "news/list.html",
        {
            "title": "Neuigkeiten & Berichte",
            "page_obj": page_obj,
            "categories": categories,
            "current_category": category_slug,
        },
    )


def article_detail_view(request, slug):
    """Detailansicht eines Artikels (404 bei Berechtigungs-/Veröffentlichungskonflikt)."""
    article = get_article_by_slug(slug, user=request.user)
    if not article:
        raise Http404("Artikel nicht gefunden oder keine Zugriffsberechtigung.")

    return render(
        request,
        "news/detail.html",
        {
            "title": article.title,
            "article": article,
        },
    )
