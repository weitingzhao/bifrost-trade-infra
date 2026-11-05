#!/usr/bin/env python3
"""R5:5.7-6 S0b fetch: read the night-shift sources into one JSON snapshot.

Read-only on every source: the infra CI PipelineRuns and the log lines of each
failed run's first failing step (kubectl), landing and card events and the
coordinator's hand-ins (psql as a read-only role), infra main's first-parent
history (git) and the card lists exported from the platform's list_questions
and list_requests tools. A source that cannot be read is stored as null with
its reason, so night_metrics.py reports Unknown for what needs it, never 0.
"""
import argparse
import json
import os
import re
import runpy
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

M = runpy.run_path(str(Path(__file__).with_name("night_metrics.py")))
moment_of, iso_z, within = M["moment_of"], M["iso_z"], M["within"]
FAIL_LINE = re.compile(r"^(FAIL|FAILED|E) ")
DEFAULT_PG = "host=192.168.10.73 port=30432 user=agent_reader dbname=bifrost_platform"
SQL = {
    "events": """select coalesce(json_agg(t order by t.event_id), '[]'::json) from (
  select event_id, event_stream_id as stream, seq, at, actor_id as actor, task_id, body_json as body
  from agentrt.event
  where (event_stream_id like 'landing:%' or event_stream_id like 'landing-cards:%')
    and not body_json ? 'landing_main' and at >= :'since' and at < :'until') t;""",
    "tasks": """select coalesce(json_agg(t order by t.created_at), '[]'::json) from (
  select task_id, repo, state, created_at, updated_at, title, plan_node_id, round_no
  from agentrt.task
  where task_class = 'handin' and created_by_actor_id = 'seat:coordinator'
    and created_at >= :'since' and created_at < :'until') t;""",
    "verifications": """select coalesce(json_agg(t order by t.created_at), '[]'::json) from (
  select v.verification_id, v.task_id, v.method, v.verdict, v.created_at, a.attempt_no
  from agentrt.verification v
  join agentrt.task k on k.task_id = v.task_id
  left join agentrt.attempt a on a.attempt_id = v.attempt_id
  where k.task_class = 'handin' and k.created_by_actor_id = 'seat:coordinator'
    and k.created_at >= :'since' and k.created_at < :'until') t;""",
}
QUESTION_FIELDS = ("id", "number", "status", "title", "task_id", "created_at", "owner_duty")
APPROVAL_FIELDS = ("id", "number", "action", "tier", "status", "env", "created_at", "decided_at", "summary")


class FetchError(Exception):
    pass


def shell_out(argv, stdin=None):
    done = subprocess.run(argv, input=stdin, capture_output=True, text=True, check=False)
    if done.returncode:
        raise FetchError(f"{Path(argv[0]).name} exit={done.returncode}: {done.stderr.strip()[:300]}")
    return done.stdout


def run_row(item):
    meta, status = item["metadata"], item.get("status") or {}
    cond = (status.get("conditions") or [{}])[0]
    results = status.get("results") or status.get("pipelineResults") or []
    return {"name": meta["name"], "uid": meta.get("uid"), "created": meta.get("creationTimestamp"),
            "started": status.get("startTime"), "completed": status.get("completionTime"),
            "status": cond.get("status"), "reason": cond.get("reason"),
            "purpose": (meta.get("labels") or {}).get("bifrost.io/purpose"),
            "params": {p["name"]: p.get("value") for p in (item.get("spec") or {}).get("params", [])},
            "results": {r["name"]: r.get("value") for r in results}, "fail": None}


def first_fail(kubectl, run, runner):
    """The first failing step in pipeline order, with its first FAIL / pytest E lines."""
    try:
        items = json.loads(runner(kubectl + ["get", "taskrun", "-l", f"tekton.dev/pipelineRun={run}",
                                             "-o", "json"]))["items"]
    except (FetchError, ValueError, KeyError) as exc:
        return {"source": "unavailable", "why": str(exc)[:200]}
    order = {"resolve": 0, "clone": 1, "check": 2}
    items.sort(key=lambda t: order.get((t["metadata"].get("labels") or {}).get("tekton.dev/pipelineTask"), 9))
    for item in items:
        status = item.get("status") or {}
        task = (item["metadata"].get("labels") or {}).get("tekton.dev/pipelineTask")
        for step in status.get("steps") or []:
            if (step.get("terminated") or {}).get("exitCode", 0) == 0:
                continue
            found = {"task": task, "step": step.get("name"), "lines": []}
            try:
                log = runner(kubectl + ["logs", status.get("podName", ""), "-c", step.get("container", "")])
            except FetchError as exc:
                return found | {"source": "unavailable", "why": str(exc)[:200]}
            found["lines"] = [line.rstrip()[:300] for line in log.splitlines() if FAIL_LINE.match(line)][:10]
            return found | {"source": "pod-log"}
    return {"source": "no-failed-step"}


