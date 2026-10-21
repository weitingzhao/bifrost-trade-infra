"""TD-411: STG's deliver pipeline runs the agentrt migrations before it rolls out;
PROD's refuses to roll out a build whose migrations its database has not applied.

The inline scripts run here as the pipeline runs them: STG's against a fake
kubectl, PROD's against a local HTTP server standing in for PROD's /health."""

import hashlib
import http.server
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import threading

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
TEKTON = ROOT / "k8s/cicd/tekton"
STG_PIPELINE = TEKTON / "pipeline-deliver-platform.yaml"
PROD_PIPELINE = TEKTON / "pipeline-deliver-platform-prod.yaml"
TASK = TEKTON / "task-agentrt-migrate-stg.yaml"
RBAC = TEKTON / "rbac-deliver-migrate-stg.yaml"
STG_JOB = ROOT / "k8s/agentrt-migrate/stg/job.yaml"
DIGEST = "sha256:" + "ab" * 32
RUN = "bifrost-deliver-platform-run-x1"


def tasks(path):
    return {t["name"]: t for t in yaml.safe_load(path.read_text())["spec"]["tasks"]}


def before(pipeline, name):
    """Every task a task waits for, directly or through others."""
    seen, todo = set(), list(pipeline[name].get("runAfter", []))
    while todo:
        t = todo.pop()
        if t not in seen:
            seen.add(t)
            todo.extend(pipeline[t].get("runAfter", []))
    return seen


# --- STG: the pipeline runs the migrations before anything moves ------------


def test_stg_pipeline_migrates_before_sync_and_rollout():
    p = tasks(STG_PIPELINE)
    m = p["agentrt-migrate"]
    assert m["taskRef"] == {"name": "bifrost-agentrt-migrate-stg"}
    assert m["runAfter"] == ["build-platform-api"]
    assert m["params"] == [{"name": "apiDigest", "value": "$(tasks.build-platform-api.results.digest)"}]
    assert "agentrt-migrate" in p["gitops-sync"]["runAfter"]
    for t in ("gitops-sync", "rollout"):
        assert "agentrt-migrate" in before(p, t), t


def task_spec():
    doc = yaml.safe_load(TASK.read_text())
    assert doc["kind"] == "Task" and doc["metadata"] == {
        "name": "bifrost-agentrt-migrate-stg",
        "namespace": "cicd",
        "labels": {"bifrost.io/purpose": "platform-deliver"},
    }
    return doc["spec"]


def stg_script():
    (step,) = task_spec()["steps"]
    return step["script"]


def test_stg_task_is_stg_only():
    spec = task_spec()
    # The namespace is not a param: nothing a caller passes moves the Job elsewhere.
    assert [p["name"] for p in spec["params"]] == ["apiDigest"]
    (step,) = spec["steps"]
    assert step["env"] == [
        {"name": "API_DIGEST", "value": "$(params.apiDigest)"},
        {"name": "DELIVER_RUN", "value": "$(context.pipelineRun.name)"},
    ]
    s = step["script"]
    assert 'NS = "bifrost-platform-stg"' in s
    for word in ("prod", "PROD"):
        assert word not in s


def embedded_job():
    s = stg_script()
    body = s.split('JOB = """\\\n', 1)[1].split('"""', 1)[0]
    return yaml.safe_load(body)


def test_stg_job_is_the_owners_job_but_the_image():
    ours = embedded_job()
    owners = yaml.safe_load(STG_JOB.read_text())
    assert ours["metadata"].pop("annotations") == {"bifrost.io/deliver-run": "__RUN__"}
    (ours_c,) = ours["spec"]["template"]["spec"]["containers"]
    (owners_c,) = owners["spec"]["template"]["spec"]["containers"]
    assert ours_c.pop("image") == "__IMAGE__"
    assert owners_c.pop("image") == "192.168.10.73:30500/bifrost-platform-api:stg"
    assert ours == owners


