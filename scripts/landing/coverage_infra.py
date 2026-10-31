#!/usr/bin/env python3
"""Run each ci-infra stage with immutable inputs and fail-closed evidence."""
import argparse
import hashlib
import json
import os
import runpy
import subprocess
import sys
import tempfile
import time
from pathlib import Path

P = runpy.run_path(str(Path(__file__).with_name("doc_policy.py")))
Error = P["PolicyError"]
STAGES = ("tools", "scope", "consumers", "doc-policy", "quick", "statics",
          "kustomize", "code-health", "parity-static")
METRICS = {"code.duplication.rocket.infra", "code.duplication.rocket.infra-py",
           "code.oversized.rocket.infra"}


def run(argv, cwd=None, env=None, capture=False):
    result = subprocess.run([str(x) for x in argv], cwd=cwd, env=env, check=False,
                            stdout=subprocess.PIPE if capture else None, text=True)
    if result.returncode:
        raise Error(f"command_failed {Path(str(argv[0])).name} exit={result.returncode}")
    return result.stdout if capture else ""


def tools_check(expected=Path("/opt/ci-infra/TOOLS.expected")):
    versions = [run(["python3", "--version"], capture=True).strip(),
                run(["git", "--version"], capture=True).strip(),
                "bash " + run(["bash", "-c", 'printf "%s" "$BASH_VERSION"'], capture=True),
                "kubectl " + json.loads(run(["kubectl", "version", "--client", "-o", "json"], capture=True))["clientVersion"]["gitVersion"],
                run(["go", "version"], capture=True).strip()]
    actual = "\n".join(versions) + "\n"
    print(actual, end="")
    if actual != expected.read_text():
        raise Error("tools_version_mismatch")


def check_workspace(args):
    infra, platform = args.cand / P["REPO"], args.cand / "bifrost-platform"
    for repo, revision in ((infra, args.revision), (platform, args.platform_revision)):
        P["sha"](revision)
        if P["git"](repo, "rev-parse", "HEAD").decode().strip() != revision:
            raise Error("checkout_mismatch")
        if P["git"](repo, "status", "--porcelain", "--untracked-files=normal").strip():
            raise Error("checkout_dirty")
    if args.base_sha:
        P["identity"](infra, args.revision, args.base_sha, args.purpose)
        base_repo = args.base / P["REPO"]
        if P["git"](base_repo, "rev-parse", "HEAD").decode().strip() != args.base_sha:
            raise Error("base_checkout_mismatch")
        if P["git"](base_repo, "status", "--porcelain", "--untracked-files=normal").strip():
            raise Error("base_checkout_dirty")
    elif args.purpose == "landing":
        raise Error("base_missing")
    return infra, platform


def metric_values(path):
    data = json.loads(path.read_text())
    if data.get("not_measured") or not isinstance(data.get("metrics"), list):
        raise Error("code_health_unmeasured")
    coverage = data.get("scan_complete", {}).get(P["REPO"], {})
    if type(coverage.get("files_read")) is not int or not coverage.get("paths_sha256"):
        raise Error("code_health_scan_incomplete")
    values = {}
    for m in data["metrics"]:
        if m.get("repo") != P["REPO"]:
            raise Error("code_health_wrong_repo")
        key, value = m["id"], m["value"]
        if key in values or type(value) is not int or value < 0:
            raise Error("code_health_invalid_metric")
        values[key] = value
    if not METRICS <= values.keys():
        raise Error("code_health_missing_metric")
    return values


def compare_health(base, candidate):
    before, after = metric_values(base), metric_values(candidate)
    if before.keys() != after.keys():
        raise Error("code_health_metric_set_changed")
    for key in before:
        print(f"code-health {key} {before[key]}→{after[key]}")
        if after[key] > before[key]:
            raise Error(f"code_health_regressed {key} {before[key]}→{after[key]}")


def code_health(args, infra):
    if not args.base_sha:
        raise Error("code_health_no_base")
    with tempfile.TemporaryDirectory(prefix="ci-infra-health-") as temp:
        directory = Path(temp)
        # Export the scanner AND its sourced baseline from M0. Neither run can
        # source a candidate baseline, nor accidentally scan its script's tree.
        for name in ("scan.sh", "baselines.env"):
            (directory / name).write_bytes(P["blob"](infra, args.base_sha, "agent-config/scripts/code-health/" + name))
        outputs = []
        for label, root in (("base", args.base), ("cand", args.cand)):
            output = directory / (label + ".json")
            result = subprocess.run(["bash", str(directory / "scan.sh"), "--root", str(root),
                                     "--repo", P["REPO"], "--json", str(output)], capture_output=True, check=False)
            # Absolute-baseline exit 1 is expected. Missing/malformed output is
            # always fatal; execution errors never manufacture zero metrics.
            if result.returncode not in (0, 1):
                raise Error("code_health_scan_failed")
            metric_values(output)
            revision = args.base_sha if label == "base" else args.revision
            names = sorted(name.encode("utf-8") for name in P["tree"](infra, revision)
                           if name.endswith((".ts", ".tsx", ".py", ".go", ".sh", ".yml", ".yaml", ".md")))
            expected = {"files_read": len(names), "paths_sha256": hashlib.sha256(b"".join(n + b"\0" for n in names)).hexdigest()}
            if json.loads(output.read_text())["scan_complete"][P["REPO"]] != expected:
                raise Error("code_health_scan_incomplete")
            outputs.append(output)
        compare_health(*outputs)


