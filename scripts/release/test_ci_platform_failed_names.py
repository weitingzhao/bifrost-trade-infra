"""A full run of bifrost-ci-platform names what failed (failed-tests).

Origin: 2026-11-16. The unit-scope shadow had compared 104 runs and found no
missed unit, but all 10 failed runs among them were "failed_unnamed": the full
path of test-api ran `go test` and exited, and failed-tests stayed empty. A
shadow that cannot name the failing package cannot say whether an incremental
run would have run it. Four of those failures, read from the pod logs, were
agentrt/rules (TestLandingHardConsoleCallSites, three times) and actions with
safego; their output is the fixture below.
"""
import pathlib
import re
import subprocess

import yaml

TASK = pathlib.Path(__file__).resolve().parents[2] / "k8s/cicd/tekton/task-ci-platform-test-api.yaml"
MOD = "github.com/weitingzhao/bifrost-platform/api/internal/"

FAILED = f"""ok  \t{MOD}actuation\t0.210s
--- FAIL: TestWriteRoutesAreCataloguedOrExempt (0.01s)
    coverage_test.go:41: POST /api/v1/bus/x is neither catalogued nor exempt
FAIL
FAIL\t{MOD}actions\t0.071s
ok  \t{MOD}agentrt/canon\t(cached)
--- FAIL: TestNoUnguardedGoroutines (0.05s)
    --- FAIL: TestNoUnguardedGoroutines/api (0.01s)
--- FAIL: TestSecond (0.00s)
FAIL
FAIL\t{MOD}safego\t0.054s
FAIL\t{MOD}server [build failed]
FAIL
"""
PASSED = f"ok  \t{MOD}actuation\t0.210s\nok  \t{MOD}actions\t0.071s\n"


def function_text() -> str:
    step = next(s for s in yaml.safe_load(TASK.read_text())["spec"]["steps"] if s["name"] == "go-test")
    return re.search(r"^named_go_test\(\) \{\n.*?^\}\n", step["script"], re.S | re.M).group(0)


def run(tmp_path, output: str, code: int):
    fake = tmp_path / "bin"
    fake.mkdir()
    (tmp_path / "out.txt").write_text(output)
    (fake / "go").write_text(f"#!/bin/sh\ncat '{tmp_path}/out.txt'\nexit {code}\n")
    (fake / "go").chmod(0o755)
    result = tmp_path / "failed-tests"
    result.write_text("")
    script = "set -euo pipefail\n" + function_text() + 'named_go_test ./... -timeout=1s\necho "after"\n'
    r = subprocess.run(["bash", "-c", script], capture_output=True, text=True,
                       env={"PATH": f"{fake}:/usr/bin:/bin", "FAILED_TESTS_RESULT": str(result), "TMPDIR": str(tmp_path)})
    return r, result.read_text()


def test_a_failed_full_run_names_each_failed_test_and_keeps_go_tests_output_and_status(tmp_path):
    r, names = run(tmp_path, FAILED, 1)
    assert r.returncode == 1 and "after" not in r.stdout
    assert FAILED in r.stdout  # what go test printed is printed
    assert names.split(",") == [
        MOD + "actions.TestWriteRoutesAreCataloguedOrExempt",
        MOD + "safego.TestNoUnguardedGoroutines",
        MOD + "safego.TestSecond",
        MOD + "server",  # did not build: the package alone
    ]


def test_a_passing_run_writes_nothing_and_goes_on(tmp_path):
    """The control: names appear only when go test failed."""
    r, names = run(tmp_path, PASSED, 0)
    assert r.returncode == 0 and r.stdout.endswith("after\n") and names == ""


def test_the_names_fit_a_tekton_result(tmp_path):
    many = "".join(f"--- FAIL: TestNumber{i:04d} (0.00s)\n" for i in range(400)) + f"FAIL\nFAIL\t{MOD}server\t1.0s\n"
    _, names = run(tmp_path, many, 1)
    assert 0 < len(names.encode()) <= 1500


def test_every_go_test_of_the_full_path_goes_through_it():
    step = next(s for s in yaml.safe_load(TASK.read_text())["spec"]["steps"] if s["name"] == "go-test")
    full = step["script"].split('if [ -n "$why" ]; then', 1)[1].split("# Incremental:", 1)[0]
    assert full.count("named_go_test ") == 3
    assert not re.search(r"^\s+go test ", full, re.M)
