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


CANDIDATE = "registry.cicd.svc.cluster.local:5000/bifrost-platform-%s:%s-candidate"


def promote_params(env_param_prefix="platform"):
    return [
        {"name": "apiImage", "value": "$(params.platformApiImage)"},
        {"name": "apiDigest", "value": "$(tasks.build-platform-api.results.digest)"},
        {"name": "consoleImage", "value": "$(params.platformConsoleImage)"},
        {"name": "consoleDigest", "value": "$(tasks.build-platform-console.results.digest)"},
    ]


def builds_go_to_candidates(p, env):
    # Review 498 A1: kaniko never pushes the tag the Deployments run.
    for kind in ("api", "console"):
        (image,) = [x["value"] for x in p["build-platform-" + kind]["params"] if x["name"] == "image"]
        assert image == CANDIDATE % (kind, env)


def test_stg_pipeline_migrates_before_promotion_sync_and_rollout():
    p = tasks(STG_PIPELINE)
    m = p["agentrt-migrate"]
    assert m["taskRef"] == {"name": "bifrost-agentrt-migrate-stg"}
    assert m["runAfter"] == ["build-platform-api"]
    assert m["params"] == [
        {"name": "apiDigest", "value": "$(tasks.build-platform-api.results.digest)"},
        {"name": "deliverRun", "value": "$(context.pipelineRun.name)"},
    ]
    builds_go_to_candidates(p, "stg")
    pr = p["promote-images"]
    assert pr["taskRef"] == {"name": "bifrost-promote-platform-images"}
    assert set(pr["runAfter"]) == {"agentrt-migrate", "build-platform-console"}
    assert pr["params"] == promote_params()
    assert p["gitops-sync"]["runAfter"] == ["promote-images"]
    for t in ("gitops-sync", "rollout"):
        assert {"agentrt-migrate", "promote-images"} <= before(p, t), t


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
    assert [p["name"] for p in spec["params"]] == ["apiDigest", "deliverRun"]
    (step,) = spec["steps"]
    assert step["env"] == [
        {"name": "API_DIGEST", "value": "$(params.apiDigest)"},
        {"name": "DELIVER_RUN", "value": "$(params.deliverRun)"},
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


FAKE_KUBECTL = r"""#!/usr/bin/env python3
import json, os, sys
log = os.environ["FAKE_LOG"]
mode = os.environ.get("FAKE_MODE", "ok")
args = sys.argv[1:]
stdin = sys.stdin.read() if args[:1] == ["create"] else ""
with open(log, "a") as f:
    f.write(json.dumps({"args": args, "stdin": stdin}) + "\n")
UID = "uid-1"
count = os.path.join(os.path.dirname(log), "pods-calls")
if args[:1] == ["create"]:
    if mode == "create-fails":
        print("forbidden", file=sys.stderr); sys.exit(1)
    if mode == "create-eof":
        print("error: unexpected EOF", file=sys.stderr); sys.exit(1)
    if mode == "create-hangs":
        import time; time.sleep(5)
    print("agentrt-migrate-abc12", end="")
elif args[:2] == ["get", "job"]:
    conds, counts = {
        "ok": ([("Complete", "True")], {"succeeded": 1}),
        "no-applied": ([("Complete", "True")], {"succeeded": 1}),
        "two-pods": ([("Complete", "True")], {"succeeded": 1}),
        "foreign-pod": ([("Complete", "True")], {"succeeded": 1}),
        "job-fails": ([("Failed", "True")], {"failed": 1}),
        "failed-with-success": ([("Failed", "True")], {"succeeded": 1, "failed": 1}),
        "target-fails": ([("FailureTarget", "True")], {"succeeded": 1}),
        "complete-with-failed": ([("Complete", "True")], {"succeeded": 1, "failed": 1}),
        "pod-late": ([("Complete", "True")], {"succeeded": 1}),
        "pods-flaky": ([("Complete", "True")], {"succeeded": 1}),
        "never-complete": ([], {"active": 1}),
        "create-hangs": ([("Complete", "True")], {"succeeded": 1}),
    }[mode]
    status = dict(counts, conditions=[{"type": t, "status": v} for t, v in conds])
    print(json.dumps({"metadata": {"name": "agentrt-migrate-abc12", "uid": UID}, "status": status}))
elif args[:2] == ["get", "pods"]:
    n = int(open(count).read()) if os.path.exists(count) else 0
    open(count, "w").write(str(n + 1))
    if mode == "pods-flaky" and n == 0:
        print("the server is busy", file=sys.stderr); sys.exit(1)
    if mode == "pod-late" and n == 0:
        print(json.dumps({"items": []})); sys.exit()
    def pod(name, uid, phase):
        return {"metadata": {"name": name, "ownerReferences": [{"kind": "Job", "uid": uid}]}, "status": {"phase": phase}}
    items = [pod("agentrt-migrate-abc12-x", UID, "Failed" if "fail" in mode else "Succeeded")]
    if mode == "two-pods":
        items.append(pod("agentrt-migrate-abc12-y", UID, "Succeeded"))
    if mode == "foreign-pod":
        items = [pod("agentrt-migrate-abc12-x", "another-uid", "Succeeded")]
    print(json.dumps({"items": items}))
elif args[:1] == ["logs"]:
    if mode == "no-applied":
        print("agentrt-migrate: something else")
    elif "fail" in mode:
        print("agentrt-migrate: migrate: 0009_x: syntax error")
    else:
        print("agentrt-migrate: env=stg database=bifrost_platform_stg applied=[7 8] seeded=false")
"""


def run_stg(tmp_path, mode="ok", digest=DIGEST, run=RUN, wait_s=None, call_s=None):
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
    if wait_s:
        env["AGENTRT_MIGRATE_WAIT_S"] = str(wait_s)
    if call_s:
        env["AGENTRT_MIGRATE_CALL_S"] = str(call_s)
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
    assert all(call["args"][call["args"].index("-n") + 1] == "bifrost-platform-stg" for call in calls[1:])
    # the log read is the Job's own succeeded pod's
    assert calls[-1]["args"][:2] == ["logs", "agentrt-migrate-abc12-x"]


def test_stg_run_name_stays_a_string():
    # A run named only with digits would otherwise be read as a number by YAML.
    assert '"__RUN__"' in stg_script()
    job = yaml.safe_load(stg_script().split('JOB = """\\\n', 1)[1].split('"""', 1)[0].replace("__RUN__", "1234"))
    assert job["metadata"]["annotations"]["bifrost.io/deliver-run"] == "1234"


@pytest.mark.parametrize(
    "mode, says",
    [
        ("job-fails", "Job agentrt-migrate-abc12 failed"),
        # Review 498 A2: the Job's verdict is its conditions, not its pod counts.
        ("failed-with-success", "Job agentrt-migrate-abc12 failed"),
        ("target-fails", "Job agentrt-migrate-abc12 failed"),
        ("complete-with-failed", "counts a failed pod"),
        ("two-pods", "with 2 succeeded pods, not one"),
        # Review 500 B2: a pod list without the Job's own pod is read again until the deadline.
        ("foreign-pod", "its succeeded pod could not be read in 3 s"),
        ("no-applied", "does not say what it applied"),
        ("create-fails", "the Job was not created: forbidden"),
    ],
)
def test_stg_stops_the_run(tmp_path, mode, says):
    out, _ = run_stg(tmp_path, mode, wait_s=3 if mode == "foreign-pod" else None)
    assert out.returncode == 1, out.stdout
    assert says in out.stdout and "nothing is rolled out" in out.stdout
    if mode in ("job-fails", "failed-with-success"):
        assert "0009_x: syntax error" in out.stdout  # the Job's log is in the run's


# kubectl's flags that change where it connects or who it is (kubectl options), long and short
CONNECTION_FLAGS = ("--request-timeout", "--server", "-s", "--kubeconfig", "--token", "--context", "--cluster",
                    "--user", "--as", "--as-group", "--as-uid", "--username", "--password", "--certificate-authority",
                    "--client-certificate", "--client-key", "--insecure-skip-tls-verify", "--tls-server-name")


@pytest.mark.parametrize("mode", ["ok", "job-fails", "pods-flaky", "two-pods", "create-fails"])
def test_stg_kubectl_keeps_the_in_cluster_identity(tmp_path, mode):
    """Review 500 A1: with --request-timeout (or --server, --kubeconfig, a token ...) and no
    kubeconfig, kubectl in a pod dials localhost:8080 instead of the in-cluster identity (the
    Owner's trial run, 2026-10-12, test_platform_prod_gate). Every call on the good and the
    refusing paths keeps to the operation's own arguments (review 503 C)."""
    out, calls = run_stg(tmp_path, mode)
    assert out.returncode == (0 if mode in ("ok", "pods-flaky") else 1), out.stdout
    assert calls
    for c in calls:
        a = c["args"]
        assert a[0] in ("create", "get", "logs"), a
        assert not [x for x in a if x.split("=", 1)[0] in CONNECTION_FLAGS], a
        assert not [x for x in a if x.startswith("--") and x != "--all-containers=true"], a
    s = stg_script()
    assert "timeout=min(CALL_S, left)" in s
    assert "request-timeout=" not in s.replace("No --request-timeout", "")


@pytest.mark.parametrize("mode", ["pod-late", "pods-flaky"])
def test_stg_waits_for_the_succeeded_pod_within_the_deadline(tmp_path, mode):
    # Review 500 B2: a pod list that is empty or fails once after Complete is read again.
    out, calls = run_stg(tmp_path, mode)
    assert out.returncode == 0, out.stdout
    assert sum(c["args"][:2] == ["get", "pods"] for c in calls) == 2


@pytest.mark.parametrize("mode, says", [("never-complete", "did not finish in 3 s"),
                                         ("foreign-pod", "could not be read in 3 s")])
def test_stg_one_deadline_bounds_the_whole_step(tmp_path, mode, says):
    # Review 503 C: the waits never sleep past the deadline (a 5 s nap against a 3 s budget).
    import time

    t0 = time.monotonic()
    out, _ = run_stg(tmp_path, mode, wait_s=3)
    elapsed = time.monotonic() - t0
    assert out.returncode == 1 and says in out.stdout
    assert elapsed < 3 + 1.5, elapsed


def run_stg_on_a_virtual_clock(monkeypatch, capsys, complete, pods):
    """STG's step in this process, its clock virtual: each kubectl call answers in 0.25 s and a
    sleep moves the clock by what it asks. Returns the exit code, the clock at the exit, the
    calls (when, the timeout given) and what the step printed."""
    import subprocess as real
    import types

    clock = {"now": 0.0}
    calls = []

    def run(args, input=None, capture_output=True, text=True, timeout=None):
        calls.append((clock["now"], timeout))
        clock["now"] += 0.25  # off the 2 s and 5 s grid, so a wait that overruns shows
        a = args[1:]
        if a[:1] == ["create"]:
            return real.CompletedProcess(args, 0, "agentrt-migrate-abc12", "")
        if a[:2] == ["get", "job"]:
            conds = [{"type": "Complete", "status": "True"}] if complete else []
            body = {"metadata": {"name": "agentrt-migrate-abc12", "uid": "uid-1"},
                    "status": {"conditions": conds, "succeeded": 1 if complete else 0}}
            return real.CompletedProcess(args, 0, json.dumps(body), "")
        if a[:2] == ["get", "pods"]:
            return real.CompletedProcess(args, 0, json.dumps({"items": pods}), "")
        return real.CompletedProcess(args, 0, "", "")

    fake_time = types.SimpleNamespace(monotonic=lambda: clock["now"],
                                      sleep=lambda s: clock.__setitem__("now", clock["now"] + s))
    fake_sp = types.SimpleNamespace(run=run, CompletedProcess=real.CompletedProcess, TimeoutExpired=real.TimeoutExpired)
    head = "import json, os, re, subprocess, sys, time\n"
    src = stg_script()
    assert src.count(head) == 1
    for k in ("AGENTRT_MIGRATE_WAIT_S", "AGENTRT_MIGRATE_CALL_S"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("API_DIGEST", DIGEST)
    monkeypatch.setenv("DELIVER_RUN", RUN)
    ns = {"__name__": "stg_step", "subprocess": fake_sp, "time": fake_time}
    with pytest.raises(SystemExit) as e:
        exec(compile(src.replace(head, "import json, os, re, sys\n"), "stg-step", "exec"), ns)
    return e.value.code, clock["now"], calls, capsys.readouterr().out


@pytest.mark.parametrize(
    "complete, pods, says",
    [
        (False, [], "did not finish in 960 s"),
        # the pod list never shows the Job's own pod (review 504 C1: the 2 s wait of the pod loop)
        (True, [{"metadata": {"name": "agentrt-migrate-abc12-x", "ownerReferences": [{"uid": "another-uid"}]},
                 "status": {"phase": "Succeeded"}}], "its succeeded pod could not be read in 960 s"),
    ],
)
def test_stg_never_runs_past_its_deadline_on_a_virtual_clock(monkeypatch, capsys, complete, pods, says):
    code, end, calls, out = run_stg_on_a_virtual_clock(monkeypatch, capsys, complete, pods)
    assert code == 1 and says in out
    # the waits end on the deadline, never a sleep past it; one call's 0.25 s at most after it
    assert 960 <= end <= 960 + 0.25 + 1e-6, end
    # no call is given more time than the step has left
    assert all(t <= 960 - when + 1e-6 for when, t in calls), [c for c in calls if c[1] > 960 - c[0]]


def test_stg_pipeline_task_has_a_backstop_timeout():
    m = tasks(STG_PIPELINE)["agentrt-migrate"]
    assert m["timeout"] == "20m"
    assert 'os.environ.get("AGENTRT_MIGRATE_WAIT_S","960")' in stg_script().replace(" ", "")


@pytest.mark.parametrize("mode, call_s", [("create-hangs", 1), ("create-eof", None)])
def test_stg_says_a_job_may_exist_when_create_got_no_answer(tmp_path, mode, call_s):
    # Review 503 B1: an answer cut off after the server made the Job is not a refusal to make it.
    out, _ = run_stg(tmp_path, mode, call_s=call_s)
    assert out.returncode == 1 and "was not confirmed" in out.stdout and "a Job may exist" in out.stdout
    assert "bifrost.io/deliver-run=" + RUN in out.stdout and "the Job was not created" not in out.stdout


@pytest.mark.parametrize("digest, run", [("sha256:" + "AB" * 32, RUN), ("latest", RUN), (DIGEST, "Bad_Name"), (DIGEST, ""),
                                         (DIGEST, "a" * 254)])
def test_stg_refuses_bad_input_before_any_call(tmp_path, digest, run):
    out, calls = run_stg(tmp_path, digest=digest, run=run)
    assert out.returncode == 1 and calls == []


def test_stg_takes_a_long_run_name(tmp_path):
    out, _ = run_stg(tmp_path, run="bifrost-deliver-platform." + "x" * 100)
    assert out.returncode == 0, out.stdout


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
    builds_go_to_candidates(p, "prod")
    pr = p["promote-images"]
    assert pr["taskRef"] == {"name": "bifrost-promote-platform-images"}
    assert set(pr["runAfter"]) == {"agentrt-schema", "build-platform-console"}
    assert pr["params"] == promote_params()
    assert {"agentrt-schema", "promote-images"} <= set(p["rollout"]["runAfter"])
    assert {"agentrt-schema", "promote-images"} <= before(p, "gitops-sync")
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
    line = "image: 192.168.10.73:30500/bifrost-platform-api:prod$"
    printed = ("test \"$(grep -c '" + line + "' k8s/agentrt-migrate/prod/job.yaml)\" = 1 && sed 's#" + line
               + "#image: 192.168.10.73:30500/bifrost-platform-api@" + DIGEST
               + "#' k8s/agentrt-migrate/prod/job.yaml | kubectl create -f -")
    assert printed in out.stdout
    # The command it prints edits exactly the PROD Job's one image line (C3 of reviews 498, 500).
    job = (ROOT / "k8s/agentrt-migrate/prod/job.yaml").read_text().splitlines()
    assert sum(re.search(line, x) is not None for x in job) == 1


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


@pytest.mark.parametrize(
    "names, says",
    [
        (("0001_core", "0002_guards", "0002_other"), "two migrations numbered 2"),
        (("0001_core", "0003_grants"), "not numbered 1 to 3 without a gap"),
        (("0002_guards",), "not numbered 1 to 2 without a gap"),
    ],
)
def test_prod_refuses_a_tree_the_migrator_refuses(tmp_path, health, names, says):
    # Review 498 B4: the migrator refuses duplicate and missing numbers; so does the check.
    d = migrations(tmp_path, names)
    health.body = {"agentrt_schema_applied": applied_of(d)}
    out = run_prod(tmp_path, d, health.url)
    assert out.returncode == 1 and says in out.stdout


def test_prod_refuses_an_applied_id_twice(tmp_path, health):
    d = migrations(tmp_path)
    twice = applied_of(d) + applied_of(d)[:1]
    health.body = {"agentrt_schema_applied": twice}
    out = run_prod(tmp_path, d, health.url)
    assert out.returncode == 1 and "names migration 1 twice" in out.stdout


# --- The promotion: the running tags move only after the gate ----------------

PROMOTE = TEKTON / "task-promote-platform-images.yaml"


def promote_script():
    doc = yaml.safe_load(PROMOTE.read_text())
    assert doc["metadata"]["name"] == "bifrost-promote-platform-images" and doc["metadata"]["namespace"] == "cicd"
    (step,) = doc["spec"]["steps"]
    assert [p["name"] for p in doc["spec"]["params"]] == ["apiImage", "apiDigest", "consoleImage", "consoleDigest"]
    return step["script"]


@pytest.fixture
def registry():
    """A registry: manifests by digest, tags set by PUT. .wrong makes GET answer other bytes,
    .media is the Content-Type GET answers, .put_digest[repo] what a PUT to repo answers."""
    import hashlib as _h

    class R(http.server.BaseHTTPRequestHandler):
        blobs, tags, wrong, put_digest = {}, {}, False, {}
        media = "application/vnd.oci.image.manifest.v1+json"

        def _send(self, code, body=b"", headers=None):
            self.send_response(code)
            for k, v in (headers or {}).items():
                self.send_header(k, v)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)

        def do_GET(self):
            repo, ref = self.path.split("/")[2], self.path.split("/")[-1]
            body = R.blobs.get((repo, ref))
            if body is None:
                return self._send(404)
            self._send(200, b"other" if R.wrong else body, {"Content-Type": R.media})

        def do_PUT(self):
            repo, tag = self.path.split("/")[2], self.path.split("/")[-1]
            body = self.rfile.read(int(self.headers["Content-Length"]))
            d = "sha256:" + _h.sha256(body).hexdigest()
            R.tags[(repo, tag)] = d
            self._send(201, b"", {"Docker-Content-Digest": R.put_digest.get(repo, d)})

        def do_HEAD(self):
            repo, tag = self.path.split("/")[2], self.path.split("/")[-1]
            d = R.tags.get((repo, tag))
            self._send(200 if d else 404, b"", {"Docker-Content-Digest": d or ""})

        def log_message(self, *_):
            pass

    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), R)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    R.url = f"http://127.0.0.1:{srv.server_address[1]}"
    R.digests = {}
    for repo in ("bifrost-platform-api", "bifrost-platform-console"):
        # an OCI image manifest as kaniko pushes it (one config, layers)
        body = json.dumps({
            "schemaVersion": 2, "mediaType": "application/vnd.oci.image.manifest.v1+json",
            "config": {"mediaType": "application/vnd.oci.image.config.v1+json", "size": 1,
                       "digest": "sha256:" + _h.sha256(repo.encode()).hexdigest()},
            "layers": [],
        }, indent=3).encode()
        d = "sha256:" + _h.sha256(body).hexdigest()
        R.blobs[(repo, d)] = body
        R.digests[repo] = d
    yield R
    srv.shutdown()


