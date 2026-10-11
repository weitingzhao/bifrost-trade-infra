"""Mutation coverage for the lane's evidence, and the AST guard the decision uses.

The allow-list is the only set of fields a mutant may change and still decide
``passed``. Everything else is evidence. Seal fields (digests, the hash chain,
output and bundle length) are rewritten after each mutant so a checksum is not
what rejects it; a mutant that resealing puts back is not counted.
"""

from __future__ import annotations

import ast
import re
from copy import deepcopy

from commands import cmd_next_round
from errors import LaneError
from events import dump_line, sha256_bytes
from evidence import attempt_dir, json_loads
from fsutil import canonical_json
from query import expected_start, start_kind
from state import inspect_lane
from support import A, B, C, TA, TB, TC, implement_ok, make_lane, passing_prechecks, review_ok, sha_set, verify_ok

F = "f" * 40
D = "d" * 40
E = "e" * 40
TD = "4" * 40
TE = "5" * 40

# Timestamps and free text the decision does not read. Printed by the test.
ALLOW = frozenset({
    "at",
    "created_at",
    "started_at",
    "ended_at",
    "lstart",
    "title",
    "reason",
    "notes",
    "note",
    "operator",
    "how",
    "evidence",
    "text",
    "pid",
    "driver_pid",
    "limit_seconds",
    "brief_path",
    "brief_copy",
    "brief_sha256",
    "config_path",
    "config_sha256",
    "pinned_files",
    "inputs",
    "max_rounds",
    "lane_id",
    "argv",
    "cwd",
    "env_names",
    "toolchain",
    "p1",
    "p2",
    "p3",
    "result",
})

# Rewritten so the mutant stays internally consistent. Not counted on their own.
SEAL = frozenset({
    "seq",
    "prev_sha256",
    "intent_sha256",
    "manifest_sha256",
    "sha256",
    "length",
})

_NAME = re.compile(r"^(?:exp|expected)(?:_[A-Za-z0-9]+)?$")
_COMPARE_OK = frozenset({"same_set", "set_delta"})

FORBIDDEN_SNIPPETS = (
    "if exp.get('tree'):\n    pass\n",
    "if exp and act:\n    pass\n",
    "x if exp else y\n",
    "if expected and act:\n    pass\n",
)

_SHAPES = ("one", "two", "context")
_STORIES = ("round1", "round2", "baseline")


def _rooted(node: ast.AST) -> bool:
    if isinstance(node, ast.Name):
        return _NAME.fullmatch(node.id) is not None
    if isinstance(node, ast.Attribute):
        return _NAME.fullmatch(node.attr) is not None or _rooted(node.value)
    if isinstance(node, ast.Call):
        return _rooted(node.func)
    if isinstance(node, ast.Subscript):
        return _rooted(node.value)
    return False


def _truthy(node: ast.AST) -> bool:
    if isinstance(node, ast.BoolOp):
        return any(_truthy(item) for item in node.values)
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
        return _truthy(node.operand)
    return _rooted(node)


class _Guard(ast.NodeVisitor):
    """Comparisons and truth tests of an expected value, outside the one function."""

    def __init__(self) -> None:
        self._stack: list[str] = []
        self.found: list[tuple[int, str]] = []

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._stack.append(node.name)
        self.generic_visit(node)
        self._stack.pop()

    visit_AsyncFunctionDef = visit_FunctionDef

    def _allowed(self) -> bool:
        return any(name in _COMPARE_OK for name in self._stack)

    def visit_Compare(self, node: ast.Compare) -> None:
        if not self._allowed():
            for op, right in zip(node.ops, node.comparators):
                if isinstance(op, (ast.Eq, ast.NotEq)) and (_rooted(node.left) or _rooted(right)):
                    self.found.append((node.lineno, "compare"))
                    break
        self.generic_visit(node)

    def _test(self, node: ast.AST) -> None:
        if not self._allowed() and _truthy(node):
            self.found.append((getattr(node, "lineno", 0), "truth"))

    def visit_If(self, node: ast.If) -> None:
        self._test(node.test)
        self.generic_visit(node)

    visit_While = visit_If
    visit_Assert = visit_If

    def visit_IfExp(self, node: ast.IfExp) -> None:
        self._test(node.test)
        self.generic_visit(node)


