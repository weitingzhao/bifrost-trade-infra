#!/usr/bin/env python3
"""Check every K3s overlay config the way the Trade APIs will read it (debt TD-06).

The overlay file is the only config for its env, and the APIs refuse to start when a
listen port is missing (``normalize_server_config`` raises). A sync script once dropped
``server.architecture.ops_port`` and api-monitor crash-looped on the next restart; this
check catches that before a deliver.

Also holds the settings that have silently gone missing before:
``daemon_scale_guard: freeze`` (D10) everywhere, ``platform_audit.enabled`` in STG and
PROD (TD-05), and ``reference_indices`` (TD-53: it lived only in a file K3s never
merges). And it refuses a key written twice: YAML keeps the last one without a word,
which once dropped STG's first ``ib_operator`` block (TD-53).

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


class _UniqueKeyLoader(yaml.SafeLoader):
    """A SafeLoader that records every mapping key written twice, with its line."""

    duplicates: list[str]


def _construct_mapping(loader: _UniqueKeyLoader, node: yaml.MappingNode, deep: bool = False):
    seen: dict = {}
    for key_node, _ in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in seen:
            loader.duplicates.append(f"{key!r} at line {key_node.start_mark.line + 1} (first at line {seen[key]})")
        else:
            seen[key] = key_node.start_mark.line + 1
    return loader.construct_mapping(node, deep=deep)


_UniqueKeyLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _construct_mapping)


def load_strict(text: str) -> tuple[dict, list[str]]:
    """The parsed YAML and every duplicated key in it."""
    loader = _UniqueKeyLoader(text)
    loader.duplicates = []
    try:
        return loader.get_single_data() or {}, loader.duplicates
    finally:
        loader.dispose()


def problems(env: str, path: Path) -> list[str]:
    cfg, duplicates = load_strict(path.read_text(encoding="utf-8"))
    out: list[str] = [f"duplicate key {d}: YAML keeps only the last one" for d in duplicates]
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
    if not cfg.get("reference_indices"):
        out.append("reference_indices is empty: the market strip and Refresh Index would answer with nothing")
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