def quick(args, infra, platform):
    generator = platform / "api/cmd/infracheck"
    if not generator.is_dir():
        raise Error("platform_infracheck_missing")
    env = dict(os.environ, GOFLAGS="-mod=mod", GOPROXY="off", GOSUMDB="off", GOTOOLCHAIN="local", GOWORK="off")
    command = ["go", "-C", str(platform / "api"), "run", "./cmd/infracheck"]
    start = time.monotonic()
    setup = run(command + ["--print-setup", "--wheelhouse", "/opt/wheels"], env=env, capture=True)
    if not setup.strip():
        raise Error("quick_setup_empty")
    run(["sh", "-c", setup], cwd=infra, env=env)
    script = run(command + ["--print-check"], env=env, capture=True)
    if not script.strip():
        raise Error("quick_check_empty")
    run(["sh", "-c", script], cwd=infra, env=env)
    seconds = time.monotonic() - start
    print(f"quick_seconds={seconds:.3f}")
    if seconds > 120:
        print("WARN quick_budget_exceeded seconds=" + str(round(seconds, 3)))
    # This warning measures this execution. There is no previous-run artifact
    # contract; logs are the timing record, not an undeclared Tekton result.


def statics(infra):
    for name in ("check_admission_guards.py", "check_agent_access.py", "check_platform_maintenance.py",
                 "check_alert_routing.py"):
        run([sys.executable, "-I", infra / "scripts" / name], cwd=infra)
    # This fixed two-repository workspace has no flex-query revision. The
    # default release-chain entry remains the full cross-repository check.
    run([sys.executable, "-I", infra / "scripts/check-release-chain.py", "--scope", "infra"], cwd=infra)
    run([sys.executable, "-I", infra / "agent-config/scripts/check_hardcoded_paths.py",
         "--ref", "HEAD", "--new-only"], cwd=infra)


def kustomize(infra):
    overlays = sorted((infra / "k8s/overlays").glob("*/"))
    if not overlays:
        raise Error("overlays_missing")
    for overlay in overlays:
        run(["kubectl", "kustomize", overlay], capture=True)


def write_result(args, name, value):
    if args.results_dir:
        (args.results_dir / name).write_text(value)


def stage(args, name, infra, platform):
    if name == "tools":
        tools_check()
    elif name in ("scope", "consumers", "doc-policy"):
        if not args.base_sha:
            print(f"{name}: skipped(no_base)")
            if name == "doc-policy":
                write_result(args, "doc-policy", "skipped")
            return
        if name == "scope" and args.purpose == "push":
            print("scope: skipped(push)")
            return
        command = [sys.executable, "-I", Path(__file__).with_name("doc_consumers.py" if name == "consumers" else "doc_policy.py")]
        if name != "consumers":
            command.append(name)
        run(command + ["--repo", infra, "--base", args.base_sha, "--revision", args.revision,
                       "--platform", platform, "--platform-revision", args.platform_revision,
                       "--purpose", args.purpose])
        if name == "doc-policy":
            write_result(args, "doc-policy", "pass")
    elif name == "quick":
        quick(args, infra, platform)
    elif name == "statics":
        statics(infra)
    elif name == "kustomize":
        kustomize(infra)
    elif name == "code-health":
        code_health(args, infra)
    elif name == "parity-static":
        script = infra / "agent-config/scripts/check-agent-config-parity.sh"
        # Older scripts silently ignore arguments and consult host hooks.
        if "--static-tree" not in script.read_text():
            raise Error("parity_static_unsupported")
        run(["bash", script, "--static-tree", args.cand], cwd=infra)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--stage", choices=(*STAGES, "all"), required=True)
    ap.add_argument("--cand", type=Path)
    ap.add_argument("--base", type=Path)
    ap.add_argument("--revision", default="")
    ap.add_argument("--base-sha", default="")
    ap.add_argument("--platform-revision", default="")
    ap.add_argument("--purpose", choices=("landing", "push"), default="landing")
    ap.add_argument("--generation", default="")
    ap.add_argument("--results-dir", type=Path)
    args = ap.parse_args()
    # The CI image has no git identity, and quick runs tests that commit and
    # revert in temporary repositories (first positive run, 2026-10-31). A
    # fixed CI identity keeps every stage independent of the host's git config.
    for key, value in (("GIT_AUTHOR_NAME", "bifrost-ci-infra"), ("GIT_AUTHOR_EMAIL", "ci-infra@bifrost.invalid"),
                       ("GIT_COMMITTER_NAME", "bifrost-ci-infra"), ("GIT_COMMITTER_EMAIL", "ci-infra@bifrost.invalid")):
        os.environ.setdefault(key, value)
    current_stage = args.stage
    try:
        if args.stage == "tools":
            tools_check()
            return 0
        if args.cand is None or args.base is None:
            raise Error("workspace_missing")
        args.cand, args.base = args.cand.resolve(), args.base.resolve()
        if args.base_sha == "0" * 40 and args.purpose == "push":
            args.base_sha = ""
        infra, platform = check_workspace(args)
        if args.results_dir:
            args.results_dir.mkdir(parents=True, exist_ok=True)
        for key, value in (("infra-commit", args.revision), ("base-commit", args.base_sha),
                           ("platform-commit", args.platform_revision), ("tools-from", args.base_sha),
                           ("purpose", args.purpose)):
            write_result(args, key, value)
        for name in STAGES if args.stage == "all" else (args.stage,):
            current_stage = name
            print(f"==> {name}", flush=True)
            stage(args, name, infra, platform)
    except (Error, OSError, ValueError, KeyError, TypeError) as exc:
        if args.results_dir and args.results_dir.is_dir() and current_stage in ("scope", "consumers", "doc-policy"):
            write_result(args, "doc-policy", "fail")
        print(f"FAIL {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
