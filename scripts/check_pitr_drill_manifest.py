#!/usr/bin/env python3
"""The PITR drill Cluster must not write the production backup bucket.

CloudNativePG archives WAL only when a Cluster has a ``spec.backup`` section.
This check fails the drill manifest when:

- any ``backup:`` key appears in the Cluster document (that section writes WAL
  into the Barman bucket);
- the Cluster name is ``bifrost-postgres`` (the production name, and the
  serverName CNPG uses when ``serverName`` is omitted);
- recovery does not read ``externalClusters`` ``serverName: bifrost-postgres``
  on ``s3://bifrost-postgres-backup/``.

Stdlib only. Exit 1 on any problem. ``--self-test`` checks the walker itself.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "k8s" / "data" / "drills" / "pitr-drill-cluster.yaml"

PRODUCTION_NAME = "bifrost-postgres"
DRILL_NAME = "bifrost-postgres-pitr-drill"
PRODUCTION_BUCKET = "s3://bifrost-postgres-backup"
BACKUP_KEY = re.compile(r"(^|[\[{,\s])backup\s*:")


def _strip_comment(line: str) -> str:
    out: list[str] = []
    quote = ""
    for ch in line:
        if quote:
            out.append(ch)
            if ch == quote:
                quote = ""
            continue
        if ch in {"'", '"'}:
            quote = ch
            out.append(ch)
            continue
        if ch == "#":
            break
        out.append(ch)
    return "".join(out).rstrip()


def _unquote(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def _cluster_documents(text: str) -> list[str]:
    chunks: list[str] = []
    current: list[str] = []
    for line in text.splitlines():
        if line.strip() == "---":
            chunks.append("\n".join(current))
            current = []
        else:
            current.append(line)
    chunks.append("\n".join(current))
    docs = []
    for chunk in chunks:
        body = "\n".join(_strip_comment(line) for line in chunk.splitlines())
        if re.search(r"(?m)^kind:\s*Cluster\s*$", body):
            docs.append(body)
    return docs


class _Walker:
    """Indent stack over one Cluster document. Fail-closed on backup keys."""

    def __init__(self, body: str) -> None:
        self.stack: list[tuple[int, str]] = []
        self.kind = ""
        self.name = ""
        self.recovery_source = ""
        self.externals: list[dict[str, str]] = []
        self._current: dict[str, str] | None = None
        self.backup_key = False
        self.archive_mode = ""
        self.archive_command = ""
        self._walk(body)

    def _path(self) -> list[str]:
        return [key for _, key in self.stack]

    def _pop_to(self, indent: int, strict: bool) -> None:
        while self.stack and (self.stack[-1][0] > indent or (strict and self.stack[-1][0] >= indent)):
            self.stack.pop()

    def _note(self, value: str) -> None:
        path = self._path()
        value = _unquote(value)
        if path == ["kind"]:
            self.kind = value
        elif path == ["metadata", "name"]:
            self.name = value
        elif path == ["spec", "bootstrap", "recovery", "source"]:
            self.recovery_source = value
        if path[-1:] == ["archive_mode"] and "parameters" in path:
            self.archive_mode = value.strip().lower()
        elif path[-1:] == ["archive_command"] and "parameters" in path:
            self.archive_command = value
        elif len(path) >= 2 and path[-2] == "externalClusters" and path[-1] == "name":
            self._current = {"name": value, "serverName": "", "destinationPath": ""}
            self.externals.append(self._current)
        elif self._current is not None and path[-1:] == ["serverName"] and "barmanObjectStore" in path:
            self._current["serverName"] = value
        elif self._current is not None and path[-1:] == ["destinationPath"] and "barmanObjectStore" in path:
            self._current["destinationPath"] = value

    def _on_key(self, indent: int, key: str, raw: str) -> None:
        self._pop_to(indent, strict=True)
        parent = self._path()
        if key == "backup" and parent == ["spec"]:
            self.backup_key = True
        self.stack.append((indent, key))
        if raw != "":
            self._note(raw)

    def _walk(self, body: str) -> None:
        for raw_line in body.splitlines():
            if not raw_line.strip():
                continue
            dash = re.match(r"^( *)- (.*)$", raw_line)
            if dash:
                dash_indent = len(dash.group(1))
                self._pop_to(dash_indent, strict=False)
                rest = dash.group(2).strip()
                if ":" not in rest:
                    continue
                key, _, value = rest.partition(":")
                self._on_key(dash_indent + 2, key.strip(), value.strip())
                continue
            key_match = re.match(r"^( *)([^ :]+):\s*(.*)$", raw_line)
            if not key_match:
                continue
            indent = len(key_match.group(1))
            self._on_key(indent, key_match.group(2), key_match.group(3).strip())


def problems_in_text(text: str) -> list[str]:
    docs = _cluster_documents(text)
    if len(docs) != 1:
        return [f"expected one Cluster document, found {len(docs)}"]
    body = docs[0]
    if any(BACKUP_KEY.search(line) for line in body.splitlines()):
        raw_backup = True
    else:
        raw_backup = False
    walked = _Walker(body)
    found: list[str] = []
    if walked.kind != "Cluster":
        found.append(f"kind is {walked.kind or 'missing'}, want Cluster")
    if walked.name == PRODUCTION_NAME:
        found.append(f"Cluster name is {PRODUCTION_NAME}; that is the production cluster")
    if walked.name != DRILL_NAME:
        found.append(f"Cluster name is {walked.name or 'missing'}, want {DRILL_NAME}")
    if raw_backup or walked.backup_key:
        found.append("Cluster document has a backup key; CNPG would archive WAL")
    if walked.archive_mode in {"on", "always"}:
        found.append(f"archive_mode is {walked.archive_mode}")
    if walked.archive_command:
        found.append("archive_command is set; the drill must not archive WAL")
    matched = [item for item in walked.externals if item["name"] == walked.recovery_source]
    if not walked.recovery_source or not matched:
        found.append("bootstrap.recovery.source does not name an externalClusters entry")
    else:
        chosen = matched[0]
        bucket = chosen["destinationPath"].rstrip("/")
        if chosen["serverName"] != PRODUCTION_NAME or bucket != PRODUCTION_BUCKET:
            found.append(
                "recovery serverName/bucket is "
                f"{chosen['serverName'] or 'missing'} {chosen['destinationPath'] or 'missing'}, "
                f"want {PRODUCTION_NAME} {PRODUCTION_BUCKET}/"
            )
    return found


_GOOD = """\
apiVersion: v1
kind: Namespace
metadata:
  name: pitr-drill