FAKE_KUBECTL = r'''#!/usr/bin/env python3
import json, os, sys
log = os.environ["FAKE_LOG"]
mode = os.environ.get("FAKE_MODE", "ok")
args = sys.argv[1:]
stdin = sys.stdin.read() if args[:1] == ["create"] else ""
with open(log, "a") as f:
    f.write(json.dumps({"args": args, "stdin": stdin}) + "\n")
if args[:1] == ["create"]:
    if mode == "create-fails":
        print("forbidden", file=sys.stderr); sys.exit(1)
    print("agentrt-migrate-abc12", end="")
elif args[:1] == ["get"]:
    status = {"failed": 1} if mode == "job-fails" else {"succeeded": 1}
    print(json.dumps({"status": status}))
elif args[:1] == ["logs"]:
    if mode == "no-applied":
        print("agentrt-migrate: something else")
    elif mode == "job-fails":
        print("agentrt-migrate: migrate: 0009_x: syntax error")
    else:
        print("agentrt-migrate: env=stg database=bifrost_platform_stg applied=[7 8] seeded=false")
'''


def run_stg(tmp_path, mode="ok", digest=DIGEST, run=RUN):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    fake = bin_dir / "kubectl"
    fake.write_text(FAKE_KUBECTL)
    fake.chmod(0o755)
    script = tmp_path / "migrate.py"
    script.write_text(stg_script())
    log = tmp_path / "calls.jsonl"
    env = {**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}", "FAKE_LOG": str(log), "FAKE_MODE": mode,
           "API_DIGEST": digest, "DELIVER_RUN": run}
    out = subprocess.run([sys.executable, str(script)], env=env, capture_output=True, text=True, timeout=60)
    calls = [json.loads(line) for line in log.read_text().splitlines()] if log.exists() else []
    return out, calls


def test_stg_runs_the_job_with_the_built_image(tmp_path):
    out, calls = run_stg(tmp_path)
    assert out.returncode == 0, out.stdout + out.stderr
    assert "agentrt migrations applied on STG by agentrt-migrate-abc12: 7, 8" in out.stdout
    create = calls[0]
    assert create["args"] == ["create", "-f", "-", "-o", "jsonpath={.metadata.name}"]
    job = yaml.safe_load(create["stdin"])
    assert job["metadata"]["namespace"] == "bifrost-platform-stg"
    assert job["metadata"]["annotations"] == {"bifrost.io/deliver-run": RUN}
    (c,) = job["spec"]["template"]["spec"]["containers"]
    assert c["image"] == "192.168.10.73:30500/bifrost-platform-api@" + DIGEST
    assert {e["name"]: e.get("value") for e in c["env"]}["PGUSER"] == "agentrt_owner_stg"
    assert all(call["args"][call["args"].index("-n") + 1] == "bifrost-platform-stg"
               for call in calls[1:])


@pytest.mark.parametrize(
    "mode, says",
    [
        ("job-fails", "Job agentrt-migrate-abc12 failed"),
        ("no-applied", "does not say what it applied"),
        ("create-fails", "the Job was not created: forbidden"),
    ],
)
def test_stg_stops_the_run(tmp_path, mode, says):
    out, _ = run_stg(tmp_path, mode)
    assert out.returncode == 1
    assert says in out.stdout and "nothing is rolled out" in out.stdout
    if mode == "job-fails":
        assert "0009_x: syntax error" in out.stdout  # the Job's log is in the run's


@pytest.mark.parametrize("digest, run", [("sha256:" + "AB" * 32, RUN), ("latest", RUN), (DIGEST, "Bad_Name"), (DIGEST, "")])
def test_stg_refuses_bad_input_before_any_call(tmp_path, digest, run):
    out, calls = run_stg(tmp_path, digest=digest, run=run)
    assert out.returncode == 1 and calls == []


