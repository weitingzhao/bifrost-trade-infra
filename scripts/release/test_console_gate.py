"""test-console must run type-check, lint, tests and build, and a later edit cannot drop one.

The four commands are the gate. A script that omits one, hides its exit, or
reorders them is rejected. The npm ci fallback line is not one of the four.

The vitest line must carry --maxWorkers equal to the step's CPU limit. That
limit has to be a whole number of CPUs; anything else is rejected, so the
worker count cannot drift away from the limit.
"""

from __future__ import annotations

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

# A script that already passes, including the pre-existing npm ci fallback.
# The fallback hides stderr; the four gate lines must not.
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


def _console_step(doc: dict) -> dict:
    tasks = (doc.get("spec") or {}).get("tasks") or []
    task = next(item for item in tasks if item.get("name") == "test-console")
    steps = (task.get("taskSpec") or {}).get("steps") or []
    if len(steps) != 1 or not isinstance(steps[0], dict):
        return {}
    return steps[0]


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
        doc = yaml.safe_load(PIPELINE.read_text(encoding="utf-8"))
        self.assertEqual(doc["metadata"]["name"], "bifrost-ci-platform")
        self.assertEqual(problems(_step_script(doc)), [])

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
