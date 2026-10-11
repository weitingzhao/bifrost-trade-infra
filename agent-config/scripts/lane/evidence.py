"""Intent and manifest publication, legal shapes, and digest checks.

Manifests have two legal shapes (ran, not started). Anything else is invalid
evidence. Output digests are recomputed from the files the event points at.
"""

from __future__ import annotations

import re
from pathlib import Path

from events import sha256_bytes
from fsutil import canonical_json, publish

_FINDING = re.compile(r"^[ \t]*(?:[-*][ \t]+)?(?:\*\*)?P([123])\b", re.MULTILINE)
VERDICT_FIX = "VERDICT: fix first"
VERDICT_SAFE = "VERDICT: safe to merge"
VERDICT_PASS = "VERDICT: pass"
END_MARK = "END OF REPORT"


def count_priorities(text: str) -> dict[str, int]:
    counts = {"p1": 0, "p2": 0, "p3": 0}
    for match in _FINDING.finditer(text):
        counts[f"p{match.group(1)}"] += 1
    return counts


def nonempty_lines(text: str) -> list[str]:
    return [line.strip() for line in text.splitlines() if line.strip()]


def parse_verify_stdout(raw: bytes) -> str:
    lines = nonempty_lines(raw.decode("utf-8", "replace"))
    return lines[-1] if lines else ""


def parse_review_report(raw: bytes) -> dict:
    text = raw.decode("utf-8-sig", "replace")
    lines = nonempty_lines(text)
    counts = count_priorities(text)
    return {
        "report_first_line": lines[0] if lines else "",
        "report_last_line": lines[-1] if lines else "",
        "p1": counts["p1"],
        "p2": counts["p2"],
        "p3": counts["p3"],
    }


def rejects_from_fields(fields: dict | None) -> bool:
    return bool(fields) and fields.get("report_first_line") == VERDICT_FIX


def attempt_dir(lane_dir: Path, exec_body: dict) -> Path:
    return lane_dir / f"r{int(exec_body['round'])}" / f"{exec_body['step']}-{exec_body['attempt_id']}"


def _is_null(value: object) -> bool:
    return value is None


def classify_manifest(obj: object, step: str) -> tuple[str, str | None]:
    """Return ``(ran|not_started|invalid, which)``."""
    if not isinstance(obj, dict):
        return "invalid", "manifest shape"
    not_started = obj.get("not_started", "missing")
    if not_started is None:
        return _classify_ran(obj, step)
    if isinstance(not_started, dict):
        return _classify_unstarted(obj, not_started)
    return "invalid", "manifest shape"


def _classify_unstarted(obj: dict, not_started: dict) -> tuple[str, str | None]:
    if not isinstance(not_started.get("check"), str) or not isinstance(not_started.get("reason"), str):
        return "invalid", "manifest shape"
    if "repo" not in not_started:
        return "invalid", "manifest shape"
    for key in ("exit", "termination", "started_at", "ended_at", "checks", "fields"):
        if obj.get(key) is not None:
            return "invalid", "manifest shape"
    outputs = obj.get("outputs")
    if outputs not in ({}, None):
        return "invalid", "manifest shape"
    if not isinstance(obj.get("exec"), dict):
        return "invalid", "manifest shape"
    return "not_started", None


def _classify_ran(obj: dict, step: str) -> tuple[str, str | None]:
    exit_body = obj.get("exit")
    if not isinstance(exit_body, dict):
        return "invalid", "manifest shape"
    code, signal = exit_body.get("code"), exit_body.get("signal")
    if (code is None) == (signal is None):
        return "invalid", "manifest shape"
    if not isinstance(obj.get("termination"), str):
        return "invalid", "manifest shape"
    if _is_null(obj.get("started_at")) or _is_null(obj.get("ended_at")):
        return "invalid", "manifest shape"
    outputs = obj.get("outputs")
    if not isinstance(outputs, dict):
        return "invalid", "manifest shape"
    for name in ("stdout", "stderr"):
        item = outputs.get(name)
        if not isinstance(item, dict) or not isinstance(item.get("length"), int) or not isinstance(item.get("sha256"), str):
            return "invalid", "manifest shape"
    fields = obj.get("fields")
    checks = obj.get("checks")
    if not isinstance(fields, dict) or not isinstance(checks, dict):
        return "invalid", "manifest shape"
    if step == "verify" and not isinstance(fields.get("stdout_last_line"), str):
        return "invalid", "manifest shape"
    if step == "review":
        report = outputs.get("report")
        if not isinstance(report, dict) or not isinstance(report.get("present"), bool):
            return "invalid", "manifest shape"
        if report.get("present"):
            if not isinstance(report.get("length"), int) or not isinstance(report.get("sha256"), str):
                return "invalid", "manifest shape"
        for key in ("report_first_line", "report_last_line", "p1", "p2", "p3"):
            if key not in fields:
                return "invalid", "manifest shape"
    if step == "implement":
        if not isinstance(obj.get("pinned"), dict) or not isinstance(obj.get("bundles"), dict):
            return "invalid", "manifest shape"
        if not isinstance(obj.get("notes"), list):
            return "invalid", "manifest shape"
    if not isinstance(obj.get("exec"), dict) or not isinstance(obj.get("intent_sha256"), str):
        return "invalid", "manifest shape"
    if not isinstance(obj.get("consumed"), dict):
        return "invalid", "manifest shape"
    return "ran", None


