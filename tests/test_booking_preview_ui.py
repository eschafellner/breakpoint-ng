import re
import shutil
import subprocess
from pathlib import Path

import pytest
from django.urls import reverse


@pytest.mark.django_db
def test_rendered_booking_price_preview(client, court_sand, guest_user):
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js required for booking preview JavaScript tests")
    client.force_login(guest_user)
    response = client.get(reverse("courts:calendar"))
    assert response.status_code == 200
    scripts = re.findall(
        r"<script>(.*?)</script>", response.content.decode(), flags=re.DOTALL
    )
    script = next(script for script in scripts if "function updatePrice" in script)
    result = subprocess.run(
        [node, str(Path(__file__).with_name("booking_price_preview.js"))],
        input=script,
        text=True,
        encoding="utf-8",
        capture_output=True,
        timeout=10,
    )
    assert result.returncode == 0, result.stdout + result.stderr
