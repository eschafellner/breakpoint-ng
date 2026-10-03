"""Wait for cloudflared's documented connection readiness endpoint."""

import sys
import time
from urllib.error import URLError
from urllib.request import urlopen


def wait_for_tunnel(base_url="http://cloudflared:2000", timeout=90, interval=2):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urlopen(
                base_url + "/ready",
                timeout=min(3, max(0.1, deadline - time.monotonic())),
            ) as response:
                if response.status == 200:
                    return
        except (URLError, TimeoutError, OSError):
            pass
        time.sleep(min(interval, max(0, deadline - time.monotonic())))
    raise RuntimeError(
        "Cloudflare Tunnel ist nicht verbunden; Token, Netzwerk und Tunnel-Logs prüfen"
    )


if __name__ == "__main__":
    try:
        wait_for_tunnel()
        print("OK: Cloudflare Tunnel ist verbunden")
    except RuntimeError as error:
        print(str(error), file=sys.stderr)
        sys.exit(1)
