"""test-console is pinned whole: the task equals a literal, and so do its clones.

The four commands, in order, --maxWorkers equal to the CPU limit, the CPU
request equal to that limit, and the key allow-lists are why the literal is
the gate. Those checks run on the literal as well as on the YAML. They do
not enumerate bad edits. A later edit of the task edits this test in the
same commit.

The script is compared after stripping trailing whitespace per line. Every
other key and value is exact. A 1s timeout, another image, a workspace
subPath or a different memory size fails that equality.

clone and clone-ui are pinned the same way: they produce what test-console
reads. clone-infra and the other tasks do not, so they are not pinned.

The task, its taskSpec and its one step may only use the keys listed below.
when, onError, retries, an env, a sidecar or a second step fail by the key's
name (or by the step count), and by the equality. They are not listed in
advance.
"""

from __future__ import annotations

import copy
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
PIPELINE = ROOT / "k8s/cicd/tekton/pipeline-ci-platform.yaml"

COMMANDS = (
    "npx tsc --noEmit",
    "npm run lint",
    "npx vitest run",
    "npm run build",
)

# Semantic fixture for the four commands. Not the pinned step: CANONICAL is.
# The old npm ci fallback stays here so these checks remain about the four
# gate lines, and a fallback on some other line is not what rejects a script.
GOOD = """#!/usr/bin/env bash
set -euo pipefail
echo "==> npm ci"
npm ci 2>/dev/null || npm install
echo "==> tsc --noEmit"
npx tsc --noEmit
echo "==> npm run lint"
npm run lint
echo "==> vitest run"
npx vitest run
echo "==> npm run build"
npm run build
"""

# The whole step script from pipeline-ci-platform.yaml. Edit it here in the
# same commit as the YAML. The install is npm ci with stderr kept: a lockfile
# mismatch must fail the step, not fall through to npm install.
CANONICAL = """#!/usr/bin/env bash
set -euo pipefail
ws="$(workspaces.source.path)"

# Scripts on: bifrost-ui's prepare builds dist/, which is not in git.
echo "==> Installing bifrost-ui"
cd "${ws}/bifrost-ui"
npm ci --no-audit --no-fund
test -f dist/index.d.ts || { echo "bifrost-ui dist/index.d.ts missing after npm ci"; exit 1; }

cd "${ws}/bifrost-platform/console"

echo "==> npm ci"
npm ci --no-audit --no-fund

echo "==> tsc --noEmit"
npx tsc --noEmit

echo "==> npm run lint"
npm run lint

echo "==> vitest run"
# The pod sees the node's cores; the limit is two CPUs.
# Measured 2026-10-11: without it, 7 of 814 tests time out.
npx vitest run --maxWorkers=2

echo "==> npm run build"
npm run build

echo "==> Console type-check, lint, tests and build passed"
"""

# Subsets, not a denylist. Today's task uses all of these and no others.
# A legitimate new key is added to the matching set, with a comment saying why.
ALLOWED_TASK_KEYS = frozenset({"name", "runAfter", "timeout", "workspaces", "taskSpec"})
ALLOWED_TASKSPEC_KEYS = frozenset({"workspaces", "steps"})
ALLOWED_STEP_KEYS = frozenset({"name", "image", "computeResources", "script"})
WANTED_RUN_AFTER = ["clone", "clone-ui"]

# The whole test-console task. A deliberate change edits this literal in the
# same commit as the YAML. script is CANONICAL; everything else is exact.
EXPECTED_CONSOLE = {
    "name": "test-console",
    "timeout": "8m0s",
    "runAfter": ["clone", "clone-ui"],
    "workspaces": [
        {"name": "source", "workspace": "source"},
    ],
    "taskSpec": {
        "workspaces": [
            {"name": "source"},
        ],
        "steps": [
            {
                "name": "typecheck-lint-test-build",
                "image": "node:20-slim",
                "computeResources": {
                    "requests": {"cpu": "2", "memory": "1Gi"},
                    "limits": {"cpu": "2", "memory": "4Gi"},
                },
                "script": CANONICAL,
            },
        ],
    },
}

