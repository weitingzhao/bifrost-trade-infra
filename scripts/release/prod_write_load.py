"""Load repository manifests and read-only kubectl dumps for the PROD matrix.

Repository mode walks every manifest under k8s/ and keeps RBAC, admission,
Tekton and Argo objects, plus Namespace and workload objects the analysis
reads (labels, priority class, runtime class). It does not read Secret data.

Dump mode requires MANIFEST.json, one entry per command in README.md, and
refuses a directory with a missing file, a missing kind, or an unexpected
JSON file.
"""

from __future__ import annotations

import json
from pathlib import Path

import yaml


# One file per README dump command. kind is what that command returns.
DUMP_SPECS = (
    ("clusterroles.json", "ClusterRole"),
    ("clusterrolebindings.json", "ClusterRoleBinding"),
    ("roles.json", "Role"),
    ("rolebindings.json", "RoleBinding"),
    ("validatingadmissionpolicies.json", "ValidatingAdmissionPolicy"),
    ("validatingadmissionpolicybindings.json", "ValidatingAdmissionPolicyBinding"),
    ("mutatingwebhookconfigurations.json", "MutatingWebhookConfiguration"),
    ("validatingwebhookconfigurations.json", "ValidatingWebhookConfiguration"),
    ("serviceaccounts.json", "ServiceAccount"),
    ("namespaces.json", "Namespace"),
    ("pipelines.json", "Pipeline"),
    ("tasks.json", "Task"),
    ("pipelineruns.json", "PipelineRun"),
    ("applications.json", "Application"),
    ("appprojects.json", "AppProject"),
)

INTERESTING = frozenset(
    {
        "Role",
        "ClusterRole",
        "RoleBinding",
        "ClusterRoleBinding",
        "ServiceAccount",
        "Namespace",
        "ValidatingAdmissionPolicy",
        "ValidatingAdmissionPolicyBinding",
        "MutatingAdmissionPolicy",
        "MutatingAdmissionPolicyBinding",
        "ValidatingWebhookConfiguration",
        "MutatingWebhookConfiguration",
        "Pipeline",
        "Task",
        "PipelineRun",
        "TaskRun",
        "Application",
        "AppProject",
        "ApplicationSet",
        "Deployment",
        "StatefulSet",
        "DaemonSet",
        "CronJob",
        "Job",
        "Pod",
    }
)

_SKIP = ("secret", "kubeconfig")
_SUFFIXES = {".yaml", ".yml"}


def objects_from(loaded) -> list[dict]:
    items = loaded if isinstance(loaded, list) else [loaded]
    docs: list[dict] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        if item.get("kind") == "List" and isinstance(item.get("items"), list):
            docs.extend(objects_from(item["items"]))
            continue
        kind = str(item.get("kind") or "")
        if not kind or kind == "Secret":
            continue
        docs.append(item)
    return docs


def _read_raw(path: Path):
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".json":
        return json.loads(text)
    return list(yaml.safe_load_all(text))


def _selected(path: Path, suffixes: set[str]) -> bool:
    if path.suffix.lower() not in suffixes or not path.is_file():
        return False
    if path.name == "MANIFEST.json":
        return False
    return not any(part in path.name.lower() for part in _SKIP)


def _count_items(loaded) -> int:
    if isinstance(loaded, dict) and loaded.get("kind") == "List":
        items = loaded.get("items") or []
        return len(items) if isinstance(items, list) else 0
    if isinstance(loaded, list):
        return len([item for item in loaded if isinstance(item, dict)])
    if isinstance(loaded, dict) and loaded.get("kind"):
        return 1
    return 0


def load_files(directory: Path, suffixes: set[str]) -> list[dict]:
    docs: list[dict] = []
    files = [directory] if directory.is_file() else sorted(directory.rglob("*"))
    for path in files:
        if not _selected(path, suffixes):
            continue
        try:
            loaded = _read_raw(path)
        except (OSError, yaml.YAMLError, json.JSONDecodeError) as exc:
            raise SystemExit(f"cannot parse {path.name}: {exc}") from exc
        docs.extend(objects_from(loaded))
    return docs


def load_repo(root: Path) -> list[dict]:
    """Every interesting manifest under k8s/, not a hand-kept path list."""
    docs: list[dict] = []
    base = root / "k8s"
    if not base.is_dir():
        raise SystemExit(f"missing {base}")
    for path in sorted(base.rglob("*")):
        if not _selected(path, _SUFFIXES):
            continue
        try:
            loaded = _read_raw(path)
        except (OSError, yaml.YAMLError, json.JSONDecodeError) as exc:
            text = path.read_text(encoding="utf-8", errors="replace")
            if any(f"kind: {kind}" in text for kind in INTERESTING):
                raise SystemExit(f"cannot parse {path.as_posix()}: {exc}") from exc
            continue
        for doc in objects_from(loaded):
            if str(doc.get("kind") or "") in INTERESTING:
                docs.append(doc)
    return docs


def load_dump(directory: Path) -> list[dict]:
    """Read a dump only after MANIFEST.json matches the README command set."""
    if not directory.is_dir():
        raise SystemExit(f"dump directory not found: {directory}")
    manifest_path = directory / "MANIFEST.json"
    if not manifest_path.is_file():
        raise SystemExit("dump is incomplete: missing MANIFEST.json")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"cannot parse MANIFEST.json: {exc}") from exc
    listed = manifest.get("files") if isinstance(manifest, dict) else None
    if not isinstance(listed, list):
        raise SystemExit("MANIFEST.json: files must be a list")
    by_name = {}
    for item in listed:
        if not isinstance(item, dict) or not item.get("name"):
            raise SystemExit("MANIFEST.json: each file needs a name")
        by_name[str(item["name"])] = item
    required = dict(DUMP_SPECS)
    for name in required:
        if name not in by_name:
            raise SystemExit(f"dump is incomplete: missing file {name}")
    present = {path.name for path in directory.glob("*.json") if path.name != "MANIFEST.json"}
    for name in sorted(present):
        if name not in by_name:
            raise SystemExit(f"dump is incomplete: unexpected file {name}")
    docs: list[dict] = []
    for name, kind in DUMP_SPECS:
        path = directory / name
        if not path.is_file():
            raise SystemExit(f"dump is incomplete: missing file {name}")
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise SystemExit(f"cannot parse {name}: {exc}") from exc
        count = _count_items(loaded)
        expected = by_name[name].get("count")
        if expected is None or int(expected) != count:
            raise SystemExit(f"dump is incomplete: {name} count {count} != manifest {expected}")
        declared = str(by_name[name].get("kind") or "")
        if declared != kind:
            raise SystemExit(f"dump is incomplete: {name} kind {declared or 'missing'} != {kind}")
        file_docs = objects_from(loaded)
        kinds = {str(doc.get("kind") or "") for doc in file_docs}
        if kinds and kinds != {kind}:
            raise SystemExit(f"dump is incomplete: missing kind {kind} in {name}")
        if count and not file_docs:
            raise SystemExit(f"dump is incomplete: missing kind {kind} in {name}")
        docs.extend(file_docs)
    return docs
