"""Run the real embedded verifier against fake kubectl responses, without a cluster."""

import ast
import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest
import yaml

from embed_platform_digest_verify import ROOT, TASK, embedded_script, generated_task
from platform_digest_verify_trial import trial_run

NS = "bifrost-platform-stg"
PROD = "bifrost-platform-prod"
INVALID_NAMESPACES = ("bifrost-platform-dev", "", "bifrost-platform-prod ", "default")
API = "sha256:" + "a" * 64
CONSOLE = "sha256:" + "b" * 64
REV = "deployment.kubernetes.io/revision"
TARGETS = ("platform-api", "platform-workers", "platform-console")


def task_spec():
    return yaml.safe_load(Path(os.environ.get("DIGEST_TASK", TASK)).read_text())["spec"]


def script():
    return next(
        s["script"] for s in task_spec()["steps"] if s["name"] == "verify-digests"
    )


def owner(kind, name, uid):
    return {
        "controller": True,
        "apiVersion": "apps/v1",
        "kind": kind,
        "name": name,
        "uid": uid,
    }


def answers(replicas=1):
    docs = {}
    for name in TARGETS:
        cn = "platform-console" if name == "platform-console" else "platform-api"
        digest = CONSOLE if name == "platform-console" else API
        labels = {"app": name, "bifrost.io/tier": "platform"}
        docs["deployment " + name] = {
            "metadata": {
                "name": name,
                "namespace": NS,
                "uid": name + "-uid",
                "generation": 7,
                "annotations": {REV: "4"},
            },
            "spec": {
                "replicas": replicas,
                "selector": {"matchLabels": labels},
                "template": {
                    "spec": {
                        "containers": [
                            {"name": cn, "image": "registry/" + cn + "@" + digest}
                        ]
                    }
                },
            },
            "status": {
                "observedGeneration": 7,
                **{
                    k: replicas
                    for k in (
                        "replicas",
                        "updatedReplicas",
                        "readyReplicas",
                        "availableReplicas",
                    )
                },
            },
        }
        pods = []
        for i in range(replicas):
            pods.append(
                {
                    "metadata": {
                        "name": name + "-pod-" + str(i),
                        "namespace": NS,
                        "uid": name + "-pod-uid-" + str(i),
                        "labels": labels,
                        "ownerReferences": [
                            owner("ReplicaSet", name + "-rs", name + "-rs-uid")
                        ],
                    },
                    "spec": {"containers": [{"name": cn}]},
                    "status": {
                        "phase": "Running",
                        "containerStatuses": [
                            {
                                "name": cn,
                                "ready": True,
                                "state": {
                                    "running": {"startedAt": "2026-10-13T00:00:00Z"}
                                },
                                "imageID": "docker-pullable://different-registry/"
                                + cn
                                + "@"
                                + digest,
                            }
                        ],
                    },
                }
            )
        docs["pods -l app=" + name + ",bifrost.io/tier=platform"] = {
            "metadata": {},
            "items": pods,
        }
        docs["replicaset " + name + "-rs"] = {
            "metadata": {
                "name": name + "-rs",
                "namespace": NS,
                "uid": name + "-rs-uid",
                "annotations": {REV: "4"},
                "ownerReferences": [owner("Deployment", name, name + "-uid")],
            }
        }
    return docs


def pod_list(docs, name="platform-api"):
    return docs["pods -l app=" + name + ",bifrost.io/tier=platform"]["items"]


def prod_answers():
    """The coordinator's read-only measurement of 2026-10-13: 1/2/1 replicas, :prod, Always."""
    docs = answers()
    console = answers(2)
    for key in docs:
        if "platform-console" in key:
            docs[key] = console[key]
    for name in TARGETS:
        dep = docs["deployment " + name]
        dep["metadata"]["namespace"] = PROD
        dep["spec"]["strategy"] = {"type": "RollingUpdate" if name == "platform-console" else "Recreate"}
        labels = {"app.kubernetes.io/name": name, "app.kubernetes.io/part-of": "bifrost-platform", "app.kubernetes.io/managed-by": "kustomize"}
        dep["spec"]["selector"]["matchLabels"] = labels
        container = dep["spec"]["template"]["spec"]["containers"][0]
        container.update(image="192.168.10.73:30500/bifrost-" + container["name"] + ":prod", imagePullPolicy="Always")
        pods = docs.pop("pods -l app=" + name + ",bifrost.io/tier=platform")
        for pod in pods["items"]:
            pod["metadata"].update(namespace=PROD, labels=labels)
            cs = pod["status"]["containerStatuses"][0]
            cs["imageID"] = "192.168.10.73:30500/bifrost-" + cs["name"] + "@" + (CONSOLE if name == "platform-console" else API)
        docs["pods -l " + ",".join(k + "=" + v for k, v in sorted(labels.items()))] = pods
        docs["replicaset " + name + "-rs"]["metadata"]["namespace"] = PROD
    return docs