# clone and clone-ui produce what test-console reads: the platform tree and
# bifrost-ui. clone-infra feeds other tasks, so it is not pinned here.
EXPECTED_CLONE = {
    "name": "clone",
    "taskRef": {"name": "bifrost-git-clone-gitea"},
    "params": [
        {"name": "url", "value": "$(params.giteaBase)/bifrost-platform.git"},
        {"name": "revision", "value": "$(params.revision)"},
        {"name": "subdir", "value": "bifrost-platform"},
    ],
    "workspaces": [
        {"name": "output", "workspace": "source"},
    ],
}
EXPECTED_CLONE_UI = {
    "name": "clone-ui",
    "taskRef": {"name": "bifrost-git-clone-gitea"},
    "params": [
        {"name": "url", "value": "$(params.giteaBase)/bifrost-ui.git"},
        {"name": "revision", "value": "$(params.uiRevision)"},
        {"name": "subdir", "value": "bifrost-ui"},
    ],
    "workspaces": [
        {"name": "output", "workspace": "source"},
    ],
}


def _invokes(line: str, command: str) -> bool:
    if line == command:
        return True
    if not line.startswith(command):
        return False
    return line[len(command):len(command) + 1] in ("", " ", "\t", "|", ";", "&")


def _gate_lines(script: str) -> list[tuple[str, str]]:
    found: list[tuple[str, str]] = []
    for raw in script.splitlines():
        line = raw.strip()
        match = None
        for command in COMMANDS:
            if _invokes(line, command) and (match is None or len(command) > len(match)):
                match = command
        if match is not None:
            found.append((match, line))
    return found


def _strict_before_commands(script: str) -> bool:
    """-e, -u and pipefail are all on before the first gate command."""
    errexit = nounset = pipefail = False
    for raw in script.splitlines():
        line = raw.strip()
        if any(_invokes(line, command) for command in COMMANDS):
            break
        if not line.startswith("set "):
            continue
        parts = line[4:].split()
        if not parts:
            continue
        if parts[0].startswith("-") and not parts[0].startswith("-o"):
            letters = parts[0][1:]
            errexit = errexit or "e" in letters
            nounset = nounset or "u" in letters
            if "o" in letters and "pipefail" in parts[1:]:
                pipefail = True
        if parts[0] == "-o" and "pipefail" in parts[1:]:
            pipefail = True
    return errexit and nounset and pipefail


def _hides_exit(line: str) -> str | None:
    if "|| true" in line or "||true" in line:
        return "|| true"
    if "|| :" in line or "||:" in line:
        return "|| :"
    if "; true" in line or ";true" in line:
        return "; true"
    if "2>/dev/null" in line:
        return "2>/dev/null"
    if "|" in line.replace("||", ""):
        return "pipe"
    return None


def problems(script: str) -> list[str]:
    """Why this script is not the Console gate. Empty means it is."""
    reasons: list[str] = []
    if not _strict_before_commands(script):
        reasons.append("script does not start with set -euo pipefail semantics")
    found = _gate_lines(script)
    got = [command for command, _line in found]
    if got != list(COMMANDS):
        reasons.append(f"command order is {got}, want {list(COMMANDS)}")
    for command, line in found:
        hidden = _hides_exit(line)
        if hidden:
            reasons.append(f"{command} hides its exit with {hidden}: {line}")
    return reasons


def whole_cpus(limit: object) -> int | None:
    """CPU limit as a positive whole number of CPUs, or None.

    ``"2"``, ``2`` and ``"2000m"`` are 2. ``"2.5"`` and ``"1500m"`` are not.
    """
    if isinstance(limit, bool):
        return None
    if isinstance(limit, int):
        return limit if limit > 0 else None
    if isinstance(limit, float):
        if limit > 0 and limit.is_integer():
            return int(limit)
        return None
    if not isinstance(limit, str):
        return None
    text = limit.strip()
    if text.endswith("m") and text[:-1].isdigit():
        milli = int(text[:-1])
        if milli > 0 and milli % 1000 == 0:
            return milli // 1000
        return None
    if not text or not text.replace(".", "", 1).isdigit() or text.count(".") > 1:
        return None
    number = float(text)
    if number > 0 and number.is_integer():
        return int(number)
    return None


def cpu_guarantee_problems(cpu_request: object, cpu_limit: object) -> list[str]:
    """Why the step is not guaranteed the CPUs its tests were measured with.

    The worker count is pinned to the limit; a request below the limit lets a
    busy node give the step less, and the same tests then time out.
    """
    limit = whole_cpus(cpu_limit)
    if limit is None:
        return [f"limits.cpu {cpu_limit!r} is not a whole number of CPUs"]
    request = whole_cpus(cpu_request)
    if request != limit:
        return [f"requests.cpu is {cpu_request!r}, want the limit ({limit}): the step must be guaranteed what it was measured with"]
    return []


