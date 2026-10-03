#!/usr/bin/env python3
"""Helpers behind the release scripts (TD-84): Tekton run state, the PROD pinned spec,
before/after snapshots of the Trade API, their diff, /health core identity and probes.

Read-only towards the cluster and the gateways: it runs `kubectl get` and HTTP GETs only.
Creating runs is left to release.sh, which prints or runs `kubectl create` itself.

Subcommands (all print to stdout; errors to stderr):
  deliver-busy [--recent-seconds N]        exit 1 if a bifrost-deliver-* run is Unknown or new
  run-state <run>                          print "<status> <reason> <pipeline>" of a PipelineRun
  clone-commits <run>                      print "<pipelineTask> <sha>" for each clone-* TaskRun
  timings <run>                            print each TaskRun's duration and the run's total
  wait <run> [--timeout S] [--interval S]  poll until the run leaves Unknown; exit 0 on success
  pinned-spec <stg-run> --template F [-o F] [--pipeline NAME]
  snapshot <env> -o F [--accounts a,b]     GET executions / performance / model-analysis
  diff <before> <after> [--allow F ...] [--json F]
  health <env> --expect-sha SHA [--core-repo DIR] [--json F]
  probes <env> --file F [--file F ...]
  core-sha <env>                           print the core_sha /api/monitor/health reports
  db-steps <env> --dir D [--done-file F] [--when before|after] [--list]
                                           print pending one-off DB steps; exit 1 if any
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Tuple

from release_checks import (  # same directory
    SHA_RE,
    cmd_core_sha,
    cmd_diff,
    cmd_health,
    cmd_probes,
    cmd_snapshot,
    die,
)

NAMESPACE = os.environ.get("CICD_NAMESPACE", "cicd")
os.environ.setdefault("KUBECONFIG", os.path.expanduser("~/.kube/bifrost-k3s.yaml"))

# ── kubectl (read-only) ──────────────────────────────────────────────────────


def kget(*args: str) -> Any:
    cmd = ["kubectl", "-n", NAMESPACE, "get", *args, "-o", "json"]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        die(f"{' '.join(cmd)} failed: {proc.stderr.strip()}")
    return json.loads(proc.stdout)


def parse_ts(value: Optional[str]) -> Optional[float]:
    if not value:
        return None
    return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc).timestamp()


def condition(obj: Dict[str, Any]) -> Tuple[str, str]:
    conds = (obj.get("status") or {}).get("conditions") or []
    succeeded = next((c for c in conds if c.get("type") == "Succeeded"), conds[0] if conds else None)
    if not succeeded:
        return "Unknown", "Pending"
    return succeeded.get("status", "Unknown"), succeeded.get("reason", "")


def pipeline_of(run: Dict[str, Any]) -> str:
    spec = run.get("spec") or {}
    if (spec.get("pipelineRef") or {}).get("name"):
        return spec["pipelineRef"]["name"]
    return "an inline pipelineSpec"


def fmt_dur(seconds: Optional[float]) -> str:
    if seconds is None:
        return "-"
    seconds = int(round(seconds))
    return f"{seconds // 60}m{seconds % 60:02d}s"


def cmd_deliver_busy(args: argparse.Namespace) -> int:
    runs = kget("pipelineruns")["items"]
    now = time.time()
    busy = []
    for run in runs:
        name = run["metadata"]["name"]
        if not name.startswith("bifrost-deliver-"):
            continue
        status, reason = condition(run)
        created = parse_ts(run["metadata"].get("creationTimestamp")) or now
        age = now - created
        if status == "Unknown":
            busy.append(f"{name}  running ({reason or 'Unknown'}), created {fmt_dur(age)} ago")
        elif age < args.recent_seconds:
            busy.append(f"{name}  {reason}, created only {fmt_dur(age)} ago (another session may be releasing)")
    if busy:
        print("deliver runs in the way:")
        for line in busy:
            print("  " + line)
        return 1
    print(f"no bifrost-deliver-* run is running or newer than {args.recent_seconds}s")
    return 0


def cmd_run_state(args: argparse.Namespace) -> int:
    run = kget("pipelinerun", args.run)
    status, reason = condition(run)
    print(status, reason or "-", pipeline_of(run))
    return 0


def child_taskruns(run: Dict[str, Any]) -> Dict[str, str]:
    """pipelineTaskName -> TaskRun name, from status.childReferences (fallback <run>-<task>)."""
    out: Dict[str, str] = {}
    for ref in (run.get("status") or {}).get("childReferences") or []:
        if ref.get("kind") == "TaskRun" and ref.get("pipelineTaskName"):
            out[ref["pipelineTaskName"]] = ref["name"]
    return out


def clone_commits(run_name: str, tasks: Optional[Iterable[str]] = None) -> Dict[str, Optional[str]]:
    run = kget("pipelinerun", run_name)
    children = child_taskruns(run)
    wanted = list(tasks) if tasks is not None else sorted(t for t in children if t.startswith("clone-"))
    trs = {tr["metadata"]["name"]: tr for tr in kget("taskruns", "-l", f"tekton.dev/pipelineRun={run_name}")["items"]}
    out: Dict[str, Optional[str]] = {}
    for task in wanted:
        tr = trs.get(children.get(task, f"{run_name}-{task}"))
        results = ((tr or {}).get("status") or {}).get("results") or []
        out[task] = next((r.get("value") for r in results if r.get("name") == "commit"), None)
    return out


def cmd_clone_commits(args: argparse.Namespace) -> int:
    commits = clone_commits(args.run)
    if not commits:
        die(f"{args.run}: no clone-* TaskRuns")
    bad = 0
    for task, sha in commits.items():
        print(task, sha or "MISSING")
        bad += 0 if sha and SHA_RE.match(sha.strip()) else 1
    return 1 if bad else 0


def print_timings(run_name: str) -> None:
    run = kget("pipelinerun", run_name)
    trs = kget("taskruns", "-l", f"tekton.dev/pipelineRun={run_name}")["items"]
    rows = []
    for tr in trs:
        st = tr.get("status") or {}
        start, end = parse_ts(st.get("startTime")), parse_ts(st.get("completionTime"))
        task = (tr["metadata"].get("labels") or {}).get("tekton.dev/pipelineTask", tr["metadata"]["name"])
        rows.append((start or 0, task, fmt_dur(end - start if start and end else None), condition(tr)[1]))
    rows.sort()
    width = max([5, *(len(r[1]) for r in rows)])
    for _, task, dur, reason in rows:
        print(f"  {task:<{width}}  {dur:>7}  {reason}")
    st = run.get("status") or {}
    start, end = parse_ts(st.get("startTime")), parse_ts(st.get("completionTime"))
    status, reason = condition(run)
    total = (end or time.time()) - start if start else None
    print(f"  {'total':<{width}}  {fmt_dur(total):>7}  {reason or status}")


def cmd_timings(args: argparse.Namespace) -> int:
    print(f"{args.run}:")
    print_timings(args.run)
    return 0


def cmd_wait(args: argparse.Namespace) -> int:
    deadline = time.time() + args.timeout
    last = None
    started = time.time()
    while True:
        run = kget("pipelinerun", args.run)
        status, reason = condition(run)
        done = {ref.get("pipelineTaskName") for ref in (run.get("status") or {}).get("childReferences") or []}
        line = f"{status} {reason} ({len(done)} tasks started)"
        if line != last:
            print(f"[{fmt_dur(time.time() - started)}] {args.run}: {line}", flush=True)
            last = line
        if status != "Unknown":
            break
        if time.time() > deadline:
            print(f"timed out after {args.timeout}s; the run is still going — do not start another", file=sys.stderr)
            return 3
        time.sleep(args.interval)
    print(f"{args.run}: {reason}")
    print_timings(args.run)
    return 0 if status == "True" else 1


# ── PROD pinned spec ─────────────────────────────────────────────────────────


def cmd_pinned_spec(args: argparse.Namespace) -> int:
    stg = kget("pipelinerun", args.stg_run)
    status, reason = condition(stg)
    if pipeline_of(stg) != "bifrost-deliver-stg":
        die(f"REFUSED: {args.stg_run} is a run of {pipeline_of(stg)}, not bifrost-deliver-stg", 1)
    if status != "True":
        die(f"REFUSED: {args.stg_run} did not succeed ({status} {reason})", 1)

    pipeline = kget("pipeline", args.pipeline)
    spec = pipeline["spec"]
    clone_tasks = [t for t in spec.get("tasks", []) if t["name"].startswith("clone-")]
    if not clone_tasks:
        die(f"REFUSED: pipeline/{args.pipeline} has no clone-* tasks", 1)
    commits = clone_commits(args.stg_run, [t["name"] for t in clone_tasks])
    problems = [f"{task}: {sha!r}" for task, sha in commits.items() if not (sha and SHA_RE.match(sha))]
    if problems:
        die("REFUSED: STG run lacks a full commit for: " + ", ".join(problems), 1)

    for task in clone_tasks:
        params = task.setdefault("params", [])
        rev = next((p for p in params if p["name"] == "revision"), None)
        if rev is None:
            die(f"REFUSED: {task['name']} has no revision param in pipeline/{args.pipeline}", 1)
        rev["value"] = commits[task["name"]]

    with open(args.template) as fh:
        template = json.load(fh)
    tspec = template["spec"]
    run = {
        "apiVersion": "tekton.dev/v1",
        "kind": "PipelineRun",
        "metadata": {
            "generateName": "bifrost-deliver-prod-pinned-",
            "namespace": NAMESPACE,
            "labels": {
                "bifrost.io/purpose": "prod-pinned",
                "bifrost.io/from-stg-run": args.stg_run,
            },
        },
        "spec": {
            "params": [{"name": "revision", "value": "main"}],
            "pipelineSpec": spec,
            **{k: tspec[k] for k in ("taskRunSpecs", "taskRunTemplate", "timeouts", "workspaces") if k in tspec},
        },
    }
    text = json.dumps(run, indent=2) + "\n"
    if args.output:
        with open(args.output, "w") as fh:
            fh.write(text)
    else:
        sys.stdout.write(text)
    for task, sha in commits.items():
        print(f"{task} {sha}", file=sys.stderr)
    return 0


# ── one-off DB steps registry ────────────────────────────────────────────────


def read_step(path: str) -> Dict[str, Any]:
    with open(path) as fh:
        text = fh.read()
    meta: Dict[str, Any] = {"file": path, "body": text}
    m = re.match(r"^---\n(.*?)\n---\n?(.*)$", text, re.S)
    if not m:
        die(f"{path}: no front matter (--- id/envs/when/done ---)")
    for line in m.group(1).splitlines():
        line = line.split("#", 1)[0]
        if ":" in line:
            k, v = line.split(":", 1)
            meta[k.strip()] = v.strip()
    meta["body"] = m.group(2)
    for k in ("id", "envs", "when"):
        if not meta.get(k):
            die(f"{path}: front matter lacks '{k}'")
    if meta["when"] not in ("before", "after"):
        die(f"{path}: when must be before or after, got {meta['when']!r}")
    return meta


def env_section(body: str, env: str) -> str:
    """The '## <env>' section of a step file, or the whole body when it has none."""
    m = re.search(rf"^##\s+{re.escape(env)}\b.*?$(.*?)(?=^##\s|\Z)", body, re.M | re.S)
    return (m.group(0) if m else body).strip()


def cmd_db_steps(args: argparse.Namespace) -> int:
    done = set()
    if args.done_file and os.path.exists(args.done_file):
        with open(args.done_file) as fh:
            for line in fh:
                parts = line.split()
                if len(parts) >= 2:
                    done.add((parts[0], parts[1]))
    files = sorted(f for f in os.listdir(args.dir) if f.endswith(".md") and f != "README.md")
    pending = 0
    for f in files:
        step = read_step(os.path.join(args.dir, f))
        envs = step["envs"].split()
        if args.env not in envs or (args.when and step["when"] != args.when):
            continue
        is_done = args.env in step.get("done", "").split() or (args.env, step["id"]) in done
        if args.list:
            print(
                f"{'done   ' if is_done else 'PENDING'} {args.env:<4} {step['when']:<6} {step['id']}  ({step['file']})"
            )
            continue
        if is_done:
            continue
        pending += 1
        print(f"── {step['id']} ({step['when']} the {args.env} deliver) — {step['file']}")
        print(env_section(step["body"], args.env))
        print()
    return 1 if pending and not args.list else 0


def main(argv: List[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("deliver-busy")
    p.add_argument("--recent-seconds", type=int, default=120)
    p.set_defaults(fn=cmd_deliver_busy)
    for name, fn in (("run-state", cmd_run_state), ("clone-commits", cmd_clone_commits), ("timings", cmd_timings)):
        p = sub.add_parser(name)
        p.add_argument("run")
        p.set_defaults(fn=fn)
    p = sub.add_parser("wait")
    p.add_argument("run")
    p.add_argument("--timeout", type=int, default=3600)
    p.add_argument("--interval", type=int, default=15)
    p.set_defaults(fn=cmd_wait)
    p = sub.add_parser("pinned-spec")
    p.add_argument("stg_run")
    p.add_argument("--template", required=True)
    p.add_argument("--pipeline", default="bifrost-deliver-prod")
    p.add_argument("-o", "--output")
    p.set_defaults(fn=cmd_pinned_spec)
    p = sub.add_parser("snapshot")
    p.add_argument("env")
    p.add_argument("-o", "--output", required=True)
    p.add_argument("--accounts")
    p.set_defaults(fn=cmd_snapshot)
    p = sub.add_parser("diff")
    p.add_argument("before")
    p.add_argument("after")
    p.add_argument("--allow", action="append")
    p.add_argument("--json")
    p.set_defaults(fn=cmd_diff)
    p = sub.add_parser("health")
    p.add_argument("env")
    p.add_argument("--expect-sha", required=True)
    p.add_argument("--core-repo")
    p.add_argument("--json")
    p.set_defaults(fn=cmd_health)
    p = sub.add_parser("probes")
    p.add_argument("env")
    p.add_argument("--file", action="append", required=True)
    p.set_defaults(fn=cmd_probes)

    p = sub.add_parser("core-sha")
    p.add_argument("env")
    p.set_defaults(fn=cmd_core_sha)
    p = sub.add_parser("db-steps")
    p.add_argument("env")
    p.add_argument("--dir", required=True)
    p.add_argument("--done-file")
    p.add_argument("--when", choices=("before", "after"))
    p.add_argument("--list", action="store_true", help="list every step for env with its state")
    p.set_defaults(fn=cmd_db_steps)

    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
