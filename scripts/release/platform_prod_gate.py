"""Read-only, bounded platform PROD source gate; embedded in the Pipeline task."""

import base64
import json
import os
import re
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path

from ci_gate import classify, _pipeline_name, _succeeded

SHA_RE = re.compile(r"[0-9a-f]{40}\Z")
DIGEST_RE = re.compile(r"sha256:[0-9a-f]{64}\Z")
BUDGET = 20


def command(args):
    env = os.environ.copy()
    env["GIT_TERMINAL_PROMPT"] = "0"
    if args[0] == "git" and env.get("GIT_USERNAME") and env.get("GIT_PASSWORD"):
        credential = base64.b64encode(
            (env["GIT_USERNAME"] + ":" + env["GIT_PASSWORD"]).encode()
        ).decode()
        # Reuse clone's Secret without putting credentials in argv or log lines.
        env.update(
            GIT_CONFIG_NOSYSTEM="1",
            GIT_CONFIG_GLOBAL="/dev/null",
            GIT_CONFIG_COUNT="3",
            GIT_CONFIG_KEY_0="http.http://gitea.cicd.svc.cluster.local:3000/.extraHeader",
            GIT_CONFIG_KEY_1="http.followRedirects",
            GIT_CONFIG_VALUE_1="false",
            GIT_CONFIG_KEY_2="credential.helper",
            GIT_CONFIG_VALUE_2="",
            GIT_CONFIG_VALUE_0="Authorization: Basic " + credential,
        )
    env.pop("GIT_USERNAME", None)
    env.pop("GIT_PASSWORD", None)
    return subprocess.run(
        args, check=True, capture_output=True, text=True, timeout=BUDGET, env=env
    ).stdout


def resolve(url, revision, directory):
    if (
        not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._/-]*", revision)
        or ".." in revision
        or "//" in revision
        or revision.endswith(("/", ".", ".lock"))
    ):
        raise ValueError("invalid revision")
    if re.fullmatch(r"[0-9a-f]+", revision) and not SHA_RE.fullmatch(revision):
        raise ValueError("invalid revision")
    command(["git", "init", "--quiet", directory])
    if not SHA_RE.fullmatch(revision):
        refs = command(
            [
                "git",
                "ls-remote",
                "--",
                url,
                "refs/heads/" + revision,
                "refs/tags/" + revision,
                "refs/tags/" + revision + "^{}",
            ]
        )
        candidates = set()
        for line in refs.splitlines():
            sha, ref = line.split("\t")
            if not SHA_RE.fullmatch(sha):
                raise ValueError("invalid mirror SHA")
            candidates.add(ref.removesuffix("^{}"))
        if len(candidates) != 1:
            raise ValueError("empty or ambiguous mirror revision")
        revision = candidates.pop()
    command(
        ["git", "-C", directory, "fetch", "--quiet", "--depth=1", "--", url, revision]
    )
    sha = command(["git", "-C", directory, "rev-parse", "FETCH_HEAD^{commit}"]).strip()
    if not SHA_RE.fullmatch(sha):
        raise ValueError("invalid resolved SHA")
    if SHA_RE.fullmatch(revision) and sha != revision:
        raise ValueError("mirror returned another SHA")
    return sha


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


# Why a tool call failed, as one of a few fixed phrases. The tool's own text is never
# printed: this step holds the mirror credential, and the log is widely readable.
CAUSES = (
    ("connection to the server", "cannot reach the API server"),
    ("connection refused", "connection refused"),
    ("could not resolve host", "cannot resolve the mirror host"),
    ("no route to host", "no route to host"),
    ("couldn't find remote ref", "ref is not in the mirror"),
    ("authentication failed", "mirror authentication failed"),
    ("doesn't have a resource type", "the API has no such resource"),
    ("serviceunavailable", "the API is unavailable"),
    ("toomanyrequests", "the API is throttling"),
    ("internalerror", "the API reported an internal error"),
    ("notfound", "not found"),
    ("timed out", "timed out"),
    ("timeout", "timed out"),
)