def fetch_runs(args, since, until, runner=shell_out):
    kubectl = [args.kubectl, "-n", args.namespace]
    if args.kubeconfig:
        kubectl += ["--kubeconfig", args.kubeconfig]
    elif not os.environ.get("KUBECONFIG"):
        raise FetchError("no --kubeconfig and no KUBECONFIG: the default context is not the cluster")
    raw = json.loads(runner(kubectl + ["get", "pipelinerun", "-l", "tekton.dev/pipeline=bifrost-ci-infra",
                                       "-o", "json"]))
    rows = sorted((run_row(item) for item in raw.get("items", [])), key=lambda r: r["created"] or "")
    for row in rows:
        if not args.no_logs and row["status"] == "False" and within(moment_of(row["created"]), (since, until)):
            row["fail"] = first_fail(kubectl, row["name"], runner)
    return rows


def fetch_db(args, since, until, runner=shell_out):
    out = {}
    for name, sql in SQL.items():
        text = runner([args.psql, "-X", "-A", "-t", "-q", "-v", "ON_ERROR_STOP=1", "-v", f"since={iso_z(since)}",
                       "-v", f"until={iso_z(until)}", "-f", "-", args.pg], stdin=sql)
        out[name] = json.loads(text)
    return out


def fetch_git(args, runner=shell_out):
    git = ["git", "-C", args.git_repo]
    head = runner(git + ["rev-parse", args.git_ref]).strip()
    fmt = "%H%x1f%cI%x1f%aI%x1f%s%x1f%(trailers:key=Landed-By,valueonly,separator=%x2C)%x1e"
    text = runner(git + ["log", "--first-parent", f"-n{args.git_depth}", f"--format={fmt}", head])
    commits = []
    for record in text.split("\x1e"):
        fields = record.strip("\n").split("\x1f")
        if len(fields) == 5:
            sha, committed, authored, subject, landed = fields
            commits.append({"sha": sha, "committed": committed, "authored": authored, "subject": subject,
                            "landed_by": landed.strip()})
    return {"ref": args.git_ref, "head": head, "commits": commits}


def card_projection(path, key, fields):
    rows = []
    for item in json.loads(Path(path).read_text())[key]:
        row = {f: item.get(f) for f in fields}
        if key == "questions":
            answer = item.get("answer") or {}
            row["answered_at"], row["answer_option"] = answer.get("at"), answer.get("option")
        rows.append(row)
    return rows


def snapshot(args, now):
    since, until = moment_of(args.since), moment_of(args.until) or now
    snap = {"schema": M["SNAPSHOT"], "fetched_at": iso_z(now), "since": iso_z(since), "until": iso_z(until),
            "sources": {}}
    steps = {"runs": lambda: fetch_runs(args, since, until), "git": lambda: fetch_git(args),
             "db": lambda: fetch_db(args, since, until),
             "questions": lambda: card_projection(args.questions, "questions", QUESTION_FIELDS)
             if args.questions else None,
             "approvals": lambda: card_projection(args.approvals, "approvals", APPROVAL_FIELDS)
             if args.approvals else None}
    for name, step in steps.items():
        try:
            snap[name] = step()
            snap["sources"][name] = "ok" if snap[name] is not None else "not given"
        except (FetchError, OSError, ValueError, KeyError) as exc:
            snap[name], snap["sources"][name] = None, f"error: {exc}"[:400]
    return snap


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", required=True)
    ap.add_argument("--since", required=True, help="ISO time; failed runs' logs and DB rows from here")
    ap.add_argument("--until", help="ISO time (default: now)")
    ap.add_argument("--kubectl", default="kubectl")
    ap.add_argument("--kubeconfig")
    ap.add_argument("--namespace", default="cicd")
    ap.add_argument("--no-logs", action="store_true", help="skip reading failing steps' logs")
    ap.add_argument("--psql", default="psql")
    ap.add_argument("--pg", default=DEFAULT_PG, help="libpq conninfo of a read-only role")
    ap.add_argument("--git-repo", default=".")
    ap.add_argument("--git-ref", default="origin/main")
    ap.add_argument("--git-depth", type=int, default=3000)
    ap.add_argument("--questions", help="list_questions(status=all) output, as JSON")
    ap.add_argument("--approvals", help="list_requests(status=all) output, as JSON")
    args = ap.parse_args(argv)
    snap = snapshot(args, datetime.now(timezone.utc))
    Path(args.out).write_text(json.dumps(snap, indent=1, sort_keys=True, ensure_ascii=False) + "\n")
    for name, state in snap["sources"].items():
        print(f"{name}: {state}")
    return 0 if all(v == "ok" for v in snap["sources"].values()) else 1


if __name__ == "__main__":
    sys.exit(main())
