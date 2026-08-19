#!/usr/bin/env python3
"""Materialize gitignored Trade K8s Secrets from overlay YAML + plugin .env.

Never prints secret values. Writes:
  k8s/base/secrets/bifrost-{dev,stg,prod}-secrets.yaml

Usage:
  python3 scripts/materialize_k8s_trade_secrets.py
  python3 scripts/materialize_k8s_trade_secrets.py --apply
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLUGIN_ENV = ROOT.parent / "bifrost-platform-plugin" / ".env"
MD_ENV = ROOT.parent / "bifrost-platform-plugin-market-data" / ".env"

OVERLAYS = {
    "dev": ROOT / "k8s/overlays/dev/config/config.dev.yaml",
    "stg": ROOT / "k8s/overlays/stg/config/config.stg.yaml",
    "prod": ROOT / "k8s/overlays/prod/config/config.prod.yaml",
}
ROOT_DEV = ROOT / "config/config.dev.yaml"
SECRET_PATHS = {
    "dev": ROOT / "k8s/base/secrets/bifrost-dev-secrets.yaml",
    "stg": ROOT / "k8s/base/secrets/bifrost-stg-secrets.yaml",
    "prod": ROOT / "k8s/base/secrets/bifrost-prod-secrets.yaml",
}

PLACEHOLDERS = frozenset({"", "REPLACE_ME", "CHANGE_ME", "changeme", "change-me"})


def _load_dotenv(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.is_file():
        return out
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        val = val.strip().strip("'").strip('"')
        if key:
            out[key] = val
    return out


def _nonempty(val: object) -> str:
    if val is None:
        return ""
    text = str(val).strip()
    if text in PLACEHOLDERS:
        return ""
    return text


def _pick(*candidates: object) -> str:
    for c in candidates:
        v = _nonempty(c)
        if v:
            return v
    return ""


def _block_field(text: str, block: str, field: str) -> str:
    m = re.search(
        rf"^{re.escape(block)}:\n(?:  .+\n)*?  {re.escape(field)}:\s*[\"']?([^\"'\n#]+)",
        text,
        flags=re.MULTILINE,
    )
    return m.group(1).strip() if m else ""


def _ops_tokens(text: str) -> tuple[str, str]:
    operator = admin = ""
    for m in re.finditer(
        r"-\s+token:\s*[\"']?([^\"'\n]+)[\"']?\s*\n\s+role:\s*[\"']?(\w+)",
        text,
    ):
        tok, role = m.group(1).strip(), m.group(2).strip().lower()
        if role == "operator" and tok and not operator:
            operator = tok
        elif role == "admin" and tok and not admin:
            admin = tok
    return operator, admin


def _existing_string_data(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    text = path.read_text(encoding="utf-8")
    out: dict[str, str] = {}
    in_sd = False
    for line in text.splitlines():
        if line.strip() == "stringData:":
            in_sd = True
            continue
        if in_sd:
            if line and not line.startswith(" ") and not line.startswith("\t"):
                break
            m = re.match(r'^\s+([A-Z0-9_]+):\s*[\"\']?(.*?)[\"\']?\s*$', line)
            if m:
                out[m.group(1)] = m.group(2)
    return out


def _yaml_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _build_secret(env_name: str, text: str, extras: dict[str, str], existing: dict[str, str]) -> dict[str, str]:
    op, admin = _ops_tokens(text)
    api_key = _block_field(text, "massive", "api_key")
    if env_name == "dev" and ROOT_DEV.is_file():
        root_text = ROOT_DEV.read_text(encoding="utf-8")
        r_op, r_admin = _ops_tokens(root_text)
        op = op or r_op
        admin = admin or r_admin
        if not _nonempty(api_key):
            api_key = _block_field(root_text, "massive", "api_key")

    polygon = _pick(
        api_key,
        extras.get("POLYGON_API_KEY"),
        extras.get("MASSIVE_API_KEY"),
        existing.get("POLYGON_API_KEY"),
        existing.get("MASSIVE_API_KEY"),
    )
    pg_pw = _block_field(text, "postgres", "password")
    gs_pw = _block_field(text, "golden_source", "password")
    return {
        "MASSIVE_API_KEY": _pick(polygon, existing.get("MASSIVE_API_KEY")),
        "POLYGON_API_KEY": _pick(polygon, existing.get("POLYGON_API_KEY")),
        "OPS_OPERATOR_TOKEN": _pick(op, extras.get("OPS_OPERATOR_TOKEN"), existing.get("OPS_OPERATOR_TOKEN")),
        "OPS_ADMIN_TOKEN": _pick(admin, extras.get("OPS_ADMIN_TOKEN"), existing.get("OPS_ADMIN_TOKEN")),
        "MARKET_DATA_WRITE_TOKEN": _pick(
            extras.get("MARKET_DATA_WRITE_TOKEN"),
            existing.get("MARKET_DATA_WRITE_TOKEN"),
        ),
        "REDIS_IB_USERNAME": _pick(
            _block_field(text, "redis_ib", "username"),
            extras.get("REDIS_IB_USERNAME"),
            "trade-prod",
        ),
        "REDIS_IB_PASSWORD": _pick(
            _block_field(text, "redis_ib", "password"),
            extras.get("REDIS_IB_TRADE_PROD_PASS"),
            extras.get("REDIS_IB_PASSWORD"),
            existing.get("REDIS_IB_PASSWORD"),
        ),
        "REDIS_MASSIVE_USERNAME": _pick(
            _block_field(text, "redis_massive", "username"),
            extras.get("REDIS_MASSIVE_USERNAME"),
            "trade-prod",
        ),
        "REDIS_MASSIVE_PASSWORD": _pick(
            _block_field(text, "redis_massive", "password"),
            extras.get("REDIS_MASSIVE_TRADE_PROD_PASS"),
            extras.get("REDIS_MASSIVE_PASSWORD"),
            existing.get("REDIS_MASSIVE_PASSWORD"),
        ),
        "PGPASSWORD": _pick(
            pg_pw,
            extras.get("POSTGRES_PASSWORD"),
            extras.get("PGPASSWORD"),
            existing.get("PGPASSWORD"),
        ),
        "GOLDEN_SOURCE_PASSWORD": _pick(
            gs_pw,
            extras.get("GOLDEN_SOURCE_PASSWORD"),
            pg_pw,
            extras.get("POSTGRES_PASSWORD"),
            extras.get("PGPASSWORD"),
            existing.get("GOLDEN_SOURCE_PASSWORD"),
        ),
    }


def _write_secret(path: Path, name: str, string_data: dict[str, str]) -> list[str]:
    missing = [k for k, v in string_data.items() if not _nonempty(v) and k != "MARKET_DATA_WRITE_TOKEN"]
    lines = [
        "apiVersion: v1",
        "kind: Secret",
        "metadata:",
        f"  name: {name}",
        "  labels:",
        "    app.kubernetes.io/part-of: bifrost",
        "type: Opaque",
        "stringData:",
    ]
    for key, val in string_data.items():
        lines.append(f'  {key}: "{_yaml_escape(val)}"')
    lines.append("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
    os.chmod(path, 0o600)
    return missing


def _upsert_dotenv(path: Path, updates: dict[str, str]) -> None:
    if not path.is_file():
        return
    text = path.read_text(encoding="utf-8")
    existing = _load_dotenv(path)
    lines = text.splitlines()
    added: list[str] = []
    for key, val in updates.items():
        if not _nonempty(val):
            continue
        if _nonempty(existing.get(key, "")):
            continue
        added.append(f"{key}={val}")
    if not added:
        return
    if lines and lines[-1].strip():
        lines.append("")
    lines.append("# Trade secrets (materialize_k8s_trade_secrets.py) — do not commit")
    lines.extend(added)
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="kubectl apply the written Secret files")
    args = parser.parse_args()

    extras: dict[str, str] = {}
    extras.update(_load_dotenv(ROOT / ".env"))
    extras.update(_load_dotenv(PLUGIN_ENV))
    extras.update(_load_dotenv(MD_ENV))

    kubeconfig = os.environ.get("KUBECONFIG") or str(Path.home() / ".kube/bifrost-k3s.yaml")
    any_missing = False
    for env_name, cfg_path in OVERLAYS.items():
        if not cfg_path.is_file():
            print(f"SKIP {env_name}: missing {cfg_path}", file=sys.stderr)
            continue
        text = cfg_path.read_text(encoding="utf-8")
        dest = SECRET_PATHS[env_name]
        existing = _existing_string_data(dest)
        data = _build_secret(env_name, text, extras, existing)
        missing = _write_secret(dest, f"bifrost-{env_name}-secrets", data)
        filled = sum(1 for v in data.values() if _nonempty(v))
        print(f"Wrote {dest.relative_to(ROOT)} keys={filled}/11 missing={missing or 'none'}")
        if missing:
            any_missing = True
        if args.apply:
            ns = f"bifrost-{env_name}"
            cmd = [
                "kubectl",
                "--kubeconfig",
                kubeconfig,
                "apply",
                "-n",
                ns,
                "-f",
                str(dest),
            ]
            print(f"Applying Secret bifrost-{env_name}-secrets in {ns}")
            subprocess.run(cmd, check=True)

    compose_keys = {
        "REDIS_IB_USERNAME": "trade-prod",
        "REDIS_IB_PASSWORD": "",
        "REDIS_MASSIVE_USERNAME": "trade-prod",
        "REDIS_MASSIVE_PASSWORD": "",
        "PGPASSWORD": "",
        "GOLDEN_SOURCE_PASSWORD": "",
        "OPS_OPERATOR_TOKEN": "",
        "OPS_ADMIN_TOKEN": "",
        "POLYGON_API_KEY": "",
        "MASSIVE_API_KEY": "",
    }
    stg_secret = _existing_string_data(SECRET_PATHS["stg"])
    for k in list(compose_keys):
        compose_keys[k] = _pick(stg_secret.get(k), extras.get(k), compose_keys.get(k))
    if SECRET_PATHS["dev"].is_file():
        dev_secret = _existing_string_data(SECRET_PATHS["dev"])
        for k in ("OPS_OPERATOR_TOKEN", "OPS_ADMIN_TOKEN", "POLYGON_API_KEY", "MASSIVE_API_KEY"):
            compose_keys[k] = _pick(dev_secret.get(k), compose_keys.get(k))
    _upsert_dotenv(ROOT / ".env", compose_keys)

    if any_missing:
        print("Some required keys were empty — fill gitignored Secret files before rollout.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
