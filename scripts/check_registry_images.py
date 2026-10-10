#!/usr/bin/env python3
"""The in-cluster registry keeps its images, and holds every image a running pod uses (TD-282).

Static (default): k8s/cicd/registry/deployment.yaml mounts a PersistentVolumeClaim at
/var/lib/registry and the Deployment uses the Recreate strategy.

--live: every image from the registry referenced by a running container resolves in the
registry (HEAD /v2/<repo>/manifests/<tag or digest>). A pod restarted with
`imagePullPolicy: Always` needs exactly that. A tag that resolves to a different digest
than the running one is reported but not a failure: the next restart pulls the new build.

Usage: python3 scripts/check_registry_images.py [--live]
Reads only. Exit 1 when the manifest is not persistent or an image is missing.
"""

from __future__ import annotations

import json
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "k8s" / "cicd" / "registry" / "deployment.yaml"
REGISTRY = "192.168.10.73:30500"
ACCEPT = ", ".join([
    "application/vnd.oci.image.index.v1+json",
    "application/vnd.oci.image.manifest.v1+json",
    "application/vnd.docker.distribution.manifest.list.v2+json",
    "application/vnd.docker.distribution.manifest.v2+json",
])


def static_problems(docs: list[dict]) -> list[str]:
    problems: list[str] = []
    claims = {d["metadata"]["name"] for d in docs if d.get("kind") == "PersistentVolumeClaim"}
    deploy = next((d for d in docs if d.get("kind") == "Deployment" and d["metadata"]["name"] == "registry"), None)
    if deploy is None:
        return ["no registry Deployment"]
    spec = deploy["spec"]
    if (spec.get("strategy") or {}).get("type") != "Recreate":
        problems.append("registry Deployment does not use the Recreate strategy")
    pod = spec["template"]["spec"]
    volumes = {v["name"]: v for v in pod.get("volumes") or []}
    mounts = {m["mountPath"]: m["name"] for c in pod["containers"] for m in c.get("volumeMounts") or []}
    vol = volumes.get(mounts.get("/var/lib/registry", ""))
    claim = ((vol or {}).get("persistentVolumeClaim") or {}).get("claimName")
    if not claim:
        problems.append("/var/lib/registry is not a PersistentVolumeClaim (the registry loses every image on restart)")
    elif claim not in claims:
        problems.append(f"PersistentVolumeClaim {claim} is not defined next to the Deployment")
    return problems


def split_ref(image: str) -> tuple[str, str]:
    """'host/repo:tag' or 'host/repo@sha256:..' -> (repo, reference)."""
    rest = image.split("/", 1)[1]
    if "@" in rest:
        repo, ref = rest.split("@", 1)
    elif ":" in rest:
        repo, ref = rest.rsplit(":", 1)
    else:
        repo, ref = rest, "latest"
    return repo, ref


def head_digest(repo: str, ref: str) -> str | None:
    req = urllib.request.Request(f"http://{REGISTRY}/v2/{repo}/manifests/{ref}", method="HEAD", headers={"Accept": ACCEPT})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.headers.get("Docker-Content-Digest") or "present"
    except urllib.error.HTTPError:
        return None


def running_images() -> dict[str, set[str]]:
    """registry image -> running digests, from containers that are actually running."""
    out = subprocess.run(["kubectl", "get", "pods", "-A", "-o", "json"], capture_output=True, text=True, check=True)
    images: dict[str, set[str]] = {}
    for pod in json.loads(out.stdout)["items"]:
        for cs in pod["status"].get("containerStatuses") or []:
            image = cs.get("image", "")
            if not image.startswith(REGISTRY + "/"):
                spec_image = next((c["image"] for c in pod["spec"]["containers"] if c["name"] == cs["name"]), "")
                if not spec_image.startswith(REGISTRY + "/"):
                    continue
                image = spec_image
            digest = (cs.get("imageID") or "").rsplit("@", 1)[-1] if "@" in (cs.get("imageID") or "") else ""
            images.setdefault(image, set())
            if digest:
                images[image].add(digest)
    return images


def live_problems() -> tuple[list[str], list[str]]:
    problems: list[str] = []
    notes: list[str] = []
    for image, digests in sorted(running_images().items()):
        repo, ref = split_ref(image)
        got = head_digest(repo, ref)
        if got is None:
            problems.append(f"missing in the registry: {repo}:{ref}" if not ref.startswith("sha256:") else f"missing in the registry: {repo}@{ref}")
        elif digests and got not in digests and got != "present":
            notes.append(f"{repo}:{ref} now resolves to {got[:19]}…, running {sorted(d[:19] for d in digests)}")
    return problems, notes


def main() -> int:
    docs = [d for d in yaml.safe_load_all(MANIFEST.read_text()) if d]
    problems = static_problems(docs)
    notes: list[str] = []
    if "--live" in sys.argv[1:]:
        live, notes = live_problems()
        problems += live
    for n in notes:
        print(f"note: {n}")
    if problems:
        for p in problems:
            print(f"FAIL {p}", file=sys.stderr)
        return 1
    print("ok: registry is persistent" + (" and holds every image a running pod uses" if "--live" in sys.argv[1:] else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
