#!/usr/bin/env python3
"""Run each ci-infra stage with immutable inputs and fail-closed evidence."""
import argparse
import json
import os
import runpy
import subprocess
import sys
import time
from pathlib import Path

P = runpy.run_path(str(Path(__file__).with_name("doc_policy.py")))
Error = P["PolicyError"]
STAGES = ("tools", "consumers", "doc-policy", "quick", "statics",
          "kustomize", "parity-static")
# code-health (the infra-only "metrics never rise" ratchet) was removed in
# cleanup wave 1, 2026-11-11; scope (the landing allow set and path tables,
# which the platform judges before it pushes) in cleanup wave 2, 2026-11-12.
# The names stay accepted as no-ops until the cluster Task without those steps
# is applied; Tasks run this file from the base.
RETIRED = ("code-health", "scope")


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


def statics(infra, platform):
    for name in ("check_admission_guards.py", "check_agent_access.py", "check_platform_maintenance.py",
                 "check_alert_routing.py"):
        run([sys.executable, "-I", infra / "scripts" / name], cwd=infra)
    # Infra's copies of platform config/ (spine, trust overrides, running images,
    # actuation policy) follow the platform main resolved for this run (TD-109).
    # Only infra is judged: ci-platform no longer runs this comparison.
    parity = infra / "scripts/check_ops_context_parity.py"
    run([sys.executable, "-I", parity, "--self-test"], cwd=infra)
    run([sys.executable, "-I", parity], cwd=infra, env=dict(os.environ, PLATFORM_ROOT=str(platform)))
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
    elif name in ("consumers", "doc-policy"):
        if not args.base_sha:
            print(f"{name}: skipped(no_base)")
            if name == "doc-policy":
                write_result(args, "doc-policy", "skipped")
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
        statics(infra, platform)
    elif name == "kustomize":
        kustomize(infra)
    elif name in RETIRED:
        print(f"{name}: retired")
    elif name == "parity-static":
        script = infra / "agent-config/scripts/check-governance-consistency.sh"
        # Older scripts silently ignore arguments and consult host hooks.
        if "--static-tree" not in script.read_text():
            raise Error("parity_static_unsupported")
        run(["bash", script, "--static-tree", args.cand], cwd=infra)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--stage", choices=(*STAGES, *RETIRED, "all"), required=True)
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
        if args.results_dir and args.results_dir.is_dir() and current_stage in ("consumers", "doc-policy"):
            write_result(args, "doc-policy", "fail")
        print(f"FAIL {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
