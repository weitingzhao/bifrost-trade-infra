"""Coordinator entry point; the recorder is used exclusively through its CLI."""
from __future__ import annotations

import argparse
import ctypes
import fcntl
import io
import json
import math
import os
import re
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

REC = Path(__file__).with_name("rec.py")
ANNOUNCEMENT = re.compile(r"^run: step (\S+) output (.+)$", re.MULTILINE)


class LaneError(Exception):
    pass


def has_control(text):
    return any(ord(ch) < 32 or 127 <= ord(ch) <= 159 or ord(ch) in (0x2028, 0x2029, 0x202E)
               for ch in text)


def rec(root, *args):
    result = subprocess.run([sys.executable, str(REC), "--root", str(root), *args],
                            capture_output=True, text=True)
    if result.returncode:
        raise LaneError(f"{args[0]} failed ({result.returncode}): {result.stderr.strip()}")
    if result.stderr:
        print(result.stderr, file=sys.stderr, end="")
    return result.stdout


def pid_start(pid):
    """Kernel process identity: Linux start ticks or macOS seconds/microseconds."""
    try:
        if sys.platform.startswith("linux"):
            fields = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()
            if fields[0] == "Z":
                return None
            return fields[19]
        if sys.platform == "darwin":
            # proc_bsdinfo from sys/proc_info.h (PROC_PIDTBSDINFO = 3).
            class BSDInfo(ctypes.Structure):
                _fields_ = [("header", ctypes.c_uint32 * 12),
                            ("comm", ctypes.c_char * 16), ("name", ctypes.c_char * 32),
                            ("tail", ctypes.c_uint32 * 6),
                            ("seconds", ctypes.c_uint64), ("micros", ctypes.c_uint64)]
            info = BSDInfo()
            lib = ctypes.CDLL("/usr/lib/libproc.dylib")
            call = lib.proc_pidinfo
            call.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_uint64,
                             ctypes.c_void_p, ctypes.c_int]
            call.restype = ctypes.c_int
            size = ctypes.sizeof(info)
            if call(pid, 3, 0, ctypes.byref(info), size) != size or info.header[1] == 5:
                return None
            return f"{info.seconds}:{info.micros}"
        return None  # Unsupported platforms fail closed.
    except (OSError, IndexError):
        return None


def lanes(root, update=None):
    path = root / "lanes.json"
    if update is None:
        if not path.exists():
            return {}
        with path.open() as stream:
            fcntl.flock(stream, fcntl.LOCK_SH)
            return json.load(stream)
    with path.open("a+") as stream:
        fcntl.flock(stream, fcntl.LOCK_EX)
        stream.seek(0)
        data = json.load(io.StringIO(stream.read() or "{}"))
        data.update(update)
        stream.seek(0)
        stream.truncate()
        json.dump(data, stream, sort_keys=True)
        stream.flush()
    return data


def start(root, args):
    if args.kind not in ("implement", "verify", "review", "merge", "other"):
        raise LaneError("--kind must be implement, verify, review, merge, or other")
    for key in ("name", "who"):
        value = getattr(args, key)
        if len(value) > 80:
            raise LaneError(f"--{key} must be at most 80 characters")
        if has_control(value):
            raise LaneError(f"--{key} must not contain a control character")
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not command:
        raise LaneError("start requires -- <command>")
    root.mkdir(parents=True, exist_ok=True)
    doc = json.load(io.StringIO(rec(root, "fold")))
    work = next((w for w in doc["works"] if w["work_id"] == args.work), None)
    if work is None:
        rec(root, "open", "--work", args.work, "--title", args.title)
    elif "closed_claim" in work:
        raise LaneError("work is closed")
    # A regular file avoids keeping a caller's pipe open or blocking the wrapper
    # after start exits. The recorder's child has its own output files.
    with tempfile.TemporaryFile(mode="w+b", dir=root) as output:
        wrapper = subprocess.Popen(
            [sys.executable, str(REC), "--root", str(root), "run", "--work", args.work,
             "--name", args.name, "--kind", args.kind, "--who", args.who, "--", *command],
            stdin=subprocess.DEVNULL, stdout=output, stderr=output,
            start_new_session=True, preexec_fn=lambda: signal.signal(signal.SIGHUP, signal.SIG_IGN))
        started = pid_start(wrapper.pid)
        deadline = time.monotonic() + 5
        match = None
        wrapper_output = ""
        while time.monotonic() < deadline:
            # pread leaves the inherited writer offset untouched.
            wrapper_output = os.pread(output.fileno(), 65536, 0).decode("utf-8", "replace")
            match = ANNOUNCEMENT.search(wrapper_output)
            if match:
                break
            time.sleep(.02)
        result = dict(work=args.work, step_id=match[1] if match else None,
                      output_dir=match[2] if match else None, wrapper_pid=wrapper.pid,
                      recorded="start not recorded" not in wrapper_output)
        # Retain even a timed-out dispatch, keyed by PID until a step is known.
        key = result["step_id"] or f"pending:{wrapper.pid}"
        lanes(root, {key: dict(result, wrapper_start=started, name=args.name,
                               who=args.who, usual_min=args.usual_min)})
        print(json.dumps(result))
        return 0 if match and result["recorded"] else 3


