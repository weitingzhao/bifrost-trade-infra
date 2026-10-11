#!/usr/bin/env python3
"""Who can change platform PROD: generate the write matrix and assert it.

``--from-repo`` reads every RBAC, admission, Tekton and Argo manifest under
k8s/. ``--from-dump DIR`` reads a read-only kubectl export described by
MANIFEST.json. The program never calls the cluster and never reads Secret data.

A write is ``refused`` only when a reviewed admission effect names that exact
field and the policy is proven to apply. Anything the program cannot prove is
``unclassified``. Exit 0 only when no row is unclassified and no exception is
invalid. On today's repository the exit code is 1.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

import yaml

import prod_write_admission as admission
import prod_write_borrow as borrow
import prod_write_dag as dag
import prod_write_load as load
import prod_write_rbac as rbac


HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
TARGETS_PATH = HERE / "prod_targets.yaml"
EFFECTS_PATH = HERE / "admission_effects.yaml"
EXCEPTIONS_PATH = HERE / "prod_write_exceptions.yaml"
_HUMAN = ("identity", "target", "field", "check", "expires", "removes")
_SYSTEM = _HUMAN + ("installed_by", "why_needed", "narrowing", "review_every_days")


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
    only: str = ""
    path: str = ""

    def key(self) -> tuple:
        return (
            self.identity,
            self.target,
            self.field,
            self.verbs,
            self.admission,
            self.classification,
            self.cel,
            self.why,
            self.only,
            self.path,
        )


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


def objects_from(loaded) -> list[dict]:
    return load.objects_from(loaded)


def load_files(directory: Path, suffixes: set[str]) -> list[dict]:
    return load.load_files(directory, suffixes)


def load_repo(root: Path = REPO) -> list[dict]:
    return load.load_repo(root)


def load_dump(directory: Path) -> list[dict]:
    return load.load_dump(directory)


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


def _parse_day(value) -> dt.date | None:
    try:
        return dt.date.fromisoformat(str(value).strip())
    except ValueError:
        return None


def validate_exceptions(exceptions: list[dict], today: dt.date) -> tuple[list[dict], list[str]]:
    valid, problems = [], []
    for index, item in enumerate(exceptions, start=1):
        kind = str(item.get("class") or "human")
        ident = str(item.get("identity") or f"entry {index}")
        if kind not in ("human", "system-component"):
            problems.append(f"invalid-exception: {ident} class {kind}")
            continue
        required = _SYSTEM if kind == "system-component" else _HUMAN
        missing = [key for key in required if not str(item.get(key) or "").strip()]
        if missing:
            problems.append(f"invalid-exception: {ident} missing {', '.join(missing)}")
            continue
        starred = [key for key in ("identity", "target", "field") if "*" in str(item.get(key) or "")]
        if starred:
            problems.append(f"invalid-exception: {ident} wildcard in {', '.join(starred)}")
            continue
        expires = _parse_day(item.get("expires"))
        if expires is None:
            problems.append(f"invalid-exception: {ident} expires is not YYYY-MM-DD")
            continue
        if expires < today:
            problems.append(f"invalid-exception: {ident} expired {expires.isoformat()}")
            continue
        if kind == "system-component":
            try:
                days = int(item.get("review_every_days"))
            except (TypeError, ValueError):
                days = 0
            if days <= 0:
                problems.append(f"invalid-exception: {ident} review_every_days must be a positive integer")
                continue
        valid.append(item)
    return valid, problems


def _exception_matches(exceptions: list[dict], identity: str, target: str, field_name: str) -> bool:
    for item in exceptions:
        if item.get("identity") == identity and item.get("target") == target and item.get("field") == field_name:
            return True
    return False


def _admission_text(hits: list[admission.PolicyHit]) -> tuple[str, str]:
    proven = sorted({hit.name for hit in hits if hit.proven})
    parts = []
    if proven:
        parts.append("gated: " + ",".join(proven))
    for hit in hits:
        if hit.proven or not hit.uncertain:
            continue
        parts.append(f"gated (uncertain: {hit.uncertain})")
    cel = " | ".join(dict.fromkeys(hit.cel for hit in hits if hit.cel))
    return ("none" if not parts else "; ".join(dict.fromkeys(parts))), cel


def _classify(identity, target, field_name, hits, effects, exceptions) -> tuple[str, str, str]:
    proven = [hit.name for hit in hits if hit.proven]
    text, cel = _admission_text(hits)
    if proven and admission.effect_refuses(effects, proven, identity, field_name):
        return "refused", text, cel
    if _exception_matches(exceptions, identity, target, field_name):
        return "named-exception", text, cel
    return "unclassified", text, cel


def _row(identity, target, field_name, verbs, source, classification, admission_text, cel, why, only="", path="") -> Row:
    return Row(identity, target, field_name, ",".join(verbs), source, admission_text, classification, cel, why, only, path)


def _rbac_rows(rules, targets, effects, exceptions, source, ns_labels, ns_known, policies, bindings) -> list[Row]:
    rows: list[Row] = []
    for identity in sorted(rules):
        for target in targets:
            grants = rbac.allowed_grants(rules[identity], target)
            if not grants:
                continue
            verbs = sorted({verb for grant in grants for verb in grant.verbs})
            hits = admission.matching_policies(policies, bindings, target, verbs, identity, ns_labels, ns_known)
            for grant in grants:
                only = "" if not grant.only else "only: " + ",".join(grant.only)
                for field_name in target.fields:
                    grouped: dict[tuple[str, str, str], list[str]] = {}
                    for verb in grant.verbs:
                        classified = _classify(identity, target.id, field_name, admission.hits_for_verb(hits, verb), effects, exceptions)
                        grouped.setdefault(classified, []).append(verb)
                    for (classification, admission_text, cel), group in sorted(grouped.items()):
                        why = target.why
                        if grant.path:
                            why = f"{grant.path}. {why}"
                        rows.append(_row(identity, target.id, field_name, group, source, classification, admission_text, cel, why, only, grant.path))
    return rows


def _class_targets(docs: list[dict]) -> list[rbac.Target]:
    priorities: set[str] = set()
    runtimes: set[str] = set()

    def walk(node) -> None:
        if isinstance(node, dict):
            if node.get("priorityClassName"):
                priorities.add(str(node["priorityClassName"]))
            if node.get("runtimeClassName"):
                runtimes.add(str(node["runtimeClassName"]))
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    for doc in docs:
        if str(doc.get("kind") or "") in {"Deployment", "StatefulSet", "DaemonSet", "CronJob", "Job", "Pod"}:
            walk(doc.get("spec") or {})
    extra = []
    for name in sorted(priorities):
        extra.append(rbac.Target(f"priorityclass/{name}", "", "scheduling.k8s.io", "priorityclasses", name, "", ("value",), "Referenced by a workload spec.priorityClassName.", "v1"))
    for name in sorted(runtimes):
        extra.append(rbac.Target(f"runtimeclass/{name}", "", "node.k8s.io", "runtimeclasses", name, "", ("handler",), "Referenced by a workload spec.runtimeClassName.", "v1"))
    return extra


def _fixed_rows(source: str, effects, exceptions) -> list[Row]:
    specs = [
        ("owner-admin", "cluster-admin", "*", ["*"], "none", "Owner admin kubeconfig is not a binding in the scanned manifests", "The Owner's admin identity can change the cluster."),
        ("owner_run_command", "host-command", "command", ["exec"], "none", "", "owner_run_command runs a host command. It is not an RBAC subject."),
        ("anyone-who-reaches-the-registry", "registry/:prod", "tag", ["push"], "registry has no authentication: anyone who reaches it", "", "The :prod tags are not an RBAC resource."),
        ("anyone-who-can-push-main", "git/main", "automated-sync", ["push"], "none", "Push permission is not in these manifests.", "Application bifrost-platform-prod syncs main automatically."),
        ("system:masters", "*", "*", ["*"], "none", "", "system:masters can do everything. It is not computed from bindings."),
        ("unknown-surface: github-push-authors", "git/main", "authors", ["unknown"], "none", "", "Who can push main is not in the manifests."),
        ("unknown-surface: registry-authentication", "registry/:prod", "auth", ["unknown"], "none", "", "Whether the registry requires authentication is not in the manifests."),
        ("unknown-surface: tekton-controller-status-writer", "pipelinerun/status", "status", ["unknown"], "none", "", "The Tekton controller identity that writes PipelineRun status is not a scanned binding."),
        ("unknown-surface: freeze-script-fail-open", "dag/freeze", "script", ["unknown"], "none", "", "A freeze task script can allow a write when the ConfigMap is missing. The script is not executed."),
        ("unknown-surface: deployment-patch-field-granularity", "deployment", "patch", ["unknown"], "none", "", "One RBAC patch verb covers image, pod template, replicas and restartedAt. The program cannot split them."),
    ]
    rows = []
    for identity, target, field_name, verbs, admission_text, cel, why in specs:
        classification, learned, learned_cel = _classify(identity, target, field_name, [], effects, exceptions)
        if learned == "none":
            learned = admission_text
        rows.append(_row(identity, target, field_name, verbs, source, classification, learned or admission_text, learned_cel or cel, why))
    return rows


def _surface_rows(surfaces: list[str], source: str) -> list[Row]:
    rows = []
    for item in surfaces:
        rows.append(_row(item, "unseen", "borrowed", ["unknown"], source, "unclassified", "none", "", "The program cannot rule out this write path.", path=item))
    return rows


def _unresolved_rows(messages: list[str], source: str) -> list[Row]:
    rows = []
    for message in messages:
        rows.append(_row("unresolved", "unresolved", message, ["unresolved"], source, "unclassified", message, "", message))
    return rows


def _dag_rows(docs, effects, exceptions, source) -> list[Row]:
    rows = []
    for item in dag.indirect_rows(docs):
        classification, admission_text, cel = _classify(item["identity"], item["target"], item["field"], [], effects, exceptions)
        why = "Pipeline side effect. A freeze counts only when its taskRef is listed, it must run, and it is on every path."
        rows.append(_row(item["identity"], item["target"], item["field"], [item["verbs"]], source, classification, admission_text, cel, why))
    return rows


def analyze(docs, targets, effects, exceptions, source, include_fixed: bool = True, today: dt.date | None = None, from_dump: bool = False) -> Report:
    today = today or dt.date.today()
    valid, invalid = validate_exceptions(exceptions, today)
    invalid.extend(admission.validate_effects(effects))
    policies, bindings = admission.index_policies(docs)
    ns_labels, ns_known = admission.namespace_index(docs)
    rules, subjects, unresolved = rbac.effective_rules(docs, from_dump=from_dump)
    if from_dump and unresolved:
        raise SystemExit("\n".join(unresolved))
    surfaces = borrow.expand(rules, docs, policies, bindings, effects, ns_labels, ns_known, from_dump)
    all_targets = list(targets) + _class_targets(docs)
    rows = _rbac_rows(rules, all_targets, effects, valid, source, ns_labels, ns_known, policies, bindings)
    rows.extend(_dag_rows(docs, effects, valid, source))
    rows.extend(_unresolved_rows([] if from_dump else unresolved, source))
    rows.extend(_surface_rows(surfaces, source))
    if include_fixed:
        rows.extend(_fixed_rows(source, effects, valid))
    rows.sort(key=lambda row: row.key())
    missing = [identity for identity in subjects if identity not in rbac.PLAN_TABLE]
    return Report(source=source, rows=rows, invalid=invalid, not_in_plan_table=missing)


def _line(row: Row) -> str:
    extra = " ".join(part for part in (row.only, row.path) if part)
    text = f"unclassified: {row.identity} {row.target} {row.field} {row.verbs}"
    return f"{text} {extra}".rstrip()


def render_md(report: Report, list_only: bool = False) -> str:
    lines = [_line(row) for row in report.unclassified()]
    if list_only:
        return "\n".join(lines) + ("\n" if lines else "")
    head = list(report.invalid) + lines
    head.append(f"not-in-plan-table: {', '.join(report.not_in_plan_table) if report.not_in_plan_table else '(none)'}")
    head.append("")
    head.append(f"# PROD write matrix ({report.source})")
    head.append("")
    head.append("| identity | target | field | verbs | source | admission | classification | only | path |")
    head.append("|---|---|---|---|---|---|---|---|---|")
    for row in report.rows:
        cells = [row.identity, row.target, row.field, row.verbs, row.source, row.admission, row.classification, row.only, row.path]
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


def build_report(root: Path, dump: Path | None, targets: Path, effects: Path, exceptions: Path, today: dt.date | None = None) -> Report:
    source = "measured" if dump else "repo"
    docs = load_dump(dump) if dump else load_repo(root)
    return analyze(docs, load_targets(targets), load_effects(effects), load_exceptions(exceptions), source, today=today, from_dump=dump is not None)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate the platform PROD write matrix.")
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--from-repo", action="store_true", help="read the repository manifests (default)")
    source.add_argument("--from-dump", type=Path, help="directory of read-only kubectl JSON plus MANIFEST.json")
    parser.add_argument("--format", choices=("md", "json"), default="md")
    parser.add_argument("--list-unclassified", action="store_true")
    parser.add_argument("--root", type=Path, default=REPO)
    parser.add_argument("--today", help="YYYY-MM-DD used to expire exceptions (default: the system date)")
    args = parser.parse_args(argv)
    today = _parse_day(args.today) if args.today else dt.date.today()
    if args.today and today is None:
        raise SystemExit("--today must be YYYY-MM-DD")
    report = build_report(args.root, args.from_dump, TARGETS_PATH, EFFECTS_PATH, EXCEPTIONS_PATH, today)
    text = render_json(report) if args.format == "json" and not args.list_unclassified else render_md(report, args.list_unclassified)
    sys.stdout.write(text)
    return report.exit_code


if __name__ == "__main__":
    sys.exit(main())
