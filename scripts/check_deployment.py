"""Verify actual HTTP delivery through Nginx, including the CSS MIME type."""

import argparse
import os
from pathlib import Path
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


class NoRedirects(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        raise RuntimeError(
            f"HTTP {code}: unerwartete Umleitung; Domain und Cloudflare Access prüfen"
        )


http = build_opener(NoRedirects())


def public_site_url():
    """Validate the public origin before any maintenance or database changes."""
    from django.http.request import validate_host

    value = os.environ.get("PUBLIC_SITE_URL", "").strip()
    if not value:
        raise RuntimeError(
            "PUBLIC_SITE_URL fehlt: In .env die Vereinsadresse eintragen, "
            "z. B. https://tennis.example"
        )
    url = urlsplit(value)
    if (
        url.scheme != "https"
        or not url.hostname
        or url.username is not None
        or url.password is not None
        or url.path not in ("", "/")
        or url.query
        or url.fragment
        or any(char.isspace() for char in value)
    ):
        raise RuntimeError(
            "PUBLIC_SITE_URL muss eine HTTPS-Adresse ohne Unterpfad sein"
        )
    # Accessing .port also rejects malformed or out-of-range port numbers.
    port = url.port or 443
    hosts = [host.strip() for host in os.getenv("DJANGO_ALLOWED_HOSTS", "").split(",")]
    if not validate_host(url.hostname, hosts):
        raise RuntimeError("Domain aus PUBLIC_SITE_URL fehlt in DJANGO_ALLOWED_HOSTS")
    origins = os.getenv("CSRF_TRUSTED_ORIGINS", "").split(",")
    for value in origins:
        origin = urlsplit(value.strip())
        pattern = origin.hostname or ""
        if pattern.startswith("*."):
            pattern = pattern[1:]
        if (
            origin.scheme == "https"
            and origin.username is None
            and origin.password is None
            and not origin.path
            and not origin.query
            and not origin.fragment
            and (origin.port or 443) == port
            and validate_host(url.hostname, [pattern])
        ):
            return url.geturl().rstrip("/")
    raise RuntimeError(
        "HTTPS-Adresse aus PUBLIC_SITE_URL fehlt in CSRF_TRUSTED_ORIGINS"
    )


def make_request(base_url, path, headers=None):
    separator = "&" if "?" in path else "?"
    url = base_url.rstrip("/") + path + separator + "_deployment_check=" + uuid4().hex
    return Request(
        url, headers={"Cache-Control": "no-cache, no-store", **(headers or {})}
    )


def check_response(
    base_url, path, expected_type, expected_body=None, *, headers=None, timeout=10
):
    request = make_request(base_url, path, headers)
    with http.open(request, timeout=timeout) as response:
        body = response.read()
        content_type = response.headers.get_content_type()
        if response.status != 200 or content_type != expected_type or not body:
            raise RuntimeError(
                f"{path}: erwartete HTTP 200 mit {expected_type} und Inhalt"
            )
        if expected_body is not None and body != expected_body:
            raise RuntimeError(
                f"{path}: ausgelieferter Inhalt entspricht nicht dem neuen Image"
            )
        print(f"OK: {path} (200, {content_type})")
        return body


def check_not_found(base_url, path, *, headers=None):
    try:
        with http.open(make_request(base_url, path, headers), timeout=10):
            pass
    except HTTPError as error:
        if error.code == 404:
            print(f"OK: {path} (404)")
            return
        raise
    raise RuntimeError(f"{path}: erwartete HTTP 404")


def wait_for_public(base_url, timeout=60, interval=2, consecutive=3):
    """Allow route propagation, but require several successive origin responses."""
    deadline = time.monotonic() + timeout
    successes = 0
    last_error = "keine erfolgreiche Antwort"
    while time.monotonic() < deadline:
        try:
            check_response(
                base_url,
                "/healthz/",
                "application/json",
                b'{"status": "ok"}',
                timeout=min(10, max(0.1, deadline - time.monotonic())),
            )
            successes += 1
            last_error = (
                f"erst {successes} von {consecutive} aufeinanderfolgenden Antworten"
            )
            if successes >= consecutive:
                return
        except (URLError, TimeoutError, OSError, RuntimeError) as error:
            successes = 0
            last_error = str(error)
            print(f"Warte auf öffentliche Website: {last_error}", flush=True)
        time.sleep(min(interval, max(0, deadline - time.monotonic())))
    raise RuntimeError(
        f"Öffentliche Website nicht zuverlässig erreichbar: {last_error}. "
        "Cloudflare-Ziel muss http://nginx:80 sein; Tunnel- und Nginx-Logs prüfen."
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://nginx")
    parser.add_argument(
        "--public", action="store_true", help="PUBLIC_SITE_URL aus der Umgebung prüfen"
    )
    parser.add_argument(
        "--validate-config", action="store_true", help="Nur Domain-Konfiguration prüfen"
    )
    parser.add_argument(
        "--origin-only",
        action="store_true",
        help="Nur HTTP-Bereitschaft und CSS prüfen",
    )
    parser.add_argument("--host", help="Hostheader für interne HTTP-Prüfungen")
    parser.add_argument(
        "--wait-timeout",
        type=float,
        default=60,
        help="Wartezeit für öffentliche Bereitschaft in Sekunden",
    )
    args = parser.parse_args()

    if args.validate_config:
        public_site_url()
        print("OK: Öffentliche Domain, erlaubte Hosts und CSRF-Origin passen zusammen")
        return
    headers = {}
    if args.public:
        if args.wait_timeout <= 0:
            parser.error("--wait-timeout muss größer als 0 sein")
        args.base_url = public_site_url()
        wait_for_public(args.base_url, timeout=args.wait_timeout)
    else:
        if urlsplit(args.base_url).scheme == "http":
            # Docker DNS names are connection targets, not public Django hosts.
            host = args.host or urlsplit(os.getenv("PUBLIC_SITE_URL", "")).hostname
            if not host and urlsplit(args.base_url).hostname == "nginx":
                host = "localhost"
            if host:
                headers = {"Host": host, "X-Forwarded-Proto": "https"}
        check_response(
            args.base_url,
            "/healthz/",
            "application/json",
            b'{"status": "ok"}',
            headers=headers,
        )

    if args.origin_only:
        check_response(
            args.base_url, "/static/css/styles.css", "text/css", headers=headers
        )
        print("OK: Nginx und Anwendung aus diesem Container-Netzwerk erreichbar")
        return

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.prod")
    import django

    django.setup()
    from django.contrib.staticfiles.storage import staticfiles_storage
    from django.utils import timezone
    from apps.core.models import ClubSettings
    from apps.news.models import Article

    for name in ("css/styles.css", "admin/css/base.css"):
        with staticfiles_storage.open(name, "rb") as asset:
            check_response(
                args.base_url,
                "/static/" + name,
                "text/css",
                asset.read(),
                headers=headers,
            )
        hashed_name = staticfiles_storage.stored_name(name)
        with staticfiles_storage.open(hashed_name, "rb") as asset:
            check_response(
                args.base_url,
                staticfiles_storage.url(name),
                "text/css",
                asset.read(),
                headers=headers,
            )

    home = check_response(args.base_url, "/", "text/html", headers=headers)
    if staticfiles_storage.url("css/styles.css").encode() not in home:
        raise RuntimeError(
            "Startseite referenziert nicht das aktuelle versionierte Stylesheet"
        )

    check_not_found(
        args.base_url, "/static/css/deployment-missing.css", headers=headers
    )
    check_not_found(args.base_url, "/static/staticfiles.json", headers=headers)
    check_not_found(
        args.base_url, "/_protected_media/club/deployment-missing.png", headers=headers
    )
    check_not_found(
        args.base_url, "/media/private/deployment-missing.pdf", headers=headers
    )

    logo = ClubSettings.objects.exclude(logo="").exclude(logo__isnull=True).first()
    article = (
        Article.objects.filter(
            visibility=Article.Visibility.PUBLIC,
            status=Article.Status.PUBLISHED,
            publish_at__lte=timezone.now(),
        )
        .exclude(cover_image="")
        .exclude(cover_image__isnull=True)
        .first()
    )
    for image in (
        logo.logo if logo else None,
        article.cover_image if article else None,
    ):
        if image:
            request = make_request(args.base_url, image.url, headers)
            with http.open(request, timeout=10) as response:
                if not response.headers.get_content_type().startswith("image/"):
                    raise RuntimeError(
                        "Öffentliches Bild wurde nicht als Bild ausgeliefert"
                    )
                with image.open("rb") as source:
                    if response.read() != source.read():
                        raise RuntimeError(
                            "Ausgeliefertes Bild stimmt nicht mit der Datei überein"
                        )
                print("OK: öffentliches Bild über Nginx")
    if not logo and not article:
        print(
            "Hinweis: Noch keine öffentlichen Bilder für den HTTP-Bildtest vorhanden."
        )


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"Deployment-Prüfung fehlgeschlagen: {error}", file=sys.stderr)
        sys.exit(1)
