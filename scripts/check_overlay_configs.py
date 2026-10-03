#!/usr/bin/env python3
"""Check every K3s overlay config the way the Trade APIs will read it (debt TD-06).

The overlay file is the only config for its env, and the APIs refuse to start when a
listen port is missing (``normalize_server_config`` raises). A sync script once dropped
``server.architecture.ops_port`` and api-monitor crash-looped on the next restart; this
check catches that before a deliver.

Also holds the two ops settings that have silently gone missing before:
``daemon_scale_guard: freeze`` (D10) everywhere, and ``platform_audit.enabled`` in STG and
PROD (TD-05).

Usage: python3 scripts/check_overlay_configs.py   (exit 1 on any problem)
"""
from __future__ import annotations

import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
CORE_SRC = ROOT.parent / "bifrost-trade-core" / "src"
if CORE_SRC.is_dir():
    sys.path.insert(0, str(CORE_SRC))

from bifrost_core.config.yaml_config import normalize_server_config  # noqa: E402

OVERLAYS = {
    "dev": ROOT / "k8s/overlays/dev/config/config.dev.yaml",
    "stg": ROOT / "k8s/overlays/stg/config/config.stg.yaml",
    "prod": ROOT / "k8s/overlays/prod/config/config.prod.yaml",
}
AUDITED = {"stg", "prod"}


def problems(env: str, path: Path) -> list[str]:
    cfg = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    out: list[str] = []
    try:
        normalize_server_config(cfg.get("server"))
    except ValueError as exc:
        out.append(f"server: {exc}")
    ops = cfg.get("ops") or {}
    if ops.get("daemon_scale_guard") != "freeze":
        out.append("ops.daemon_scale_guard must be 'freeze' while D10 is BLOCKED")
    if env in AUDITED and not (ops.get("platform_audit") or {}).get("enabled"):
        out.append("ops.platform_audit.enabled must be true (Ops actuations need an audit trail)")
    if "audit" in ops:
        out.append("ops.audit is a dead key (nothing reads it); use ops.platform_audit")
    return out


def main() -> int:
    bad = 0
    for env, path in OVERLAYS.items():
        found = problems(env, path)
        bad += len(found)
        print(f"{'FAIL' if found else 'ok  '} {env:<4} {path.relative_to(ROOT)}")
        for p in found:
            print(f"       - {p}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
