"""ci_gate finds a CI run for repo@sha whether the repo is a param or a label."""

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from ci_gate import classify  # noqa: E402

SHA = "a" * 40


def _run(pipeline, params, labels=None, ok="True"):
    return {
        "metadata": {"labels": {"tekton.dev/pipeline": pipeline, **(labels or {})}},
        "spec": {"params": [{"name": k, "value": v} for k, v in params.items()]},
        "status": {"conditions": [{"type": "Succeeded", "status": ok}]},
    }


def test_python_run_with_repo_param() -> None:
    runs = [_run("bifrost-ci-python", {"repo": "bifrost-trade-core", "revision": SHA})]
    assert classify(runs, "bifrost-trade-core", SHA) == "succeeded"


def test_frontend_run_with_repo_only_as_label() -> None:
    # 2026-10-07: ci-frontend-9ptxp had revision + uiRevision params and the repo
    # only in bifrost.io/repo, so release.sh read it as missing.
    runs = [_run("bifrost-ci-frontend", {"revision": SHA, "uiRevision": "main"},
                 {"bifrost.io/repo": "bifrost-trade-frontend"})]
    assert classify(runs, "bifrost-trade-frontend", SHA) == "succeeded"


def test_label_of_another_repo_does_not_match() -> None:
    runs = [_run("bifrost-ci-frontend", {"revision": SHA}, {"bifrost.io/repo": "bifrost-ui"})]
    assert classify(runs, "bifrost-trade-frontend", SHA) == "missing"


def test_failed_run_reads_failed() -> None:
    runs = [_run("bifrost-ci-frontend", {"revision": SHA}, {"bifrost.io/repo": "bifrost-trade-frontend"}, ok="False")]
    assert classify(runs, "bifrost-trade-frontend", SHA) == "failed"


# R5:5.7-1: one SHA can have a console-scope run (only the Go tests a console change can
# reach) and a full one. A full run decides; a release takes only a full one.
def _platform(ok="True", scope=None):
    run = _run("bifrost-ci-platform", {"revision": SHA, "uiRevision": "main"}, {"bifrost.io/repo": "bifrost-platform"}, ok)
    if scope is not None:
        run["status"]["results"] = [{"name": "platform-commit", "value": SHA}] + [
            {"name": "api-scope", "value": v} for v in (scope if isinstance(scope, list) else [scope])]
    return run


def test_a_full_run_decides_over_a_console_one() -> None:
    from ci_gate import gate
    cases = [
        # (runs, push to main, release)
        ([_platform("True", "console")], "succeeded", "console"),
        ([_platform("True", "console"), _platform("False")], "failed", "failed"),
        ([_platform("True", "console"), _platform("False", "full")], "failed", "failed"),
        ([_platform("False", "console"), _platform("True")], "succeeded", "succeeded"),
        ([_platform("False", "console"), _platform("True", "full")], "succeeded", "succeeded"),
        ([_platform("False", "console")], "failed", "failed"),
        # a run from before api-scope ran every test
        ([_platform("True")], "succeeded", "succeeded"),
        # a malformed api-scope (two, empty, another value) counts for nothing, as B5 reads it
        ([_platform("True", ["full", "full"])], "malformed", "malformed"),
        ([_platform("True", "")], "malformed", "malformed"),
        ([_platform("True", "partial")], "malformed", "malformed"),
        ([_platform("False", ["console", "full"])], "malformed", "malformed"),
        ([_platform("True", ["full", "full"]), _platform("False")], "failed", "failed"),
        ([_platform("True", "partial"), _platform("True", "console")], "succeeded", "console"),
        ([_platform("False", ""), _platform("True", "full")], "succeeded", "succeeded"),
        ([_platform("Unknown", "console")], "missing", "missing"),
    ]
    for runs, push, release in cases:
        assert classify(runs, "bifrost-platform", SHA) == push, runs
        assert classify(runs, "bifrost-platform", SHA, require_full=True) == release, runs
    code, text = gate([_platform("True", "console")], [("bifrost-platform", SHA)], "", require_full=True)
    assert code == 2 and "a release needs a full run" in text, text
    assert gate([_platform("True", "console")], [("bifrost-platform", SHA)], "")[0] == 0
    code, text = gate([_platform("True", ["full", "full"])], [("bifrost-platform", SHA)], "")
    assert code == 2 and "malformed api-scope" in text, text
    # the other pipelines have no api-scope: unchanged
    py = [_run("bifrost-ci-python", {"repo": "bifrost-trade-core", "revision": SHA})]
    assert classify(py, "bifrost-trade-core", SHA, require_full=True) == "succeeded"