@pytest.mark.parametrize("bad_console_index", [None, 0, 1])
def test_prod_shape(tmp_path, bad_console_index):
    docs = prod_answers()
    if bad_console_index is not None:
        pods = next(v["items"] for k, v in docs.items() if k.startswith("pods ") and "platform-console" in k)
        pods[bad_console_index]["status"]["containerStatuses"][0]["imageID"] = "r@" + API
    result = execute(tmp_path, docs, env={"NAMESPACE": PROD})
    if bad_console_index is None:
        assert result.returncode == 0, result.stdout + result.stderr
        assert (tmp_path / "api-result").read_text() == API
        assert (tmp_path / "console-result").read_text() == CONSOLE
    else:
        assert_refused(result, tmp_path)


def execute(
    tmp_path, docs=None, mode="", env=None, source=None, retry_docs=None, clock=None
):
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "answers.json").write_text(
        json.dumps(answers() if docs is None else docs)
    )
    (tmp_path / "retry.json").write_text(json.dumps(retry_docs))
    fake = """#!PYTHON
import json, os, sys, time
from pathlib import Path
root = Path(os.environ['FAKE_ROOT'])
a = sys.argv[1:]
with (root/'calls').open('a') as f: f.write(json.dumps(a)+'\\n')
key = ' '.join(a[3:-2])
mode = os.environ['FAKE_MODE']
if mode == 'forbidden':
 print('Forbidden private-tool-output', file=sys.stderr); sys.exit(1)
if mode == 'failed' or (mode == 'rs-failed' and key.startswith('replicaset')):
 print('private-tool-output token=NEVER_PRINT', file=sys.stderr); sys.exit(1)
if mode == 'timeout': time.sleep(10)
if mode == 'duplicate': print('{"items": [], "items": []}'); sys.exit(0)
if mode == 'malformed': print('{private-tool-output'); sys.exit(0)
if mode == 'invalid-utf8': os.write(1, bytes([255])); sys.exit(0)
if mode == 'long-integer': print('{"number":' + '9'*5000 + '}'); sys.exit(0)
if a[2] == 'rollout':
 if mode == 'rollout-failed' or (mode == 'rollout-status-failed' and a[3] == 'status'):
  print('private-tool-output token=NEVER_PRINT', file=sys.stderr); sys.exit(1)
 sys.exit(0)
if key == 'deployment platform-api':
 n = int((root/'round').read_text())+1 if (root/'round').exists() else 1
 (root/'round').write_text(str(n))
round = int((root/'round').read_text())
docs = json.loads((root/'answers.json').read_text())
retry = json.loads((root/'retry.json').read_text())
if retry is not None and round > 1: docs = retry
print(json.dumps(docs[key]))
""".replace("PYTHON", sys.executable)
    kubectl = tmp_path / "kubectl"
    kubectl.write_text(fake)
    kubectl.chmod(0o755)
    path = tmp_path / "embedded.py"
    path.write_text(script() if source is None else source)
    environment = {
        **os.environ,
        "PATH": str(tmp_path) + os.pathsep + os.environ["PATH"],
        "FAKE_ROOT": str(tmp_path),
        "FAKE_MODE": mode,
        "NAMESPACE": NS,
        "API_DIGEST": API,
        "CONSOLE_DIGEST": CONSOLE,
        "REQUIRE_SPEC_DIGEST": "false",
        "RECORD_APPLICATION": "none",
        "API_DIGEST_PATH": str(tmp_path / "api-result"),
        "CONSOLE_DIGEST_PATH": str(tmp_path / "console-result"),
        "VERIFIED_AT_PATH": str(tmp_path / "time-result"),
        **(env or {}),
    }
    # Remove only wall-clock sleeping; the actual embedded code and subprocesses run.
    loader = "import time,runpy; time.sleep=lambda _:None; "
    if clock:
        loader += clock + "; "
    loader += "runpy.run_path(" + repr(str(path)) + ",run_name='__main__')"
    return subprocess.run(
        [sys.executable, "-c", loader],
        env=environment,
        text=True,
        capture_output=True,
        timeout=20,
    )


def assert_refused(result, tmp_path):
    assert result.returncode == 1, result.stdout + result.stderr
    assert result.stdout.startswith("REFUSED: platform digest verification: ")
    assert result.stderr == ""
    assert "private-tool-output" not in result.stdout
    assert "NEVER_PRINT" not in result.stdout
    assert not any(
        (tmp_path / p).exists() for p in ("api-result", "console-result", "time-result")
    )


@pytest.mark.parametrize("replicas", [1, 2])
def test_all_match(tmp_path, replicas):
    from datetime import datetime

    result = execute(tmp_path, answers(replicas))
    assert result.returncode == 0, result.stdout + result.stderr
    assert (tmp_path / "api-result").read_bytes() == API.encode()
    assert (tmp_path / "console-result").read_bytes() == CONSOLE.encode()
    assert datetime.fromisoformat(
        (tmp_path / "time-result").read_text().replace("Z", "+00:00")
    ).tzinfo


