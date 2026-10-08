"""Backup integrity, fail-fast scripts and tunnel readiness without live data."""

import gzip
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
from unittest.mock import MagicMock, patch
from urllib.error import URLError

import pytest

from config.settings.prod import CELERY_BEAT_SCHEDULE
from scripts.check_tunnel import wait_for_tunnel
from scripts.media_archive import backup, restore


def test_media_archive_round_trip_and_validation(tmp_path):
    source = tmp_path / "source/media"
    (source / "news/covers").mkdir(parents=True)
    (source / "news/covers/court.png").write_bytes(b"image bytes")
    output = io.BytesIO()
    backup(source, output)
    target = tmp_path / "restored/media"
    restore(target, io.BytesIO(output.getvalue()), validate_only=True)
    assert not target.exists()
    restore(target, io.BytesIO(output.getvalue()))
    assert (target / "news/covers/court.png").read_bytes() == b"image bytes"


@pytest.mark.parametrize(
    "name",
    ["../outside", "/etc/passwd", "media/../outside", "other/file", "media\\outside"],
)
def test_media_restore_rejects_escaping_paths_before_writing(tmp_path, name):
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode="w:gz") as archive:
        good = tarfile.TarInfo("media/good.png")
        good.size = 2
        archive.addfile(good, io.BytesIO(b"ok"))
        bad = tarfile.TarInfo(name)
        bad.size = 3
        archive.addfile(bad, io.BytesIO(b"bad"))
    target = tmp_path / "media"
    with pytest.raises(ValueError):
        restore(target, io.BytesIO(stream.getvalue()))
    assert not target.exists()


def test_media_restore_rejects_links_and_corrupt_gzip(tmp_path):
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode="w:gz") as archive:
        link = tarfile.TarInfo("media/link")
        link.type = tarfile.SYMTYPE
        link.linkname = "../outside"
        archive.addfile(link)
    with pytest.raises(ValueError):
        restore(tmp_path / "media", io.BytesIO(stream.getvalue()))
    with pytest.raises((OSError, EOFError)):
        restore(tmp_path / "media", io.BytesIO(gzip.compress(b"tar bytes")[:-5]))
    assert not (tmp_path / "media").exists()


def test_tunnel_waits_for_real_readiness_and_times_out():
    response = MagicMock(status=200)
    response.__enter__.return_value = response
    with (
        patch(
            "scripts.check_tunnel.urlopen",
            side_effect=[URLError("not connected"), response],
        ),
        patch("scripts.check_tunnel.time.sleep"),
    ):
        wait_for_tunnel(timeout=1, interval=0)
    with patch("scripts.check_tunnel.urlopen", side_effect=URLError("not connected")):
        with pytest.raises(RuntimeError, match="nicht verbunden"):
            wait_for_tunnel(timeout=0.01, interval=0.01)


