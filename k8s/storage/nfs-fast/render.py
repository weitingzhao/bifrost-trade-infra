#!/usr/bin/env python3
"""Fill the @TOKENS@ of k8s/storage/nfs-fast from a private site file (TD-444 step 5 runbook §3.2).

The repository is public: the NAS address, the old PV names and the node names live
in the runbook's private site mapping (§10), not here. The Owner (or the coordinator,
from the private record) writes a site file with KEY=VALUE lines:

  NAS_IP=<IPv4>                      the NFS server for every PV
  PROBE_NODE_A=<node> PROBE_NODE_B=<node>   writer / reader nodes of the §3.5 probes (must differ)
  OLD_PV_B1=pvc-<uuid> ... OLD_PV_REG=pvc-<uuid>   old PVs for rollback-pvc.yaml (§3.7 A)
  MARKET_DATA_IMAGE=<registry>/bifrost-market-data@sha256:<digest>   arc/replica image (§5.2)

and runs, from the package root (<pkg>):

  python3 k8s/storage/nfs-fast/render.py --site <private file> --run-id <id> --groups daily,monitoring \
      --out <rundir>/<SHA>/rendered

Every *.yaml of the named groups (directories under k8s/storage/nfs-fast) is copied
with its tokens replaced; the arc replica script is copied as is. A token that is unknown, unset or malformed stops the
render; nothing is written unless every file renders. The output carries its own
SHA256SUMS. Only keys a rendered group uses are required (OLD_PV_F1 / F2 wait for group 2b).
"""

from __future__ import annotations

import argparse
import hashlib
import ipaddress
import re
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
TOKEN = re.compile(r"@([A-Z][A-Z0-9_]*)@")
FORMATS = {
    "NAS_IP": lambda v: ipaddress.IPv4Address(v) and True,
    "PROBE_NODE_A": lambda v: re.fullmatch(r"[a-z0-9]([-a-z0-9.]*[a-z0-9])?", v) is not None,
    "PROBE_NODE_B": lambda v: re.fullmatch(r"[a-z0-9]([-a-z0-9.]*[a-z0-9])?", v) is not None,
    "PROBE_TOKEN": lambda v: re.fullmatch(r"td444-[A-Za-z0-9-]{1,40}", v) is not None,
    "MARKET_DATA_IMAGE": lambda v: re.fullmatch(r"[A-Za-z0-9.:/_-]+/bifrost-market-data@sha256:[0-9a-f]{64}", v) is not None,
}
OLD_PV = re.compile(r"pvc-[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")


def load_site(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    for n, raw in enumerate(path.read_text().splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise SystemExit(f"{path}:{n}: expected KEY=VALUE")
        k, v = (s.strip() for s in line.split("=", 1))
        if k in out:
            raise SystemExit(f"{path}:{n}: {k} given twice")
        out[k] = v
    return out


def valid(key: str, value: str) -> bool:
    if key.startswith("OLD_PV_"):
        return OLD_PV.fullmatch(value) is not None
    check = FORMATS.get(key)
    if check is None:
        return False
    try:
        return bool(check(value))
    except ValueError:
        return False


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--site", required=True, type=Path)
    ap.add_argument("--run-id", required=True, help="becomes @PROBE_TOKEN@ as td444-<run-id>")
    ap.add_argument("--groups", required=True, help="comma list: daily,finance,monitoring,reg,arc")
    ap.add_argument("--out", required=True, type=Path)
    args = ap.parse_args()
    groups = [g for g in args.groups.split(",") if g]
    for g in groups:
        if not (HERE / g).is_dir():
            raise SystemExit(f"unknown group {g}")

    site = load_site(args.site)
    site["PROBE_TOKEN"] = f"td444-{args.run_id}"
    for k, v in site.items():
        if not valid(k, v):
            raise SystemExit(f"site value {k} is unknown or malformed")
    if site.get("PROBE_NODE_A") and site.get("PROBE_NODE_A") == site.get("PROBE_NODE_B"):
        raise SystemExit("PROBE_NODE_A and PROBE_NODE_B must be different nodes")
    if args.out.exists():
        raise SystemExit(f"{args.out} exists; render into a new directory")

    rendered: dict[Path, bytes] = {}
    for src in sorted(HERE.rglob("*")):
        if not src.is_file() or src.suffix == ".pyc" or "__pycache__" in src.parts:
            continue
        rel = src.relative_to(HERE)
        if len(rel.parts) < 2 or rel.parts[0] not in groups:
            continue
        if src.suffix in (".yaml", ".yml"):
            text = src.read_text()
            missing = sorted({m for m in TOKEN.findall(text) if m not in site})
            if missing:
                raise SystemExit(f"{rel}: site file lacks {', '.join(missing)}")
            out = TOKEN.sub(lambda m: site[m.group(1)], text)
            if TOKEN.search(out):
                raise SystemExit(f"{rel}: a token survived rendering")
            rendered[rel] = out.encode()
        elif rel.parts[0] == "arc" and src.suffix == ".py":
            rendered[rel] = src.read_bytes()

    args.out.mkdir(parents=True)
    sums = []
    for rel, data in rendered.items():
        dst = args.out / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(data)
        sums.append(f"{hashlib.sha256(data).hexdigest()}  ./{rel.as_posix()}")
    (args.out / "SHA256SUMS").write_text("\n".join(sums) + "\n")
    print(f"rendered {len(rendered)} files into {args.out} (check: cd {args.out} && shasum -a 256 -c SHA256SUMS)")
    return 0


if __name__ == "__main__":
    os.umask(0o077)
    sys.exit(main())
