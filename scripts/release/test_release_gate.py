"""Release-gate decisions. No network: the inputs are JSON objects."""

import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(__file__))

from release_gate import decide  # noqa: E402

SHA = "a" * 40
UI = "b" * 40
OTHER = "c" * 40
NOW = "2026-10-10T12:00:00Z"
SCRIPT = os.path.join(os.path.dirname(__file__), "release_gate.py")


def _ci(name, sha, ok, start="2026-10-10T09:00:00Z"):
    conds = []
    if ok is not None:
        conds.append({"type": "Succeeded", "status": ok})
    return {
        "metadata": {
            "name": name,
            "labels": {"tekton.dev/pipeline": "bifrost-ci-platform"},
            "creationTimestamp": start,
        },
        "spec": {
            "pipelineRef": {"name": "bifrost-ci-platform"},
            "params": [{"name": "revision", "value": sha}],
        },
        "status": {"startTime": start, "conditions": conds},
    }


def _stg(name, ok, start, end=None, pipeline="bifrost-deliver-platform"):
    run = {
        "metadata": {
            "name": name,
            "labels": {"tekton.dev/pipeline": pipeline},
            "creationTimestamp": start,
        },
        "spec": {
            "pipelineRef": {"name": pipeline},
            "params": [{"name": "revision", "value": "main"}, {"name": "uiRevision", "value": "main"}],
        },
        "status": {
            "startTime": start,
            "conditions": [{"type": "Succeeded", "status": ok}],
        },
    }
    if end:
        run["status"]["completionTime"] = end
    return run


def _clone(run_name, task, sha):
    return {
        "metadata": {
            "name": f"{run_name}-{task}",
            "labels": {
                "tekton.dev/pipelineRun": run_name,
                "tekton.dev/pipelineTask": task,
            },
        },
        "status": {
            "conditions": [{"type": "Succeeded", "status": "True"}],
            "completionTime": "2026-10-10T11:35:00Z",
            "results": [{"name": "commit", "value": sha}],
        },
    }


def _doc(runs, taskruns=None, platform=SHA, ui=UI, now=NOW, soak=10):
    doc = {
        "platform_sha": platform,
        "ui_sha": ui,
        "pipelineruns": {"apiVersion": "v1", "kind": "List", "items": runs},
        "now": now,
        "soak_minutes": soak,
    }
    if taskruns is not None:
        doc["taskruns"] = {"items": taskruns}
    return doc


def _good_stg():
    return _stg("stg-good", "True", "2026-10-10T11:30:00Z", "2026-10-10T11:40:00Z")


def _clones(run="stg-good", platform=SHA, ui=UI):
    return [_clone(run, "clone-platform", platform), _clone(run, "clone-ui", ui)]


def test_clone_results_on_the_run() -> None:
    run = _good_stg()
    run["status"]["cloneResults"] = {"clone-platform": SHA, "clone-ui": UI}
    code, text = decide(_doc([_ci("ci-platform-ok", SHA, "True"), run]))
    assert code == 0
    assert text.splitlines()[0] == "pass"


def test_pass() -> None:
    runs = [
        _ci("ci-old-red", SHA, "False", "2026-10-10T08:00:00Z"),
        _ci("ci-platform-ok", SHA, "True"),
        _stg("stg-old", "False", "2026-10-10T10:00:00Z", "2026-10-10T10:05:00Z"),
        _good_stg(),
        # A newer prod delivery must not hide the STG success.
        _stg("prod-newer", "False", "2026-10-10T11:50:00Z", "2026-10-10T11:55:00Z",
             pipeline="bifrost-deliver-platform-prod"),
    ]
    code, text = decide(_doc(runs, _clones()))
    assert code == 0
    assert text.splitlines()[0] == "pass"


def test_ci_red() -> None:
    runs = [_ci("ci-platform-red", SHA, "False"), _good_stg()]
    code, text = decide(_doc(runs, _clones()))
    assert code == 1
    assert text.splitlines()[0] == f"CI failed for {SHA}: ci-platform-red"


def test_ci_running() -> None:
    running = _ci("ci-platform-open", SHA, "Unknown")
    code, text = decide(_doc([running, _good_stg()], _clones()))
    assert code == 2
    assert text.splitlines()[0] == f"CI has not finished for {SHA}"


def test_no_ci_run() -> None:
    other = _ci("ci-python", SHA, "True")
    other["metadata"]["labels"]["tekton.dev/pipeline"] = "bifrost-ci-python"
    other["spec"]["pipelineRef"]["name"] = "bifrost-ci-python"
    code, text = decide(_doc([other, _good_stg()], _clones()))
    assert code == 1
    assert text.splitlines()[0] == f"no CI run for {SHA}"


def test_allow_red_key_does_not_let_a_red_ci_through() -> None:
    doc = _doc([_ci("ci-platform-red", SHA, "False")], _clones())
    doc["allow_red"] = "owner said so"
    code, text = decide(doc)
    assert code == 1
    assert text.splitlines()[0] == f"CI failed for {SHA}: ci-platform-red"


def test_stg_on_another_platform_sha() -> None:
    runs = [_ci("ci-platform-ok", SHA, "True"), _good_stg()]
    code, text = decide(_doc(runs, _clones(platform=OTHER)))
    assert code == 1
    assert text.splitlines()[0] == f"STG runs {OTHER}, not {SHA}"


def test_stg_on_another_ui_sha() -> None:
    runs = [_ci("ci-platform-ok", SHA, "True"), _good_stg()]
    code, text = decide(_doc(runs, _clones(ui=OTHER)))
    assert code == 1
    assert text.splitlines()[0] == f"STG runs {OTHER}, not {UI}"


def test_soak_not_reached() -> None:
    runs = [
        _ci("ci-platform-ok", SHA, "True"),
        _stg("stg-fresh", "True", "2026-10-10T11:50:00Z", "2026-10-10T11:57:00Z"),
    ]
    code, text = decide(_doc(runs, _clones("stg-fresh")))
    assert code == 1
    assert text.splitlines()[0] == "STG has run this for 3 min, need 10"


def test_newer_failed_stg_does_not_count() -> None:
    runs = [
        _ci("ci-platform-ok", SHA, "True"),
        _stg("stg-good", "True", "2026-10-10T10:00:00Z", "2026-10-10T10:05:00Z"),
        _stg("stg-bad", "False", "2026-10-10T11:00:00Z", "2026-10-10T11:05:00Z"),
    ]
    code, text = decide(_doc(runs, _clones()))
    assert code == 1
    assert text.splitlines()[0] == "newest STG delivery stg-bad did not succeed"


def test_malformed_input() -> None:
    code, text = decide({"platform_sha": "not-a-sha", "ui_sha": UI, "now": NOW})
    assert code == 1
    assert text.splitlines()[0].startswith("malformed input:")

    code, text = decide({
        "platform_sha": SHA,
        "ui_sha": UI,
        "now": NOW,
        "pipelineruns": "not-a-list",
    })
    assert code == 1
    assert text.splitlines()[0].startswith("malformed input:")

    proc = subprocess.run(
        [sys.executable, SCRIPT, "--input", "-"],
        input="{",
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode != 0
    assert proc.stdout.splitlines()[0].startswith("malformed input:")

    proc = subprocess.run(
        [sys.executable, SCRIPT],
        input=json.dumps({"platform_sha": SHA}),
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode != 0
    assert proc.stdout.splitlines()[0].startswith("malformed input:")
