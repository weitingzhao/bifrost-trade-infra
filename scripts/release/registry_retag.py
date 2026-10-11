"""Move a registry tag onto a manifest STG already pulled (W-56 G2).

Docker Registry HTTP API v2. ``promote`` reads the manifest bytes a tag or
digest points at (OCI and Docker, a single manifest or an index) and PUTs
those same bytes under another tag. It does not pull layers and it does not
rebuild.

``promote(repo, source, target, keep_as)`` first points ``keep_as`` at whatever
``target`` points at now, when that tag exists, then points ``target`` at
``source``. A second call with the same source and target writes nothing.
The registry base URL is the keyword ``base_url`` or ``REGISTRY_URL``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import urllib.error
import urllib.request
from typing import NamedTuple, Optional

MEDIA_TYPES = (
    "application/vnd.docker.distribution.manifest.v2+json",
    "application/vnd.docker.distribution.manifest.list.v2+json",
    "application/vnd.oci.image.manifest.v1+json",
    "application/vnd.oci.image.index.v1+json",
)
ACCEPT = ", ".join(MEDIA_TYPES)
_DIGEST = re.compile(r"sha256:[0-9a-f]{64}")


class RegistryError(Exception):
    pass


class NotFound(RegistryError):
    pass


class Manifest(NamedTuple):
    body: bytes
    media_type: str
    digest: str


def digest_of(body: bytes) -> str:
    return "sha256:" + hashlib.sha256(body).hexdigest()


def promote(repo: str, source: str, target: str, keep_as: str, *, base_url: Optional[str] = None) -> str:
    """Point keep_as at target's current manifest, then point target at source.

    Returns the digest ``target`` names when this returns. Idempotent: when
    ``target`` already names that digest, ``keep_as`` is left alone.
    """
    base = _base(base_url)
    try:
        src = _get(base, repo, source)
    except NotFound as exc:
        raise RegistryError(f"source manifest {repo}:{source} not found") from exc
    try:
        current = _get(base, repo, target)
    except NotFound:
        current = None
    if current is not None and current.digest == src.digest:
        return src.digest
    if current is not None:
        _put(base, repo, keep_as, current)
    _put(base, repo, target, src)
    return src.digest


def pod_digest(doc: dict, container: str) -> str:
    """The image digest every non-terminating pod is running for ``container``.

    Pods with ``deletionTimestamp`` are skipped. Every remaining pod must be
    Ready and must agree. ``imageID`` may be ``sha256:…``, ``repo@sha256:…``,
    or ``docker-pullable://host/repo@sha256:…``.
    """
    if not isinstance(doc, dict) or not isinstance(doc.get("items"), list):
        raise RegistryError("pod list is not a kubectl list object")
    found: list[str] = []
    for pod in doc["items"]:
        if not isinstance(pod, dict):
            raise RegistryError("pod is not an object")
        meta = pod.get("metadata") or {}
        if meta.get("deletionTimestamp"):
            continue
        name = str(meta.get("name") or "?")
        statuses = ((pod.get("status") or {}).get("containerStatuses") or [])
        matched = [item for item in statuses if isinstance(item, dict) and item.get("name") == container]
        if len(matched) != 1:
            raise RegistryError(f"pod {name} has no container {container}")
        if not matched[0].get("ready"):
            raise RegistryError(f"pod {name} container {container} is not ready")
        digests = _DIGEST.findall(str(matched[0].get("imageID") or ""))
        if len(digests) != 1:
            raise RegistryError(f"pod {name} imageID has no sha256 digest")
        found.append(digests[0])
    if not found:
        raise RegistryError(f"no ready pods for container {container}")
    if len(set(found)) != 1:
        raise RegistryError(f"pods for {container} disagree: {sorted(set(found))}")
    return found[0]


def _base(base_url: Optional[str]) -> str:
    raw = (base_url if base_url is not None else os.environ.get("REGISTRY_URL", "")).strip()
    if not raw:
        raise RegistryError("REGISTRY_URL is not set")
    if "://" not in raw:
        raw = "http://" + raw
    raw = raw.rstrip("/")
    if raw.endswith("/v2"):
        raw = raw[:-3]
    return raw


def _manifest_url(base: str, repo: str, ref: str) -> str:
    repo = repo.strip("/")
    if not repo or "/" in repo or ".." in repo:
        raise RegistryError(f"refusing repo {repo!r}")
    if not ref or "/" in ref or ".." in ref:
        raise RegistryError(f"refusing reference {ref!r}")
    return f"{base}/v2/{repo}/manifests/{ref}"


def _get(base: str, repo: str, ref: str) -> Manifest:
    status, headers, body = _request(_manifest_url(base, repo, ref), "GET", accept=ACCEPT)
    if status == 404:
        raise NotFound(f"{repo}:{ref}")
    if status != 200:
        raise RegistryError(f"GET {repo}:{ref} -> {status}")
    media = headers.get("content-type", "").split(";")[0].strip()
    if media not in MEDIA_TYPES:
        raise RegistryError(f"GET {repo}:{ref} returned {media or 'no media type'}")
    digest = digest_of(body)
    advertised = headers.get("docker-content-digest", "").strip()
    if advertised and advertised != digest:
        raise RegistryError(f"GET {repo}:{ref} digest {advertised} != sha256 of body")
    return Manifest(body, media, digest)


def _put(base: str, repo: str, ref: str, manifest: Manifest) -> None:
    status, headers, _body = _request(
        _manifest_url(base, repo, ref),
        "PUT",
        data=manifest.body,
        content_type=manifest.media_type,
    )
    if status not in (200, 201):
        raise RegistryError(f"PUT {repo}:{ref} -> {status}")
    advertised = headers.get("docker-content-digest", "").strip()
    if advertised and advertised != manifest.digest:
        raise RegistryError(f"PUT {repo}:{ref} digest {advertised} != sha256 of body")


def _headers(message) -> dict[str, str]:
    return {str(key).lower(): str(value) for key, value in message.items()}


def _request(
    url: str,
    method: str,
    *,
    data: Optional[bytes] = None,
    accept: str = "",
    content_type: str = "",
) -> tuple[int, dict[str, str], bytes]:
    req = urllib.request.Request(url, data=data, method=method)
    if accept:
        req.add_header("Accept", accept)
    if content_type:
        req.add_header("Content-Type", content_type)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, _headers(resp.headers), resp.read()
    except urllib.error.HTTPError as exc:
        return exc.code, _headers(exc.headers), exc.read()
    except urllib.error.URLError as exc:
        raise RegistryError(f"{method} {url} failed: {exc.reason}") from exc


def _print_digest(ref_digest: str) -> int:
    print(ref_digest)
    return 0


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Retag a registry manifest without pulling it")
    sub = parser.add_subparsers(dest="cmd", required=True)

    promote_p = sub.add_parser("promote")
    promote_p.add_argument("--registry", required=True)
    promote_p.add_argument("--repo", required=True)
    promote_p.add_argument("--source", required=True)
    promote_p.add_argument("--target", required=True)
    promote_p.add_argument("--keep-as", required=True)

    show_p = sub.add_parser("digest")
    show_p.add_argument("--registry", required=True)
    show_p.add_argument("--repo", required=True)
    show_p.add_argument("--ref", required=True)

    pods_p = sub.add_parser("pod-digest")
    pods_p.add_argument("--container", required=True)
    pods_p.add_argument("--pods", help="kubectl get pods -o json (default stdin)")

    args = parser.parse_args(argv)
    try:
        if args.cmd == "promote":
            return _print_digest(promote(
                args.repo, args.source, args.target, args.keep_as, base_url=args.registry,
            ))
        if args.cmd == "digest":
            return _print_digest(_get(_base(args.registry), args.repo, args.ref).digest)
        raw = sys.stdin.read() if not args.pods else open(args.pods, encoding="utf-8").read()
        return _print_digest(pod_digest(json.loads(raw), args.container))
    except (RegistryError, json.JSONDecodeError, OSError) as exc:
        print(f"registry: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