def test_stg_rbac_is_jobs_and_logs_in_stg_only():
    docs = list(yaml.safe_load_all(RBAC.read_text()))
    assert [d["kind"] for d in docs] == ["Role", "RoleBinding"]
    role, binding = docs
    assert role["metadata"] == {"name": "tekton-deliver-migrate", "namespace": "bifrost-platform-stg"}
    assert role["rules"] == [
        {"apiGroups": ["batch"], "resources": ["jobs"], "verbs": ["create", "get"]},
        {"apiGroups": [""], "resources": ["pods/log"], "verbs": ["get"]},
    ]
    assert binding["metadata"] == role["metadata"]
    assert binding["roleRef"] == {"apiGroup": "rbac.authorization.k8s.io", "kind": "Role", "name": "tekton-deliver-migrate"}
    assert binding["subjects"] == [{"kind": "ServiceAccount", "name": "tekton-deliver", "namespace": "cicd"}]
    assert "bifrost-platform-prod" not in yaml.safe_dump_all(docs)


# --- PROD: no rollout over a database that misses this build's migrations ---


def test_prod_pipeline_checks_before_rollout():
    p = tasks(PROD_PIPELINE)
    c = p["agentrt-schema"]
    assert c["runAfter"] == ["build-platform-api"]
    assert c["workspaces"] == [{"name": "source", "workspace": "build-context"}]
    assert c["params"] == [{"name": "apiDigest", "value": "$(tasks.build-platform-api.results.digest)"}]
    assert "agentrt-schema" in p["rollout"]["runAfter"]
    assert "agentrt-schema" in before(p, "gitops-sync")
    # PROD gets no migration step and no Job: the Owner's stays the only one.
    assert not any(t.get("taskRef", {}).get("name") == "bifrost-agentrt-migrate-stg" for t in p.values())
    s = prod_script()
    assert "subprocess" not in s and "kubectl create -f -" in s  # only in the command it prints


def prod_script():
    (step,) = tasks(PROD_PIPELINE)["agentrt-schema"]["taskSpec"]["steps"]
    assert step["env"] == [{"name": "API_DIGEST", "value": "$(params.apiDigest)"}]
    return step["script"]


def migrations(tmp_path, names=("0001_core", "0002_guards", "0003_grants")):
    d = tmp_path / "migrations"
    d.mkdir(exist_ok=True)
    for n in names:
        (d / f"{n}.sql").write_text(f"-- {n}\n")
    (d / "embed.go").write_text("package migrations\n")
    return d


def applied_of(d, skip=(), edit=()):
    out = []
    for f in sorted(d.glob("*.sql")):
        n = int(f.name[:4])
        if n in skip:
            continue
        sha = hashlib.sha256(f.read_bytes()).hexdigest()
        out.append({"id": n, "sha256": ("0" * 64 if n in edit else sha)})
    return out


@pytest.fixture
def health():
    """A /health server; set .body to what it answers."""
    class H(http.server.BaseHTTPRequestHandler):
        body = {}

        def do_GET(self):
            raw = json.dumps(H.body).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(raw)

        def log_message(self, *_):
            pass

    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    H.url = f"http://127.0.0.1:{srv.server_address[1]}/health"
    yield H
    srv.shutdown()


def run_prod(tmp_path, d, url, digest=DIGEST):
    script = tmp_path / "check.py"
    script.write_text(prod_script())
    env = {**os.environ, "API_DIGEST": digest, "MIGRATIONS_DIR": str(d), "HEALTH_URL": url}
    return subprocess.run([sys.executable, str(script)], env=env, capture_output=True, text=True, timeout=60)


def test_prod_passes_when_every_migration_is_applied(tmp_path, health):
    d = migrations(tmp_path)
    health.body = {"status": "ok", "agentrt_schema": "current", "agentrt_schema_applied": applied_of(d)}
    out = run_prod(tmp_path, d, health.url)
    assert out.returncode == 0, out.stdout
    assert "PROD's database has all 3 this build carries (0001_core, 0002_guards, 0003_grants)" in out.stdout