---
apiVersion: postgresql.cnpg.io/v1
kind: Cluster
metadata:
  name: bifrost-postgres-pitr-drill
spec:
  instances: 1
  # backup: must stay absent
  bootstrap:
    recovery:
      source: bifrost-postgres
  externalClusters:
    - name: bifrost-postgres
      barmanObjectStore:
        destinationPath: s3://bifrost-postgres-backup/
        serverName: bifrost-postgres
"""

_WITH_BACKUP = _GOOD.replace(
    "  instances: 1\n",
    "  instances: 1\n  backup:\n    retentionPolicy: 30d\n",
)


def self_test() -> list[str]:
    failures: list[str] = []

    def expect(label: str, text: str, bad: bool) -> None:
        got = problems_in_text(text)
        if bad and not got:
            failures.append(f"{label}: expected problems, found none")
        if not bad and got:
            failures.append(f"{label}: expected clean, found {got}")

    expect("good", _GOOD, bad=False)
    expect("backup section", _WITH_BACKUP, bad=True)
    expect("flow backup", _GOOD.replace("instances: 1", "instances: 1\n  extra: {backup: {}}"), bad=True)
    expect(
        "production name",
        _GOOD.replace("name: bifrost-postgres-pitr-drill", "name: bifrost-postgres"),
        bad=True,
    )
    expect(
        "wrong serverName",
        _GOOD.replace("serverName: bifrost-postgres", "serverName: bifrost-postgres-pitr-drill"),
        bad=True,
    )
    expect("commented backup", _GOOD, bad=False)
    return failures


def main() -> int:
    failed = self_test()
    if "--self-test" in sys.argv:
        if failed:
            print("\n".join(failed), file=sys.stderr)
            return 1
        print("self-test ok")
        return 0
    if failed:
        print("checker self-test failed:", file=sys.stderr)
        print("\n".join(failed), file=sys.stderr)
        return 1
    if not MANIFEST.is_file():
        print(f"missing {MANIFEST}", file=sys.stderr)
        return 1
    manifest_problems = problems_in_text(MANIFEST.read_text())
    if manifest_problems:
        print(f"{MANIFEST}:", file=sys.stderr)
        print("\n".join(manifest_problems), file=sys.stderr)
        return 1
    print(f"ok {MANIFEST}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
