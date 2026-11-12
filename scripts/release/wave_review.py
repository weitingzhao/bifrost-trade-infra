#!/usr/bin/env python3
"""Wave review table: what one cleanup / release wave cost, from CI to PROD.

Reads (never writes) the cluster's PipelineRuns in `cicd`, the `reuse` TaskRuns of
platform CI, main's first-parent history in local checkouts, and approval cards the
caller passes in. Prints a Markdown table and keeps a JSON snapshot of what it read,
so a later review still has the runs after the TTL janitor deletes them.

    # a time window (Chicago time unless the value carries an offset) and/or commits
    python3 scripts/release/wave_review.py --since '2026-11-12 08:51' --until '2026-11-12 10:47' \
        --sha ab4c2fba --sha 06c63320 --sha 568cc4ab --sha f3bc0a69 \
        --git infra=. --git platform=../bifrost-platform \
        --cards 460-466 --approvals-json cards.json --label cleanup-wave-2

    # the same table again from a snapshot, offline
    python3 scripts/release/wave_review.py --from-snapshot <file> --since ... --until ...

Approval cards: the platform's approval API has no read path without a token, and this
script reads no token. Pass the cards as JSON (`--approvals-json`: a list of records as
`get_request` / `list_requests` return them, or `{"approvals": [...]}`); `--cards` alone
lists the numbers without their action types.

Pushes to main: Gitea's API needs credentials for these repositories, so pushes are
inferred from webhook CI runs whose base and revision both lie on main's first-parent
chain (one run per push), next to the first-parent commit count in the window (an
upper bound). `--skip-tests`: push-main.sh keeps no record, so the table says so.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import subprocess
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

SCHEMA = "wave-review/1"
CT = ZoneInfo("America/Chicago")
ZERO_SHA = "0" * 40
PARAM_KEYS = ("revision", "commit", "base", "infraRevision", "uiRevision", "mode", "path", "purpose")
RESULT_KEYS = ("api-scope", "tested-by")
LABEL_KEYS = ("bifrost.io/repo", "bifrost.io/purpose", "bifrost.io/mode", "triggers.tekton.dev/eventlistener")
CI_REPO = {"bifrost-ci-infra": "infra", "bifrost-ci-platform": "platform"}
DEFAULT_ARCHIVE = Path.home() / "agent-work" / "wave-review"


def parse_time(text: str, tz: dt.tzinfo = CT) -> dt.datetime:
    value = dt.datetime.fromisoformat(text.strip().replace("Z", "+00:00"))
    return value if value.tzinfo else value.replace(tzinfo=tz)


def iso(value: dt.datetime | None) -> str:
    return value.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ") if value else ""


def ct(value: dt.datetime | None) -> str:
    return value.astimezone(CT).strftime("%m-%d %H:%M:%S") if value else "-"


def span(seconds: float | None) -> str:
    if seconds is None:
        return "-"
    s = int(round(seconds))
    h, rest = divmod(s, 3600)
    return f"{h}h{rest // 60:02d}m{rest % 60:02d}s" if h else f"{rest // 60}m{rest % 60:02d}s"


def when(text: str | None) -> dt.datetime | None:
    return parse_time(text, dt.timezone.utc) if text else None


# ---------------------------------------------------------------- collection (read-only)

def kubectl_json(kubeconfig: str, namespace: str, *args: str) -> dict:
    cmd = ["kubectl", "--kubeconfig", kubeconfig, "-n", namespace, "get", *args, "-o", "json"]
    return json.loads(subprocess.run(cmd, check=True, capture_output=True, text=True).stdout)


def trim_run(item: dict) -> dict:
    meta, status = item["metadata"], item.get("status") or {}
    params = {p["name"]: p["value"] for p in item.get("spec", {}).get("params", []) or []
              if p["name"] in PARAM_KEYS and isinstance(p.get("value"), str)}
    results = {r["name"]: r["value"] for r in status.get("results", []) or []
               if r["name"] in RESULT_KEYS and isinstance(r.get("value"), str)}
    cond = (status.get("conditions") or [{}])[0]
    labels = meta.get("labels") or {}
    return {
        "name": meta["name"],
        "pipeline": labels.get("tekton.dev/pipeline", ""),
        "created": meta.get("creationTimestamp", ""),
        "started": status.get("startTime", ""),
        "completed": status.get("completionTime", ""),
        "result": cond.get("reason", "Unknown"),
        "params": params,
        "results": results,
        "labels": {k: labels[k] for k in LABEL_KEYS if k in labels},
        "approval": (meta.get("annotations") or {}).get("bifrost.io/approval-id", ""),
    }


def reuse_results(taskruns: dict) -> dict:
    out = {}
    for item in taskruns.get("items", []):
        run = (item["metadata"].get("labels") or {}).get("tekton.dev/pipelineRun")
        values = {r["name"]: r.get("value", "") for r in (item.get("status") or {}).get("results", []) or []}
        if run:
            out[run] = {"reuse": values.get("reuse", ""), "tested-by": values.get("tested-by", "")}
    return out


def first_parent(path: str, since: dt.datetime) -> list:
    out = subprocess.run(["git", "-C", path, "log", "--first-parent", "--format=%H %cI", "origin/main",
                          f"--since={iso(since)}"], check=True, capture_output=True, text=True).stdout
    return [line.split(" ", 1) for line in out.splitlines() if line.strip()]


def collect(kubeconfig: str, namespace: str, gits: dict, since: dt.datetime | None) -> dict:
    runs = [trim_run(i) for i in kubectl_json(kubeconfig, namespace, "pipelinerun").get("items", [])]
    reuse = reuse_results(kubectl_json(kubeconfig, namespace, "taskrun", "-l", "tekton.dev/pipelineTask=reuse"))
    for run in runs:
        if run["name"] in reuse:
            run["reuse"] = reuse[run["name"]]
    horizon = (since or dt.datetime.now(dt.timezone.utc)) - dt.timedelta(days=3)
    return {
        "schema": SCHEMA,
        "captured_at": iso(dt.datetime.now(dt.timezone.utc)),
        "namespace": namespace,
        "oldest_run": min((r["created"] for r in runs if r["created"]), default=""),
        "runs": runs,
        "git": {repo: first_parent(path, horizon) for repo, path in gits.items()},
    }


def merge_archive(snapshot: dict, archive: Path, skip: Path | None = None) -> dict:
    """Runs kept by earlier snapshots in `archive` are added when the cluster no longer has them."""
    names = {r["name"] for r in snapshot["runs"]}
    oldest = snapshot.get("oldest_run", "")
    added = 0
    for f in sorted(archive.iterdir()) if archive.is_dir() else []:
        if f.suffix != ".json" or f == skip:
            continue
        try:
            old = json.loads(f.read_text())
        except (OSError, ValueError):
            continue
        if old.get("schema") != SCHEMA:
            continue
        for run in old.get("runs", []):
            if run["name"] not in names:
                snapshot["runs"].append(dict(run, source=f.name))
                names.add(run["name"])
                added += 1
        if old.get("oldest_run") and (not oldest or old["oldest_run"] < oldest):
            oldest = old["oldest_run"]
    snapshot["archive_runs"] = added
    snapshot["archive_oldest_run"] = oldest
    return snapshot


# ---------------------------------------------------------------- selection and summary

def kind(run: dict) -> str:
    p, name = run["pipeline"], run["name"]
    if p == "bifrost-ci-platform":
        return "landing-ci" if name.startswith("landing-ci-") else "ci-platform"
    if p == "bifrost-apply-manifest":
        return "apply-manifest/" + run["params"].get("mode", "?")
    return {"bifrost-ci-infra": "ci-infra", "bifrost-deliver-platform": "deliver-platform (STG)",
            "bifrost-deliver-platform-prod": "deliver-platform-prod (PROD)"}.get(p, p or "other")


def primary_revision(run: dict) -> str:
    return run["params"].get("revision") or run["params"].get("commit") or ""


def select(runs: list, since: dt.datetime | None, until: dt.datetime | None, shas: list) -> list:
    out = []
    for run in runs:
        created = when(run["created"])
        if since and (not created or created < since):
            continue
        if until and (not created or created > until):
            continue
        rev = primary_revision(run)
        if shas and not any(rev.startswith(s) for s in shas):
            continue
        out.append(run)
    return sorted(out, key=lambda r: (r["created"], r["name"]))


def duration(run: dict) -> float | None:
    start, end = when(run["started"] or run["created"]), when(run["completed"])
    return (end - start).total_seconds() if start and end else None


def reuse_of(run: dict) -> tuple[str, str]:
    r = run.get("reuse") or {}
    tested_by = r.get("tested-by") or run["results"].get("tested-by", "")
    reused = r.get("reuse") or ("yes" if tested_by else ("no" if "tested-by" in run["results"] else ""))
    return reused, tested_by


def pushes(runs: list, git: dict) -> dict:
    """Webhook CI runs whose base and revision are both on main's first-parent chain: one per push."""
    out = {}
    for repo, chain in git.items():
        on_main = {sha for sha, _ in chain}
        hits = [r["name"] for r in runs if CI_REPO.get(r["pipeline"]) == repo
                and r["labels"].get("triggers.tekton.dev/eventlistener")
                and r["params"].get("revision") in on_main and r["params"].get("base") in on_main]
        out[repo] = hits
    return out


