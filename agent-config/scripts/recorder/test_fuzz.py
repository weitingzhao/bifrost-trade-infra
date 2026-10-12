"""Fixed-seed fuzz. Counts are the design's unless RECORDER_FUZZ_N scales them.

Families keep the ratio 4000:5000:8000:1500:1500. Seed 20261011.
"""

from __future__ import annotations

import os
import random

from publish import publish_total
from read import fold_total

_FULL = {"A": 4000, "B": 5000, "C": 8000, "D": 1500, "E": 1500}
_RATIO = 20000


def _count(family: str) -> int:
    raw = os.environ.get("RECORDER_FUZZ_N")
    if not raw:
        return _FULL[family]
    total = int(raw)
    return max(1, _FULL[family] * total // _RATIO)


def _rng(family: str) -> random.Random:
    seed = os.environ.get("RECORDER_FUZZ_SEED", "20261011")
    return random.Random(f"{seed}:{family}")


def _exercise(rng: random.Random, n: int, kind: str) -> int:
    largest = 0
    for index in range(n):
        if kind == "A":
            blob = bytes(rng.getrandbits(8) for _ in range(rng.randrange(0, 80)))
        elif kind == "B":
            blob = rng.randbytes(rng.randrange(0, 200)) if hasattr(rng, "randbytes") else bytes(rng.getrandbits(8) for _ in range(rng.randrange(0, 200)))
        elif kind == "C":
            text = "".join(chr(rng.randrange(32, 127)) for _ in range(rng.randrange(0, 120)))
            blob = text.encode()
        elif kind == "D":
            blob = b'{"at":1,"by":"coordinator","prev_sha256":"","seq":1,"text":"n","type":"note","v":2}\n'
            if rng.randrange(2):
                blob = blob[: rng.randrange(len(blob))]
        else:
            blob = bytes(rng.getrandbits(8) for _ in range(rng.randrange(0, 40)))
        largest = max(largest, len(blob))
        now = (1, 10**6, -1)[index % 3]
        folded = fold_total([("w1", blob)], [], now)
        assert type(folded.document()) is dict
        raw = publish_total(folded, "board")
        assert type(raw) is bytes
    return largest


def test_fuzz_a_random_bytes():
    assert _exercise(_rng("A"), _count("A"), "A") >= 0


def test_fuzz_b_random_bytes():
    assert _exercise(_rng("B"), _count("B"), "B") >= 0


def test_fuzz_c_random_text():
    assert _exercise(_rng("C"), _count("C"), "C") >= 0


def test_fuzz_d_torn_json():
    assert _exercise(_rng("D"), _count("D"), "D") >= 0


def test_fuzz_e_random_bytes():
    assert _exercise(_rng("E"), _count("E"), "E") >= 0


def test_fuzz_sample_two_hundred_pass_handleput(tmp_path):
    """Two hundred fixed-seed outputs, plus the fallback fixtures, go through HandlePut."""
    import subprocess
    from test_publish import FIXTURES, PLATFORM

    if not PLATFORM.is_dir():
        raise AssertionError("没有跑")
    written = 0
    for family in "ABCDE":
        rng = _rng(family)
        for index in range(40):
            if family == "A":
                blob = bytes(rng.getrandbits(8) for _ in range(rng.randrange(0, 80)))
            elif family == "B":
                blob = rng.randbytes(rng.randrange(0, 200))
            elif family == "C":
                blob = "".join(chr(rng.randrange(32, 127)) for _ in range(rng.randrange(0, 120))).encode()
            elif family == "D":
                blob = b'{"at":1,"by":"coordinator","prev_sha256":"","seq":1,"text":"n","type":"note","v":2}\n'
                if rng.randrange(2):
                    blob = blob[: rng.randrange(len(blob))]
            else:
                blob = bytes(rng.getrandbits(8) for _ in range(rng.randrange(0, 40)))
            raw = publish_total(fold_total([("w1", blob)], [], (1, 10**6, -1)[index % 3]), "board")
            (tmp_path / f"{family}-{index:02d}.json").write_bytes(raw)
            written += 1
    assert written == 200
    for name in (
        "fallback-argument.json",
        "fallback-fold-caught.json",
        "fallback-publish-caught.json",
        "fallback-last-resort.json",
    ):
        target = tmp_path / name
        target.write_bytes((FIXTURES / name).read_bytes())
    env = os.environ.copy()
    env["RECORDER_FIXTURES"] = str(tmp_path)
    env["GOMAXPROCS"] = "2"
    proc = subprocess.run(
        ["go", "test", "-count=1", "-timeout=120s", "-run", "TestRecorderFixturesPassHandlePut", "./internal/agentprogress/"],
        cwd=PLATFORM / "api",
        env=env,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