def detail(stderr):
    text = stderr.lower() if isinstance(stderr, str) else ""
    for needle, cause in CAUSES:
        if needle in text:
            return cause
    return "unrecognised error output (%d characters)" % len(text)


def read_json(args):
    # One whole-process deadline (BUDGET); never retry. No --request-timeout, --server or
    # other connection flag: with any of them kubectl in a pod stops falling back to the
    # in-cluster identity and dials localhost:8080 (found by the Owner's trial run, 2026-10-12).
    try:
        return json.loads(
            command(["kubectl", "-n", "cicd", *args, "-o", "json"]),
            object_pairs_hook=unique_object,
        )
    except subprocess.CalledProcessError as exc:
        text = exc.stderr.lower() if isinstance(exc.stderr, str) else ""
        if "forbidden" in text or "unauthorized" in text:
            raise ValueError(
                "identity cannot read PipelineRuns/TaskRuns in cicd"
            ) from exc
        # Say why: "query failed" alone left the Owner's trial run unexplained (2026-10-12).
        raise ValueError("query failed: " + detail(exc.stderr)) from exc


def validate_run(run):
    if not isinstance(run, dict) or not isinstance(run.get("metadata"), dict):
        raise ValueError("malformed run")
    spec = run["spec"]
    if not isinstance(spec, dict):
        raise ValueError("malformed spec")
    params = spec.get("params", [])
    if not isinstance(params, list):
        raise ValueError("malformed params")
    names = [p["name"] for p in params]
    if len(names) != len(set(names)) or any(
        not isinstance(p["value"], str)
        for p in params
        if p["name"] in ("repo", "revision")
    ):
        raise ValueError("ambiguous params")
    conditions = run.get("status", {}).get("conditions", [])
    states = [c["status"] for c in conditions if c["type"] == "Succeeded"]
    if len(states) > 1 or any(s not in ("True", "False", "Unknown") for s in states):
        raise ValueError("ambiguous status")


def run_time(run, field):
    name = run["metadata"]["name"]
    value = (
        run.get("status", {}).get(field)
        if field == "completionTime"
        else run["metadata"].get(field)
    )
    try:
        stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if stamp.tzinfo is None:
            raise ValueError("timezone missing")
        return stamp
    except (AttributeError, TypeError, ValueError) as exc:
        raise ValueError(f"STG run {name} has missing or unparsable {field}") from exc


def latest_stg(runs):
    stg = [r for r in runs if _pipeline_name(r) == "bifrost-deliver-platform"]
    if not stg:
        raise ValueError("no STG delivery")
    latest = max(run_time(r, "creationTimestamp") for r in stg)
    chosen = [r for r in stg if run_time(r, "creationTimestamp") == latest]
    if len(chosen) != 1:
        raise ValueError("ambiguous latest STG delivery")
    chosen = chosen[0]
    state = _succeeded(chosen)
    if state != "True":
        raise ValueError(
            f"STG run {chosen['metadata']['name']} is {state or 'running/no Succeeded condition'}"
        )
    run_time(chosen, "completionTime")
    # This check stands for "STG is running this commit"; any other run that had not
    # finished before the newest one was created may have rolled STG after it.
    for run in stg:
        if run is not chosen and run_time(run, "completionTime") >= latest:
            raise ValueError(
                f"STG run {run['metadata']['name']} had not finished before the newest run started"
            )
    return chosen


def stg_child(stg, task_name, label):
    """The STG run's one TaskRun for task_name, read and checked to be that run's and Succeeded."""
    children = [
        c
        for c in stg["status"]["childReferences"]
        if c["pipelineTaskName"] == task_name and c["kind"] == "TaskRun"
    ]
    if len(children) != 1:
        raise ValueError("missing or ambiguous " + task_name + " TaskRun")
    task = read_json(["get", "taskrun", children[0]["name"]])
    validate_run(task)
    if (
        task["metadata"]["name"] != children[0]["name"]
        or task["metadata"]["labels"]["tekton.dev/pipelineRun"]
        != stg["metadata"]["name"]
        or _succeeded(task) != "True"
    ):
        raise ValueError(label + " TaskRun identity/status mismatch")
    return task


