"""Nothing outside this directory imports it, and it imports nothing on a release path."""

from __future__ import annotations

import ast
from pathlib import Path

SHADOW = Path(__file__).resolve().parent
REPO = SHADOW.parents[3]
RELEASE = (
    REPO / "scripts" / "release",
    REPO / "k8s" / "cicd",
    REPO / "agent-config" / "scripts" / "git-hooks",
    REPO / "agent-config" / "scripts" / "agent-guard",
)


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                found.add(alias.name.split(".", 1)[0])
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            found.add(node.module.split(".", 1)[0])
    return found


def _release_modules() -> set[str]:
    names = set()
    for base in RELEASE:
        if not base.exists():
            continue
        for path in base.rglob("*.py"):
            names.add(path.stem)
    return names


def test_nothing_outside_shadow_imports_it():
    banned = {"proxy", "shadow"}
    offenders = []
    for path in REPO.rglob("*.py"):
        if SHADOW in path.parents or path == SHADOW:
            continue
        if any(name in _imports(path) for name in banned):
            offenders.append(str(path.relative_to(REPO)))
    assert offenders == []


def test_shadow_imports_nothing_on_a_release_path():
    release = _release_modules() - {"conftest", "__init__"}
    needles = (
        "scripts/release",
        "k8s/cicd",
        "agent-config/scripts/git-hooks",
        "agent-config/scripts/agent-guard",
    )
    offenders = []
    for path in (SHADOW / "proxy.py", SHADOW / "shadow.py"):
        text = path.read_text(encoding="utf-8")
        for needle in needles:
            if needle in text:
                offenders.append(f"{path.name}: {needle}")
        for name in _imports(path):
            if name in release:
                offenders.append(f"{path.name}: {name}")
    assert offenders == []