def worker_pin_problems(script: str, cpu_limit: object) -> list[str]:
    """Why vitest's --maxWorkers does not match this step's CPU limit."""
    count = whole_cpus(cpu_limit)
    if count is None:
        return [f"cpu limit {cpu_limit!r} is not a whole number of CPUs"]
    want = f"--maxWorkers={count}"
    lines = [line for command, line in _gate_lines(script) if command == "npx vitest run"]
    if len(lines) != 1:
        return [f"vitest line lacks {want}"]
    tokens = [
        tok for tok in lines[0].split()
        if tok == "--maxWorkers" or tok.startswith("--maxWorkers=")
    ]
    if tokens == [want]:
        return []
    if not tokens:
        return [f"vitest line lacks {want}"]
    return [f"vitest line has {tokens[0]}, want {want}"]


_PINNED = GOOD.replace("\nnpx vitest run\n", "\nnpx vitest run --maxWorkers=2\n", 1)

# Negative cases. The expected worker count is read from the limit, so a
# flag that used to match still fails once the limit changes.
WORKER_DRIFT = (
    ("flag absent", GOOD, "2"),
    ("different number", GOOD.replace("\nnpx vitest run\n", "\nnpx vitest run --maxWorkers=4\n", 1), "2"),
    ("limit changed", _PINNED, "4"),
    ("millicpu fraction", _PINNED, "1500m"),
    ("fractional cpus", _PINNED, "2.5"),
)


def _norm(script: str) -> str:
    """Strip trailing whitespace per line. Nothing else is normalised."""
    return "\n".join(line.rstrip() for line in script.splitlines())


def _norm_scripts(task: dict) -> dict:
    """Copy whose step scripts use _norm. Every other value is untouched."""
    task = copy.deepcopy(task)
    steps = (task.get("taskSpec") or {}).get("steps") or []
    if isinstance(steps, list):
        for step in steps:
            if isinstance(step, dict) and isinstance(step.get("script"), str):
                step["script"] = _norm(step["script"])
    return task


def console_matches(doc: dict) -> bool:
    """The one test-console task equals EXPECTED_CONSOLE.

    The script uses per-line trailing-whitespace normalisation. Everything
    else — timeout, image, both workspace layers, resources — is exact.
    """
    tasks = _console_tasks(doc)
    if len(tasks) != 1:
        return False
    return _norm_scripts(tasks[0]) == _norm_scripts(EXPECTED_CONSOLE)


def _task(doc: dict, name: str) -> dict | None:
    tasks = (doc.get("spec") or {}).get("tasks") or []
    found = [
        item for item in tasks
        if isinstance(item, dict) and item.get("name") == name
    ]
    if len(found) != 1:
        return None
    return found[0]


def clones_match(doc: dict) -> bool:
    """clone and clone-ui equal their literals. No other task is compared."""
    return _task(doc, "clone") == EXPECTED_CLONE and _task(doc, "clone-ui") == EXPECTED_CLONE_UI


def _console_tasks(doc: dict) -> list[dict]:
    tasks = (doc.get("spec") or {}).get("tasks") or []
    return [
        item for item in tasks
        if isinstance(item, dict) and item.get("name") == "test-console"
    ]


def shape_problems(doc: dict) -> list[str]:
    """Why this document is not the pinned test-console task. Empty means it is."""
    reasons: list[str] = []
    tasks = _console_tasks(doc)
    if len(tasks) != 1:
        reasons.append(f"{len(tasks)} tasks named test-console, want 1")
        return reasons
    task = tasks[0]
    for key in sorted(set(task) - ALLOWED_TASK_KEYS):
        reasons.append(f"unexpected task key: {key}")
    if task.get("runAfter") != WANTED_RUN_AFTER:
        reasons.append(f"runAfter is {task.get('runAfter')!r}, want {WANTED_RUN_AFTER!r}")
    spec = task.get("taskSpec")
    if not isinstance(spec, dict):
        reasons.append("taskSpec is missing")
        return reasons
    for key in sorted(set(spec) - ALLOWED_TASKSPEC_KEYS):
        reasons.append(f"unexpected taskSpec key: {key}")
    steps = spec.get("steps")
    if not isinstance(steps, list) or len(steps) != 1 or not isinstance(steps[0], dict):
        count = len(steps) if isinstance(steps, list) else 0
        reasons.append(f"{count} steps, want 1")
        return reasons
    step = steps[0]
    for key in sorted(set(step) - ALLOWED_STEP_KEYS):
        reasons.append(f"unexpected step key: {key}")
    script = step.get("script")
    if not isinstance(script, str) or _norm(script) != _norm(CANONICAL):
        reasons.append("script is not the pinned Console gate")
    return reasons


