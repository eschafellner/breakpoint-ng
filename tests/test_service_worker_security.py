import shutil
import subprocess
from pathlib import Path

import pytest


def test_worker_preserves_private_data_and_refreshes_emergency_contacts():
    node = shutil.which("node")
    if not node:
        pytest.skip(
            "Node.js is required to execute the service worker regression tests"
        )
    root = Path(__file__).resolve().parent.parent
    result = subprocess.run(
        [node, "tests/service_worker_security.js"],
        cwd=root,
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert result.returncode == 0, result.stdout + result.stderr