def commits_in(chain: list, since: dt.datetime | None, until: dt.datetime | None) -> int:
    return sum(1 for _, t in chain if (not since or parse_time(t) >= since) and (not until or parse_time(t) <= until))


def card_range(text: str) -> list:
    out = []
    for part in filter(None, (p.strip().lstrip("#") for p in text.split(","))):
        lo, _, hi = part.partition("-")
        out.extend(range(int(lo), int(hi.lstrip("#") or lo) + 1))
    return out


def load_approvals(path: str) -> list:
    data = json.loads(Path(path).read_text())
    rows = data.get("approvals", data) if isinstance(data, dict) else data
    return [{k: a.get(k) for k in ("number", "action", "tier", "env", "runner", "status",
                                     "created_at", "decided_at", "summary")} for a in rows]


def pick_cards(approvals: list, numbers: list, since, until) -> list:
    if numbers:
        known = {a["number"]: a for a in approvals}
        return [known.get(n, {"number": n}) for n in sorted(set(numbers))]
    return sorted((a for a in approvals if a.get("created_at")
                   and (not since or when(a["created_at"]) >= since) and (not until or when(a["created_at"]) <= until)),
                  key=lambda a: a["number"])


def summarize(runs: list, cards: list, git: dict, since, until) -> dict:
    by = lambda k: [r for r in runs if kind(r) == k]  # noqa: E731
    ci = [r for r in runs if kind(r) in ("ci-platform", "landing-ci", "ci-infra")]
    prod = [r for r in by("deliver-platform-prod (PROD)") if r["completed"]]
    first = min((when(r["started"] or r["created"]) for r in ci), default=None)
    last = max((when(r["completed"]) for r in prod), default=None)
    plat = by("ci-platform")
    return {
        "first_ci_start": iso(first), "prod_done": iso(last),
        "first_ci_to_prod_s": (last - first).total_seconds() if first and last else None,
        "platform_ci": len(plat),
        "platform_ci_full": [r["name"] for r in plat if reuse_of(r)[0] != "yes"],
        "platform_ci_reused": [r["name"] for r in plat if reuse_of(r)[0] == "yes"],
        "landing_ci": [r["name"] for r in by("landing-ci")],
        "infra_ci": [(r["name"], r["result"]) for r in by("ci-infra")],
        "stg": [(r["name"], duration(r), r["result"]) for r in by("deliver-platform (STG)")],
        "prod": [(r["name"], duration(r), r["result"]) for r in by("deliver-platform-prod (PROD)")],
        "apply_plan": len(by("apply-manifest/plan")), "apply_apply": len(by("apply-manifest/apply")),
        "cards": cards,
        "pushes": pushes(runs, git),
        "main_commits": {repo: commits_in(chain, since, until) for repo, chain in git.items()},
    }


