"""Regressions for misleading tunnel success and public origin verification."""

from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, HTTPServer
import threading
from urllib.error import HTTPError, URLError

import pytest

from scripts.check_deployment import (
    check_response,
    main,
    public_site_url,
    wait_for_public,
)


@pytest.fixture
def public_config(monkeypatch):
    monkeypatch.setenv("PUBLIC_SITE_URL", "https://tennis.example")
    monkeypatch.setenv("DJANGO_ALLOWED_HOSTS", "tennis.example")
    monkeypatch.setenv("CSRF_TRUSTED_ORIGINS", "https://tennis.example")


@pytest.mark.parametrize(
    "url",
    [
        "",
        "http://tennis.example",
        "https://tennis.example/path",
        "https://user:password@tennis.example",
        "https://tennis.example?query=1",
        "https://tennis.example#fragment",
        "https://tennis.example:bad",
        "https://tennis.example:99999",
        "https://",
        "https://tennis.example /",
        "https://[invalid",
    ],
)
def test_public_configuration_rejects_missing_or_invalid_url(
    public_config, monkeypatch, url
):
    monkeypatch.setenv("PUBLIC_SITE_URL", url)
    with pytest.raises((RuntimeError, ValueError)):
        public_site_url()


@pytest.mark.parametrize(
    "name,value",
    [
        ("DJANGO_ALLOWED_HOSTS", "other.example"),
        ("CSRF_TRUSTED_ORIGINS", "https://other.example"),
        ("CSRF_TRUSTED_ORIGINS", "http://tennis.example"),
        ("CSRF_TRUSTED_ORIGINS", "https://tennis.example:8443"),
        ("CSRF_TRUSTED_ORIGINS", "https://tennis.example/path"),
        ("CSRF_TRUSTED_ORIGINS", "https://user:password@tennis.example"),
    ],
)
def test_public_configuration_checks_host_and_csrf(
    public_config, monkeypatch, name, value
):
    monkeypatch.setenv(name, value)
    with pytest.raises(RuntimeError, match=name):
        public_site_url()


def test_public_configuration_accepts_domain_patterns(public_config, monkeypatch):
    monkeypatch.setenv("PUBLIC_SITE_URL", "https://www.tennis.example/")
    monkeypatch.setenv("DJANGO_ALLOWED_HOSTS", "localhost, .tennis.example")
    monkeypatch.setenv("CSRF_TRUSTED_ORIGINS", "https://*.tennis.example")
    assert public_site_url() == "https://www.tennis.example"


def test_missing_public_url_never_silently_skips_check(monkeypatch):
    monkeypatch.delenv("PUBLIC_SITE_URL", raising=False)
    monkeypatch.setattr("sys.argv", ["check_deployment.py", "--public"])
    with pytest.raises(RuntimeError, match="PUBLIC_SITE_URL fehlt"):
        main()


def test_configuration_check_needs_no_http_or_database(public_config, monkeypatch):
    monkeypatch.setattr("sys.argv", ["check_deployment.py", "--validate-config"])
    monkeypatch.setattr(
        "scripts.check_deployment.http.open",
        lambda *args, **kwargs: pytest.fail("Unexpected HTTP request"),
    )
    main()


@contextmanager
def origin(handler):
    server = HTTPServer(("127.0.0.1", 0), handler)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=5)


def test_origin_check_uses_public_host_and_forwarded_scheme(public_config, monkeypatch):
    requests = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            requests.append(
                (self.path, self.headers["Host"], self.headers["X-Forwarded-Proto"])
            )
            if self.headers["Host"] != "tennis.example":
                self.send_error(400)
                return
            health = self.path.startswith("/healthz/")
            self.send_response(200)
            self.send_header(
                "Content-Type", "application/json" if health else "text/css"
            )
            self.end_headers()
            self.wfile.write(
                b'{"status": "ok"}' if health else b"body { color: green; }"
            )

        def log_message(self, *args):
            pass

    with origin(Handler) as url:
        monkeypatch.setattr(
            "sys.argv", ["check_deployment.py", "--origin-only", "--base-url", url]
        )
        main()
    assert len(requests) == 2
    assert all(
        host == "tennis.example" and scheme == "https" for _, host, scheme in requests
    )
    assert all("_deployment_check=" in path for path, _, _ in requests)


@pytest.mark.parametrize("response_code", [302, 502])
def test_http_check_rejects_access_redirect_and_bad_gateway(response_code):
    requests = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            requests.append(self.path)
            self.send_response(response_code)
            if response_code == 302:
                self.send_header("Location", "/access-login")
            self.end_headers()

        def log_message(self, *args):
            pass

    with origin(Handler) as url:
        with pytest.raises((RuntimeError, HTTPError)):
            check_response(url, "/healthz/", "application/json")
    assert len(requests) == 1  # A login redirect must not be followed.


def test_public_wait_requires_successes_after_last_failure(monkeypatch):
    results = iter(
        [
            None,
            HTTPError("https://tennis.example", 502, "Bad Gateway", {}, None),
            None,
            None,
            None,
        ]
    )
    attempts = []

    def check(*args, **kwargs):
        attempts.append(args)
        result = next(results)
        if result:
            raise result

    monkeypatch.setattr("scripts.check_deployment.check_response", check)
    monkeypatch.setattr("scripts.check_deployment.time.sleep", lambda interval: None)
    wait_for_public("https://tennis.example", interval=0)
    assert len(attempts) == 5


def test_public_wait_fails_when_origin_stays_unreachable(monkeypatch):
    ticks = iter([0, 0, 0, 2, 3])
    monkeypatch.setattr("scripts.check_deployment.time.monotonic", lambda: next(ticks))
    monkeypatch.setattr("scripts.check_deployment.time.sleep", lambda interval: None)

    def unreachable(*args, **kwargs):
        raise URLError("connection refused")

    monkeypatch.setattr("scripts.check_deployment.check_response", unreachable)
    with pytest.raises(RuntimeError, match="http://nginx:80"):
        wait_for_public("https://tennis.example", timeout=1)
