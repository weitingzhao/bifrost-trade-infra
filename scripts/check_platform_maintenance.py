#!/usr/bin/env python3
"""Ops maintenance runs in one place: PROD platform-workers (TD-253 ratchet).

Owner 2026-10-07: autopilot and data maintenance run only in PROD; local and STG run none.
Until then a local Mac process fixed things on weeks-old signals while two in-cluster copies
sat ready to. This check renders every k8s/overlays/platform-* kustomization and holds:

- only platform-prod's platform-workers sets PATROL_SKILLS_DIR, mounts patrol skills,
  or turns on CHECKLIST_PROBER — no platform-api, no STG;
- wherever patrol skills are mounted, PATROL_DISPATCH=local (no skill goes to Cursor Cloud);
- while TD-253 is in report-only trial, PATROL_MODE=report there. Lifting it is an Owner
  decision; change REPORT_ONLY below in the same commit as the overlay;
- STG platform-workers has PLATFORM_DATA_CLONE_SCHEDULER and PLATFORM_PATROL_LOOP
  off (code defaults both on). PROD must not turn them off.

Usage: python3 scripts/check_platform_maintenance.py   (exit 1 on any problem)
"""

from __future__ import annotations

import pathlib
import subprocess
import sys

import yaml

ROOT = pathlib.Path(__file__).resolve().parent.parent
OVERLAYS = sorted((ROOT / "k8s" / "overlays").glob("platform-*"))
MAINTAINER = ("platform-prod", "platform-workers")
REPORT_ONLY = True

MAINT_ENV = ("PATROL_SKILLS_DIR", "CHECKLIST_PROBER")
# Code treats anything else, including unset, as on.
LOOP_OFF = {"0", "false", "off", "no"}
LOOP_SWITCHES = ("PLATFORM_DATA_CLONE_SCHEDULER", "PLATFORM_PATROL_LOOP")


def render(path: pathlib.Path) -> list[dict]:
    out = subprocess.run(["kubectl", "kustomize", str(path)], capture_output=True, text=True, check=True)
    return [d for d in yaml.safe_load_all(out.stdout) if d]


def env_of(container: dict) -> dict[str, str]:
    return {e["name"]: str(e.get("value", "")) for e in container.get("env", []) if "name" in e}


def main() -> int:
    problems: list[str] = []
    maintainers = 0
    saw_stg_workers = False
    saw_prod_workers = False
    for ov in OVERLAYS:
        if not (ov / "kustomization.yaml").exists():
            continue
        for d in render(ov):
            if d.get("kind") != "Deployment":
                continue
            name = d["metadata"]["name"]
            spec = d["spec"]["template"]["spec"]
            if name == "platform-workers" and ov.name in ("platform-stg", "platform-prod"):
                if ov.name == "platform-stg":
                    saw_stg_workers = True
                else:
                    saw_prod_workers = True
                for c in spec.get("containers", []):
                    env = env_of(c)
                    for key in LOOP_SWITCHES:
                        val = env.get(key, "").strip().lower()
                        where = f"{ov.name}/{name}"
                        if ov.name == "platform-stg" and val not in LOOP_OFF:
                            problems.append(f"{where}: {key}={env.get(key, '(unset)')}, want off (STG observes)")
                        if ov.name == "platform-prod" and val in LOOP_OFF:
                            problems.append(f"{where}: {key} is off; PROD is where maintenance runs")
            skill_vols = {
                v["name"]
                for v in spec.get("volumes", [])
                if "patrol-skills" in (v.get("configMap") or {}).get("name", "")
            }
            for c in spec.get("containers", []):
                env = env_of(c)
                mounts = [m for m in c.get("volumeMounts", []) if m["name"] in skill_vols]
                maint = bool(mounts) or "PATROL_SKILLS_DIR" in env or env.get("CHECKLIST_PROBER", "").lower() == "on"
                where = f"{ov.name}/{name}"
                if not maint:
                    continue
                if (ov.name, name) != MAINTAINER:
                    problems.append(f"{where}: maintenance ({', '.join(k for k in MAINT_ENV if k in env) or 'patrol skills'}) outside {'/'.join(MAINTAINER)}")
                    continue
                maintainers += 1
                if env.get("PATROL_DISPATCH") != "local":
                    problems.append(f"{where}: patrol skills mounted without PATROL_DISPATCH=local")
                if REPORT_ONLY and env.get("PATROL_MODE") != "report":
                    problems.append(f"{where}: PATROL_MODE={env.get('PATROL_MODE', '(unset)')}, want report (TD-253 trial)")
    if maintainers != 1:
        problems.append(f"{maintainers} maintaining container(s), want exactly 1 ({'/'.join(MAINTAINER)})")
    if not saw_stg_workers:
        problems.append("platform-stg/platform-workers was not rendered")
    if not saw_prod_workers:
        problems.append("platform-prod/platform-workers was not rendered")
    for p in problems:
        print("FAIL", p)
    if not problems:
        print(
            f"ok: maintenance only in {'/'.join(MAINTAINER)} "
            f"(dispatch local, report-only={REPORT_ONLY}); "
            "STG data-clone scheduler and patrol loop off"
        )
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