def run_promote(tmp_path, registry, env_over=None, tag="stg"):
    script = tmp_path / "promote.py"
    script.write_text(promote_script())
    host = "registry.cicd.svc.cluster.local:5000/"
    env = {**os.environ, "REGISTRY_URL": registry.url,
           "API_IMAGE": host + "bifrost-platform-api:" + tag, "API_DIGEST": registry.digests["bifrost-platform-api"],
           "CONSOLE_IMAGE": host + "bifrost-platform-console:" + tag,
           "CONSOLE_DIGEST": registry.digests["bifrost-platform-console"], **(env_over or {})}
    return subprocess.run([sys.executable, str(script)], env=env, capture_output=True, text=True, timeout=60)


@pytest.mark.parametrize("tag", ["stg", "prod"])
def test_promote_points_the_running_tags_at_the_checked_digests(tmp_path, registry, tag):
    out = run_promote(tmp_path, registry, tag=tag)
    assert out.returncode == 0, out.stdout
    for repo in ("bifrost-platform-api", "bifrost-platform-console"):
        assert registry.tags[(repo, tag)] == registry.digests[repo]


@pytest.mark.parametrize(
    "over, says",
    [
        ({"API_IMAGE": "registry.cicd.svc.cluster.local:5000/bifrost-platform-api:latest"}, "is not registry"),
        ({"API_IMAGE": "registry.cicd.svc.cluster.local:5000/bifrost-platform-console:stg"}, "is not registry"),
        ({"CONSOLE_IMAGE": "elsewhere:5000/bifrost-platform-console:stg"}, "is not registry"),
        ({"API_DIGEST": "sha256:" + "0" * 63}, "invalid api digest"),
    ],
)
def test_promote_refuses_a_target_before_moving_anything(tmp_path, registry, over, says):
    out = run_promote(tmp_path, registry, over)
    assert out.returncode == 1 and says in out.stdout
    assert registry.tags == {}


