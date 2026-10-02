"""Readiness and authorized media delivery for the production reverse proxy."""

from pathlib import Path, PurePosixPath
from urllib.parse import quote

from django.conf import settings
from django.db import DatabaseError, connection
from django.db.models import Q
from django.http import FileResponse, Http404, HttpResponse, JsonResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_safe

from apps.accounts.models import User
from apps.news.models import Article
from apps.news.selectors import get_article_by_slug

from .models import ClubSettings


@never_cache
@require_safe
def health_view(request):
    """Report readiness without rendering templates or exposing configuration."""
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
    except DatabaseError:
        return JsonResponse({"status": "unavailable"}, status=503)
    return JsonResponse({"status": "ok"})


IMAGE_TYPES = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".avif": "image/avif",
    ".bmp": "image/bmp",
    ".tif": "image/tiff",
    ".tiff": "image/tiff",
    ".ico": "image/x-icon",
}


@never_cache
@require_safe
def media_view(request, path):
    """Authorize existing image records before Nginx transfers their bytes."""
    relative = PurePosixPath(path)
    if (
        relative.is_absolute()
        or ".." in relative.parts
        or "\\" in path
        or any(ord(char) < 32 for char in path)
        or relative.suffix.lower() not in IMAGE_TYPES
    ):
        raise Http404

    permitted = False
    if path.startswith("club/"):
        permitted = ClubSettings.objects.filter(logo=path).exists()
    elif path.startswith("news/"):
        articles = Article.objects.filter(
            Q(cover_image=path)
            | Q(gallery_images__image=path)
            | Q(gallery_images__image_medium=path)
            | Q(gallery_images__image_thumb=path)
        ).distinct()
        permitted = any(
            get_article_by_slug(article.slug, user=request.user) is not None
            for article in articles
        )
    elif path.startswith("avatars/") and request.user.is_authenticated:
        owners = User.objects.filter(avatar=path)
        if not request.user.is_staff:
            owners = owners.filter(pk=request.user.pk)
        permitted = owners.exists()

    if not permitted:
        raise Http404

    root = Path(settings.MEDIA_ROOT).resolve()
    target = (root / path).resolve()
    if not target.is_relative_to(root) or not target.is_file():
        raise Http404

    content_type = IMAGE_TYPES[relative.suffix.lower()]
    if getattr(settings, "NGINX_MEDIA_ACCEL", False):
        response = HttpResponse(content_type=content_type)
        response["X-Accel-Redirect"] = "/_protected_media/" + quote(path, safe="/")
    else:
        response = FileResponse(target.open("rb"), content_type=content_type)
    response["X-Content-Type-Options"] = "nosniff"
    return response
