"""Start the installed API once, against the PCS files in ``data/``.

The process is ``python -m address_validation``, the same entry point a
fresh virtualenv runs. The suite waits until ``/api/v1/ready`` reports
that the extract and the suggestion index are loaded, then sends queries
over HTTP.
"""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest

_REPO = Path(__file__).resolve().parents[2]
_DATA_DIR = _REPO / "data"
_FILES = ("PCS_HNR.dat", "PCS_STR.dat", "PCS_WPL.dat")
_READY_TIMEOUT_S = 30


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _stop(process: subprocess.Popen[str]) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


@pytest.fixture(scope="session")
def api_client(tmp_path_factory: pytest.TempPathFactory) -> Iterator[httpx.Client]:
    """HTTP client for a server loaded with the real PCS files."""
    missing = [name for name in _FILES if not (_DATA_DIR / name).is_file()]
    if missing:
        pytest.skip("PCS data files not present: " + ", ".join(missing))

    port = _free_port()
    log_path = tmp_path_factory.mktemp("functional-api") / "server.log"
    log_file = log_path.open("w", encoding="utf-8")
    env = os.environ.copy()
    env["ADDRESS_HOST"] = "127.0.0.1"
    env["ADDRESS_PORT"] = str(port)
    env["ADDRESS_DATA_DIR"] = str(_DATA_DIR)
    env["PYTHONUNBUFFERED"] = "1"
    process = subprocess.Popen(
        [sys.executable, "-m", "address_validation"],
        cwd=_REPO,
        env=env,
        stdout=log_file,
        stderr=subprocess.STDOUT,
        text=True,
    )
    base = f"http://127.0.0.1:{port}"
    deadline = time.monotonic() + _READY_TIMEOUT_S
    ready = False
    try:
        while time.monotonic() < deadline:
            if process.poll() is not None:
                break
            try:
                response = httpx.get(f"{base}/api/v1/ready", timeout=1)
            except httpx.HTTPError:
                time.sleep(0.2)
                continue
            if response.status_code == 200 and response.json().get("ready") is True:
                ready = True
                break
            time.sleep(0.2)
        if not ready:
            _stop(process)
            log_file.close()
            tail = log_path.read_text(encoding="utf-8")[-4000:]
            pytest.fail(f"API did not become ready at {base}\n{tail}")
        with httpx.Client(base_url=base, timeout=30) as client:
            yield client
    finally:
        _stop(process)
        if not log_file.closed:
            log_file.close()