def test_promote_refuses_other_bytes_and_a_tag_that_does_not_read_back(tmp_path, registry):
    registry.wrong = True
    out = run_promote(tmp_path, registry)
    assert out.returncode == 1 and "other bytes" in out.stdout and registry.tags == {}
    registry.wrong = False
    registry.put_digest["bifrost-platform-api"] = "sha256:" + "f" * 64
    out = run_promote(tmp_path, registry)
    assert out.returncode == 1 and "does not read back" in out.stdout
    assert "running tags this step set and read back: none" in out.stdout
    # the PUT went out, so the tag may have moved: the refusal says so (review 500 B1)
    assert "may have written, not read back: bifrost-platform-api:stg" in out.stdout


def test_promote_reports_what_it_set_and_what_it_is_unsure_of(tmp_path, registry):
    registry.put_digest["bifrost-platform-console"] = "sha256:" + "f" * 64
    out = run_promote(tmp_path, registry)
    assert out.returncode == 1
    assert "running tags this step set and read back: bifrost-platform-api:stg" in out.stdout
    assert "may have written, not read back: bifrost-platform-console:stg" in out.stdout


def test_promote_reads_both_manifests_before_either_tag_moves(tmp_path, registry):
    # Review 500 B1: an unreadable console manifest leaves the api tag where it was.
    del registry.blobs[("bifrost-platform-console", registry.digests["bifrost-platform-console"])]
    out = run_promote(tmp_path, registry)
    assert out.returncode == 1 and "cannot be read from the registry" in out.stdout
    assert registry.tags == {} and "may have written" not in out.stdout