def _file_digest(path: Path) -> tuple[int, str] | None:
    if not path.is_file():
        return None
    data = path.read_bytes()
    return len(data), sha256_bytes(data)


def assess_attempt(lane_dir: Path, intent_event: dict | None, recorded: dict | None) -> dict:
    """Problems are ordered; the first one is the ``which`` of invalid evidence."""
    problems: list[str] = []
    manifest = None
    if recorded is None:
        return {"problems": problems, "manifest": None}
    exec_body = recorded.get("exec") or {}
    root = attempt_dir(lane_dir, exec_body)
    intent_path = root / "rec" / "intent.json"
    intent_sha = (intent_event or {}).get("intent_sha256")
    if not intent_path.is_file():
        problems.append("intent missing")
    else:
        got = sha256_bytes(intent_path.read_bytes())
        if intent_sha and got != intent_sha:
            problems.append("intent_sha256 mismatch")
    manifest_path = root / "rec" / "manifest.json"
    if not manifest_path.is_file():
        problems.append("manifest missing")
        return {"problems": problems, "manifest": None}
    blob = manifest_path.read_bytes()
    if sha256_bytes(blob) != recorded.get("manifest_sha256"):
        problems.append("manifest sha256 mismatch")
        return {"problems": problems, "manifest": None}
    try:
        text = blob.decode("utf-8")
        if text.endswith("\n"):
            text = text[:-1]
        manifest = json_loads(text)
    except ValueError:
        problems.append("manifest shape")
        return {"problems": problems, "manifest": None}
    kind, _which = classify_manifest(manifest, exec_body.get("step", ""))
    if kind == "invalid":
        problems.append("manifest shape")
        return {"problems": problems, "manifest": manifest}
    if (manifest.get("exec") or {}) != exec_body:
        problems.append("exec mismatch")
    if manifest.get("intent_sha256") != intent_sha:
        problems.append("intent_sha256 mismatch")
    if not _facts_match(manifest, recorded):
        problems.append("facts mismatch")
    problems.extend(_output_problems(root, manifest, exec_body.get("step", "")))
    return {"problems": problems, "manifest": manifest}


def json_loads(text: str):
    from fsutil import loads_strict

    obj = loads_strict(text)
    if not isinstance(obj, dict):
        raise ValueError("object")
    return obj


def _facts_match(manifest: dict, recorded: dict) -> bool:
    if manifest.get("not_started") != recorded.get("not_started"):
        return False
    if manifest.get("exit") != recorded.get("exit"):
        return False
    if manifest.get("consumed") != recorded.get("consumed"):
        return False
    step = (recorded.get("exec") or {}).get("step")
    if step == "implement":
        # An unstarted implement pins nothing. The event carries an empty set;
        # the unstarted manifest shape does not repeat it.
        if manifest.get("not_started") is not None:
            if recorded.get("pinned") not in ({}, None) or recorded.get("bundles") not in ({}, None):
                return False
        elif manifest.get("pinned") != recorded.get("pinned") or manifest.get("bundles") != recorded.get("bundles"):
            return False
    if step == "review" and bool(recorded.get("rejects")) != rejects_from_fields(manifest.get("fields")):
        if manifest.get("outputs", {}).get("report", {}).get("present"):
            return False
    return True


def _output_problems(root: Path, manifest: dict, step: str) -> list[str]:
    if manifest.get("not_started") is not None:
        return []
    problems = []
    outputs = manifest.get("outputs") or {}
    for name in ("stdout", "stderr"):
        spec = outputs.get(name) or {}
        got = _file_digest(root / "out" / name)
        if got is None:
            problems.append(f"{name} missing")
            continue
        length, digest = got
        if length != spec.get("length") or digest != spec.get("sha256"):
            problems.append(f"{name} changed")
    if step == "review":
        report = outputs.get("report") or {}
        path = root / "out" / "report"
        if report.get("present"):
            got = _file_digest(path)
            if got is None:
                problems.append("report missing")
            else:
                length, digest = got
                if length != report.get("length") or digest != report.get("sha256"):
                    problems.append("report changed")
    if step == "implement":
        for repo, spec in (manifest.get("bundles") or {}).items():
            got = _file_digest(root / "rec" / f"{repo}.bundle")
            if got is None:
                problems.append("bundle missing")
                break
            length, digest = got
            if length != spec.get("length") or digest != spec.get("sha256"):
                problems.append("bundle changed")
                break
    return problems


def publish_json_doc(dest: Path, obj: dict) -> str:
    data = canonical_json(obj).encode("utf-8")
    publish(dest, data)
    return sha256_bytes(data)


def manifest_digest(obj: dict) -> str:
    return sha256_bytes(canonical_json(obj).encode("utf-8"))