# ---------------------------------------------------------------- rendering

def render(label: str, snap: dict, runs: list, s: dict, since, until, shas: list) -> str:
    L = [f"# Wave review: {label}", ""]
    window = f"{ct(since)} → {ct(until)} CT" if since or until else "whole snapshot"
    L.append(f"Window: {window}" + (f"; commits {', '.join(shas)}" if shas else "") + ".")
    oldest = snap.get("archive_oldest_run") or snap.get("oldest_run")
    L.append(f"Data: {len(runs)} runs selected; snapshot {snap.get('captured_at', '?')}, "
             f"oldest run on record {oldest or '?'}"
             + (f", {snap.get('archive_runs')} runs from earlier snapshots" if snap.get("archive_runs") else "") + ".")
    if since and oldest and since < when(oldest):
        L.append("")
        L.append("**Run records expired**: the window starts before the oldest run the cluster (or an earlier "
                 "snapshot) still holds; runs before " + ct(when(oldest)) + " CT are missing"
                 + (" and none were found." if not runs else "."))
    L += ["", "## Runs", "",
          "| run | kind | revision | start (CT) | duration | result | reuse / tested-by | api-scope |",
          "|---|---|---|---|---|---|---|---|"]
    for r in runs:
        reused, tested_by = reuse_of(r)
        reuse_cell = f"{reused} / {tested_by or '-'}" if reused else "-"
        L.append(f"| {r['name']} | {kind(r)} | {primary_revision(r)[:8] or '-'} | {ct(when(r['started'] or r['created']))} "
                 f"| {span(duration(r))} | {r['result']} | {reuse_cell} | {r['results'].get('api-scope') or '-'} |")
    if not runs:
        L.append("| (none) | | | | | | | |")
    fmt = lambda rows: ", ".join(f"{n} {span(d)} {res}" for n, d, res in rows) or "none"  # noqa: E731
    infra_red = [n for n, res in s["infra_ci"] if res != "Succeeded"]
    cards = s["cards"]
    kinds: dict = {}
    for c in cards:
        kinds[c.get("action") or "unknown"] = kinds.get(c.get("action") or "unknown", 0) + 1
    mac = [c for c in cards if c.get("runner") == "owner"]
    push_cells = []
    for repo, hits in sorted(s["pushes"].items()):
        push_cells.append(f"{repo} {len(hits)} (CI-inferred: {', '.join(hits) or 'none'}; "
                          f"{s['main_commits'].get(repo, 0)} first-parent commits, approx.)")
    L += ["", "## Summary", "", "| item | value |", "|---|---|",
          f"| first CI start → PROD done | {span(s['first_ci_to_prod_s'])}"
          f" ({ct(when(s['first_ci_start']))} → {ct(when(s['prod_done']))} CT) |",
          f"| platform CI (ci-platform) | {s['platform_ci']}: full {len(s['platform_ci_full'])} "
          f"({', '.join(s['platform_ci_full']) or '-'}), reused {len(s['platform_ci_reused'])} "
          f"({', '.join(s['platform_ci_reused']) or '-'}) |",
          f"| landing CI | {len(s['landing_ci'])} ({', '.join(s['landing_ci']) or '-'}) |",
          f"| infra CI | {len(s['infra_ci'])}" + (f" ({len(infra_red)} not green: {', '.join(infra_red)})" if infra_red else "") + " |",
          f"| STG deliver | {fmt(s['stg'])} |",
          f"| PROD deliver | {fmt(s['prod'])} |",
          f"| apply-manifest | {s['apply_plan']} plan, {s['apply_apply']} apply |",
          f"| Owner cards | {len(cards)}" + (f": {', '.join('#' + str(c['number']) for c in cards)} ("
                                              + ", ".join(f"{k} ×{v}" for k, v in sorted(kinds.items())) + ")" if cards else "")
          + f"; on the Mac terminal (runner owner): {len(mac)}" + (" (types unknown: pass --approvals-json)" if "unknown" in kinds else "") + " |",
          f"| pushes to main | {'; '.join(push_cells) or 'not read (pass --git repo=path)'} |",
          "| --skip-tests | no record: push-main.sh keeps no log of its flags |"]
    return "\n".join(L) + "\n"