CASES = [
    "image-mismatch",
    "workers-console-digest",
    "empty-image",
    "malformed-image",
    "no-pods",
    "only-terminating",
    "extra-pod",
    "extra-current-rs-pod",
    "extra-old-rs-pod",
    "fewer-replicas",
    "pending",
    "missing-status",
    "empty-status",
    "duplicate-status",
    "wrong-status-name",
    "waiting",
    "terminated",
    "not-ready",
    "extra-container",
    "wrong-container",
    "init-status",
    "ephemeral-status",
    "init-spec",
    "ephemeral-spec",
    "generation",
    "no-replicas",
    "replica-count",
    "updated-count",
    "ready-count",
    "available-count",
    "missing-owner",
    "no-controller",
    "two-controllers",
    "job-owner",
    "statefulset-owner",
    "daemonset-owner",
    "pod-api-version",
    "rs-uid",
    "rs-no-controller",
    "rs-two-controllers",
    "rs-kind",
    "rs-api-version",
    "rs-other-deployment",
    "rs-deployment-uid",
    "old-revision",
    "missing-dep-revision",
    "missing-rs-revision",
    "rs-name",
    "dep-name",
    "namespace",
    "incomplete-list",
    "selector-mismatch",
    "duplicate-pod",
    "foreign-replacement",
    "missing-field",
    "wrong-shape",
    "empty-selector",
    "selector-expressions",
    "console-only",
    "extra-state",
]


def broken(case):
    docs = answers(2 if case == "fewer-replicas" else 1)
    dep = docs["deployment platform-api"]
    pods = pod_list(docs)
    pod = pods[0]
    cs = pod["status"]["containerStatuses"][0]
    rs = docs["replicaset platform-api-rs"]["metadata"]
    pr = pod["metadata"]["ownerReferences"][0]
    dr = rs["ownerReferences"][0]
    if case in ("image-mismatch", "workers-console-digest", "console-only"):
        target = pod_list(
            docs,
            {
                "workers-console-digest": "platform-workers",
                "console-only": "platform-console",
            }.get(case, "platform-api"),
        )[0]
        target["status"]["containerStatuses"][0]["imageID"] = "repo@" + (
            CONSOLE if case == "workers-console-digest" else "sha256:" + "c" * 64
        )
    elif case in ("empty-image", "malformed-image"):
        cs["imageID"] = "" if case == "empty-image" else "repo@sha256:" + "a" * 63
    elif case == "no-pods":
        pods.clear()
    elif case == "only-terminating":
        pod["metadata"]["deletionTimestamp"] = "2026-10-13T00:00:00Z"
    elif case == "extra-pod":
        pods.append(copy.deepcopy(pod))
    elif case in ("extra-current-rs-pod", "extra-old-rs-pod"):
        extra = copy.deepcopy(pod)
        extra["metadata"].update(name="extra-pod", uid="extra-unique-uid")
        if case == "extra-old-rs-pod":
            extra["metadata"]["ownerReferences"][0].update(
                name="platform-api-old-rs", uid="old-rs-uid"
            )
            old_rs = copy.deepcopy(docs["replicaset platform-api-rs"])
            old_rs["metadata"].update(name="platform-api-old-rs", uid="old-rs-uid")
            old_rs["metadata"]["annotations"][REV] = "3"
            docs["replicaset platform-api-old-rs"] = old_rs
        pods.append(extra)
    elif case == "fewer-replicas":
        pods.pop()
    elif case == "pending":
        pod["status"]["phase"] = "Pending"
    elif case == "missing-status":
        del pod["status"]["containerStatuses"]
    elif case == "empty-status":
        pod["status"]["containerStatuses"] = []
    elif case == "duplicate-status":
        pod["status"]["containerStatuses"].append(copy.deepcopy(cs))
    elif case == "wrong-status-name":
        cs["name"] = "other"
    elif case in ("waiting", "terminated"):
        cs["state"] = {case: {}}
    elif case == "extra-state":
        cs["state"]["waiting"] = {}
    elif case == "not-ready":
        cs["ready"] = False
    elif case == "extra-container":
        pod["spec"]["containers"].append({"name": "sidecar"})
    elif case == "wrong-container":
        pod["spec"]["containers"][0]["name"] = "other"
    elif case in ("init-status", "ephemeral-status"):
        pod["status"][
            "initContainerStatuses"
            if case == "init-status"
            else "ephemeralContainerStatuses"
        ] = [{}]
    elif case in ("init-spec", "ephemeral-spec"):
        pod["spec"][
            "initContainers" if case == "init-spec" else "ephemeralContainers"
        ] = [{}]
    elif case == "generation":
        dep["status"]["observedGeneration"] -= 1
    elif case == "no-replicas":
        dep["spec"]["replicas"] = 0
    elif case in ("replica-count", "updated-count", "ready-count", "available-count"):
        dep["status"][
            dict(
                zip(
                    (
                        "replica-count",
                        "updated-count",
                        "ready-count",
                        "available-count",
                    ),
                    (
                        "replicas",
                        "updatedReplicas",
                        "readyReplicas",
                        "availableReplicas",
                    ),
                )
            )[case]
        ] = 0
    elif case == "missing-owner":
        del pod["metadata"]["ownerReferences"]
    elif case == "no-controller":
        pr["controller"] = False
    elif case == "two-controllers":
        pod["metadata"]["ownerReferences"].append(copy.deepcopy(pr))
    elif case in ("job-owner", "statefulset-owner", "daemonset-owner"):
        pr["kind"] = {
            "job-owner": "Job",
            "statefulset-owner": "StatefulSet",
            "daemonset-owner": "DaemonSet",
        }[case]
    elif case == "pod-api-version":
        pr["apiVersion"] = "apps/v2"
    elif case == "rs-uid":
        rs["uid"] = "rebuilt-same-name"
    elif case == "rs-no-controller":
        dr["controller"] = False
    elif case == "rs-two-controllers":
        rs["ownerReferences"].append(copy.deepcopy(dr))
    elif case == "rs-kind":
        dr["kind"] = "Job"
    elif case == "rs-api-version":
        dr["apiVersion"] = "apps/v2"
    elif case == "rs-other-deployment":
        dr.update(name="platform-workers", uid="platform-workers-uid")
    elif case == "rs-deployment-uid":
        dr["uid"] = "rebuilt-deployment"
    elif case == "old-revision":
        rs["annotations"][REV] = "3"
    elif case == "missing-dep-revision":
        del dep["metadata"]["annotations"][REV]
    elif case == "missing-rs-revision":
        del rs["annotations"][REV]
    elif case == "rs-name":
        rs["name"] = "wrong"
    elif case == "dep-name":
        dep["metadata"]["name"] = "wrong"
    elif case == "namespace":
        pod["metadata"]["namespace"] = "other"
    elif case == "incomplete-list":
        docs["pods -l app=platform-api,bifrost.io/tier=platform"]["metadata"][
            "continue"
        ] = "remaining"
    elif case == "selector-mismatch":
        pod["metadata"]["labels"] = {"app": "other"}
    elif case == "duplicate-pod":
        docs = answers(2)
        pod_list(docs)[1]["metadata"]["uid"] = pod_list(docs)[0]["metadata"]["uid"]
    elif case == "foreign-replacement":
        old = copy.deepcopy(pod)
        old["metadata"]["deletionTimestamp"] = "2026-10-13T00:00:00Z"
        pods.append(old)
        dr.update(name="platform-workers", uid="platform-workers-uid")
    elif case == "missing-field":
        del dep["status"]["readyReplicas"]
    elif case == "wrong-shape":
        dep["status"] = []
    elif case == "empty-selector":
        dep["spec"]["selector"]["matchLabels"] = {}
    elif case == "selector-expressions":
        dep["spec"]["selector"]["matchExpressions"] = [
            {"key": "extra", "operator": "Exists"}
        ]
    else:
        raise AssertionError(case)
    return docs


