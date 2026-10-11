"""Ratchet tests T10 and T33."""

from __future__ import annotations

import io
import sys
import tempfile
import textwrap
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import prod_ratchet  # noqa: E402

ROLE = textwrap.dedent(
    """\
    apiVersion: rbac.authorization.k8s.io/v1
    kind: ClusterRole
    metadata:
      name: example-role
      labels:
        app: example
    rules:
      - apiGroups: [""]
        resources: ["configmaps"]
        resourceNames: ["platform-config"]
        verbs: ["patch"]
    """
)

TASK = textwrap.dedent(
    """\
    apiVersion: tekton.dev/v1
    kind: Task
    metadata:
      name: example-task
      namespace: cicd
    spec:
      serviceAccountName: example-sa
      steps:
        - name: run
          image: example.invalid/tool:1
          script: |
            echo one
    """
)

BINDING = textwrap.dedent(
    """\
    apiVersion: admissionregistration.k8s.io/v1
    kind: ValidatingAdmissionPolicyBinding
    metadata:
      name: example-binding
    spec:
      policyName: example
      validationActions: ["Deny"]
    """
)


def _write(root: Path, name: str, text: str) -> None:
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


class RatchetTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "tree"
        self.baseline = Path(self.tmp.name) / "baseline.jsonl"
        _write(self.root, "role.yaml", ROLE)
        _write(self.root, "task.yaml", TASK)
        _write(self.root, "binding.yaml", BINDING)
        code, out, err = self._run("--write")
        self.assertEqual(code, 0, err or out)

    def tearDown(self):
        self.tmp.cleanup()

    def _run(self, *args: str) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        argv = ["--root", str(self.root), "--baseline", str(self.baseline), "--fixed", str(HERE / "prod_fixed_identities.json"), *args]
        with redirect_stdout(out), redirect_stderr(err):
            code = prod_ratchet.main(argv)
        return code, out.getvalue(), err.getvalue()

    def test_t10_each_surface_change_fails_and_names_the_row(self):
        cases = [
            ("crd.yaml", textwrap.dedent(
                """\
                apiVersion: apiextensions.k8s.io/v1
                kind: CustomResourceDefinition
                metadata:
                  name: widgets.example.invalid
                spec:
                  group: example.invalid
                  names:
                    plural: widgets
                  versions:
                    - name: v1
                      subresources:
                        status: {}
                """
            ), "widgets.example.invalid"),
        ]
        code, out, err = self._run("--check")
        self.assertEqual(code, 0, err or out)

        _write(self.root, "crd.yaml", cases[0][1])
        code, out, _err = self._run("--check")
        self.assertNotEqual(code, 0)
        self.assertIn("多出一行", out)
        self.assertIn("widgets.example.invalid", out)
        (self.root / "crd.yaml").unlink()

        role = ROLE.replace(
            "app: example",
            'app: example\n    rbac.authorization.k8s.io/aggregate-to-admin: "true"',
        )
        _write(self.root, "role.yaml", role)
        code, out, _err = self._run("--check")
        self.assertNotEqual(code, 0)
        self.assertIn("example-role", out)
        _write(self.root, "role.yaml", ROLE)

        _write(self.root, "role.yaml", ROLE.replace("platform-config", "other-config"))
        code, out, _err = self._run("--check")
        self.assertNotEqual(code, 0)
        self.assertIn("example-role", out)
        _write(self.root, "role.yaml", ROLE)

        _write(self.root, "task.yaml", TASK.replace("echo one", "echo two"))
        code, out, _err = self._run("--check")
        self.assertNotEqual(code, 0)
        self.assertIn("example-task", out)
        _write(self.root, "task.yaml", TASK)

        _write(self.root, "task.yaml", TASK.replace("example-sa", "other-sa"))
        code, out, _err = self._run("--check")
        self.assertNotEqual(code, 0)
        self.assertIn("example-task", out)
        _write(self.root, "task.yaml", TASK)

        _write(self.root, "binding.yaml", BINDING.replace("Deny", "Warn"))
        code, out, _err = self._run("--check")
        self.assertNotEqual(code, 0)
        self.assertIn("example-binding", out)

    def test_t33_deleted_baseline_line_is_an_extra_row(self):
        lines = self.baseline.read_text(encoding="utf-8").splitlines()
        self.baseline.write_text("\n".join(lines[1:]) + "\n", encoding="utf-8")
        code, out, _err = self._run("--check")
        self.assertNotEqual(code, 0)
        self.assertIn("多出一行", out)
        self.baseline.write_text("this is not json\n", encoding="utf-8")
        code, _out, err = self._run("--check")
        self.assertEqual(code, 2)
        self.assertIn("invalid JSON", err)
        missing = self.baseline.with_name("missing-baseline.jsonl")
        if missing.exists():
            missing.unlink()
        code, _out, err = self._run("--check", "--baseline", str(missing))
        self.assertEqual(code, 2)
        self.assertIn("unreadable", err)


if __name__ == "__main__":
    unittest.main()
