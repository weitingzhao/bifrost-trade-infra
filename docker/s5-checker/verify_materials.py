"""Reject incomplete line-A build output before an image can be published."""

import hashlib
import json
from pathlib import Path
import re


def verify(root):
    materials = json.loads((root / "materials.json").read_text())
    for name in [
        "profileDigest",
        "toolchainDigest",
        "callersDigest",
        "typesDigest",
        "testsDigest",
    ]:
        value = materials.get(name, "")
        if not re.fullmatch("[0-9a-f]{64}", value) or value == "0" * 64:
            raise ValueError("missing trusted material: " + name)
    ui = materials.get("uiSHA", "")
    if not re.fullmatch("[0-9a-f]{40}", ui) or ui == "0" * 40:
        raise ValueError("missing fixed UI")
    lock = json.loads((root / "TOOLS.lock.json").read_text())
    canonical = json.dumps(
        lock, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode()
    if materials["toolchainDigest"] != hashlib.sha256(canonical).hexdigest():
        raise ValueError("toolchain digest does not match image lock")


if __name__ == "__main__":
    verify(Path("/opt/s5"))