@pytest.mark.parametrize("case", CASES)
def test_refuses(tmp_path, case):
    assert_refused(execute(tmp_path, broken(case)), tmp_path)


@pytest.mark.parametrize(
    "mode", ["forbidden", "failed", "rs-failed", "duplicate", "malformed", "timeout"]
)
def test_read_errors(tmp_path, mode):
    # Reduce only query timeout for the sleeping fake command.
    source = (
        script().replace("QUERY_BUDGET = 5", "QUERY_BUDGET = 0.15")
        if mode == "timeout"
        else script()
    )
    result = execute(tmp_path, mode=mode, source=source)
    assert_refused(result, tmp_path)
    assert mode != "forbidden" or "identity cannot read" in result.stdout


@pytest.mark.parametrize("mode", ["invalid-utf8", "long-integer"])
def test_unexpected_value_error_fixed_log(tmp_path, mode):
    result = execute(tmp_path, mode=mode)
    assert_refused(result, tmp_path)
    assert result.stdout == (
        "REFUSED: platform digest verification: "
        "missing or malformed verification evidence\n"
    )
    assert result.stderr == ""


@pytest.mark.parametrize("index", [0, 1])
def test_all_console_pod_digests(tmp_path, index):
    docs = answers(2)
    pod_list(docs, "platform-console")[index]["status"]["containerStatuses"][0][
        "imageID"
    ] = "r@sha256:" + "c" * 64
    assert_refused(execute(tmp_path, docs), tmp_path)


@pytest.mark.parametrize(
    "image_id,accepted",
    [("r@" + API + "@sha256:" + "c" * 64, False),
     ("r@" + API + "0", False),
     ("r@sha256:" + "c" * 64 + "@" + API, True),
     (API, False)],
    ids=["correct-then-wrong", "extra-digit", "wrong-then-correct", "bare-digest"],
)
def test_image_id_suffix(tmp_path, image_id, accepted):
    docs = answers()
    pod_list(docs)[0]["status"]["containerStatuses"][0]["imageID"] = image_id
    result = execute(tmp_path, docs)
    if accepted:
        assert result.returncode == 0, result.stdout
    else:
        assert_refused(result, tmp_path)


@pytest.mark.parametrize("name", ["-rs", "bad name", "bad=name", "", "a" * 254,
                                      "UPPER", "rs-", "rs..name", "rs.-name"])
def test_invalid_rs_name_before_kubectl(tmp_path, name):
    docs = answers()
    pod_list(docs)[0]["metadata"]["ownerReferences"][0]["name"] = name
    # Provide consistent evidence: refusal must precede a ReplicaSet query.
    rs = docs.pop("replicaset platform-api-rs")
    rs["metadata"]["name"] = name
    docs["replicaset " + name] = rs
    assert_refused(execute(tmp_path, docs), tmp_path)
    calls = [json.loads(line) for line in (tmp_path / "calls").read_text().splitlines()]
    assert all(a[3] != "replicaset" for a in calls)


