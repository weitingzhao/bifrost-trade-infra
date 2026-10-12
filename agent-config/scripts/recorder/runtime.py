"""Local process adapter. No platform reads, publishing, or execution verdicts."""
from __future__ import annotations

import os
import re
import shlex
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from commands import RecorderError, _new_id, _work_dir, _write, _view
from estimate import usual_for
from events import append_bytes, dump_line, seal
from locks import acquire, hold, probe, release
from fsutil import canonical_json
from model import WORK_ID_RE
from read import fold_total, read_log, round_trip

HEARTBEAT_SECONDS = 60
RUN_NAME = re.compile(r"([0-9a-f]{8})-([0-9a-f]{8})")


def read_root(root: Path):
    """Table C: all directories, empty logs, unread counts, observer files."""
    logs, observer, unread = [], [], 0
    for directory in sorted(root.iterdir()):  # A root failure must reach the CLI.
        if not directory.is_dir():
            continue
        if directory.name == "_observer":
            for path in sorted(directory.iterdir()):
                if path.name == "lock" or not path.is_file():
                    continue
                try:
                    observer.append((path.name, path.read_bytes()))
                except OSError:
                    # No caller-side observer unread parameter: an invalid name
                    # contributes one files_unread through the total fold.
                    observer.append(("unread:" + path.name, b""))
            continue
        try:
            path = directory / "events.jsonl"
            data = path.read_bytes() if path.exists() else b""
            logs.append((directory.name, data))
        except OSError:
            unread += 1
    return logs, observer, unread


def fold_root(root: Path, now: float | None = None):
    logs, observer, unread = read_root(root)
    return fold_total(logs, observer, time.time() if now is None else now, unread).document()


def _text(text: str, limit: int = 200):
    # Output is quoted text; remove characters the event reader disallows.
    return "".join(c for c in text if ord(c) >= 32 and not 127 <= ord(c) <= 159
                   and not 0xD800 <= ord(c) <= 0xDFFF
                   and ord(c) not in {0x2028, 0x2029}
                   and not 0x202A <= ord(c) <= 0x202E
                   and not 0x2066 <= ord(c) <= 0x2069)[:limit]


def _last_line(path: Path):
    with path.open("rb") as stream:
        stream.seek(max(0, path.stat().st_size - 4096))
        lines = stream.read().decode("utf-8", "replace").splitlines()
    return _text(lines[-1]) if lines else ""


def run_process(root: Path, args) -> int:
    command = args.child_command
    if command[:1] == ["--"]:
        command = command[1:]
    if not command:
        raise RecorderError("run requires -- <command>")
    step_id, run_id = _new_id(), _new_id()
    directory = None
    recorded = False
    alive = None
    child = None
    pending_signals = []
    old_handlers = {}

    def forward(signum, _frame):
        if child is None:
            pending_signals.append(signum)
        else:
            try:
                os.killpg(child.pid, signum)
            except ProcessLookupError:
                pass

    def record(fields):
        nonlocal recorded
        if recorded:
            try:
                _write(root, args.work, [fields], "wrapper", "run")
            except (RecorderError, OSError) as exc:
                print(f"run: recording stopped: {exc}", file=sys.stderr)
                recorded = False

    try:
        for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
            if signal.getsignal(sig) is signal.SIG_IGN:
                continue  # An inherited "ignore" (nohup, a background job) stays ignored, for the child too.
            old_handlers[sig] = signal.signal(sig, forward)
        try:
            directory = _work_dir(root, args.work) / "runs" / f"{step_id}-{run_id}"
            directory.parent.mkdir(parents=True, exist_ok=True)
            directory.mkdir()  # Exclusive; never reuse even on an id collision.
            alive = acquire(directory / "alive.lock", "run", timeout=0)
            fields = dict(type="step_declared", step_id=step_id, name=args.name,
                          kind=args.kind, who=args.who, watch="process")
            for key in ("after", "round", "replaces"):
                value = getattr(args, key)
                if value is not None:
                    fields[key] = value
            if args.replaces and args.text is not None:
                fields["replaces_text"] = args.text
            usual = usual_for(root, args.kind)
            if usual is not None:
                fields["usual_s"], fields["usual_basis"] = usual
            started = dict(type="step_started", step_id=step_id, run_id=run_id,
                           command=_text(shlex.join(command)))
            _write(root, args.work, [fields, started], "wrapper", "run")
            recorded = True
        except Exception as exc:  # Whatever bookkeeping raises, the requested command still runs.
            print(f"run: start not recorded; command will run: {exc!r}", file=sys.stderr)
        # Failure to set up the recorder must not suppress the requested child.
        stdout = stderr = None
        try:
            if alive is not None:
                stdout = (directory / "stdout").open("wb")
                stderr = (directory / "stderr").open("wb")
        except OSError as exc:
            if stdout is not None:
                stdout.close()
            stdout = stderr = None
            print(f"run: output files unavailable: {exc}", file=sys.stderr)
        # The wrapper prints nothing else: say where the child's output goes before it starts.
        print(f"run: step {step_id} output {directory if stdout is not None else 'not captured'}", file=sys.stderr)
        try:
            try:
                child = subprocess.Popen(command, stdout=stdout, stderr=stderr,
                                         close_fds=True, start_new_session=True)
            except OSError as exc:
                record(dict(type="step_finished", step_id=step_id, run_id=run_id,
                            exit={"code": 127}, quote=_text(str(exc))))
                return 127
            for sig in pending_signals:
                forward(sig, None)
            while True:
                try:
                    code = child.wait(timeout=HEARTBEAT_SECONDS)
                    break
                except subprocess.TimeoutExpired:
                    seen = dict(type="step_seen", step_id=step_id, run_id=run_id,
                                sampled_at=time.time(), alive=True)
                    if stdout is not None and stderr is not None:
                        seen["output_bytes"] = sum((directory / name).stat().st_size
                                                   for name in ("stdout", "stderr"))
                        seen["text"] = _last_line(directory / "stdout")
                    record(seen)
            ended = dict(type="step_finished", step_id=step_id, run_id=run_id,
                         exit={"code": code} if code >= 0 else
                         {"signal": signal.Signals(-code).name})
            if args.quote_first_line:
                try:
                    with args.quote_first_line.open("rb") as stream:
                        ended["quote"] = _text(stream.readline(4096).decode("utf-8", "replace"))
                except OSError as exc:
                    print(f"run: quote unavailable: {exc}", file=sys.stderr)
            elif stdout is not None:
                ended["quote"] = _last_line(directory / "stdout")
            record(ended)
        finally:
            if stdout is not None:
                stdout.close()
            if stderr is not None:
                stderr.close()
    finally:
        if alive is not None:
            release(alive)
        for sig, handler in old_handlers.items():
            signal.signal(sig, handler)
    if code < 0:
        sig = -code
        if sig not in (signal.SIGKILL, signal.SIGSTOP):
            signal.signal(sig, signal.SIG_DFL)
        os.kill(os.getpid(), sig)  # Preserve wait status, including signal death.
    return code