def test_production_beat_schedules_existing_tasks():
    jobs = CELERY_BEAT_SCHEDULE
    assert {job["task"] for job in jobs.values()} == {
        "apps.members.tasks.task_end_expired_memberships",
        "apps.courts.tasks.send_booking_reminders",
        "apps.tournaments.tasks.expire_pending_partners",
        "apps.core.tasks.deliver_pending_emails",
    }
    assert jobs["booking-reminders"]["schedule"].minute == {0}
    assert jobs["end-expired-memberships"]["schedule"].hour == {0}

    # Parse the actual Compose file: every writer must receive rotation keys.
    root = Path(__file__).resolve().parents[1]
    portable = root / ".deployment-tests/docker-compose.exe"
    if portable.exists():
        compose = [str(portable)]
    elif shutil.which("docker"):
        compose = [shutil.which("docker"), "compose"]
    else:
        pytest.skip("Docker Compose is required to validate deployment variables")
    environment = os.environ.copy()
    environment.update(
        DJANGO_SECRET_KEY="test-current-key",
        DJANGO_SECRET_KEY_FALLBACKS="test-previous-key",
        DJANGO_ALLOWED_HOSTS="test.example",
        CSRF_TRUSTED_ORIGINS="https://test.example",
        DB_PASSWORD="test-password",
        CLOUDFLARE_TUNNEL_TOKEN="test-token",
        PUBLIC_SITE_URL="https://test.example",
        APP_IMAGE="ghcr.io/test/breakpoint-ng:v1.0.0",
    )
    command = compose + [
        "--profile",
        "diagnostics",
        "--env-file",
        str(root / ".env.example"),
        "-f",
        str(root / "docker-compose.prod.yml"),
        "config",
    ]
    result = subprocess.run(
        command + ["--format", "json"],
        env=environment,
        capture_output=True,
        text=True,
        check=True,
        timeout=20,
    )
    services = json.loads(result.stdout)["services"]
    assert services["tunnel_probe"]["network_mode"] == "service:cloudflared"
    assert services["tunnel_probe"]["profiles"] == ["diagnostics"]
    assert not services["cloudflared"].get("ports")
    assert not services["nginx"].get("ports")
    for name in ["prepare", "web", "celery_worker", "celery_beat"]:
        assert services[name]["image"] == environment["APP_IMAGE"]
        assert "build" not in services[name]
        assert (
            services[name]["environment"]["DJANGO_SECRET_KEY_FALLBACKS"]
            == "test-previous-key"
        )
    environment["DJANGO_SECRET_KEY"] = ""
    invalid = subprocess.run(
        command + ["--quiet"],
        env=environment,
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert invalid.returncode != 0
    assert "DJANGO_SECRET_KEY" in invalid.stderr


def bash_binary():
    bash = shutil.which("bash")
    if not bash and Path("C:/Program Files/Git/bin/bash.exe").exists():
        bash = "C:/Program Files/Git/bin/bash.exe"
    if not bash:
        pytest.skip("Bash is required for deployment script tests")
    return bash


def run_script(tmp_path, script, arguments, **flags):
    root = Path(__file__).resolve().parents[1]
    workspace = tmp_path / "project"
    workspace.mkdir()
    shutil.copytree(
        root / "scripts",
        workspace / "scripts",
        ignore=shutil.ignore_patterns("__pycache__"),
    )
    for filename in ("update.sh", "docker-compose.prod.yml"):
        shutil.copy(root / filename, workspace / filename)
    (workspace / ".env").write_text(
        "# Test configuration\nAPP_IMAGE=ghcr.io/test/breakpoint-ng:v1.0.0\n"
        "DB_PASSWORD=test-password\nDJANGO_SECRET_KEY=test-deploy-only-secret\n"
        "DJANGO_ALLOWED_HOSTS=tennis.example\nCSRF_TRUSTED_ORIGINS=https://tennis.example\n"
        "CLOUDFLARE_TUNNEL_TOKEN=test-token\nPUBLIC_SITE_URL=https://tennis.example\n"
    )
    media = tmp_path / "fixture.tar.gz"
    source = tmp_path / "source/media"
    source.mkdir(parents=True)
    (source / "court.png").write_bytes(b"image")
    with media.open("wb") as stream:
        backup(source, stream)
    log = tmp_path / "commands.log"
    env = os.environ.copy()
    env.update(
        BACKUP_DIR=(tmp_path / "backups").as_posix(),
        DOCKER_TEST_LOG=log.as_posix(),
        MOCK_MEDIA_ARCHIVE=media.as_posix(),
        MOCK_DUMP_EXIT="0",
        MOCK_VALIDATE_EXIT="0",
        MOCK_PSQL_EXIT="0",
        MOCK_RUNNING="db\nredis",
        MOCK_WORKER_EXIT="0",
        MOCK_TUNNEL_EXIT="0",
        MOCK_PUBLIC_EXIT="0",
        MOCK_CONFIG_EXIT="0",
        MOCK_ORIGIN_EXIT="0",
        MOCK_IMAGE_PULL_EXIT="0",
        MOCK_INFRA_PULL_EXIT="0",
        MOCK_APP_IMAGE="ghcr.io/test/breakpoint-ng:v1.0.0",
        MOCK_REAL_CONFIG="0",
    )
    env.update({name: str(value) for name, value in flags.items()})
    mock = r"""
docker() {
    printf '%s\n' "$*" >> "$DOCKER_TEST_LOG"
    if [ "$MOCK_REAL_CONFIG" = 1 ] && [[ "$*" == *"config --quiet" || "$*" == *"config prepare" ]]; then
        command docker "$@"
        return $?
    fi
    case "$*" in
        *"config prepare") printf 'services:\n  db:\n    image: postgres:16-alpine\n  prepare:\n    image: %s\n  redis:\n    image: redis:7-alpine\n' "${APP_IMAGE:-$MOCK_APP_IMAGE}" ;;
        *"pull prepare") return "$MOCK_IMAGE_PULL_EXIT" ;;
        *"pull nginx cloudflared"|*"pull --policy missing nginx cloudflared") return "$MOCK_INFRA_PULL_EXIT" ;;
        *"ps -a -q prepare") printf 'prepare-test-id\n' ;;
        "wait prepare-test-id") printf '0\n' ;;
        *"--wait --wait-timeout 120 celery_worker celery_beat") return "$MOCK_WORKER_EXIT" ;;
        *"python scripts/check_tunnel.py") return "$MOCK_TUNNEL_EXIT" ;;
        *"python scripts/check_deployment.py --public") return "$MOCK_PUBLIC_EXIT" ;;
        *"scripts/check_deployment.py --validate-config") return "$MOCK_CONFIG_EXIT" ;;
        *"run --rm --no-deps --pull never -T tunnel_probe") return "$MOCK_ORIGIN_EXIT" ;;
        *"ps --status running --services") printf '%s\n' "$MOCK_RUNNING" ;;
        *pg_dump*) printf 'SELECT 1;\n'; return "$MOCK_DUMP_EXIT" ;;
        *"media_archive.py backup") cat "$MOCK_MEDIA_ARCHIVE" ;;
        *"media_archive.py validate") cat >/dev/null; return "$MOCK_VALIDATE_EXIT" ;;
        *psql*) cat >/dev/null; return "$MOCK_PSQL_EXIT" ;;
        *"media_archive.py restore") cat >/dev/null ;;
    esac
    return 0
}
export -f docker
git() {
    printf 'git %s\n' "$*" >> "$DOCKER_TEST_LOG"
    case "$*" in
        "status --porcelain"|"pull --ff-only") return 0 ;;
        *) return 1 ;;
    esac
}
export -f git
bash "$@"
"""
    result = subprocess.run(
        [bash_binary(), "-c", mock, "test", script, *arguments],
        cwd=workspace,
        env=env,
        capture_output=True,
    )
    return result, log.read_text() if log.exists() else ""


@pytest.mark.parametrize("dump_exit,validate_exit", [(0, 0), (1, 0), (0, 1)])
def test_backup_uses_volume_and_rejects_partial_results(
    tmp_path, dump_exit, validate_exit
):
    result, commands = run_script(
        tmp_path,
        "scripts/backup.sh",
        [],
        MOCK_DUMP_EXIT=dump_exit,
        MOCK_VALIDATE_EXIT=validate_exit,
    )
    files = list((tmp_path / "backups").iterdir())
    if dump_exit or validate_exit:
        assert result.returncode != 0
        assert files == []
    else:
        assert result.returncode == 0, result.stderr.decode(errors="replace")
        assert len(files) == 2
        assert (
            "--no-deps --pull never -T --entrypoint python web scripts/media_archive.py backup"
            in commands
        )
        assert '"$POSTGRES_USER"' in commands
        sql = next(file for file in files if file.name.endswith("sql.gz"))
        assert gzip.decompress(sql.read_bytes()) == b"SELECT 1;\n"


@pytest.mark.parametrize(
    "scenario",
    ["success", "running", "prepare_running", "invalid_media", "db_error", "missing"],
)
def test_restore_refuses_unsafe_or_failed_steps(tmp_path, scenario):
    database = tmp_path / "db.sql.gz"
    database.write_bytes(gzip.compress(b"SELECT 1;"))
    media = tmp_path / "media.tar.gz"
    media.write_bytes(b"placeholder; Docker mock validates separately")
    if scenario == "missing":
        database.unlink()
    flags = {}
    if scenario == "running":
        flags["MOCK_RUNNING"] = "db\nweb"
    elif scenario == "prepare_running":
        flags["MOCK_RUNNING"] = "db\nprepare"
    elif scenario == "invalid_media":
        flags["MOCK_VALIDATE_EXIT"] = 1
    elif scenario == "db_error":
        flags["MOCK_PSQL_EXIT"] = 1
    result, commands = run_script(
        tmp_path, "scripts/restore.sh", [database.as_posix(), media.as_posix()], **flags
    )
    if scenario == "success":
        assert result.returncode == 0, result.stderr.decode(errors="replace")
        assert "--set=ON_ERROR_STOP=1 --single-transaction" in commands
        assert "media_archive.py restore" in commands
    else:
        assert result.returncode != 0
        assert "media_archive.py restore" not in commands
        if scenario != "db_error":
            assert "psql" not in commands


@pytest.mark.parametrize(
    "failure",
    ["MOCK_WORKER_EXIT", "MOCK_TUNNEL_EXIT", "MOCK_ORIGIN_EXIT", "MOCK_PUBLIC_EXIT"],
)
def test_deployment_failure_stops_tunnel_and_does_not_report_success(tmp_path, failure):
    result, commands = run_script(tmp_path, "scripts/deploy.sh", [], **{failure: 1})
    assert result.returncode != 0
    assert "Deployment erfolgreich geprüft".encode() not in result.stdout
    assert commands.splitlines()[-1].endswith("stop cloudflared")
    assert not (Path(__file__).resolve().parents[1] / ".deployment-lock").exists()


def test_invalid_domain_fails_before_maintenance(tmp_path):
    result, commands = run_script(tmp_path, "scripts/deploy.sh", [], MOCK_CONFIG_EXIT=1)
    assert result.returncode != 0
    assert "--validate-config" in commands
    assert "stop cloudflared" not in commands
    assert "pg_dump" not in commands
    assert "force-recreate" not in commands


@pytest.mark.parametrize("script", ["scripts/deploy.sh", "update.sh"])
def test_skipping_public_check_requires_explicit_option_and_reports_limit(
    tmp_path, script
):
    result, commands = run_script(
        tmp_path, script, ["--skip-public-check"], MOCK_PUBLIC_EXIT=1
    )
    assert result.returncode == 0, result.stderr.decode(errors="replace")
    assert "--validate-config" in commands
    assert "run --rm --no-deps --pull never -T tunnel_probe" in commands
    assert "check_deployment.py --public" not in commands
    assert "öffentliche Website NICHT geprüft".encode() in result.stdout
    assert "Deployment erfolgreich geprüft".encode() not in result.stdout
    assert "Update erfolgreich".encode() not in result.stdout


def test_update_propagates_public_check_failure(tmp_path):
    result, commands = run_script(tmp_path, "update.sh", [], MOCK_PUBLIC_EXIT=1)
    assert result.returncode != 0
    assert "check_deployment.py --public" in commands
    assert "Update erfolgreich".encode() not in result.stdout


@pytest.mark.parametrize(
    "arguments", [["--unknown"], ["--skip-public-check", "unexpected"]]
)
def test_bad_deploy_arguments_fail_before_docker(tmp_path, arguments):
    result, commands = run_script(tmp_path, "scripts/deploy.sh", arguments)
    assert result.returncode == 2
    assert not commands


def test_release_update_downloads_image_without_git_or_build(tmp_path):
    result, commands = run_script(tmp_path, "update.sh", ["v0.1.1"])
    assert result.returncode == 0, result.stderr.decode(errors="replace")
    assert "pull prepare" in commands
    assert "git " not in commands
    assert "build prepare" not in commands
    assert "pull --policy missing nginx cloudflared" in commands
    assert "pull nginx cloudflared" not in commands
    assert "--force-recreate cloudflared" not in commands
    for command in commands.splitlines():
        if "up -d" in command:
            assert "--no-build --pull never" in command
    configuration = (tmp_path / "project/.env").read_text()
    assert "APP_IMAGE=ghcr.io/eschafellner/breakpoint-ng:v0.1.1\n" in configuration
    assert "DB_PASSWORD=test-password\n" in configuration
    assert list((tmp_path / "project").glob(".env.release.*")) == []
    assert commands.index("pull prepare") < commands.index("stop cloudflared")


@pytest.mark.parametrize("failure", ["MOCK_IMAGE_PULL_EXIT", "MOCK_INFRA_PULL_EXIT"])
def test_release_download_failure_keeps_running_site_and_selection(tmp_path, failure):
    result, commands = run_script(tmp_path, "update.sh", ["v0.1.1"], **{failure: 1})
    assert result.returncode != 0
    assert "stop cloudflared" not in commands
    assert "pg_dump" not in commands
    assert (
        "APP_IMAGE=ghcr.io/test/breakpoint-ng:v1.0.0\n"
        in (tmp_path / "project/.env").read_text()
    )


def test_failed_deployment_keeps_target_for_retry_after_migrations(tmp_path):
    result, _ = run_script(tmp_path, "update.sh", ["v0.1.1"], MOCK_PUBLIC_EXIT=1)
    assert result.returncode != 0
    assert (
        "APP_IMAGE=ghcr.io/eschafellner/breakpoint-ng:v0.1.1\n"
        in (tmp_path / "project/.env").read_text()
    )
    assert not (tmp_path / "project/.deployment-lock").exists()


@pytest.mark.parametrize(
    "image",
    [
        "ghcr.io/test/breakpoint-ng:v2.3.4-rc.1",
        "ghcr.io/test/breakpoint-ng@sha256:" + "a" * 64,
    ],
)
def test_custom_release_or_digest_is_persisted(tmp_path, image):
    result, _ = run_script(tmp_path, "update.sh", [image])
    assert result.returncode == 0, result.stderr.decode(errors="replace")
    assert f"APP_IMAGE={image}\n" in (tmp_path / "project/.env").read_text()


@pytest.mark.parametrize(
    "image",
    [
        "latest",
        "ghcr.io/test/breakpoint-ng:latest",
        "v1.0",
        "ghcr.io/test/breakpoint-ng@sha256:abc",
        "ghcr.io/test/breakpoint-ng:bad\nAPP_IMAGE=:v1.0.0",
    ],
)
def test_invalid_release_selection_fails_before_docker(tmp_path, image):
    result, commands = run_script(tmp_path, "update.sh", [image])
    assert result.returncode == 2
    assert not commands


@pytest.mark.parametrize("image", ["ghcr.io/test/breakpoint-ng:latest", "v1.0.0"])
def test_mutable_configured_image_fails_before_download_or_maintenance(tmp_path, image):
    result, commands = run_script(tmp_path, "update.sh", [], APP_IMAGE=image)
    assert result.returncode != 0
    assert "pull " not in commands
    assert "stop cloudflared" not in commands


def test_infrastructure_downloads_require_explicit_option(tmp_path):
    result, commands = run_script(tmp_path, "update.sh", ["--update-infrastructure"])
    assert result.returncode == 0, result.stderr.decode(errors="replace")
    assert "pull nginx cloudflared" in commands
    assert "pull --policy missing nginx cloudflared" not in commands
    assert commands.index("pull nginx cloudflared") < commands.index("stop cloudflared")


@pytest.mark.parametrize(
    "image",
    [
        "ghcr.io/test/breakpoint-ng:v2.3.4",
        "ghcr.io/test/breakpoint-ng@sha256:" + "a" * 64,
    ],
)
def test_deployment_resolves_only_app_image_from_real_compose_config(tmp_path, image):
    if not shutil.which("docker"):
        pytest.skip("Docker Compose is required to parse the real deployment config")
    result, _ = run_script(tmp_path, "update.sh", [image], MOCK_REAL_CONFIG=1)
    assert result.returncode == 0, result.stderr.decode(errors="replace")
    assert f"Lade Release-Image: {image}".encode() in result.stdout
    assert b"test-deploy-only-secret" not in result.stdout + result.stderr