def comparison_sites(tree: ast.AST) -> list[tuple[int, str]]:
    guard = _Guard()
    guard.visit(tree)
    return guard.found


def _repos(shape: str) -> dict:
    if shape == "two":
        return {
            "alpha": {"role": "change", "target_ref": "main", "target_sha": A, "tree": TA},
            "beta": {"role": "change", "target_ref": "main", "target_sha": A, "tree": TA},
        }
    if shape == "context":
        return {
            "repo": {"role": "change", "target_ref": "main", "target_sha": A, "tree": TA},
            "ctx": {"role": "context", "target_ref": "main", "target_sha": A, "tree": TA},
        }
    return {"repo": {"role": "change", "target_ref": "main", "target_sha": A, "tree": TA}}


def _pins(shape: str) -> tuple[dict, dict, dict, dict]:
    if shape == "two":
        pin1 = {"alpha": {"commit": B, "tree": TB}, "beta": {"commit": C, "tree": TC}}
        pin2 = {"alpha": {"commit": D, "tree": TD}, "beta": {"commit": E, "tree": TE}}
        return pin1, pin2, {"alpha": b"a1", "beta": b"b1"}, {"alpha": b"a2", "beta": b"b2"}
    if shape == "context":
        pin1 = {"repo": {"commit": B, "tree": TB}, "ctx": {"commit": A, "tree": TA}}
        pin2 = {"repo": {"commit": C, "tree": TC}, "ctx": {"commit": A, "tree": TA}}
        return pin1, pin2, {"repo": b"bundle"}, {"repo": b"bundle2"}
    pin1 = sha_set(B, TB)
    pin2 = sha_set(C, TC)
    return pin1, pin2, {"repo": b"bundle"}, {"repo": b"bundle2"}


def _drive(lane, consumed, pinned, bundles, kind) -> None:
    implement_ok(
        lane,
        consumed=consumed,
        pinned=pinned,
        pre_checks=passing_prechecks("implement", consumed, kind=kind, expected=consumed),
        bundle_bytes=bundles,
        notes=[],
    )
    verify_ok(lane, consumed=pinned, pre_checks=passing_prechecks("verify", pinned))
    review_ok(lane, consumed=pinned, pre_checks=passing_prechecks("review", pinned))


def _fail_round(lane, consumed, pinned, bundles, kind) -> None:
    implement_ok(
        lane,
        exit_code=9,
        consumed=consumed,
        pinned=pinned,
        pre_checks=passing_prechecks("implement", consumed, kind=kind, expected=consumed),
        bundle_bytes=bundles,
        notes=[],
    )


def build_lane(tmp, shape: str, story: str):
    tmp.mkdir(parents=True, exist_ok=True)
    repos = _repos(shape)
    lane = make_lane(tmp, f"{shape}-{story}", max_rounds=3, repos=repos)
    base = {name: {"commit": A, "tree": TA} for name in repos}
    pin1, pin2, bundles1, bundles2 = _pins(shape)
    if story == "round1":
        _drive(lane, base, pin1, bundles1, "baseline")
        return lane
    _fail_round(lane, base, pin1, bundles1, "baseline")
    start_mode = "baseline" if story == "baseline" else "pinned"
    cmd_next_round(lane.root, lane.lane_id, brief=str(lane.brief), start=start_mode)
    events = lane.events()
    targets = repos
    start = expected_start(events, 2, targets)
    kind = start_kind(events, 2)
    _drive(lane, start, pin2, bundles2, kind)
    return lane


def _corpus(lane) -> dict:
    events = lane.events()
    manifests = []
    for event in events:
        if event.get("type") != "step_recorded":
            continue
        path = attempt_dir(lane.dir, event["exec"]) / "rec" / "manifest.json"
        manifests.append(json_loads(path.read_text(encoding="utf-8")))
    return {"events": events, "manifests": manifests}