def test_prod_passes_an_older_build_and_says_so(tmp_path, health):
    d = migrations(tmp_path, ("0001_core", "0002_guards"))
    (tmp_path / "x").mkdir()
    extra = applied_of(migrations(tmp_path / "x", ("0001_core", "0002_guards", "0003_grants")))
    health.body = {"agentrt_schema": "current", "agentrt_schema_applied": extra}
    out = run_prod(tmp_path, d, health.url)
    assert out.returncode == 0, out.stdout
    assert "does not carry: [3]" in out.stdout


def test_prod_refuses_a_missing_migration_and_names_the_job(tmp_path, health):
    d = migrations(tmp_path)
    health.body = {"agentrt_schema": "current", "agentrt_schema_applied": applied_of(d, skip={3})}
    out = run_prod(tmp_path, d, health.url)
    assert out.returncode == 1
    assert "PROD's database misses 0003_grants, which this build carries" in out.stdout
    assert ("sed 's#image: 192.168.10.73:30500/bifrost-platform-api:prod#image: 192.168.10.73:30500/"
            "bifrost-platform-api@" + DIGEST + "#' k8s/agentrt-migrate/prod/job.yaml | kubectl create -f -") in out.stdout
    # The command it prints edits exactly the PROD Job's image line.
    assert "image: 192.168.10.73:30500/bifrost-platform-api:prod" in (ROOT / "k8s/agentrt-migrate/prod/job.yaml").read_text()


def test_prod_refuses_an_edited_migration(tmp_path, health):
    d = migrations(tmp_path)
    health.body = {"agentrt_schema": "edited", "agentrt_schema_applied": applied_of(d, edit={2})}
    out = run_prod(tmp_path, d, health.url)
    assert out.returncode == 1 and "other bytes for 0002_guards" in out.stdout


@pytest.mark.parametrize(
    "body, says",
    [
        ({"status": "ok", "agentrt_schema": "current"}, "does not say which migrations"),
        ({"agentrt_schema": "unknown"}, "does not say which migrations"),
        ({"agentrt_schema_applied": [{"id": True, "sha256": "0" * 64}]}, "not an id and a sha256"),
        ({"agentrt_schema_applied": [{"id": 1, "sha256": "short"}]}, "not an id and a sha256"),
        ({"agentrt_schema_applied": ["0001"]}, "not an id and a sha256"),
    ],
)
def test_prod_refuses_a_health_it_cannot_read(tmp_path, health, body, says):
    d = migrations(tmp_path)
    health.body = body
    out = run_prod(tmp_path, d, health.url)
    assert out.returncode == 1 and says in out.stdout


def test_prod_refuses_a_bad_digest_and_an_empty_tree(tmp_path, health):
    d = migrations(tmp_path)
    health.body = {"agentrt_schema_applied": applied_of(d)}
    assert run_prod(tmp_path, d, health.url, digest="latest").returncode == 1
    empty = tmp_path / "empty"
    empty.mkdir()
    out = run_prod(tmp_path, empty, health.url)
    assert out.returncode == 1 and "carries no migrations" in out.stdout


def test_prod_refuses_when_health_is_unreachable(tmp_path):
    d = migrations(tmp_path)
    out = run_prod(tmp_path, d, "http://127.0.0.1:9/health")
    assert out.returncode == 1 and "could not be read" in out.stdout


def test_prod_reads_the_real_source_layout():
    # The script reads the migrations where clone-platform puts bifrost-platform.
    p = tasks(PROD_PIPELINE)
    sub = {x["name"]: x["value"] for x in p["clone-platform"]["params"]}["subdir"]
    assert sub == "bifrost-platform"
    assert 'SRC = "/workspace/source/bifrost-platform/api/internal/agentrt/migrations"' in prod_script()
    assert re.search(r'FILE_RE = re\.compile\(r"\(\[0-9\]\{4\}\)_', prod_script())
