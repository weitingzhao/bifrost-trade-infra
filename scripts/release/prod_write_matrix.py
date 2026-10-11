#!/usr/bin/env python3
"""Who can change platform PROD: generate the write matrix and assert it.

Two modes share one analysis. ``--from-repo`` (default) reads the manifests
under k8s/platform-rbac, k8s/cicd/tekton, k8s/cicd/applications,
k8s/overlays/platform-prod and k8s/base-platform. ``--from-dump DIR`` reads
JSON from a read-only kubectl export; this program never calls the cluster.
See scripts/release/README.md for the export commands.

Rows are writes RBAC allows, plus undominated pipeline side effects and three
fixed rows (owner admin, owner_run_command, the unauthenticated registry).
Exit 0 only when every row is refused or a valid named exception. Today the
repository still has unclassified rows, so the exit code is 1.

A matching ValidatingAdmissionPolicy is recorded as ``gated: <policy>``. It
becomes ``refused`` only when scripts/release/admission_effects.yaml says that
policy refuses this identity and field. CEL is not evaluated.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

import yaml

import prod_write_admission as admission
import prod_write_dag as dag
import prod_write_rbac as rbac


HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
TARGETS_PATH = HERE / "prod_targets.yaml"
EFFECTS_PATH = HERE / "admission_effects.yaml"
EXCEPTIONS_PATH = HERE / "prod_write_exceptions.yaml"
SCAN = (
    "k8s/platform-rbac",
    "k8s/cicd/tekton",
    "k8s/cicd/applications",
    "k8s/overlays/platform-prod",
    "k8s/base-platform",
)
_SKIP = ("secret", "kubeconfig")
_EXCEPTION_KEYS = ("identity", "target", "field", "check", "expiry", "removes")


@dataclass(frozen=True)
class Row:
    identity: str
    target: str
    field: str
    verbs: str
    source: str
    admission: str
    classification: str
    cel: str = ""
    why: str = ""

    def key(self) -> tuple:
        return (self.identity, self.target, self.field, self.verbs, self.admission, self.classification, self.cel, self.why)


@dataclass
class Report:
    source: str
    rows: list[Row] = field(default_factory=list)
    invalid: list[str] = field(default_factory=list)
    not_in_plan_table: list[str] = field(default_factory=list)

    def unclassified(self) -> list[Row]:
        return [row for row in self.rows if row.classification == "unclassified"]

    @property
    def exit_code(self) -> int:
        return 1 if self.unclassified() or self.invalid else 0


def _read_raw(path: Path):
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".json":
        return json.loads(text)
    return list(yaml.safe_load_all(text))


def objects_from(loaded) -> list[dict]:
    items = loaded if isinstance(loaded, list) else [loaded]
    docs: list[dict] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        if item.get("kind") == "List" and isinstance(item.get("items"), list):
            docs.extend(objects_from(item["items"]))
            continue
        if item.get("kind") == "Secret":
            continue
        if item.get("kind"):
            docs.append(item)
    return docs


def _selected(path: Path, suffixes: set[str]) -> bool:
    if path.suffix.lower() not in suffixes or not path.is_file():
        return False
    name = path.name.lower()
    return not any(part in name for part in _SKIP)


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


def load_repo(root: Path = REPO) -> list[dict]:
    docs: list[dict] = []
    for relative in SCAN:
        docs.extend(load_files(root / relative, {".yaml", ".yml"}))
    return docs


def load_dump(directory: Path) -> list[dict]:
    return load_files(directory, {".json"})


def _mapping_list(path: Path, key: str) -> list[dict]:
    if not path.is_file():
        raise SystemExit(f"missing {path.name}")
    loaded = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    items = loaded.get(key) or []
    if not isinstance(items, list):
        raise SystemExit(f"{path.name}: {key} must be a list")
    return [item for item in items if isinstance(item, dict)]


def load_targets(path: Path = TARGETS_PATH) -> list[rbac.Target]:
    targets = []
    for item in _mapping_list(path, "targets"):
        fields = item.get("fields") or []
        targets.append(
            rbac.Target(
                id=str(item.get("id") or ""),
                namespace=str(item.get("namespace") or ""),
                api_group=str(item.get("api_group") or ""),
                resource=str(item.get("resource") or ""),
                name=str(item.get("name") or ""),
                subresource=str(item.get("subresource") or ""),
                fields=tuple(str(field_name) for field_name in fields),
                why=str(item.get("why") or ""),
                api_version=str(item.get("api_version") or ""),
            )
        )
    missing = [target.id or "<unnamed>" for target in targets if not target.id or not target.resource or not target.fields]
    if missing:
        raise SystemExit(f"targets missing id, resource or fields: {', '.join(missing)}")
    return targets


def load_effects(path: Path = EFFECTS_PATH) -> list[dict]:
    return _mapping_list(path, "effects")


def load_exceptions(path: Path = EXCEPTIONS_PATH) -> list[dict]:
    return _mapping_list(path, "exceptions")


def validate_exceptions(exceptions: list[dict]) -> tuple[list[dict], list[str]]:
    valid, problems = [], []
    for index, item in enumerate(exceptions, start=1):
        missing = [key for key in _EXCEPTION_KEYS if not str(item.get(key) or "").strip()]
        if missing:
            ident = item.get("identity") or f"entry {index}"
            problems.append(f"invalid-exception: {ident} missing {', '.join(missing)}")
            continue
        valid.append(item)
    return valid, problems


def _exception_matches(exceptions: list[dict], identity: str, target: str, field_name: str) -> bool:
    for item in exceptions:
        if item.get("identity") not in (identity, "*"):
            continue
        if item.get("target") not in (target, "*"):
            continue
        if item.get("field") not in (field_name, "*"):
            continue
        return True
    return False


def _classify(identity: str, target: str, field_name: str, hits: list[admission.PolicyHit], effects: list[dict], exceptions: list[dict]) -> tuple[str, str, str]:
    names = [hit.name for hit in hits]
    if names and admission.effect_refuses(effects, names, identity, field_name):
        classification = "refused"
    elif _exception_matches(exceptions, identity, target, field_name):
        classification = "named-exception"
    else:
        classification = "unclassified"
    text = "none" if not names else "gated: " + ",".join(sorted(set(names)))
    cel = " | ".join(dict.fromkeys(hit.cel for hit in hits if hit.cel))
    return classification, text, cel


def _row(identity: str, target: str, field_name: str, verbs: list[str], source: str, classification: str, admission_text: str, cel: str, why: str) -> Row:
    return Row(
        identity=identity,
        target=target,
        field=field_name,
        verbs=",".join(verbs),
        source=source,
        admission=admission_text,
        classification=classification,
        cel=cel,
        why=why,
    )


def _rbac_rows(docs, targets, effects, exceptions, source, ns_labels, ns_known, policies, bindings) -> list[Row]:
    rules_by_identity, _subjects = rbac.effective_rules(docs)
    rows: list[Row] = []
    for identity in sorted(rules_by_identity):
        rules = rules_by_identity[identity]
        for target in targets:
            verbs = rbac.allowed_verbs(rules, target)
            if not verbs:
                continue
            hits = admission.matching_policies(policies, bindings, target, verbs, identity, ns_labels, ns_known)
            for field_name in target.fields:
                grouped: dict[tuple[str, str, str], list[str]] = {}
                for verb in verbs:
                    verb_hits = admission.hits_for_verb(hits, verb)
                    classified = _classify(identity, target.id, field_name, verb_hits, effects, exceptions)
                    grouped.setdefault(classified, []).append(verb)
                for (classification, admission_text, cel), group in sorted(grouped.items()):
                    rows.append(_row(identity, target.id, field_name, group, source, classification, admission_text, cel, target.why))
    return rows


def _fixed_rows(source: str, effects: list[dict], exceptions: list[dict]) -> list[Row]:
    specs = [
        (
            "owner-admin",
            "cluster-admin",
            "*",
            ["*"],
            "none",
            "Owner admin kubeconfig is not a binding in the scanned manifests",
            "The Owner's admin identity can change the cluster. It is not granted by these manifests.",
        ),
        (
            "owner_run_command",
            "host-command",
            "command",
            ["exec"],
            "none",
            "",
            "owner_run_command runs a host command as the Owner. It is not an RBAC subject.",
        ),
        (
            "anyone-who-reaches-the-registry",
            "registry/:prod",
            "tag",
            ["push"],
            "registry has no authentication: anyone who reaches it",
            "",
            "The :prod tags are not an RBAC resource. A pod restart with imagePullPolicy Always pulls them.",
        ),
        (
            "anyone-who-can-push-main",
            "git/main",
            "automated-sync",
            ["push"],
            "none",
            "Application bifrost-platform-prod sets syncPolicy.automated prune and selfHeal. Push permission is not in these manifests.",
            "A push to main is followed by Argo automated sync into bifrost-platform-prod. GitHub permissions are not RBAC.",
        ),
    ]
    rows = []
    for identity, target, field_name, verbs, admission_text, cel, why in specs:
        classification, learned, learned_cel = _classify(identity, target, field_name, [], effects, exceptions)
        # Fixed rows carry their own admission text when no policy matched.
        if learned == "none":
            learned = admission_text
        rows.append(_row(identity, target, field_name, verbs, source, classification, learned or admission_text, learned_cel or cel, why))
    return rows


def _dag_rows(docs, effects, exceptions, source) -> list[Row]:
    rows = []
    for item in dag.indirect_rows(docs):
        classification, admission_text, cel = _classify(item["identity"], item["target"], item["field"], [], effects, exceptions)
        why = "Pipeline side effect is not dominated by a release-window task on the runAfter graph."
        rows.append(_row(item["identity"], item["target"], item["field"], [item["verbs"]], source, classification, admission_text, cel, why))
    return rows


def analyze(docs: list[dict], targets: list[rbac.Target], effects: list[dict], exceptions: list[dict], source: str, include_fixed: bool = True) -> Report:
    valid, invalid = validate_exceptions(exceptions)
    invalid.extend(admission.validate_effects(effects))
    policies, bindings = admission.index_policies(docs)
    ns_labels, ns_known = admission.namespace_index(docs)
    _rules, subjects = rbac.effective_rules(docs)
    rows = _rbac_rows(docs, targets, effects, valid, source, ns_labels, ns_known, policies, bindings)
    rows.extend(_dag_rows(docs, effects, valid, source))
    if include_fixed:
        rows.extend(_fixed_rows(source, effects, valid))
    rows.sort(key=lambda row: row.key())
    missing = [identity for identity in subjects if identity not in rbac.PLAN_TABLE]
    return Report(source=source, rows=rows, invalid=invalid, not_in_plan_table=missing)


def render_md(report: Report, list_only: bool = False) -> str:
    lines = [f"unclassified: {row.identity} {row.target} {row.field} {row.verbs}" for row in report.unclassified()]
    if list_only:
        return "\n".join(lines) + ("\n" if lines else "")
    head = list(report.invalid) + lines
    head.append(f"not-in-plan-table: {', '.join(report.not_in_plan_table) if report.not_in_plan_table else '(none)'}")
    head.append("")
    head.append(f"# PROD write matrix ({report.source})")
    head.append("")
    head.append("| identity | target | field | verbs | source | admission | classification |")
    head.append("|---|---|---|---|---|---|---|")
    for row in report.rows:
        cells = [row.identity, row.target, row.field, row.verbs, row.source, row.admission, row.classification]
        head.append("| " + " | ".join(cell.replace("|", "/") for cell in cells) + " |")
    head.append("")
    return "\n".join(head)


def render_json(report: Report) -> str:
    payload = {
        "source": report.source,
        "invalid": report.invalid,
        "not_in_plan_table": report.not_in_plan_table,
        "unclassified": [asdict(row) for row in report.unclassified()],
        "rows": [asdict(row) for row in report.rows],
    }
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"


def build_report(root: Path, dump: Path | None, targets: Path, effects: Path, exceptions: Path) -> Report:
    source = "measured" if dump else "repo"
    docs = load_dump(dump) if dump else load_repo(root)
    return analyze(docs, load_targets(targets), load_effects(effects), load_exceptions(exceptions), source)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate the platform PROD write matrix.")
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--from-repo", action="store_true", help="read the repository manifests (default)")
    source.add_argument("--from-dump", type=Path, help="directory of read-only kubectl JSON")
    parser.add_argument("--format", choices=("md", "json"), default="md")
    parser.add_argument("--list-unclassified", action="store_true")
    parser.add_argument("--root", type=Path, default=REPO)
    args = parser.parse_args(argv)
    report = build_report(args.root, args.from_dump, TARGETS_PATH, EFFECTS_PATH, EXCEPTIONS_PATH)
    text = render_json(report) if args.format == "json" and not args.list_unclassified else render_md(report, args.list_unclassified)
    sys.stdout.write(text)
    return report.exit_code


if __name__ == "__main__":
    sys.exit(main())
