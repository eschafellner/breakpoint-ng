"""Production regressions, including optional HTTP tests against real Nginx.

Run HTTP tests with NGINX_BINARY pointing to a local nginx executable. No Docker
daemon or live deployment is needed; all files and listeners are temporary.
"""

from contextlib import contextmanager
from datetime import timedelta
import io
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import threading
import time
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from wsgiref.simple_server import make_server

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.core.wsgi import get_wsgi_application
from django.db import DatabaseError
from django.urls import reverse
from django.utils import timezone
from PIL import Image

from apps.news.models import Article, ArticleImage
from config.settings.prod import STORAGES
from scripts.check_deployment import check_response, main as check_deployment


@pytest.fixture
def image_file():
    stream = io.BytesIO()
    Image.new("RGB", (16, 16), color="green").save(stream, "PNG")
    return SimpleUploadedFile("court.png", stream.getvalue(), content_type="image/png")


@pytest.fixture
def production_files(settings, tmp_path):
    settings.DEBUG = False
    settings.NGINX_MEDIA_ACCEL = True
    settings.MEDIA_ROOT = tmp_path / "media"
    settings.STATIC_ROOT = tmp_path / "staticfiles"
    settings.STORAGES = STORAGES
    settings.ALLOWED_HOSTS = ["testserver", "127.0.0.1", "localhost"]
    settings.CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
    return settings


@pytest.mark.django_db
def test_readiness_checks_database(client):
    assert client.get(reverse("health")).json() == {"status": "ok"}
    with patch("apps.core.deployment_views.connection.cursor", side_effect=DatabaseError):
        response = client.get(reverse("health"))
    assert response.status_code == 503
    assert response.json() == {"status": "unavailable"}
    assert "no-store" in response["Cache-Control"]


@pytest.mark.django_db
@pytest.mark.parametrize("visibility", [Article.Visibility.PUBLIC, Article.Visibility.MEMBERS])
def test_image_access_matches_article(client, member_user, guest_user, production_files, image_file, visibility):
    article = Article.objects.create(
        title="Image permissions", body="Test", status=Article.Status.PUBLISHED,
        visibility=visibility, cover_image=image_file, cover_image_alt="Court",
    )
    url = article.cover_image.url
    for user in (None, guest_user, member_user):
        client.logout()
        if user:
            client.force_login(user)
        response = client.get(url)
        allowed = visibility == Article.Visibility.PUBLIC or user == member_user
        assert response.status_code == (200 if allowed else 404)
        if allowed:
            assert response["Content-Type"] == "image/png"
            assert response["X-Accel-Redirect"].startswith("/_protected_media/news/covers/")
            assert "no-store" in response["Cache-Control"]


@pytest.mark.django_db
@pytest.mark.parametrize("state", ["draft", "scheduled", "archived"])
def test_unpublished_images_require_editor(client, admin_user, production_files, image_file, state):
    article = Article.objects.create(
        title="Unpublished", body="Test", cover_image=image_file, cover_image_alt="Court",
        status={"draft": Article.Status.DRAFT, "archived": Article.Status.ARCHIVED,
                "scheduled": Article.Status.PUBLISHED}[state],
        publish_at=timezone.now() + timedelta(days=1) if state == "scheduled" else timezone.now(),
    )
    assert client.get(article.cover_image.url).status_code == 404
    client.force_login(admin_user)
    assert client.get(article.cover_image.url).status_code == 200


@pytest.mark.django_db
@pytest.mark.parametrize("field", ["image", "image_medium", "image_thumb"])
def test_gallery_sizes_preserve_members_visibility(client, member_user, production_files, image_file, field):
    article = Article.objects.create(
        title="Private gallery", body="Test", status=Article.Status.PUBLISHED,
        visibility=Article.Visibility.MEMBERS,
    )
    gallery = ArticleImage.objects.create(article=article, alt_text="Court", **{field: image_file})
    url = getattr(gallery, field).url
    assert client.get(url).status_code == 404
    client.force_login(member_user)
    assert client.get(url).status_code == 200


