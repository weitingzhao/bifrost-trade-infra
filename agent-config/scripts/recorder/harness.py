"""Event builders shared by the recorder tests. Not part of the recorder."""

from __future__ import annotations

from pathlib import Path

from events import Log, dump_line, seal
from fold import fold

P = "a1b2c3d4"
R = "b1b2c3d4"
N = "c1b2c3d4"
RUN = "d1b2c3d4"
RUN2 = "e1b2c3d4"
WAIT_A = "f1b2c3d4"
WAIT_D = "a2b2c3d4"
APPR = "appr_0123456789abcdef"
QUESTION = "q_0123456789abcdef"
WORK = "w1"
LOCATOR = {"cluster": "prod", "namespace": "cicd", "name": "run-1"}


def ev(seq: int, at: float, typ: str, by: str, **fields) -> dict:
    event = {"type": typ, "v": 1, "seq": seq, "prev_sha256": "", "at": at, "by": by}
    event.update(fields)
    return event


class LogBuilder:
    def __init__(self):
        self.events: list[dict] = []
        self.at = 0

    def add(self, typ: str, by: str, at: float | None = None, **fields) -> dict:
        if at is None:
            self.at += 1
            at = self.at
        else:
            self.at = at
        event = ev(len(self.events) + 1, at, typ, by, **fields)
        self.events.append(event)
        return event


def fold_one(events, now, observer=None, work_id=WORK, **flags) -> dict:
    log = {"work_id": work_id, "events": events}
    log.update(flags)
    return fold([log], observer or [], now)


def work_of(doc, index=0) -> dict:
    return doc["works"][index]


def step_of(doc, index=0, work=0) -> dict:
    return doc["works"][work]["steps"][index]


def save_log(directory: Path, specs: list[tuple]) -> list[dict]:
    """Write a sealed log. ``specs`` are ``(by, at, fields)`` without the envelope."""
    directory.mkdir(parents=True, exist_ok=True)
    log = Log()
    lines = []
    written = []
    for by, at, fields in specs:
        sealed = seal(dict(fields), log, by, at)
        line = dump_line(sealed)
        log.events.append(sealed)
        log.digests.append(line.split(b" ", 1)[0].decode("ascii"))
        lines.append(line)
        written.append(sealed)
    (directory / "events.jsonl").write_bytes(b"".join(lines))
    return written


def opened(work_id=WORK, title="T", **extra) -> dict:
    fields = {"work_id": work_id, "title": title}
    fields.update(extra)
    return fields


def round_for(at: float, confirmed: list, failed: list | None = None, round_id: str = "ab12cd34") -> dict:
    return ev(
        1,
        at,
        "observer_round",
        "observer",
        round_id=round_id,
        started_at=at,
        ended_at=at,
        confirmed=list(confirmed),
        failed=list(failed or []),
    )