def _console_step(doc: dict) -> dict:
    tasks = _console_tasks(doc)
    if len(tasks) != 1:
        return {}
    steps = (tasks[0].get("taskSpec") or {}).get("steps") or []
    if len(steps) != 1 or not isinstance(steps[0], dict):
        return {}
    return steps[0]


def _load() -> dict:
    return yaml.safe_load(PIPELINE.read_text(encoding="utf-8"))


def _with_script(script: str) -> dict:
    doc = copy.deepcopy(_load())
    _console_step(doc)["script"] = script
    return doc


def _wrap_checks(script: str) -> str:
    start = script.index('echo "==> tsc --noEmit"')
    marker = "npm run build\n"
    end = script.index(marker) + len(marker)
    return script[:start] + "if false; then\n" + script[start:end] + "fi\n" + script[end:]


# Script edits the equality rejects. The semantic checks do not see these:
# the commands are still present, in order, with their exits intact.
SCRIPT_EDITS = (
    (
        "set +e after the strict-mode line",
        CANONICAL.replace("set -euo pipefail\n", "set -euo pipefail\nset +e\n", 1),
    ),
    (
        "exit 0 before the checks",
        CANONICAL.replace(
            'echo "==> tsc --noEmit"\n',
            'exit 0\necho "==> tsc --noEmit"\n',
            1,
        ),
    ),
    ("checks wrapped in if false", _wrap_checks(CANONICAL)),
)


def _set_param(task: dict, name: str, value: str) -> None:
    for param in task["params"]:
        if param.get("name") == name:
            param["value"] = value
            return
    raise AssertionError(name)


def _with_edit(kind: str) -> dict:
    doc = copy.deepcopy(_load())
    tasks = doc["spec"]["tasks"]
    task = next(item for item in tasks if item.get("name") == "test-console")
    step = task["taskSpec"]["steps"][0]
    if kind == "timeout":
        task["timeout"] = "1s"
    elif kind == "image":
        step["image"] = "node:18-slim"
    elif kind == "subPath":
        # On the task binding, so the step sees a different directory.
        task["workspaces"][0]["subPath"] = "bifrost-platform/console"
    elif kind == "limits-memory":
        step["computeResources"]["limits"]["memory"] = "64Mi"
    elif kind == "requests-memory":
        step["computeResources"]["requests"]["memory"] = "1Ti"
    elif kind == "onError":
        step["onError"] = "continue"
    elif kind == "when":
        # Always false: the step would be skipped. The key alone is enough.
        task["when"] = [{"input": "false", "operator": "in", "values": ["true"]}]
    elif kind == "runAfter":
        task["runAfter"] = ["clone"]
    elif kind == "duplicate":
        tasks.append(copy.deepcopy(task))
    elif kind == "drop-clone-ui":
        doc["spec"]["tasks"] = [item for item in tasks if item.get("name") != "clone-ui"]
    elif kind == "revision-main":
        _set_param(_task(doc, "clone"), "revision", "main")
    elif kind == "subdir":
        _set_param(_task(doc, "clone-ui"), "subdir", "somewhere")
    else:
        raise AssertionError(kind)
    return doc


# Object edits. The expected fragment is the key, or the runAfter / count text.
SHAPE_EDITS = (
    ("onError: continue on the step", "onError", "unexpected step key: onError"),
    ("when on the task", "when", "unexpected task key: when"),
    ("runAfter changed to [clone]", "runAfter", "runAfter is ['clone']"),
    ("a second task named test-console", "duplicate", "2 tasks named test-console"),
)

