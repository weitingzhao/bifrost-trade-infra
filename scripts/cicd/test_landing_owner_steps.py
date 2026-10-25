"""Validate the published Owner commands without credentials or a cluster."""
import json
import os
from pathlib import Path
import re
import subprocess
import sys

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
DOCUMENT = ROOT / "agent-config/work/multi-agent/OWNER-STEPS-landing-s0-2026-10-24.md"


def test_all_owner_shell_blocks_parse():
    blocks = re.findall(r"```bash\n(.*?)```", DOCUMENT.read_text(), re.S)
    assert blocks
    for block in blocks:
        result = subprocess.run(["bash", "-n"], input=block, capture_output=True, text=True)
        assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("present,status", [(False, 0), (True, 0), (False, 7)])
def test_prod_binding_check_stops_on_presence_or_read_failure(present, status):
    blocks = re.findall(r"```bash\n(.*?)```", DOCUMENT.read_text(), re.S)
    block = next(b for b in blocks if "landing_prod_binding=" in b)
    # Export a shell function into the documented child bash; never invoke kubectl.
    fake = ('kubectl() {\n'
            + ('echo rolebinding.rbac.authorization.k8s.io/bifrost-platform-gitea-creds-prod\n' if present else '')
            + f'return {status}\n' + '}\nexport -f kubectl\n')
    result = subprocess.run(["bash"], input=fake + block, capture_output=True, text=True)
    if present or status:
        assert result.returncode != 0
        assert "PASS:" not in result.stdout
        if present:
            assert "S6 did not take effect" in result.stderr
    else:
        assert result.returncode == 0, result.stderr
        assert "PASS: PROD credential binding absent" in result.stdout


def test_rollback_commands_pipe_git_manifest_to_apply(tmp_path):
    commands = [line for line in DOCUMENT.read_text().splitlines()
                if line.startswith("git show ") and " apply " in line]
    assert len(commands) == 2
    # A shell function consumes stdin instead of running kubectl. No kubeconfig is opened.
    capture = tmp_path / "capture.py"
    capture.write_text('''import json, os, sys
from pathlib import Path
Path(os.environ["TEST_CAPTURE"]).write_text(json.dumps({"args": sys.argv[1:], "input": sys.stdin.read()}))
''')
    output = tmp_path / "output.json"
    env = {**os.environ, "TEST_PYTHON": sys.executable, "TEST_HELPER": str(capture),
           "TEST_CAPTURE": str(output)}
    baseline = subprocess.check_output(
        ["git", "show", "881253d:k8s/cicd/tekton/pipeline-ci-platform.yaml"], cwd=ROOT, text=True)
    for index, command in enumerate(commands):
        script = 'kubectl() { "$TEST_PYTHON" "$TEST_HELPER" "$@"; }\n' + command
        result = subprocess.run(["bash", "-euo", "pipefail"], input=script, cwd=ROOT,
                                env=env, capture_output=True, text=True)
        assert result.returncode == 0, result.stderr
        captured = json.loads(output.read_text())
        args = captured["args"]
        assert args[0] == "--kubeconfig" and args[1].endswith("/kube/admin.yaml")
        assert args[2:] == ["apply", *(["--dry-run=server"] if index == 0 else []), "-f", "-"]
        assert captured["input"] == baseline
        manifest = yaml.safe_load(captured["input"])
        assert manifest["kind"] == "Pipeline"
        metadata = manifest["metadata"]
        assert metadata["name"] == "bifrost-ci-platform"
        assert metadata["namespace"] == "cicd"
        assert not {"resourceVersion", "managedFields", "uid", "creationTimestamp"} & metadata.keys()
        assert "kubectl.kubernetes.io/last-applied-configuration" not in metadata.get("annotations", {})
