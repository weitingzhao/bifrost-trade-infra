"""The proxy against fake jobs. One job at a time; each job is a process the test starts."""

from __future__ import annotations

import subprocess
import sys
import time
import uuid
from pathlib import Path

PROXY = Path(__file__).resolve().parent / "proxy.py"


def _token() -> str:
    return "sj" + uuid.uuid4().hex[:12]


def _job(token: str, seconds: float) -> subprocess.Popen:
    return subprocess.Popen(
        [sys.executable, "-c", "import time,sys; time.sleep(float(sys.argv[1]))", str(seconds), token]
    )


def _proxy(token: str, done: Path, poll: str) -> subprocess.Popen:
    return subprocess.Popen(
        [sys.executable, str(PROXY), "--pattern", token, "--done", str(done), "--poll", poll]
    )


def test_exit_0(tmp_path):
    token = _token()
    done = tmp_path / "job.done"
    job = _job(token, 0.6)
    proxy = _proxy(token, done, "0.2")
    done.write_text("exit=0\nexit=9\n", encoding="utf-8")
    assert job.wait(timeout=5) == 0
    assert proxy.wait(timeout=5) == 0


def test_exit_9(tmp_path):
    token = _token()
    done = tmp_path / "job.done"
    job = _job(token, 0.4)
    proxy = _proxy(token, done, "0.2")
    done.write_text("noise exit=9 tail\n", encoding="utf-8")
    assert job.wait(timeout=5) == 0
    assert proxy.wait(timeout=5) == 9


def test_marker_before_the_process_is_gone(tmp_path):
    token = _token()
    done = tmp_path / "job.done"
    job = _job(token, 1.2)
    proxy = _proxy(token, done, "0.2")
    done.write_text("exit=0\n", encoding="utf-8")
    time.sleep(0.4)
    assert proxy.poll() is None
    assert job.wait(timeout=5) == 0
    assert proxy.wait(timeout=5) == 0


def test_vanished_without_a_marker(tmp_path):
    token = _token()
    done = tmp_path / "missing.done"
    proxy = _proxy(token, done, "1")
    started = time.monotonic()
    assert proxy.wait(timeout=40) == 70
    elapsed = time.monotonic() - started
    assert elapsed >= 30
    assert elapsed < 36