def test_promote_refuses_what_is_not_an_image_manifest(tmp_path, registry):
    registry.media = "text/html"
    out = run_promote(tmp_path, registry)
    assert out.returncode == 1 and "not an image manifest or index" in out.stdout
    assert registry.tags == {}


def test_promote_is_dominated_by_the_freeze_check_in_both_pipelines():
    for path in (STG_PIPELINE, PROD_PIPELINE):
        p = tasks(path)
        assert "freeze-check" in before(p, "promote-images"), path


def test_the_registry_collection_keeps_the_candidate_tags():
    # Review 500 B3: a candidate a run built and has not promoted yet is read by digest by its
    # migration Job and its promotion; the registry's collection must not take it meanwhile.
    import ast

    src = (ROOT / "scripts/registry/keepset.py").read_text()
    (line,) = [x for x in src.splitlines() if x.startswith("MOVING = ")]
    moving = ast.literal_eval(line.split("=", 1)[1].strip())
    for p, env in ((STG_PIPELINE, "stg"), (PROD_PIPELINE, "prod")):
        built = {str(prm["value"]).rsplit(":", 1)[1] for t in tasks(p).values()
                 for prm in t.get("params", []) if prm["name"] == "image" and ":" in str(prm["value"])}
        assert built == {env + "-candidate"}, (p, built)
        assert built <= moving


def test_no_task_uses_a_pipeline_only_variable():
    # Tekton substitutes $(context.pipelineRun.*) and $(context.pipeline.*) in a Pipeline, not
    # in a Task: a Task that names one gets the literal text (STG 2026-10-22 01:45Z, TD-411's
    # first real run refused before rollout). A Task takes them as params from its Pipeline.
    tekton = TASK.parent
    seen = []
    for path in sorted(tekton.glob("*.yaml")):
        for doc in yaml.safe_load_all(path.read_text()):
            if not doc or doc.get("kind") != "Task":
                continue
            seen.append(path.name)
            text = yaml.safe_dump(doc["spec"])
            for var in ("$(context.pipelineRun.", "$(context.pipeline."):
                assert var not in text, (path.name, var)
    assert "task-agentrt-migrate-stg.yaml" in seen