def test_release_and_the_prod_gate_require_a_full_run(tmp_path) -> None:
    import json
    import subprocess
    here = os.path.dirname(__file__)
    runs = tmp_path / "runs.json"
    runs.write_text(json.dumps({"items": [_platform("True", "console")]}))
    gate = os.path.join(here, "ci_gate.py")
    args = ["python3", gate, "--runs", str(runs), f"bifrost-platform={SHA}"]
    assert subprocess.run(args, capture_output=True).returncode == 0
    assert subprocess.run(args + ["--require-full"], capture_output=True).returncode == 2
    # A landing's incremental run is a partial run too (countdown 20).
    runs.write_text(json.dumps({"items": [_platform("True", "incremental")]}))
    assert subprocess.run(args, capture_output=True).returncode == 0
    assert subprocess.run(args + ["--require-full"], capture_output=True).returncode == 2
    release = open(os.path.join(here, "release.sh")).read()
    # The Owner, 2026-11-06: release.sh asks for a full run only with the switch on.
    assert release.count('ci_gate.py" --runs') == 1
    assert '[[ "${BIFROST_RELEASE_REQUIRE_FULL_CI:-off}" == on ]] && full=(--require-full)' in release
    # push-main counts a console run when no full one has finished (a lane's commit has no other).
    push_main = [line for line in open(os.path.join(here, "push-main.sh")).read().splitlines()
                 if "ci_gate.py" in line and not line.lstrip().startswith("#")]
    assert push_main and not any("--require-full" in line for line in push_main)
    prod = open(os.path.join(here, "platform_prod_gate.py")).read()
    assert 'classify(runs, "bifrost-platform", sha, require_full=require_full)' in prod
    assert 'require_full = os.environ.get("REQUIRE_FULL_CI", "off") == "on"' in prod


def _reuse_pair(scope="full"):
    original = _platform(scope=scope)
    original["spec"]["params"][0]["value"] = "b" * 40
    original["metadata"].update(name="original", creationTimestamp="2026-11-06T10:00:00Z")
    reuse = _platform(scope="full")
    reuse["metadata"].update(name="reuse", creationTimestamp="2026-11-06T11:00:00Z")
    for run in (original, reuse):
        run["status"]["results"] += [
            {"name": name, "value": value}
            for name, value in (("platform-tree", "c" * 40), ("ui-commit", "d" * 40),
                                ("infra-commit", "e" * 40))]
    reuse["status"]["results"].append({"name": "tested-by", "value": "original"})
    return original, reuse


def test_reuse_full_green_and_release_output():
    from ci_gate import gate
    original, reuse = _reuse_pair()
    assert classify([reuse, original], "bifrost-platform", SHA, True) == "succeeded"
    code, output = gate(iter([reuse, original]), [("bifrost-platform", SHA)], "", True)
    assert code == 0
    assert "tested by original" in output


def test_reuse_rejects_invalid_originals():
    import copy
    original, reuse = _reuse_pair()
    variants = []
    red = copy.deepcopy(original)
    red["status"]["conditions"][0]["status"] = "False"
    variants.append([red, reuse])
    for name in ("platform-tree", "ui-commit", "infra-commit"):
        other = copy.deepcopy(original)
        next(r for r in other["status"]["results"] if r["name"] == name)["value"] = "f" * 40
        variants.append([other, reuse])
    chain = copy.deepcopy(original)
    chain["status"]["results"].append({"name": "tested-by", "value": "older"})
    variants.append([chain, reuse])
    for timestamp in ("2026-11-06T12:00:00Z", "2026-11-06T11:00:00Z", "invalid", None):
        later = copy.deepcopy(original)
        later["metadata"]["creationTimestamp"] = timestamp
        variants.append([later, reuse])
    variants += [[reuse], [original, copy.deepcopy(original), reuse]]
    for runs in variants:
        assert classify(runs, "bifrost-platform", SHA, True) != "succeeded"


def test_reuse_inherits_original_scope():
    original, reuse = _reuse_pair("incremental")
    assert classify([original, reuse], "bifrost-platform", SHA) == "succeeded"
    assert classify([original, reuse], "bifrost-platform", SHA, True) == "console"


def test_reuse_requires_unambiguous_identity_results():
    import copy
    original, reuse = _reuse_pair()
    for name in ("platform-tree", "ui-commit", "infra-commit", "tested-by"):
        for remove in (True, False):
            bad = copy.deepcopy(reuse)
            results = bad["status"]["results"]
            item = next(r for r in results if r["name"] == name)
            if remove:
                if name == "tested-by":
                    continue
                results.remove(item)
            else:
                results.append(item.copy())
            assert classify([original, bad], "bifrost-platform", SHA, True) != "succeeded"