@pytest.mark.django_db
def test_logo_public_avatar_owner_only(client, member_user, guest_user, club_settings, production_files, image_file):
    club_settings.logo = image_file
    club_settings.save()
    assert client.get(club_settings.logo.url).status_code == 200
    image_file.seek(0)
    member_user.avatar = image_file
    member_user.save()
    assert client.get(member_user.avatar.url).status_code == 404
    client.force_login(guest_user)
    assert client.get(member_user.avatar.url).status_code == 404
    client.force_login(member_user)
    assert client.get(member_user.avatar.url).status_code == 200


@pytest.mark.django_db
def test_unknown_files_and_traversal_are_not_public(client, production_files):
    root = Path(production_files.MEDIA_ROOT)
    (root / "club").mkdir(parents=True)
    (root / "club" / "orphan.png").write_bytes(b"unreferenced")
    for path in ("club/orphan.png", "private/document.pdf", "../secret.png", "club\\secret.png"):
        assert client.get("/media/" + path).status_code == 404


@pytest.mark.django_db
def test_development_delivers_authorized_media(client, settings, club_settings, image_file, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    settings.NGINX_MEDIA_ACCEL = False
    club_settings.logo = image_file
    club_settings.save()
    response = client.get(club_settings.logo.url)
    assert response.status_code == 200
    assert b"".join(response.streaming_content).startswith(b"\x89PNG")
    assert "X-Accel-Redirect" not in response


@contextmanager
def nginx_proxy(settings, tmp_path):
    binary = os.environ.get("NGINX_BINARY") or shutil.which("nginx")
    if not binary:
        pytest.skip("NGINX_BINARY is required for the real Nginx HTTP tests")
    binary = Path(binary).resolve()
    mime_types = binary.parent / "conf" / "mime.types"
    if not mime_types.exists():
        mime_types = Path("/etc/nginx/mime.types")

    call_command("collectstatic", interactive=False, verbosity=0)
    backend = make_server("127.0.0.1", 0, get_wsgi_application())
    thread = threading.Thread(target=backend.serve_forever, daemon=True)
    thread.start()
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]

    prefix = tmp_path / "nginx"
    (prefix / "logs").mkdir(parents=True)
    (prefix / "temp").mkdir()
    config = (Path(__file__).resolve().parents[1] / "deploy/nginx/default.conf").read_text(encoding="utf-8")
    config = config.replace("listen 80;", f"listen 127.0.0.1:{port};")
    config = config.replace("http://web:8000", f"http://127.0.0.1:{backend.server_port}")
    config = config.replace("/app/staticfiles/", Path(settings.STATIC_ROOT).as_posix() + "/")
    config = config.replace("/app/media/", Path(settings.MEDIA_ROOT).as_posix() + "/")
    wrapper = (
        "daemon off;\nworker_processes 1;\nevents { worker_connections 64; }\nhttp {\n"
        f'include "{mime_types.as_posix()}";\n{config}\n}}\n'
    )
    (prefix / "nginx.conf").write_text(wrapper, encoding="utf-8")
    command = [str(binary), "-p", prefix.as_posix() + "/", "-c", "nginx.conf"]
    options = {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}
    process = None
    try:
        validation = subprocess.run(command + ["-t"], capture_output=True, **options)
        assert validation.returncode == 0, validation.stderr.decode(errors="replace")
        process = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, **options)
        origin = f"http://127.0.0.1:{port}"
        for _ in range(50):
            try:
                with urlopen(origin + "/healthz/", timeout=1) as response:
                    assert response.status == 200
                break
            except OSError:
                if process.poll() is not None:
                    pytest.fail((prefix / "logs/error.log").read_text())
                time.sleep(0.1)
        else:
            pytest.fail("Nginx did not become ready")
        yield origin
    finally:
        if process is not None and process.poll() is None:
            subprocess.run(command + ["-s", "quit"], check=True, capture_output=True, **options)
            process.wait(timeout=10)
        backend.shutdown()
        backend.server_close()
        thread.join(timeout=5)