def _observer_round(root: Path, fields: dict):
    directory = root / "_observer"
    date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    with hold(directory, "observe"):
        for serial in range(1, 10000):
            path = directory / f"{date}-{serial:04d}.jsonl"
            data = path.read_bytes() if path.exists() else b""
            loaded = read_log(path.name, data, observer=True)
            if loaded.broken_line is not None or loaded.torn_tail or loaded.full:
                continue
            event = seal(fields, _view([], loaded.digests), "observer", time.time())
            if round_trip(event):
                raise RecorderError("invalid observer round")
            blob = dump_line(event)
            if len(data) + len(blob) > 4 * 1024 * 1024:
                continue
            append_bytes(path, blob)
            return
    raise RecorderError("observer files full")


def observe(root: Path):
    started = time.time()
    logs, _observer, _unread = read_root(root)
    unrecorded = []
    skipped = False
    truncated = False
    for work_id, data in logs:
        if re.fullmatch(WORK_ID_RE, work_id) is None:
            continue
        loaded = read_log(work_id, data)
        view = loaded.view
        skipped |= any(wait.ref["kind"] != "none"
                       for wait in view.waits.values())
        skipped |= any(step.watch == "record"
                       for step in view.steps.values())
        runs = root / work_id / "runs"
        valid_runs = {(step.step_id, step.run_id) for step in view.steps.values()
                      if step.watch == "process" and step.started}
        for step in view.steps.values():
            if step.watch != "process" or not step.started or step.ended:
                continue
            free, _label = probe(runs / f"{step.step_id}-{step.run_id}" / "alive.lock")
            if free and not step.dead:
                try:
                    _write(root, work_id, [dict(type="step_seen", step_id=step.step_id,
                           run_id=step.run_id, sampled_at=time.time(), alive=False)],
                           "observer", "observe")
                except (RecorderError, OSError) as exc:
                    print(f"observe: append failed for {work_id}/{step.step_id}: {exc}", file=sys.stderr)
        if runs.is_dir():
            for directory in sorted(runs.iterdir()):
                match = RUN_NAME.fullmatch(directory.name)
                if not directory.is_dir() or match is None:
                    continue
                step_id, run_id = match.groups()
                if (step_id, run_id) in valid_runs:
                    continue
                free, _label = probe(directory / "alive.lock")
                if not free:
                    if len(unrecorded) == 400:
                        truncated = True
                        continue
                    unrecorded.append(dict(work_id=work_id, step_id=step_id, run_id=run_id))
    if skipped:
        print("observe: platform references were not read (process-only slice)", file=sys.stderr)
    fields = dict(type="observer_round", round_id=_new_id(), started_at=started,
                  ended_at=time.time(), confirmed=[], failed=[], unrecorded=unrecorded)
    if truncated:
        fields["truncated"] = True
    _observer_round(root, fields)
    print(canonical_json(fields))