def main(argv: list | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--since", help="window start; Chicago time unless it carries an offset or Z")
    ap.add_argument("--until", help="window end")
    ap.add_argument("--sha", action="append", default=[], help="keep runs whose revision/commit starts with it")
    ap.add_argument("--cards", default="", help="approval card numbers, e.g. 460-466,470")
    ap.add_argument("--approvals-json", help="approval records (get_request / list_requests output)")
    ap.add_argument("--git", action="append", default=[], metavar="REPO=PATH", help="checkout to read main from")
    ap.add_argument("--kubeconfig", default=os.environ.get("KUBECONFIG") or str(Path.home() / ".kube/bifrost-k3s.yaml"))
    ap.add_argument("--namespace", default="cicd")
    ap.add_argument("--archive", default=str(DEFAULT_ARCHIVE), help="snapshot directory (read and written)")
    ap.add_argument("--no-archive", action="store_true", help="neither write nor merge snapshots")
    ap.add_argument("--from-snapshot", help="render from this snapshot instead of the cluster")
    ap.add_argument("--label", default="wave")
    ap.add_argument("--json-out", help="also write the summary as JSON here")
    a = ap.parse_args(argv)
    since = parse_time(a.since) if a.since else None
    until = parse_time(a.until) if a.until else None
    shas = [s.lower() for s in a.sha]
    if a.from_snapshot:
        snap = json.loads(Path(a.from_snapshot).read_text())
    else:
        gits = dict(g.split("=", 1) for g in a.git)
        snap = collect(a.kubeconfig, a.namespace, gits, since)
    if a.approvals_json:
        snap["approvals"] = load_approvals(a.approvals_json)
    snap["query"] = {"since": iso(since), "until": iso(until), "shas": shas, "cards": a.cards, "label": a.label}
    written = None
    if not a.from_snapshot and not a.no_archive:
        archive = Path(a.archive).expanduser()
        archive.mkdir(parents=True, exist_ok=True)
        written = archive / f"{snap['captured_at'].replace(':', '')}-{a.label}.json"
        written.write_text(json.dumps(snap, indent=1, ensure_ascii=False))
        merge_archive(snap, archive, skip=written)
    runs = select(snap["runs"], since, until, shas)
    cards = pick_cards(snap.get("approvals", []), card_range(a.cards), since, until)
    summary = summarize(runs, cards, snap.get("git", {}), since, until)
    sys.stdout.write(render(a.label, snap, runs, summary, since, until, shas))
    if written:
        print(f"\nSnapshot: {written}")
    if a.json_out:
        Path(a.json_out).write_text(json.dumps({"query": snap["query"], "runs": runs, "summary": summary},
                                               indent=1, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
