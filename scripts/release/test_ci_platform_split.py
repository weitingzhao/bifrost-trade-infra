"""R5:5.7-5: test-api runs in two parts side by side in bifrost-ci-platform.

Part store runs ./internal/agentrt/store alone, part rest go vet and every other package;
together each package once. These cases run test-api's own step for each part against the
small module of test_ci_platform_scope.py (its helpers, not a copy).
"""
from __future__ import annotations

import shutil

import pytest

from test_ci_platform_scope import module, run_api


@pytest.mark.skipif(shutil.which("go") is None, reason="go is not installed")
def test_the_two_parts_run_every_package_once_and_vet_in_rest(tmp_path):
    # R5:5.7-5: part store runs ./internal/agentrt/store alone, part rest go vet and every
    # other package; together each package once. Here every package passes and marks it.
    api = module(tmp_path, {"api/internal/agentrt/store/a_test.go":
                            'package store\nimport ("os"; "testing")\n'
                            'func TestRan(t *testing.T) { os.WriteFile(os.Getenv("RAN_DIR")+"/store", nil, 0o600) }\n'})
    (api / "internal/other/a_test.go").write_text('package other\nimport ("os"; "testing")\n'
                                                   'func TestRan(t *testing.T) { os.WriteFile(os.Getenv("RAN_DIR")+"/other", nil, 0o600) }\n')
    r, ran = run_api(tmp_path, api, "full", "store")
    assert r.returncode == 0, r.stdout + r.stderr
    assert sorted(p.name for p in ran.iterdir()) == ["store"] and "==> go vet" not in r.stdout
    r, ran = run_api(tmp_path, api, "full", "rest")
    assert r.returncode == 0, r.stdout + r.stderr
    assert sorted(p.name for p in ran.iterdir()) == ["cluster", "other", "rules", "s5check"]
    assert "==> go vet ./..." in r.stdout and "every one but example.invalid/scope/internal/agentrt/store (part rest)" in r.stdout
    r, ran = run_api(tmp_path, api, "full")
    assert r.returncode == 0 and sorted(p.name for p in ran.iterdir()) == ["cluster", "other", "rules", "s5check", "store"]
    # Console scope: the scope check passes on this tree, so part store runs nothing and
    # part rest runs the listed packages, as the whole task did.
    r, ran = run_api(tmp_path, api, "console", "store")
    assert r.returncode == 0 and "part store runs no test" in r.stdout and not list(ran.iterdir()), r.stdout
    r, ran = run_api(tmp_path, api, "console", "rest")
    assert r.returncode == 0 and sorted(p.name for p in ran.iterdir()) == ["cluster", "rules", "s5check"], r.stdout
    # An unknown part runs nothing and fails the task.
    r, ran = run_api(tmp_path, api, "full", "Store")
    assert r.returncode != 0 and "unknown part Store" in r.stdout and not list(ran.iterdir())