@pytest.mark.parametrize(
    "digest", ["", "sha256:" + "a" * 63, API + "\n", API.upper(), "repo@" + API]
)
@pytest.mark.parametrize("key", ["API_DIGEST", "CONSOLE_DIGEST"])
def test_bad_digest(tmp_path, key, digest):
    assert_refused(execute(tmp_path, env={key: digest}), tmp_path)
    assert not (tmp_path / "calls").exists()


def test_terminating_old_pod_ignored(tmp_path):
    docs = answers()
    old = copy.deepcopy(pod_list(docs)[0])
    old["metadata"]["deletionTimestamp"] = "2026-10-13T00:00:00Z"
    old["status"]["containerStatuses"][0]["imageID"] = "wrong"
    pod_list(docs).append(old)
    assert execute(tmp_path, docs).returncode == 0


@pytest.mark.parametrize("phase", ["Succeeded", "Failed"])
@pytest.mark.parametrize("correct_digest", [False, True])
def test_terminal_pod_ignored(tmp_path, phase, correct_digest):
    docs = answers()
    old = copy.deepcopy(pod_list(docs)[0])
    old["metadata"].update(name="old-pod", uid="old-pod-uid")
    old["status"]["phase"] = phase
    if not correct_digest:
        old["status"]["containerStatuses"][0]["imageID"] = "wrong"
    pod_list(docs).append(old)
    assert execute(tmp_path / "with-running", docs).returncode == 0
    pod_list(docs).pop(0)
    assert_refused(execute(tmp_path / "only-terminal", docs), tmp_path / "only-terminal")


def test_pending_without_status(tmp_path):
    docs = answers()
    pod_list(docs)[0]["status"] = {"phase": "Pending"}
    assert_refused(execute(tmp_path, docs), tmp_path)


@pytest.mark.parametrize("value", [None, {}, False, ""])
def test_malformed_optional_container_status(tmp_path, value):
    docs = answers()
    pod_list(docs)[0]["status"]["initContainerStatuses"] = value
    assert_refused(execute(tmp_path, docs), tmp_path)


def test_zero_replicas_not_vacuous_success(tmp_path):
    assert_refused(execute(tmp_path, answers(0)), tmp_path)


def test_retry_whole_set(tmp_path):
    # First attempt: API/worker pass, console fails. Next attempt must reread API.
    result = execute(tmp_path, broken("console-only"), retry_docs=answers())
    assert result.returncode == 0, result.stdout
    calls = [json.loads(line) for line in (tmp_path / "calls").read_text().splitlines()]
    assert sum(a[3:5] == ["deployment", "platform-api"] for a in calls) == 2
    assert sum(a[3:5] == ["deployment", "platform-workers"] for a in calls) == 2


def test_old_revision_can_clear_on_retry(tmp_path):
    assert (
        execute(tmp_path, broken("old-revision"), retry_docs=answers()).returncode == 0
    )


def test_no_cross_attempt_success(tmp_path):
    # API passes only the first attempt; console passes only later attempts.
    assert_refused(
        execute(tmp_path, broken("console-only"), retry_docs=broken("image-mismatch")),
        tmp_path,
    )
    assert (tmp_path / "round").read_text() == "3"


def test_deadline(tmp_path):
    assert_refused(
        execute(
            tmp_path,
            clock="time.monotonic=lambda:next(ticks); ticks=iter([0, 100, 100])",
        ),
        tmp_path,
    )
    assert not (tmp_path / "calls").exists()


@pytest.mark.parametrize(
    "env",
    [
        {"RECORD_APPLICATION": "bifrost-platform-prod"},
        {"REQUIRE_SPEC_DIGEST": ""},
    ],
)
def test_modes_fail_closed(tmp_path, env):
    assert_refused(execute(tmp_path, env=env), tmp_path)
    assert not (tmp_path / "calls").exists()


@pytest.mark.parametrize("namespace", INVALID_NAMESPACES)
@pytest.mark.parametrize("step", ["rollout-restart", "verify-digests"])
def test_namespace_refused_before_calls(tmp_path, namespace, step):
    source = next(s["script"] for s in task_spec()["steps"] if s["name"] == step)
    result = execute(tmp_path, source=source, env={"NAMESPACE": namespace})
    assert result.returncode == 1
    assert result.stderr == ""
    assert result.stdout.startswith("REFUSED: ")
    assert not (tmp_path / "calls").exists()


def test_spec_digest_check(tmp_path):
    docs = answers()
    assert (
        execute(
            tmp_path / "positive", docs, env={"REQUIRE_SPEC_DIGEST": "true"}
        ).returncode
        == 0
    )
    docs["deployment platform-api"]["spec"]["template"]["spec"]["containers"][0][
        "image"
    ] = "registry/api:stg"
    assert_refused(
        execute(tmp_path, docs, env={"REQUIRE_SPEC_DIGEST": "true"}), tmp_path
    )


