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
    )
    command = compose + [
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
    for name in ["prepare", "web", "celery_worker", "celery_beat"]:
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
    media = tmp_path / "fixture.tar.gz"
    source = tmp_path / "source/media"
    source.mkdir(parents=True)
    (source / "court.png").write_bytes(b"image")
    with media.open("wb") as stream:
        backup(source, stream)
    log = tmp_path / "commands.log"
    env = os.environ.copy()
    env.update(
        BACKUP_DIR=os.path.relpath(tmp_path / "backups", root).replace("\\", "/"),
        DOCKER_TEST_LOG=log.as_posix(),
        MOCK_MEDIA_ARCHIVE=media.as_posix(),
        MOCK_DUMP_EXIT="0",
        MOCK_VALIDATE_EXIT="0",
        MOCK_PSQL_EXIT="0",
        MOCK_RUNNING="db\nredis",
        MOCK_WORKER_EXIT="0",
        MOCK_TUNNEL_EXIT="0",
        MOCK_PUBLIC_EXIT="0",
    )
    env.update({name: str(value) for name, value in flags.items()})
    mock = r"""
docker() {
    printf '%s\n' "$*" >> "$DOCKER_TEST_LOG"
    case "$*" in
        *"ps -a -q prepare") printf 'prepare-test-id\n' ;;
        "wait prepare-test-id") printf '0\n' ;;
        *"--wait --wait-timeout 120 celery_worker celery_beat") return "$MOCK_WORKER_EXIT" ;;
        *"python scripts/check_tunnel.py") return "$MOCK_TUNNEL_EXIT" ;;
        *"python scripts/check_deployment.py --public") return "$MOCK_PUBLIC_EXIT" ;;
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
bash "$@"
"""
    result = subprocess.run(
        [bash_binary(), "-c", mock, "test", script, *arguments],
        cwd=root,
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
            "--no-deps -T --entrypoint python web scripts/media_archive.py backup"
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
    "failure", ["MOCK_WORKER_EXIT", "MOCK_TUNNEL_EXIT", "MOCK_PUBLIC_EXIT"]
)
def test_deployment_failure_stops_tunnel_and_does_not_report_success(tmp_path, failure):
    result, commands = run_script(tmp_path, "scripts/deploy.sh", [], **{failure: 1})
    assert result.returncode != 0
    assert "Deployment erfolgreich geprüft".encode() not in result.stdout
    assert commands.splitlines()[-1].endswith("stop cloudflared")
    assert not (Path(__file__).resolve().parents[1] / ".deployment-lock").exists()
