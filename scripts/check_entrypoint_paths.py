#!/usr/bin/env python3
"""Check that every Python script a Trade workload runs is actually in its image.

Renders k8s/overlays/{dev,stg,prod} with `kubectl kustomize`, picks the containers
whose image is built from a Dockerfile in k8s/cicd/docker/, resolves each `.py`
in their command/args against that Dockerfile's WORKDIR and COPY lines, and
checks the file exists in the sibling repo it is copied from.

Why: from 2026-08-24 to 2026-09-26 the db-init Jobs ran
/app/scripts/run_db_refresh_schema.py. The image has no /app/scripts, so every
schema refresh crash-looped, and the failed Jobs expired after a day unseen.

A sibling repo that is not checked out is reported NOT MEASURED and fails the
check: an unchecked path is not a passing one.

Usage:
  python3 scripts/check_entrypoint_paths.py
  python3 scripts/check_entrypoint_paths.py --workspace /path/to/stocks
Exit: 0 all found · 1 a script is missing · 2 could not check.
"""
from __future__ import annotations

import argparse
import posixpath
import shlex
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
DOCKER_DIR = ROOT / "k8s/cicd/docker"
OVERLAYS = ("dev", "stg", "prod")

# Image repository name (prefix) -> Dockerfile it is built from. All bifrost-api-*
# tags are one image (task-kaniko-all-apis-stg.yaml retags it per domain).
IMAGE_DOCKERFILES = {
    "bifrost-api-": "Dockerfile.api-stg",
    "bifrost-worker": "Dockerfile.worker-stg",
}


def _dockerfile_layout(name: str) -> tuple[str, list[tuple[str, str]]]:
    """Return (final WORKDIR, [(path in image, source path in build context)])."""
    workdir = "/"
    copies: list[tuple[str, str]] = []
    for raw in (DOCKER_DIR / name).read_text(encoding="utf-8").splitlines():
        parts = raw.split()
        if not parts:
            continue
        op = parts[0].upper()
        if op == "FROM":
            workdir = "/"
        elif op == "WORKDIR":
            workdir = posixpath.normpath(posixpath.join(workdir, parts[1]))
        elif op == "COPY":
            args = [p for p in parts[1:] if not p.startswith("--")]
            if any(p.startswith("--from") for p in parts[1:]) or len(args) < 2:
                continue
            *srcs, dest = args
            dest = posixpath.join(workdir, dest)
            for src in srcs:
                if len(srcs) > 1 or dest.endswith("/"):
                    target = posixpath.join(dest, posixpath.basename(src.rstrip("/")))
                else:
                    target = dest
                copies.append((posixpath.normpath(target), src.rstrip("/")))
    return workdir, copies


def _dockerfile_for(image: str) -> str | None:
    repo = image.rsplit("/", 1)[-1].split("@", 1)[0].split(":", 1)[0]
    for prefix, dockerfile in IMAGE_DOCKERFILES.items():
        if repo.startswith(prefix):
            return dockerfile
    return None


def _containers(node):
    if isinstance(node, dict):
        for key, value in node.items():
            if key in ("containers", "initContainers") and isinstance(value, list):
                yield from (c for c in value if isinstance(c, dict) and c.get("image"))
            else:
                yield from _containers(value)
    elif isinstance(node, list):
        for item in node:
            yield from _containers(item)


def _scripts(container: dict) -> list[str]:
    out: list[str] = []
    for token in [*(container.get("command") or []), *(container.get("args") or [])]:
        # `sh -c "python scripts/x.py ..."` carries the path inside one string.
        try:
            words = shlex.split(str(token))
        except ValueError:
            words = str(token).split()
        out.extend(w for w in words if w.endswith(".py"))
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--workspace",
        type=Path,
        default=ROOT.parent,
        help="directory holding the sibling repos (default: parent of this repo)",
    )
    args = parser.parse_args()

    layouts = {name: _dockerfile_layout(name) for name in set(IMAGE_DOCKERFILES.values())}
    missing = unmeasured = checked = 0

    for overlay in OVERLAYS:
        try:
            rendered = subprocess.run(
                ["kubectl", "kustomize", str(ROOT / "k8s/overlays" / overlay)],
                check=True,
                capture_output=True,
                text=True,
            ).stdout
        except (OSError, subprocess.CalledProcessError) as exc:
            print(f"NOT MEASURED  {overlay}: kubectl kustomize failed: {exc}", file=sys.stderr)
            unmeasured += 1
            continue

        for doc in yaml.safe_load_all(rendered):
            if not doc:
                continue
            owner = f"{doc.get('kind')}/{doc.get('metadata', {}).get('name')}"
            for container in _containers(doc):
                dockerfile = _dockerfile_for(container["image"])
                if dockerfile is None:
                    continue
                image_workdir, copies = layouts[dockerfile]
                workdir = container.get("workingDir") or image_workdir
                for script in _scripts(container):
                    path = posixpath.normpath(posixpath.join(workdir, script))
                    where = f"{overlay}  {owner}  {container.get('name')}  {script}"
                    matches = [
                        (target, src)
                        for target, src in copies
                        if path == target or path.startswith(target + "/")
                    ]
                    checked += 1
                    if not matches:
                        print(f"MISSING       {where}: {path} is not copied into the image ({dockerfile})")
                        missing += 1
                        continue
                    target, src = max(matches, key=lambda m: len(m[0]))
                    repo = src.split("/", 1)[0]
                    if not (args.workspace / repo).is_dir():
                        print(f"NOT MEASURED  {where}: sibling repo {repo} not at {args.workspace}")
                        unmeasured += 1
                        continue
                    source = args.workspace / src / posixpath.relpath(path, target)
                    if source.is_file():
                        print(f"ok            {where}")
                    else:
                        print(f"MISSING       {where}: {path} <- {source.relative_to(args.workspace)} does not exist")
                        missing += 1

    print(f"\n{checked} script path(s) checked · {missing} missing · {unmeasured} not measured")
    if missing:
        return 1
    return 2 if unmeasured or not checked else 0


if __name__ == "__main__":
    sys.exit(main())
