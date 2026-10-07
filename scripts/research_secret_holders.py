"""Deployments that mount a Secret, derived the same way as holder_deployments().

The rotation helper restarts every match. It never hard-codes one Deployment name.
"""

from __future__ import annotations

import hashlib
import json
from typing import Iterable


def deployments_mounting(items: Iterable[dict], secret_name: str) -> list[tuple[str, str]]:
    """Return (namespace, name) for Deployments whose pod spec names the Secret.

    `secret_name` is matched as a JSON string so a prefix of another name does
    not count. The objects are Deployment resources as kubectl -o json returns them.
    """
    needle = json.dumps(secret_name)
    found: list[tuple[str, str]] = []
    for deploy in items:
        meta = deploy.get("metadata") or {}
        spec = ((deploy.get("spec") or {}).get("template") or {}).get("spec") or {}
        if needle in json.dumps(spec):
            found.append((str(meta.get("namespace", "")), str(meta.get("name", ""))))
    return found


def secret_checksum(data: dict) -> str:
    """Checksum of a Secret's data map. The digest is not the secret values."""
    blob = json.dumps(data or {}, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(blob).hexdigest()
