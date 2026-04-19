"""
Start the Dash app and open the default browser to the dashboard.

Run from anywhere, e.g.::
    python path/to/vix_dashboard/launcher.py

Or from the repo root (parent of the ``vix_dashboard`` package folder)::
    python vix_dashboard/launcher.py
"""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
import webbrowser
from pathlib import Path

HOST = "127.0.0.1"
PORT = 8050
URL = f"http://{HOST}:{PORT}/"


def _project_root() -> Path:
    """Directory that must be cwd for ``python -m vix_dashboard.main`` (parent of package)."""
    return Path(__file__).resolve().parent.parent


def _wait_for_port(timeout_s: float = 45.0) -> bool:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        try:
            with socket.create_connection((HOST, PORT), timeout=1.0):
                return True
        except OSError:
            time.sleep(0.25)
    return False


def main() -> int:
    root = _project_root()
    if not (root / "vix_dashboard" / "main.py").is_file():
        print(
            "Could not find vix_dashboard package next to this launcher "
            f"(expected {root / 'vix_dashboard' / 'main.py'}).",
            file=sys.stderr,
        )
        return 1

    env = os.environ.copy()
    proc = subprocess.Popen(
        [sys.executable, "-m", "vix_dashboard.main"],
        cwd=str(root),
        env=env,
    )
    if not _wait_for_port():
        print(f"Server did not open {HOST}:{PORT} in time.", file=sys.stderr)
        proc.terminate()
        return 1

    webbrowser.open(URL)
    print(f"Opened {URL} (PID {proc.pid}). Press Ctrl+C to stop.\n")
    try:
        return proc.wait()
    except KeyboardInterrupt:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
        print("\nStopped.")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