def test_kubectl_keeps_the_in_cluster_identity(tmp_path):
    assert execute(tmp_path).returncode == 0
    for line in (tmp_path / "calls").read_text().splitlines():
        a = json.loads(line)
        assert a[:3] == ["-n", NS, "get"]
        assert a[-2:] == ["-o", "json"]
        assert a[3:-2] in [["deployment", n] for n in TARGETS] + [
            ["replicaset", n + "-rs"] for n in TARGETS
        ] + [["pods", "-l", "app=" + n + ",bifrost.io/tier=platform"] for n in TARGETS]
    tree = ast.parse(script())
    calls = [
        n
        for n in ast.walk(tree)
        if isinstance(n, ast.Call)
        and isinstance(n.func, ast.Attribute)
        and isinstance(n.func.value, ast.Name)
        and n.func.value.id == "subprocess"
        and n.func.attr == "run"
    ]
    assert len(calls) == 1
    assert (
        ast.unparse(calls[0].args[0])
        == "['kubectl', '-n', namespace, 'get', *args, '-o', 'json']"
    )


def test_pipeline_wiring():
    pipeline = yaml.safe_load(
        Path(os.environ.get("DIGEST_PIPELINE", ROOT / "k8s/cicd/tekton/pipeline-deliver-platform.yaml")).read_text()
    )["spec"]
    rollout = next(t for t in pipeline["tasks"] if t["name"] == "rollout")
    assert rollout["taskRef"]["name"] == "bifrost-rollout-verify-platform"
    assert rollout["runAfter"] == ["gitops-sync"]
    assert not {"when", "onError", "retries"} & rollout.keys()
    # TD-335, TD-419: gitops-sync pins the run's digests; the rollout check requires them
    # in the Deployment spec as well as in the Pods.
    assert {p["name"]: p["value"] for p in rollout["params"]} == {
        "namespace": NS,
        "apiDigest": "$(tasks.build-platform-api.results.digest)",
        "consoleDigest": "$(tasks.build-platform-console.results.digest)",
        "requireSpecDigest": "true",
        "recordApplication": "none",
    }


def prod_pipeline():
    return yaml.safe_load(Path(os.environ.get("DIGEST_PROD_PIPELINE", ROOT / "k8s/cicd/tekton/pipeline-deliver-platform-prod.yaml")).read_text())["spec"]


def test_prod_pipeline_wiring():
    tasks = prod_pipeline()["tasks"]
    names = [t["name"] for t in tasks]
    rollout = next(t for t in tasks if t["name"] == "rollout")
    assert names.count("rollout") == 1
    assert rollout["taskRef"] == {"name": "bifrost-rollout-verify-platform"}
    assert len(rollout["params"]) == 5
    # TD-335: the pair STG verified (the source gate's results), required in the spec.
    assert {p["name"]: p["value"] for p in rollout["params"]} == {
        "namespace": PROD,
        "apiDigest": "$(tasks.check-source.results.api-digest)",
        "consoleDigest": "$(tasks.check-source.results.console-digest)",
        "requireSpecDigest": "true",
        "recordApplication": "none",
    }
    assert not {"when", "onError", "retries"} & rollout.keys()
    # The pin and sync comes first, then the check; the schema check and the promotion
    # come before both.
    assert rollout["runAfter"] == ["gitops-sync"]
    sync = next(t for t in tasks if t["name"] == "gitops-sync")
    assert sync["runAfter"] == ["promote-images"]
    assert names.index("agentrt-schema") < names.index("promote-images") < names.index("gitops-sync") < names.index("rollout")
    assert all(t.get("taskRef", {}).get("name") != "bifrost-rollout-platform-stg" for t in tasks)


def test_prod_pipeline_cannot_skip_the_check():
    # `when` or `onError` on an upstream task skips rollout too, and the run
    # would still succeed. `finally`, `retries` and `matrix` do not skip it;
    # they are pinned so that adding one to this pipeline is a deliberate change.
    spec = prod_pipeline()
    assert "finally" not in spec
    for t in spec["tasks"]:
        assert not {"when", "onError", "retries", "matrix"} & t.keys(), t["name"]


def namespace_condition(source):
    tests = [
        ast.unparse(n.test)
        for n in ast.walk(ast.parse(source))
        if isinstance(n, ast.If) and "bifrost-platform-stg" in ast.unparse(n.test)
    ]
    assert len(tests) == 1
    return tests[0]


def test_exactly_two_namespaces_in_source():
    # The refusal tests sample a few other names. This pins the whole condition
    # in each of the three places, so a third name inside or around it fails.
    pair = "('bifrost-platform-stg', 'bifrost-platform-prod')"
    verify = (ROOT / "scripts/release/platform_digest_verify.py").read_text()
    assert namespace_condition(verify) == (
        "namespace not in " + pair + " or os.environ['RECORD_APPLICATION'] != 'none'"
    )
    restart = task_spec()["steps"][0]["script"]
    assert namespace_condition(restart) == (
        "os.environ['NAMESPACE'] not in " + pair
        + " or os.environ['RECORD_APPLICATION'] != 'none'"
        + " or os.environ['REQUIRE_SPEC_DIGEST'] not in ('true', 'false')"
    )
    trial = (ROOT / "scripts/release/platform_digest_verify_trial.py").read_text()
    assert namespace_condition(trial) == "namespace not in " + pair
    assert trial.count('choices=("bifrost-platform-stg", "bifrost-platform-prod")') == 1