def one_result(task, name):
    values = [r["value"] for r in task["status"]["results"] if r["name"] == name]
    if len(values) != 1 or not isinstance(values[0], str):
        raise ValueError("missing or ambiguous " + name + " result")
    return values[0]


def pipeline_runs(pipeline):
    doc = read_json(["get", "pipelineruns", "-l", "tekton.dev/pipeline=" + pipeline])
    if (
        not isinstance(doc, dict)
        or not isinstance(doc.get("items"), list)
        or not isinstance(doc.get("metadata", {}), dict)
        or doc.get("metadata", {}).get("continue")
    ):
        raise ValueError("malformed or incomplete PipelineRun list")
    for run in doc["items"]:
        validate_run(run)
        ref = run["spec"].get("pipelineRef")
        if (
            _pipeline_name(run) != pipeline
            or not isinstance(ref, dict)
            or ref.get("name") != pipeline
        ):
            raise ValueError("PipelineRun does not match selector " + pipeline)
    return doc["items"]


def main():
    sha = os.environ.get("REVISION", "unresolved")
    condition = "CI/STG"
    try:
        with tempfile.TemporaryDirectory() as tmp:
            base = os.environ["GITEA_BASE"]
            if base != "http://gitea.cicd.svc.cluster.local:3000/bifrost":
                raise ValueError("invalid Gitea base")
            sha = resolve(
                base + "/bifrost-platform.git",
                os.environ["REVISION"],
                tmp + "/platform",
            )
            condition = "CI"
            runs = pipeline_runs("bifrost-ci-platform")
            if classify(runs, "bifrost-platform", sha) != "succeeded":
                raise ValueError("no exact-SHA Succeeded CI")
            condition = "STG"
            stg = latest_stg(pipeline_runs("bifrost-deliver-platform"))
            task = stg_child(stg, "clone-platform", "clone")
            commits = [
                r["value"] for r in task["status"]["results"] if r["name"] == "commit"
            ]
            if len(commits) != 1 or commits[0] != sha:
                raise ValueError("STG clone commit differs or is ambiguous")
            condition = "CI/STG"
            ui = resolve(
                base + "/bifrost-ui.git", os.environ["UI_REVISION"], tmp + "/ui"
            )
            # TD-335: PROD deploys the console STG built, so it must be of this UI commit.
            condition = "STG"
            if one_result(stg_child(stg, "clone-ui", "UI clone"), "commit") != ui:
                raise ValueError("STG UI clone commit differs from uiRevision")
            # The pair the same STG run's rollout verified on STG: its verifier writes
            # them only once the Pods ran them, and took them from that run's builds.
            rollout = stg_child(stg, "rollout", "rollout")
            api, console = one_result(rollout, "api-digest"), one_result(rollout, "console-digest")
            if not DIGEST_RE.fullmatch(api) or not DIGEST_RE.fullmatch(console):
                raise ValueError("STG rollout digests are malformed")
            Path(os.environ["COMMIT_PATH"]).write_text(sha)
            Path(os.environ["UI_COMMIT_PATH"]).write_text(ui)
            Path(os.environ["API_DIGEST_PATH"]).write_text(api)
            Path(os.environ["CONSOLE_DIGEST_PATH"]).write_text(console)
        return 0
    except Exception as exc:
        if isinstance(exc, ValueError):
            reason = str(exc)
        elif isinstance(exc, subprocess.CalledProcessError):
            # git: the credential travels in the environment, never in argv or output.
            reason = "CalledProcessError: " + detail(exc.stderr)
        else:
            reason = type(exc).__name__
        sha = " ".join(sha.split())
        print(f"REFUSED: {condition} cannot be shown for {sha}: {reason}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