def _fill_seals(lane, corpus: dict) -> None:
    """Put file digests back so a mutated checksum is not why the mutant fails."""
    events = corpus["events"]
    manifests = corpus["manifests"]
    recorded = [event for event in events if isinstance(event, dict) and event.get("type") == "step_recorded"]
    for event, body in zip(recorded, manifests):
        if not isinstance(body, dict):
            continue
        exec_body = event.get("exec")
        if not isinstance(exec_body, dict):
            continue
        if not all(isinstance(exec_body.get(key), (str, int)) for key in ("round", "step", "attempt_id")):
            continue
        if not isinstance(exec_body.get("step"), str):
            continue
        try:
            root = attempt_dir(lane.dir, exec_body)
        except (KeyError, TypeError, ValueError):
            continue
        outputs = body.get("outputs")
        if isinstance(outputs, dict):
            for name in ("stdout", "stderr"):
                _fill_file(outputs.get(name), root / "out" / name)
            report = outputs.get("report")
            if isinstance(report, dict) and report.get("present") is True:
                _fill_file(report, root / "out" / "report")
        bundles = body.get("bundles")
        if isinstance(bundles, dict):
            for repo, spec in bundles.items():
                _fill_file(spec, root / "rec" / f"{repo}.bundle")


def _fill_file(spec, path) -> None:
    if not isinstance(spec, dict) or not path.is_file():
        return
    data = path.read_bytes()
    if "length" in spec:
        spec["length"] = len(data)
    if "sha256" in spec:
        spec["sha256"] = sha256_bytes(data)


def _drop_manifest(lane, event) -> None:
    exec_body = event.get("exec") if isinstance(event, dict) else None
    if not isinstance(exec_body, dict) or not isinstance(exec_body.get("step"), str):
        return
    if not isinstance(exec_body.get("attempt_id"), str) or not isinstance(exec_body.get("round"), int):
        return
    try:
        dest = attempt_dir(lane.dir, exec_body) / "rec" / "manifest.json"
    except (KeyError, TypeError, ValueError):
        return
    if dest.is_file():
        dest.unlink()


def _write(lane, corpus: dict) -> None:
    _fill_seals(lane, corpus)
    events = corpus["events"]
    manifests = corpus["manifests"]
    recorded = [event for event in events if isinstance(event, dict) and event.get("type") == "step_recorded"]
    for index, event in enumerate(recorded):
        if index >= len(manifests):
            _drop_manifest(lane, event)
    for event, body in zip(recorded, manifests):
        exec_body = event.get("exec") if isinstance(event, dict) else None
        if not isinstance(exec_body, dict) or not isinstance(exec_body.get("step"), str):
            continue
        if not isinstance(exec_body.get("attempt_id"), str) or not isinstance(exec_body.get("round"), int):
            continue
        try:
            dest = attempt_dir(lane.dir, exec_body) / "rec" / "manifest.json"
        except (KeyError, TypeError, ValueError):
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        data = canonical_json(body).encode("utf-8")
        dest.write_bytes(data)
        event["manifest_sha256"] = sha256_bytes(data)
    _sync_verdict_maps(events)
    prev = ""
    chunks = []
    for index, event in enumerate(events, 1):
        if isinstance(event, dict):
            event["seq"] = index
            event["prev_sha256"] = prev
            line = dump_line(event)
        else:
            body = canonical_json(event).encode("utf-8")
            line = sha256_bytes(body).encode("ascii") + b" " + body + b"\n"
        prev = line[:64].decode("ascii")
        chunks.append(line)
    (lane.dir / "events.jsonl").write_bytes(b"".join(chunks))


def _sync_verdict_maps(events: list) -> None:
    """A verdict's manifest map is a seal. Put the recorded digests back into keys that remain."""
    recorded: dict = {}
    for event in events:
        if not isinstance(event, dict) or event.get("type") != "step_recorded":
            continue
        body = event.get("exec") or {}
        recorded.setdefault(body.get("round"), {})[body.get("step")] = event.get("manifest_sha256")
    for event in events:
        if not isinstance(event, dict) or event.get("type") != "verdict":
            continue
        manifests = event.get("manifests")
        if not isinstance(manifests, dict):
            continue
        for step, digest in (recorded.get(event.get("round")) or {}).items():
            if step in manifests:
                manifests[step] = digest


def _blank_seals(node) -> None:
    if isinstance(node, dict):
        for key in list(node):
            if key in ("sha256", "length", "manifest_sha256", "intent_sha256", "seq", "prev_sha256"):
                node[key] = None
            else:
                _blank_seals(node[key])
        if isinstance(node.get("manifests"), dict):
            node["manifests"] = {key: None for key in node["manifests"]}
    elif isinstance(node, list):
        for item in node:
            _blank_seals(item)