def record(root, args):
    quote = args.quote
    if quote is not None:
        lines = quote.splitlines()
        quote = lines[0] if lines else ""
        quote = "".join(ch for ch in quote if not has_control(ch))[:200]
    event = json.load(io.StringIO(rec(root, "declare", "--work", args.work, "--name", args.name,
                           "--kind", args.kind, "--who", args.who, "--watch", "none")))
    step = event["step_id"]
    finish = ["finish", "--work", args.work, "--step", step, "--reported",
              "finished" if args.result == "done" else "failed"]
    if quote is not None:
        finish += ["--quote", quote]
    try:
        rec(root, "start", "--work", args.work, "--step", step)
        result = rec(root, *finish)
    except (LaneError, OSError, ValueError) as exc:
        raise LaneError(f"step {step} left behind: {exc}") from exc
    print(result, end="")
    return 0


def stop(root, args):
    entry = lanes(root).get(args.step)
    if not entry or entry.get("wrapper_start") is None:
        print("wrapper is gone", file=sys.stderr)
        return 4
    pid = entry["wrapper_pid"]
    if not isinstance(pid, int) or pid <= 0 or pid_start(pid) != entry["wrapper_start"]:
        print("wrapper is gone", file=sys.stderr)
        return 4
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        print("wrapper is gone", file=sys.stderr)
        return 4
    return 0


def status(root, args):
    rec(root, "observe")
    doc = json.load(io.StringIO(rec(root, "fold")))
    metadata = lanes(root)
    now = time.time()
    steps = []
    unrecorded = []
    for work in doc["works"]:
        if work.get("unrecorded_runs"):
            unrecorded.append(dict(work=work["work_id"], title=work.get("title", work["work_id"]),
                                   unrecorded_runs=work["unrecorded_runs"]))
        for step in work["steps"]:
            if "ended" in step:
                continue
            usual = metadata.get(step["step_id"], {}).get("usual_min")
            if usual is None and "usual_s" in step:
                usual = step["usual_s"] / 60
            dead = step["state"] == "dead"
            since = step.get("since") if dead else step.get("started", step.get("since"))
            elapsed = max(0, now - since) if since is not None else None
            steps.append(dict(work=work["work_id"], title=work.get("title", work["work_id"]),
                              step_id=step["step_id"], name=step["name"], who=step["who"],
                              state=step["state"], since=since, elapsed_s=elapsed,
                              usual_min=usual, over=bool(not dead and usual is not None and elapsed is not None
                                                        and elapsed > 2 * usual * 60)))
    owners = doc["owner_all"]
    if args.json:
        print(json.dumps(dict(steps=steps, owners=owners, unrecorded=unrecorded)))
    else:
        for step in steps:
            elapsed = (f'since {step["since"]}' if step["state"] == "dead" else
                       "unknown" if step["elapsed_s"] is None else f'{step["elapsed_s"]:.1f}s')
            usual = "unknown" if step["usual_min"] is None else f'{step["usual_min"]:g}m'
            print(f'{step["title"]} | {step["name"]} | {step["who"]} | {step["state"]}'
                  f' | {elapsed} | usual {usual}' + (" | OVER" if step["over"] else ""))
        for owner in owners:
            print(f'Owner | {owner["title"]} | since {owner["since"]}')
        for work in unrecorded:
            print(f'{work["title"]} | work {work["work"]} | unrecorded runs {work["unrecorded_runs"]}')
    return 0


def positive(value):
    number = float(value)
    if not math.isfinite(number) or number <= 0:
        raise argparse.ArgumentTypeError("usual-min must be finite and positive")
    return number


def main(argv=None):
    parser = argparse.ArgumentParser(prog="lane.py")
    parser.add_argument("--root", default=None)
    sub = parser.add_subparsers(dest="action", required=True)
    for action in ("start", "record"):
        p = sub.add_parser(action)
        for key in ("work", "name", "kind", "who"):
            p.add_argument("--" + key, required=True)
        if action == "start":
            p.add_argument("--title", required=True)
            p.add_argument("--usual-min", type=positive)
            p.add_argument("command", nargs=argparse.REMAINDER)
        else:
            p.add_argument("--result", choices=("done", "failed"), required=True)
            p.add_argument("--quote")
    sub.add_parser("stop").add_argument("--step", required=True)
    sub.add_parser("status").add_argument("--json", action="store_true")
    # Owner arguments belong to rec.py; forwarding the original tokens preserves
    # both its validation and its output, without duplicating the schema.
    for action in ("owner-open", "owner-close"):
        sub.add_parser(action, add_help=False)
    tokens = list(sys.argv[1:] if argv is None else argv)
    args, extra = parser.parse_known_args(tokens)
    root = Path(args.root or os.environ.get("BIFROST_RECORDER_ROOT")
                or "~/agent-work/recorder-root").expanduser().resolve()
    try:
        if args.action in ("owner-open", "owner-close"):
            result = subprocess.run([sys.executable, str(REC), "--root", str(root), args.action, *extra])
            return result.returncode
        if extra:
            parser.error("unrecognized arguments: " + " ".join(extra))
        return {"start": start, "record": record, "stop": stop, "status": status}[args.action](root, args)
    except (LaneError, OSError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