def test_required_params_and_no_skip():
    spec = task_spec()
    assert [step["name"] for step in spec["steps"]] == ["rollout-restart", "verify-digests"]
    assert all("onError" not in step for step in spec["steps"])
    assert all(
        step["script"].startswith("#!/usr/bin/env python3\n") for step in spec["steps"]
    )
    assert {p["name"] for p in spec["params"]} == {
        "namespace",
        "apiDigest",
        "consoleDigest",
        "requireSpecDigest",
        "recordApplication",
    }
    assert all("default" not in p for p in spec["params"])
    assert "invalid expected digest" in script()
    assert "skip" not in script().lower()
    assert "DIGEST_RE.fullmatch(api_digest)" in script()
    calls = [n for n in ast.walk(ast.parse(script())) if isinstance(n, ast.Call)]
    assert any(ast.unparse(n) == "DIGEST_RE.fullmatch(console_digest)" for n in calls)


def test_protected_files_unchanged():
    # Slice 3 changes only PROD rollout wiring; its new hash is pinned here.
    # TD-411 adds the agentrt schema check and the promotion of the checked images
    # before the PROD rollout. TD-335 (W-31 3.4 ①) removes PROD's builds: it deploys the
    # digests STG verified, pinned in the application. The hash below is the file with
    # both. The shared legacy restart Task stays unchanged.
    hashes = {
        "task-deliver-platform.yaml": "4795263ba3c5135c9c5bd5d1880626ab41558b32a47d33524fc18a45d89388e2",
        "pipeline-deliver-platform-prod.yaml": "0aca0fcfa680623db983fde5805874e1fae8333a509601e89541401d4be6333d",
    }
    for filename, expected in hashes.items():
        assert (
            hashlib.sha256(
                (ROOT / "k8s/cicd/tekton" / filename).read_bytes()
            ).hexdigest()
            == expected
        )


def test_rbac_only_stg_prod_read_additions():
    docs = list(
        yaml.safe_load_all(
            Path(os.environ.get("DIGEST_RBAC", ROOT / "k8s/cicd/tekton/rbac-deliver-platform.yaml")).read_text()
        )
    )
    base = {
        "apiGroups": ["apps"],
        "resources": ["deployments"],
        "verbs": ["get", "patch", "list", "watch"],
    }
    assert docs[0]["rules"] == [
        base,
        {"apiGroups": [""], "resources": ["pods"], "verbs": ["get", "list"]},
        {"apiGroups": ["apps"], "resources": ["replicasets"], "verbs": ["get"]},
    ]
    assert docs[2]["rules"] == docs[0]["rules"]
    assert docs[0]["metadata"]["namespace"] == NS
    assert docs[2]["metadata"]["namespace"] == "bifrost-platform-prod"
    # The whole file: two Roles, each bound to tekton-deliver and to nothing else.
    # A fifth document, or another subject, would add access these rules do not show.
    assert [d["kind"] for d in docs] == ["Role", "RoleBinding", "Role", "RoleBinding"]
    for role, binding in ((docs[0], docs[1]), (docs[2], docs[3])):
        assert binding["metadata"]["namespace"] == role["metadata"]["namespace"]
        assert binding["roleRef"] == {
            "apiGroup": "rbac.authorization.k8s.io",
            "kind": "Role",
            "name": role["metadata"]["name"],
        }
        assert binding["subjects"] == [
            {"kind": "ServiceAccount", "name": "tekton-deliver", "namespace": "cicd"}
        ]


def test_embed_current():
    original = TASK.read_text()
    assert generated_task(original) == original
    body = next(
        s["script"]
        for s in yaml.safe_load(original)["spec"]["steps"]
        if s["name"] == "verify-digests"
    )
    assert body == embedded_script()


@pytest.mark.parametrize("namespace", [NS, PROD])
def test_trial_exact_step_without_rollout(tmp_path, namespace):
    run = trial_run(API, CONSOLE, namespace)
    assert run["metadata"]["generateName"] == "platform-digest-trial-"
    task = run["spec"]["pipelineSpec"]["tasks"][0]
    assert {p["name"]: p["value"] for p in task["params"]}["namespace"] == namespace
    original = yaml.safe_load(TASK.read_text())["spec"]
    assert task["taskSpec"]["steps"] == [original["steps"][1]]
    assert task["taskSpec"]["results"] == original["results"]
    assert run["spec"]["taskRunSpecs"] == [
        {"pipelineTaskName": "verify-digests", "serviceAccountName": "tekton-deliver"}
    ]
    assert run["spec"]["taskRunTemplate"]["podTemplate"]["nodeSelector"] == {
        "kubernetes.io/arch": "amd64"
    }
    assert (
        execute(tmp_path, prod_answers() if namespace == PROD else answers(), env={"NAMESPACE": namespace}, source=task["taskSpec"]["steps"][0]["script"]).returncode == 0
    )
    assert (
        "kubectl create -f trial.yaml"
        in subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts/release/platform_digest_verify_trial.py"),
                "--help",
            ],
            capture_output=True,
            text=True,
            check=True,
        ).stdout
    )


@pytest.mark.parametrize("namespace", INVALID_NAMESPACES)
def test_trial_invalid_namespace(namespace):
    with pytest.raises(ValueError):
        trial_run(API, CONSOLE, namespace)
    result = subprocess.run([sys.executable, str(ROOT / "scripts/release/platform_digest_verify_trial.py"), API, CONSOLE, "--namespace", namespace], capture_output=True, text=True)
    assert result.returncode == 2
    assert result.stdout == ""