@pytest.mark.django_db(transaction=True)
def test_nginx_http_styles_cache_gzip_and_missing_files(production_files, tmp_path, club_settings):
    from django.contrib.staticfiles.storage import staticfiles_storage

    with nginx_proxy(production_files, tmp_path) as origin:
        for name in ("css/styles.css", "admin/css/base.css"):
            path = staticfiles_storage.url(name)
            with urlopen(origin + path) as response:
                assert response.headers.get_content_type() == "text/css"
                assert "immutable" in response.headers["Cache-Control"]
                assert response.read()
        with urlopen(origin + "/static/css/styles.css") as response:
            assert "immutable" not in response.headers["Cache-Control"]
            assert response.headers["X-Content-Type-Options"] == "nosniff"
        request = Request(origin + "/static/css/styles.css", headers={"Accept-Encoding": "gzip"})
        with urlopen(request) as response:
            assert response.headers["Content-Encoding"] == "gzip"
        for path in ("/static/missing.css", "/static/staticfiles.json", "/_protected_media/secret.png"):
            with pytest.raises(HTTPError) as error:
                urlopen(origin + path)
            assert error.value.code == 404
        home = check_response(origin, "/", "text/html")
        assert staticfiles_storage.url("css/styles.css").encode() in home
        with patch.object(sys, "argv", ["check_deployment.py", "--base-url", origin]):
            check_deployment()


@pytest.mark.django_db(transaction=True)
def test_nginx_transfers_authorized_images(production_files, tmp_path, club_settings, image_file):
    club_settings.logo = image_file
    club_settings.save()
    article = Article.objects.create(
        title="Members image", body="Test", status=Article.Status.PUBLISHED,
        visibility=Article.Visibility.MEMBERS, cover_image=image_file, cover_image_alt="Court",
    )
    with nginx_proxy(production_files, tmp_path) as origin:
        with urlopen(origin + club_settings.logo.url) as response:
            assert response.headers.get_content_type() == "image/png"
            assert response.read().startswith(b"\x89PNG")
            assert "no-store" in response.headers["Cache-Control"]
        with patch.object(sys, "argv", ["check_deployment.py", "--base-url", origin]):
            check_deployment()
        for path in (article.cover_image.url, "/_protected_media/" + club_settings.logo.name):
            with pytest.raises(HTTPError) as error:
                urlopen(origin + path)
            assert error.value.code == 404


def test_http_check_rejects_html_disguised_as_stylesheet():
    from http.server import BaseHTTPRequestHandler, HTTPServer

    class HtmlHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(b"<html>Error page</html>")

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), HtmlHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with pytest.raises(RuntimeError, match="text/css"):
            check_response(f"http://127.0.0.1:{server.server_port}", "/styles.css", "text/css")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


@pytest.mark.parametrize("prepare_exit,http_exit", [(0, 0), (1, 0), (0, 1)])
def test_deploy_publishes_only_after_successful_checks(tmp_path, prepare_exit, http_exit):
    """Exercise the real Bash flow without a daemon or production data."""
    bash = shutil.which("bash")
    if not bash and os.name == "nt":
        candidate = Path("C:/Program Files/Git/bin/bash.exe")
        if candidate.exists():
            bash = str(candidate)
    if not bash:
        pytest.skip("Bash is required to exercise the deployment script")

    command_log = tmp_path / "docker-commands.log"
    environment = os.environ.copy()
    environment.update(
        DOCKER_TEST_LOG=command_log.as_posix(),
        PREPARE_TEST_EXIT=str(prepare_exit),
        HTTP_TEST_EXIT=str(http_exit),
    )
    mock = r'''
docker() {
    printf '%s\n' "$*" >> "$DOCKER_TEST_LOG"
    case "$*" in
        *"ps -a -q prepare") printf 'prepare-test-id\n' ;;
        "wait prepare-test-id") printf '%s\n' "$PREPARE_TEST_EXIT" ;;
        *"python scripts/check_deployment.py") return "$HTTP_TEST_EXIT" ;;
    esac
    return 0
}
export -f docker
bash scripts/deploy.sh
'''
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run([bash, "-c", mock], cwd=root, env=environment, capture_output=True)
    commands = command_log.read_text().splitlines()
    publishes = [command for command in commands if "up -d" in command and "cloudflared" in command]
    if prepare_exit or http_exit:
        assert result.returncode != 0
        assert not publishes
    else:
        assert result.returncode == 0, result.stderr.decode(errors="replace")
        assert len(publishes) == 1
        check_index = next(i for i, command in enumerate(commands) if "check_deployment.py" in command)
        assert commands.index(publishes[0]) > check_index
    stop_index = next(i for i, command in enumerate(commands) if "stop cloudflared" in command)
    prepare_index = next(i for i, command in enumerate(commands) if "force-recreate prepare" in command)
    assert stop_index < prepare_index