def _semantic(corpus: dict):
    clone = deepcopy(corpus)
    recorded = sum(1 for event in clone["events"] if isinstance(event, dict) and event.get("type") == "step_recorded")
    clone["manifests"] = list(clone["manifests"])[:recorded]
    _blank_seals(clone)
    return clone


def _parent(root, path):
    current = root
    for part in path[:-1]:
        current = current[part]
    return current, path[-1]


def _hashes(node, found: set[str]) -> None:
    if isinstance(node, dict):
        for key, value in node.items():
            if key in ("commit", "tree", "target_sha") and isinstance(value, str) and len(value) == 40:
                found.add(value)
            else:
                _hashes(value, found)
    elif isinstance(node, list):
        for value in node:
            _hashes(value, found)


def _is_sha_set(node) -> bool:
    if not isinstance(node, dict) or not node:
        return False
    for info in node.values():
        if not isinstance(info, dict) or "commit" not in info or "tree" not in info:
            return False
    return True


def _mutations(corpus: dict):
    """Yield ``(label, path, op, extra)`` for one fixture. ``op`` is applied to a copy."""
    pool = set()
    _hashes(corpus, pool)
    yield from _walk(corpus["events"], ("events",), pool)
    yield from _walk(corpus["manifests"], ("manifests",), pool)
    events = corpus["events"]
    for index in range(len(events)):
        yield (f"append event {index}", ("events",), "append", index)
    for index in range(len(events) - 1):
        yield (f"reorder events {index}", ("events",), "reorder", index)


def _walk(node, path, pool: set[str]):
    if isinstance(node, dict):
        yield (f"add-field {_show(path)}", path, "add-field", None)
        names = list(node)
        for key in names:
            if key in SEAL:
                continue
            child = path + (key,)
            yield from _leaf(node[key], child, pool)
            yield from _walk(node[key], child, pool)
        if _is_sha_set(node):
            for name in names:
                yield (f"drop-repo { _show(path) } {name}", path, "drop-repo", name)
            ordered = sorted(name for name in names if isinstance(name, str))
            if len(ordered) >= 2:
                yield (f"swap-repos { _show(path) }", path, "swap-repos", (ordered[0], ordered[1]))
            for name in ordered:
                info = node[name]
                if isinstance(info, dict) and info.get("commit") != info.get("tree"):
                    yield (f"swap-commit-tree {_show(path)} {name}", path + (name,), "swap-pair", None)
    elif isinstance(node, list):
        for index, value in enumerate(node):
            child = path + (index,)
            yield from _leaf(value, child, pool)
            yield from _walk(value, child, pool)
        for index in range(len(node)):
            yield (f"dup {_show(path)}[{index}]", path, "dup", index)
        for index in range(len(node) - 1):
            if node[index] != node[index + 1]:
                yield (f"swap { _show(path) } [{index}]", path, "swap", index)


def _leaf(value, path, pool: set[str]):
    shown = _show(path)
    yield (f"delete {shown}", path, "delete", None)
    if value is not None:
        yield (f"null {shown}", path, "null", None)
    if value != "":
        yield (f"empty {shown}", path, "empty", None)
    key = path[-1] if path else None
    if key in ("commit", "tree", "target_sha") and isinstance(value, str) and value in pool:
        for other in sorted(pool):
            if other != value:
                yield (f"replace {shown} {other}", path, "replace", other)


def _show(path) -> str:
    return "/".join(str(part) for part in path)


def _apply(corpus: dict, path, op: str, extra) -> None:
    if op == "append":
        corpus["events"].append(deepcopy(corpus["events"][extra]))
        return
    if op == "reorder":
        events = corpus["events"]
        events[extra], events[extra + 1] = events[extra + 1], events[extra]
        return
    if op == "add-field":
        node = _at(corpus, path)
        if isinstance(node, dict):
            node["__extra__"] = "extra"
        return
    if op in ("dup", "swap", "drop-repo", "swap-repos"):
        node = _at(corpus, path)
        if op == "dup":
            node.insert(extra, deepcopy(node[extra]))
        elif op == "swap":
            node[extra], node[extra + 1] = node[extra + 1], node[extra]
        elif op == "drop-repo":
            node.pop(extra, None)
        else:
            left, right = extra
            for field in ("commit", "tree"):
                node[left][field], node[right][field] = node[right][field], node[left][field]
        return
    parent, key = _parent(corpus, path)
    if op == "delete":
        if isinstance(parent, dict):
            parent.pop(key, None)
        else:
            del parent[key]
        return
    if op == "null":
        parent[key] = None
        return
    if op == "empty":
        parent[key] = ""
        return
    if op == "replace":
        parent[key] = extra
        return
    if op == "swap-pair":
        info = parent[key]
        info["commit"], info["tree"] = info["tree"], info["commit"]


