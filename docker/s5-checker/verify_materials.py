"""Reject incomplete line-A build output before an image can be published."""

import hashlib
import json
from pathlib import Path
import re

MATERIAL_DIGESTS = (
    "profileDigest",
    "toolchainDigest",
    "callersDigest",
    "typesDigest",
    "testsDigest",
)
MATERIAL_FIELDS = MATERIAL_DIGESTS + ("uiSHA",)


def canonical(value):
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode()


def toolchain_digest(lock):
    """THE S5 toolchainDigest: SHA-256 of the canonical TOOLS.lock.json.

    Same definition as platform s5check.ToolchainDigest; the shared golden is
    pinned in test_verify_materials.py and platform
    rules/s5check/testdata/ci-materials-golden.json.
    """
    if not isinstance(lock, dict) or not isinstance(
        (lock.get("typescript") or {}).get("version"), str
    ):
        raise ValueError("tool lock does not pin TypeScript")
    return hashlib.sha256(canonical(lock)).hexdigest()


def check_materials(materials, placeholder=False):
    """Exact s5check --ci-materials shape; non-zero unless a placeholder."""
    if not isinstance(materials, dict) or set(materials) != set(MATERIAL_FIELDS):
        raise ValueError("S5 materials must have exactly " + ", ".join(MATERIAL_FIELDS))
    for name in MATERIAL_FIELDS:
        size = 40 if name == "uiSHA" else 64
        value = materials[name]
        zero = "0" * size
        if not isinstance(value, str) or not re.fullmatch(
            "[0-9a-f]{" + str(size) + "}", value
        ):
            raise ValueError("invalid trusted material: " + name)
        if placeholder != (value == zero):
            if placeholder:
                raise ValueError("UNBUILT placeholder must be all zeros: " + name)
            raise ValueError("missing trusted material: " + name)
    return materials


def verify(root):
    raw = (root / "materials.json").read_text().strip()
    materials = json.loads(raw)
    if canonical(materials).decode() != raw:
        raise ValueError("materials are not canonical JSON")
    check_materials(materials)
    lock = json.loads((root / "TOOLS.lock.json").read_text())
    if materials["toolchainDigest"] != toolchain_digest(lock):
        raise ValueError("toolchain digest does not match image lock")


if __name__ == "__main__":
    verify(Path("/opt/s5"))
