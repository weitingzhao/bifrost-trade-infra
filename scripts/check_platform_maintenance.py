#!/usr/bin/env python3
"""PROD patrol skills are mounted on both platform-api and platform-workers (W-33).

Owner 2026-10-07: autopilot and data maintenance run only in PROD; local and STG run none.
W-33 moved /patrol onto platform-api, so the api pod must see the same skill files and
the same dispatch/mode as workers. The patrol loop and the checklist prober stay on
platform-workers. This check renders every k8s/overlays/platform-* kustomization and holds:

- platform-prod's platform-api and platform-workers both mount patrol skills;
- those two containers share PATROL_SKILLS_DIR, PATROL_MODE and PATROL_DISPATCH;
- CHECKLIST_PROBER=on only on platform-prod/platform-workers;
- platform-api does not set PLATFORM_PATROL_LOOP on (the loop stays on workers);
- wherever patrol skills are mounted, PATROL_DISPATCH=local (no skill goes to Cursor Cloud);
- while TD-253 is in report-only trial, PATROL_MODE=report. Lifting it is an Owner
  decision; change REPORT_ONLY below in the same commit as the overlay;
- STG platform-workers has PLATFORM_DATA_CLONE_SCHEDULER and PLATFORM_PATROL_LOOP
  off (code defaults both on). PROD workers must not turn them off.
- no other deployment mounts the skills or turns the prober on.

Usage: python3 scripts/check_platform_maintenance.py   (exit 1 on any problem)
"""

from __future__ import annotations

import pathlib
import subprocess
import sys

import yaml

ROOT = pathlib.Path(__file__).resolve().parent.parent
OVERLAYS = sorted((ROOT / "k8s" / "overlays").glob("platform-*"))
SKILL_PAIR = {("platform-prod", "platform-api"), ("platform-prod", "platform-workers")}
PROBER = ("platform-prod", "platform-workers")
REPORT_ONLY = True
SHARED_ENV = ("PATROL_SKILLS_DIR", "PATROL_MODE", "PATROL_DISPATCH")

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
    skill_env: dict[tuple[str, str], tuple[str, str, str]] = {}
    probers = 0
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
                has_skills = bool(mounts) or "PATROL_SKILLS_DIR" in env
                prober_on = env.get("CHECKLIST_PROBER", "").lower() == "on"
                where = f"{ov.name}/{name}"
                key = (ov.name, name)
                if key == ("platform-prod", "platform-api"):
                    loop = env.get("PLATFORM_PATROL_LOOP", "").strip().lower()
                    if loop and loop not in LOOP_OFF:
                        problems.append(
                            f"{where}: PLATFORM_PATROL_LOOP={env['PLATFORM_PATROL_LOOP']}; the patrol loop stays on workers"
                        )
                if prober_on:
                    if key != PROBER:
                        problems.append(f"{where}: CHECKLIST_PROBER=on outside {'/'.join(PROBER)}")
                    else:
                        probers += 1
                if not has_skills:
                    continue
                if key not in SKILL_PAIR:
                    problems.append(f"{where}: patrol skills outside PROD platform-api and platform-workers")
                    continue
                if not mounts:
                    problems.append(f"{where}: PATROL_SKILLS_DIR set without the skills volume")
                skill_env[key] = tuple(env.get(k, "") for k in SHARED_ENV)
                if env.get("PATROL_DISPATCH") != "local":
                    problems.append(f"{where}: patrol skills mounted without PATROL_DISPATCH=local")
                if REPORT_ONLY and env.get("PATROL_MODE") != "report":
                    problems.append(f"{where}: PATROL_MODE={env.get('PATROL_MODE', '(unset)')}, want report (TD-253 trial)")
    if set(skill_env) != SKILL_PAIR:
        got = ", ".join(f"{a}/{b}" for a, b in sorted(skill_env)) or "(none)"
        problems.append(f"skill mounts on {got}, want platform-prod/platform-api and platform-prod/platform-workers")
    else:
        api = skill_env[("platform-prod", "platform-api")]
        workers = skill_env[("platform-prod", "platform-workers")]
        if api != workers:
            problems.append(
                "platform-prod api "
                + ",".join(f"{k}={v}" for k, v in zip(SHARED_ENV, api))
                + " != workers "
                + ",".join(f"{k}={v}" for k, v in zip(SHARED_ENV, workers))
            )
        elif api[0] != "/app/patrol-skills":
            problems.append(f"PATROL_SKILLS_DIR={api[0]}, want /app/patrol-skills")
    if probers != 1:
        problems.append(f"{probers} checklist prober(s), want exactly 1 ({'/'.join(PROBER)})")
    if not saw_stg_workers:
        problems.append("platform-stg/platform-workers was not rendered")
    if not saw_prod_workers:
        problems.append("platform-prod/platform-workers was not rendered")
    for p in problems:
        print("FAIL", p)
    if not problems:
        print(
            "ok: PROD platform-api and platform-workers share "
            + "/".join(SHARED_ENV)
            + f" (report-only={REPORT_ONLY}); checklist prober only on {'/'.join(PROBER)}; "
            "STG data-clone scheduler and patrol loop off"
        )
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