def _at(root, path):
    current = root
    for part in path:
        current = current[part]
    return current


def _allowed(path, op: str, original: dict) -> bool:
    """True when this mutant may still decide passed.

    ``ALLOW`` is timestamps and free text. Deleting the verdict event is the
    other case: the decision is recomputed from the evidence, so the stamp is
    not an input. The same evidence then waits as a pending pass.
    """
    if op == "delete" and len(path) == 2 and path[0] == "events":
        event = original["events"][path[1]]
        if isinstance(event, dict) and event.get("type") == "verdict":
            return True
    keys = [part for part in path if isinstance(part, str)]
    return bool(keys) and keys[-1] in ALLOW


def _verdict(lane) -> tuple[str | None, str | None]:
    try:
        view = inspect_lane(lane.dir)
    except (KeyError, TypeError, ValueError) as exc:
        return "unknown", f"evidence invalid: {exc}"
    return view.get("decide_result"), view.get("decide_reason")


def test_mutation_no_mutant_passes(tmp_path):
    """Every resealed mutant of a passing lane fails, unless its field is on ALLOW."""
    counts = {"mutants": 0, "invalid": 0, "failed": 0, "allowed": 0}
    used: set[str] = set()
    failures: list[str] = []
    for shape in _SHAPES:
        for story in _STORIES:
            lane = build_lane(tmp_path / f"{shape}-{story}", shape, story)
            original = _corpus(lane)
            _fill_seals(lane, original)
            base = _semantic(original)
            result, reason = _verdict(lane)
            assert result == "passed", (shape, story, result, reason)
            for label, path, op, extra in _mutations(original):
                trial = deepcopy(original)
                _apply(trial, path, op, extra)
                _write(lane, trial)
                if _semantic(trial) == base:
                    continue
                got, why = _verdict(lane)
                counts["mutants"] += 1
                if got == "passed":
                    if op in ("append", "reorder") or not _allowed(path, op, original):
                        failures.append(f"{shape}/{story} {label} -> {got} {why}")
                    else:
                        counts["allowed"] += 1
                        if op == "delete" and len(path) == 2:
                            used.add("verdict-event")
                        else:
                            leaf = next((part for part in reversed(path) if isinstance(part, str)), "")
                            used.add(leaf)
                elif got == "unknown" or (why or "").startswith("evidence invalid"):
                    counts["invalid"] += 1
                else:
                    counts["failed"] += 1
    listed = ", ".join(sorted(ALLOW))
    print(
        f"mutants={counts['mutants']} invalid={counts['invalid']} "
        f"failed={counts['failed']} allowed-by-list={counts['allowed']} "
        f"allow=[{listed}; delete of a verdict event]"
    )
    if used:
        print("allowed-fields-hit: " + ", ".join(sorted(used)))
    for line in failures:
        print("MUTANT PASSED " + line)
    assert failures == []


def _intent_consumed(lane, consumed: dict) -> None:
    """Change only the implement intent's consumed set, and the digest that seals that file."""
    corpus = _corpus(lane)
    intent = next(
        event for event in corpus["events"]
        if event.get("type") == "step_intent" and (event.get("exec") or {}).get("step") == "implement"
    )
    recorded = next(
        event for event in corpus["events"]
        if event.get("type") == "step_recorded" and (event.get("exec") or {}).get("step") == "implement"
    )
    intent["consumed"] = consumed
    path = attempt_dir(lane.dir, intent["exec"]) / "rec" / "intent.json"
    document = json_loads(path.read_text(encoding="utf-8"))
    document["consumed"] = consumed
    data = canonical_json(document).encode("utf-8")
    path.write_bytes(data)
    digest = sha256_bytes(data)
    intent["intent_sha256"] = digest
    kept = recorded["consumed"]
    corpus["manifests"][0]["intent_sha256"] = digest
    recorded_index = corpus["events"].index(recorded)
    _write(lane, corpus)
    assert corpus["events"][recorded_index]["consumed"] == kept