@pytest.mark.parametrize("namespace", [None, NS, PROD])
def test_trial_cli_namespace(namespace):
    args = [sys.executable, str(ROOT / "scripts/release/platform_digest_verify_trial.py"), API, CONSOLE]
    if namespace is not None:
        args += ["--namespace", namespace]
    result = subprocess.run(args, capture_output=True, text=True, check=True)
    assert yaml.safe_load(result.stdout) == trial_run(API, CONSOLE, namespace or NS)


def test_release_doc_lists_every_refusal():
    doc = (ROOT / "docs/RELEASE.md").read_text()
    reasons = []
    for step in yaml.safe_load(TASK.read_text())["spec"]["steps"]:
        for node in ast.walk(ast.parse(step["script"])):
            if (
                isinstance(node, ast.Raise)
                and isinstance(node.exc, ast.Call)
                and getattr(node.exc.func, "id", "") == "VerificationRefused"
                and node.exc.args
            ):
                reasons.append(node.exc.args[0].value)
            if (
                isinstance(node, ast.Constant)
                and isinstance(node.value, str)
                and (
                    node.value.startswith("REFUSED: ")
                    or node.value == "missing or malformed verification evidence"
                )
            ):
                reasons.append(node.value.strip())
    assert len(reasons) > 20
    assert not [r for r in reasons if r not in doc]


def test_apply_manifest_list():
    text = (ROOT / "scripts/k3s/apply-cicd-platform-pipeline.sh").read_text()
    assert (
        'kubectl apply -f "${ROOT}/k8s/cicd/tekton/task-rollout-verify-platform.yaml"'
        in text
    )
    assert (
        text.index("/rbac-deliver-platform.yaml")
        < text.index("/task-rollout-verify-platform.yaml")
        < text.index("/pipeline-deliver-platform.yaml")
    )


@pytest.mark.parametrize("namespace", [NS, PROD])
def test_rollout_waits_without_a_restart_when_the_spec_names_the_digest(tmp_path, namespace):
    # TD-335: gitops-sync pinned the digests into the Deployments; the spec change is the
    # rollout, and a restart would only roll them again (PROD's api is Recreate).
    source = task_spec()["steps"][0]["script"]
    result = execute(tmp_path, source=source, env={"NAMESPACE": namespace, "REQUIRE_SPEC_DIGEST": "true"})
    assert result.returncode == 0, result.stdout + result.stderr
    calls = [json.loads(line) for line in (tmp_path / "calls").read_text().splitlines()]
    assert calls == [
        ["-n", namespace, "rollout", "status", "deployment/" + name, "--timeout=300s"]
        for name in ("platform-api", "platform-console", "platform-workers")
    ]


@pytest.mark.parametrize("namespace", [NS, PROD])
def test_rollout_restart_and_wait(tmp_path, namespace):
    source = task_spec()["steps"][0]["script"]
    result = execute(tmp_path, source=source, env={"NAMESPACE": namespace})
    assert result.returncode == 0, result.stdout + result.stderr
    calls = [json.loads(line) for line in (tmp_path / "calls").read_text().splitlines()]
    assert calls == [
        a
        for name in ("platform-api", "platform-console", "platform-workers")
        for a in (
            ["-n", namespace, "rollout", "restart", "deployment/" + name],
            ["-n", namespace, "rollout", "status", "deployment/" + name, "--timeout=300s"],
        )
    ]


@pytest.mark.parametrize("mode", ["rollout-failed", "rollout-status-failed"])
def test_rollout_failure_fixed_log(tmp_path, mode):
    result = execute(tmp_path, source=task_spec()["steps"][0]["script"], mode=mode)
    assert result.returncode == 1
    assert result.stdout == "REFUSED: platform rollout failed or timed out\n"
    assert result.stderr == ""


@pytest.mark.parametrize(
    "env",
    [
        {"API_DIGEST": ""},
        {"CONSOLE_DIGEST": API + "\n"},
        {"REQUIRE_SPEC_DIGEST": "yes"},
        {"REQUIRE_SPEC_DIGEST": ""},
        {"RECORD_APPLICATION": "bifrost-platform-prod"},
    ],
)
def test_rollout_bad_params_before_writes(tmp_path, env):
    result = execute(tmp_path, source=task_spec()["steps"][0]["script"], env=env)
    assert result.returncode == 1
    assert result.stdout == "REFUSED: invalid STG or PROD rollout parameters\n"
    assert not (tmp_path / "calls").exists()


@pytest.mark.parametrize("phase", ["Pending", "Unknown", None, "failed", "absent"])
def test_only_succeeded_and_failed_are_left_out(tmp_path, phase):
    """The other side of the terminal-pod rule: leaving out too much is the direction that answers wrong. A pod
    whose phase is anything but Succeeded or Failed, or is missing, still counts, so an extra one refuses."""
    docs = answers()
    extra = copy.deepcopy(pod_list(docs)[0])
    extra["metadata"].update(name="extra-pod", uid="extra-unique-uid")
    if phase == "absent":
        del extra["status"]["phase"]
    else:
        extra["status"]["phase"] = phase
    pod_list(docs).append(extra)
    assert_refused(execute(tmp_path, docs), tmp_path)