# Value edits the equality rejects. The allow-list still permits these keys.
VALUE_EDITS = (
    ("timeout: 1s", "timeout"),
    ("a different image", "image"),
    ("subPath on the task workspace", "subPath"),
    ("limits.memory: 64Mi", "limits-memory"),
    ("requests.memory: 1Ti", "requests-memory"),
)

# clone-ui removed makes the DAG invalid. A fixed revision or a different
# subdir makes test-console read the wrong tree.
CLONE_EDITS = (
    ("clone-ui removed", "drop-clone-ui"),
    ("clone revision set to main", "revision-main"),
    ("clone-ui subdir changed", "subdir"),
)


def _step_script(doc: dict) -> str:
    return _console_step(doc).get("script") or ""


def _without(script: str, command: str) -> str:
    kept = [line for line in script.splitlines() if line.strip() != command]
    return "\n".join(kept) + "\n"


def _swap_lines(script: str, left: str, right: str) -> str:
    lines = script.splitlines()
    i = lines.index(left)
    j = lines.index(right)
    lines[i], lines[j] = lines[j], lines[i]
    return "\n".join(lines) + "\n"


class ConsoleGateTests(unittest.TestCase):
    def test_real_pipeline_step_is_the_gate(self) -> None:
        doc = _load()
        self.assertEqual(doc["metadata"]["name"], "bifrost-ci-platform")
        self.assertEqual(shape_problems(doc), [])
        script = _step_script(doc)
        limit = ((_console_step(doc).get("computeResources") or {}).get("limits") or {}).get("cpu")
        # The canonical text is the gate for the same reason the YAML script is.
        self.assertEqual(problems(CANONICAL), [])
        self.assertEqual(worker_pin_problems(CANONICAL, limit), [])
        self.assertEqual(problems(script), [])
        self.assertEqual(worker_pin_problems(script, limit), [])

    def test_only_trailing_whitespace_per_line_is_normalised(self) -> None:
        spaced = CANONICAL.replace("set -euo pipefail", "set -euo pipefail   ", 1)
        self.assertEqual(shape_problems(_with_script(spaced)), [])
        self.assertTrue(console_matches(_with_script(spaced)))
        indented = CANONICAL.replace("set -euo pipefail", " set -euo pipefail", 1)
        reasons = shape_problems(_with_script(indented))
        self.assertTrue(any("pinned" in reason for reason in reasons), reasons)
        self.assertFalse(console_matches(_with_script(indented)))

    def test_script_edits_are_rejected(self) -> None:
        for label, script in SCRIPT_EDITS:
            self.assertNotEqual(_norm(script), _norm(CANONICAL), label)
            reasons = shape_problems(_with_script(script))
            self.assertTrue(any("pinned" in reason for reason in reasons), (label, reasons))
            self.assertFalse(console_matches(_with_script(script)), label)

    def test_shape_edits_are_rejected(self) -> None:
        for label, kind, needle in SHAPE_EDITS:
            reasons = shape_problems(_with_edit(kind))
            self.assertTrue(any(needle in reason for reason in reasons), (label, reasons))

    def test_the_parsed_task_equals_the_literal(self) -> None:
        got = _console_tasks(_load())
        self.assertEqual(
            [_norm_scripts(task) for task in got],
            [_norm_scripts(EXPECTED_CONSOLE)],
        )
        step = EXPECTED_CONSOLE["taskSpec"]["steps"][0]
        resources = step["computeResources"]
        # The literal is the gate for the same reason the YAML task is.
        self.assertEqual(problems(step["script"]), [])
        self.assertEqual(worker_pin_problems(step["script"], resources["limits"]["cpu"]), [])
        self.assertEqual(
            cpu_guarantee_problems(resources["requests"]["cpu"], resources["limits"]["cpu"]),
            [],
        )
        self.assertEqual(shape_problems({"spec": {"tasks": [EXPECTED_CONSOLE]}}), [])
        for label, kind in VALUE_EDITS:
            self.assertFalse(console_matches(_with_edit(kind)), label)
        for label, kind, _needle in SHAPE_EDITS:
            self.assertFalse(console_matches(_with_edit(kind)), label)

    def test_clone_and_clone_ui_equal_the_literals(self) -> None:
        doc = _load()
        self.assertEqual(_task(doc, "clone"), EXPECTED_CLONE)
        self.assertEqual(_task(doc, "clone-ui"), EXPECTED_CLONE_UI)
        for label, kind in CLONE_EDITS:
            self.assertFalse(clones_match(_with_edit(kind)), label)

    def test_a_clean_script_passes(self) -> None:
        self.assertEqual(problems(GOOD), [])

    def test_removing_a_command_is_rejected(self) -> None:
        for command in COMMANDS:
            reasons = problems(_without(GOOD, command))
            self.assertTrue(any(command in reason and "order" in reason for reason in reasons), reasons)

    def test_or_true_is_rejected(self) -> None:
        script = GOOD.replace("\nnpm run lint\n", "\nnpm run lint || true\n", 1)
        reasons = problems(script)
        self.assertTrue(any("|| true" in reason for reason in reasons), reasons)

    def test_changed_order_is_rejected(self) -> None:
        script = _swap_lines(GOOD, "npm run lint", "npx vitest run")
        reasons = problems(script)
        self.assertTrue(any("order" in reason for reason in reasons), reasons)
        self.assertFalse(any("|| true" in reason for reason in reasons), reasons)

    def test_other_exit_hiding_is_rejected(self) -> None:
        cases = {
            "|| :": GOOD.replace("\nnpx tsc --noEmit\n", "\nnpx tsc --noEmit || :\n", 1),
            "; true": GOOD.replace("\nnpm run build\n", "\nnpm run build; true\n", 1),
            "2>/dev/null": GOOD.replace("\nnpx vitest run\n", "\nnpx vitest run 2>/dev/null\n", 1),
            "pipe": GOOD.replace("\nnpm run lint\n", "\nnpm run lint | tee /tmp/lint\n", 1),
        }
        for label, script in cases.items():
            reasons = problems(script)
            self.assertTrue(any(label in reason for reason in reasons), (label, reasons))

    def test_missing_strict_mode_is_rejected(self) -> None:
        script = GOOD.replace("set -euo pipefail", "set -e", 1)
        reasons = problems(script)
        self.assertTrue(any("set -euo pipefail" in reason for reason in reasons), reasons)

    def test_cpu_request_equals_the_limit(self) -> None:
        doc = yaml.safe_load(PIPELINE.read_text(encoding="utf-8"))
        resources = _console_step(doc).get("computeResources") or {}
        request = (resources.get("requests") or {}).get("cpu")
        limit = (resources.get("limits") or {}).get("cpu")
        self.assertEqual(cpu_guarantee_problems(request, limit), [])
        self.assertEqual(cpu_guarantee_problems("2", "2"), [])
        self.assertEqual(cpu_guarantee_problems("2000m", 2), [])

    def test_a_cpu_request_below_the_limit_is_rejected(self) -> None:
        for request, limit in (("500m", "2"), ("1", "2"), (None, "2"), ("2", "4"), ("2", "1500m")):
            with self.subTest(request=request, limit=limit):
                self.assertNotEqual(cpu_guarantee_problems(request, limit), [])

    def test_worker_pin_tracks_the_cpu_limit(self) -> None:
        doc = yaml.safe_load(PIPELINE.read_text(encoding="utf-8"))
        step = _console_step(doc)
        limit = ((step.get("computeResources") or {}).get("limits") or {}).get("cpu")
        self.assertEqual(worker_pin_problems(step.get("script") or "", limit), [])
        self.assertEqual(worker_pin_problems(_PINNED, "2"), [])
        self.assertEqual(worker_pin_problems(_PINNED, 2), [])
        self.assertEqual(worker_pin_problems(_PINNED, "2000m"), [])

    def test_worker_pin_drift_is_rejected(self) -> None:
        for label, script, limit in WORKER_DRIFT:
            reasons = worker_pin_problems(script, limit)
            self.assertTrue(reasons, label)
            if label == "flag absent":
                self.assertTrue(any("lacks --maxWorkers=2" in reason for reason in reasons), reasons)
            elif label == "different number":
                self.assertTrue(
                    any("has --maxWorkers=4" in reason and "want --maxWorkers=2" in reason for reason in reasons),
                    reasons,
                )
            elif label == "limit changed":
                self.assertTrue(
                    any("has --maxWorkers=2" in reason and "want --maxWorkers=4" in reason for reason in reasons),
                    reasons,
                )
            else:
                self.assertTrue(
                    any("not a whole number of CPUs" in reason for reason in reasons),
                    (label, reasons),
                )


if __name__ == "__main__":
    unittest.main()