def test_review62_intent_consumed_is_not_ignored(tmp_path):
    """A legal pass whose implement intent consumed set is tampered does not pass. Fails on 2ef2721."""
    cases = {
        "tree-only": {"repo": {"tree": TA}},
        "empty": {},
        "wrong": sha_set(B, TB),
        "extra-repo": {"repo": {"commit": A, "tree": TA}, "other": {"commit": A, "tree": TA}},
        "unknown-field": {"repo": {"commit": A, "tree": TA, "note": "x"}},
    }
    for name, consumed in cases.items():
        lane = build_lane(tmp_path / name, "one", "round1")
        _intent_consumed(lane, consumed)
        result, why = _verdict(lane)
        assert result != "passed", (name, result, why)


def test_review62_duplicate_round_opened_does_not_replace_the_start(tmp_path):
    """A second round_opened does not become the start. Fails on 2ef2721."""
    lane = make_lane(tmp_path, "dup-open", max_rounds=2)
    fake = sha_set(A, F)
    corpus = _corpus(lane)
    opened = next(event for event in corpus["events"] if event.get("type") == "round_opened")
    extra = deepcopy(opened)
    extra["start_set"] = fake
    corpus["events"].append(extra)
    _write(lane, corpus)
    try:
        implement_ok(
            lane,
            consumed=fake,
            pinned=sha_set(B, TB),
            pre_checks=passing_prechecks("implement", fake, kind="baseline", expected=fake),
            bundle_bytes={"repo": b"bundle"},
            notes=[],
        )
        verify_ok(lane, consumed=sha_set(B, TB), pre_checks=passing_prechecks("verify", sha_set(B, TB)))
        review_ok(lane, consumed=sha_set(B, TB), pre_checks=passing_prechecks("review", sha_set(B, TB)))
    except LaneError:
        pass
    result, why = _verdict(lane)
    assert result != "passed", (result, why)


def test_review62_unchanged_commit_changed_tree_does_not_pass(tmp_path):
    """One change repo moves; the other keeps the commit and changes the tree. Fails on 2ef2721."""
    repos = _repos("two")
    lane = make_lane(tmp_path, "tree-only", max_rounds=2, repos=repos)
    base = {name: {"commit": A, "tree": TA} for name in repos}
    pinned = {"alpha": {"commit": B, "tree": TB}, "beta": {"commit": A, "tree": F}}
    implement_ok(
        lane,
        consumed=base,
        pinned=pinned,
        pre_checks=passing_prechecks("implement", base, kind="baseline", expected=base),
        bundle_bytes={"alpha": b"alpha"},
        notes=[],
    )
    try:
        verify_ok(lane, consumed=pinned, pre_checks=passing_prechecks("verify", pinned))
        review_ok(lane, consumed=pinned, pre_checks=passing_prechecks("review", pinned))
    except LaneError:
        pass
    result, why = _verdict(lane)
    assert result != "passed", (result, why)
    assert "commit unchanged but tree changed" in (why or "")


def test_review62_baseline_unknown_field_and_incomplete_sets(tmp_path):
    """Unknown baseline fields, a short pin and a short rejected set are not filled or skipped. Fails on 2ef2721."""
    lane = build_lane(tmp_path / "base", "two", "round1")
    corpus = _corpus(lane)
    corpus["events"][0]["repos"]["alpha"]["note"] = "extra"
    _write(lane, corpus)
    result, why = _verdict(lane)
    assert result != "passed", (result, why)

    short = build_lane(tmp_path / "pin", "two", "round1")
    body = _corpus(short)
    recorded = next(
        event for event in body["events"]
        if event.get("type") == "step_recorded" and event["exec"]["step"] == "implement"
    )
    recorded["pinned"].pop("beta")
    manifest = body["manifests"][0]
    manifest["pinned"].pop("beta")
    _write(short, body)
    result, why = _verdict(short)
    assert result != "passed", (result, why)

    rejected = build_lane(tmp_path / "rej", "two", "round1")
    log = _corpus(rejected)
    review = next(
        event for event in log["events"]
        if event.get("type") == "step_recorded" and event["exec"]["step"] == "review"
    )
    review["sha_set"] = {"alpha": {"commit": B, "tree": TB}}
    _write(rejected, log)
    result, why = _verdict(rejected)
    assert result != "passed", (result, why)
