"""Verify actual HTTP delivery through Nginx, including the CSS MIME type."""

import argparse
import os
from pathlib import Path
import sys
from urllib.error import HTTPError
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def check_response(base_url, path, expected_type, expected_body=None):
    request = Request(base_url.rstrip("/") + path, headers={"Cache-Control": "no-cache"})
    with urlopen(request, timeout=10) as response:
        body = response.read()
        content_type = response.headers.get_content_type()
        if response.status != 200 or content_type != expected_type or not body:
            raise RuntimeError(f"{path}: erwartete HTTP 200 mit {expected_type} und Inhalt")
        if expected_body is not None and body != expected_body:
            raise RuntimeError(f"{path}: ausgelieferter Inhalt entspricht nicht dem neuen Image")
        print(f"OK: {path} (200, {content_type})")
        return body


def check_not_found(base_url, path):
    try:
        with urlopen(base_url.rstrip("/") + path, timeout=10):
            pass
    except HTTPError as error:
        if error.code == 404:
            print(f"OK: {path} (404)")
            return
        raise
    raise RuntimeError(f"{path}: erwartete HTTP 404")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://nginx")
    args = parser.parse_args()

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.prod")
    import django

    django.setup()
    from django.contrib.staticfiles.storage import staticfiles_storage
    from django.utils import timezone
    from apps.core.models import ClubSettings
    from apps.news.models import Article

    check_response(args.base_url, "/healthz/", "application/json")
    for name in ("css/styles.css", "admin/css/base.css"):
        with staticfiles_storage.open(name, "rb") as asset:
            check_response(args.base_url, "/static/" + name, "text/css", asset.read())
        hashed_name = staticfiles_storage.stored_name(name)
        with staticfiles_storage.open(hashed_name, "rb") as asset:
            check_response(
                args.base_url, staticfiles_storage.url(name), "text/css", asset.read()
            )

    home = check_response(args.base_url, "/", "text/html")
    if staticfiles_storage.url("css/styles.css").encode() not in home:
        raise RuntimeError("Startseite referenziert nicht das aktuelle versionierte Stylesheet")

    check_not_found(args.base_url, "/static/css/deployment-missing.css")
    check_not_found(args.base_url, "/static/staticfiles.json")
    check_not_found(args.base_url, "/_protected_media/club/deployment-missing.png")
    check_not_found(args.base_url, "/media/private/deployment-missing.pdf")

    logo = ClubSettings.objects.exclude(logo="").exclude(logo__isnull=True).first()
    article = Article.objects.filter(
        visibility=Article.Visibility.PUBLIC,
        status=Article.Status.PUBLISHED,
        publish_at__lte=timezone.now(),
    ).exclude(cover_image="").exclude(cover_image__isnull=True).first()
    for image in (logo.logo if logo else None, article.cover_image if article else None):
        if image:
            request = Request(args.base_url.rstrip("/") + image.url)
            with urlopen(request, timeout=10) as response:
                if not response.headers.get_content_type().startswith("image/"):
                    raise RuntimeError("Öffentliches Bild wurde nicht als Bild ausgeliefert")
                with image.open("rb") as source:
                    if response.read() != source.read():
                        raise RuntimeError("Ausgeliefertes Bild stimmt nicht mit der Datei überein")
                print("OK: öffentliches Bild über Nginx")
    if not logo and not article:
        print("Hinweis: Noch keine öffentlichen Bilder für den HTTP-Bildtest vorhanden.")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"Deployment-Prüfung fehlgeschlagen: {error}", file=sys.stderr)
        sys.exit(1)
