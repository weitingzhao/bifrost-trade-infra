"""Release-policy check (LANE-RP): may this release go without waiting for the Owner?

The Owner signs a policy (policy.yaml + policy.sig in ConfigMap cicd/bifrost-release-policy)
with ssh-keygen -Y sign. A release is auto-approved only when all of these hold:

  * the freeze ConfigMap cicd/bifrost-release-freeze reads frozen=false (missing or
    unreadable counts as frozen; lifting a freeze needs an unfreeze text signed by the
    same key, and a freeze once seen cannot be erased by deleting its record);
  * the policy signature verifies against agent-config/release-policy/allowed_signers;
  * the policy has not expired;
  * the action is in `allow`;
  * no changed path matches the signed path table (no_ddl, no_d10_paths,
    no_trust_anchor_change) for any repo=old..new pair;
  * the caller reported no other blocker (--block).

Anything else waits for the Owner (exit 3). platform-api applies the same rules in Go
(api/internal/releasepolicy) to the same signed copy of the path table.

policy.yaml is canonical JSON (a YAML subset): `render` writes it, so this script needs
no YAML library and platform-api reads it with its YAML parser.

Exit codes: 0 auto-approved / valid · 1 invalid (verify) · 2 usage or input error ·
3 waiting on the Owner · 4 frozen.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Optional

NS_POLICY = "bifrost-release-policy"
NS_UNFREEZE = "bifrost-release-unfreeze"
PRINCIPAL = "owner"
PATH_RULES = ("no_ddl", "no_d10_paths", "no_trust_anchor_change")
SIGN_COMMAND = "bifrost-trade-infra/scripts/release/release.sh policy sign"
CLOCK_SKEW = timedelta(minutes=5)

EXIT_OK, EXIT_INVALID, EXIT_USAGE, EXIT_OWNER, EXIT_FROZEN = 0, 1, 2, 3, 4


# ── time ─────────────────────────────────────────────────────────────────────

def utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def iso(ts: datetime) -> str:
    return ts.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_iso(value: Any) -> Optional[datetime]:
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip().replace("Z", "+00:00")
    try:
        ts = datetime.fromisoformat(text)
    except ValueError:
        return None
    if ts.tzinfo is None:
        return None
    return ts.astimezone(timezone.utc)


# ── the draft template: the small YAML subset release-policy.draft.yaml uses ──

def _scalar(text: str) -> Any:
    text = text.strip()
    if text in ("", "null", "~"):
        return None
    if text == "true":
        return True
    if text == "false":
        return False
    if text.startswith("[") and text.endswith("]"):
        inner = text[1:-1].strip()
        return [] if not inner else [_scalar(part) for part in inner.split(",")]
    if re.fullmatch(r"-?\d+", text):
        return int(text)
    if len(text) >= 2 and text[0] == text[-1] and text[0] in "\"'":
        return text[1:-1]
    return text


def _strip_comment(line: str) -> str:
    if line.lstrip().startswith("#"):
        return ""
    cut = line.find(" #")
    return line if cut < 0 else line[:cut]


def parse_template(text: str) -> dict[str, Any]:
    """Top-level `key: scalar`, or `key:` followed by an indented list of scalars
    or an indented map of scalars. Anything deeper is refused."""
    out: dict[str, Any] = {}
    current: Optional[str] = None
    for lineno, raw in enumerate(text.splitlines(), 1):
        line = _strip_comment(raw).rstrip()
        if not line.strip():
            continue
        indent = len(line) - len(line.lstrip(" "))
        body = line.strip()
        if indent == 0:
            key, sep, rest = body.partition(":")
            if not sep or not key:
                raise ValueError(f"template line {lineno}: expected key: value")
            if rest.strip():
                out[key] = _scalar(rest)
                current = None
            else:
                out[key] = None
                current = key
            continue
        if current is None:
            raise ValueError(f"template line {lineno}: indented line without a parent key")
        if body.startswith("- "):
            if out[current] is None:
                out[current] = []
            if not isinstance(out[current], list):
                raise ValueError(f"template line {lineno}: {current} mixes a list and a map")
            out[current].append(_scalar(body[2:]))
            continue
        key, sep, rest = body.partition(":")
        if not sep or not rest.strip():
            raise ValueError(f"template line {lineno}: nested blocks are not supported")
        if out[current] is None:
            out[current] = {}
        if not isinstance(out[current], dict):
            raise ValueError(f"template line {lineno}: {current} mixes a list and a map")
        out[current][key.strip()] = _scalar(rest)
    return out


def render_policy(template: dict[str, Any], paths: dict[str, Any], signed_at: datetime,
                  days: Optional[int] = None) -> dict[str, Any]:
    valid_days = int(days if days is not None else template.get("valid_days") or 7)
    if valid_days < 1:
        raise ValueError("valid days must be at least 1")
    allow = template.get("allow") or []
    if not isinstance(allow, list) or not all(isinstance(a, str) and a for a in allow):
        raise ValueError("template allow must be a list of names")
    conditions = template.get("conditions") or {}
    if not isinstance(conditions, dict):
        raise ValueError("template conditions must be a map")
    if int(template.get("version") or 0) != 1:
        raise ValueError("template version must be 1")
    if int(paths.get("version") or 0) != 1 or not isinstance(paths.get("rules"), dict):
        raise ValueError("paths.json must be version 1 with a rules map")
    return {
        "version": 1,
        "policy_id": "rp-" + signed_at.strftime("%Y%m%d-%H%M"),
        "signed_by": PRINCIPAL,
        "signed_at": iso(signed_at),
        "expires_at": iso(signed_at + timedelta(days=valid_days)),
        "valid_days": valid_days,
        "allow": list(allow),
        "conditions": conditions,
        "limits": template.get("limits") or {},
        "reminders": template.get("reminders") or {},
        "ci_repos": list(paths.get("ci_repos") or []),
        "db_step_pipelines": list(paths.get("db_step_pipelines") or []),
        "paths": paths["rules"],
    }


def dump_policy(policy: dict[str, Any]) -> str:
    return json.dumps(policy, indent=2, sort_keys=True) + "\n"


# ── globs ────────────────────────────────────────────────────────────────────

_GLOB_CACHE: dict[str, re.Pattern[str]] = {}


def glob_regex(pattern: str) -> re.Pattern[str]:
    cached = _GLOB_CACHE.get(pattern)
    if cached is not None:
        return cached
    out, i = [], 0
    while i < len(pattern):
        if pattern.startswith("**/", i):
            out.append("(?:.*/)?")
            i += 3
        elif pattern.startswith("**", i):
            out.append(".*")
            i += 2
        elif pattern[i] == "*":
            out.append("[^/]*")
            i += 1
        elif pattern[i] == "?":
            out.append("[^/]")
            i += 1
        else:
            out.append(re.escape(pattern[i]))
            i += 1
    compiled = re.compile("^" + "".join(out) + "$")
    _GLOB_CACHE[pattern] = compiled
    return compiled


def path_matches(path: str, pattern: str) -> bool:
    return bool(glob_regex(pattern).match(path.lstrip("/")))


def rule_hits(paths_table: dict[str, Any], rule: str, repo: str, files: Iterable[str]) -> list[str]:
    hits = []
    for entry in paths_table.get(rule) or []:
        if entry.get("repo") not in ("*", repo):
            continue
        for f in files:
            if any(path_matches(f, p) for p in entry.get("paths") or []):
                hits.append(f)
    return sorted(set(hits))


# ── ssh signatures ───────────────────────────────────────────────────────────

def anchor_lines(allowed_signers: Path) -> list[str]:
    try:
        text = allowed_signers.read_text(encoding="utf-8")
    except OSError:
        return []
    return [ln for ln in text.splitlines() if ln.strip() and not ln.lstrip().startswith("#")]


def ssh_verify(data: bytes, signature: str, allowed_signers: Path, namespace: str) -> tuple[bool, str]:
    if not anchor_lines(allowed_signers):
        return False, f"no signing key in {allowed_signers} (the Owner has not set the trust anchor)"
    if not signature.strip():
        return False, "signature is empty"
    with tempfile.TemporaryDirectory(prefix="release-policy-") as tmp:
        sig_path = Path(tmp) / "data.sig"
        sig_path.write_text(signature if signature.endswith("\n") else signature + "\n", encoding="utf-8")
        proc = subprocess.run(
            ["ssh-keygen", "-Y", "verify", "-f", str(allowed_signers), "-I", PRINCIPAL,
             "-n", namespace, "-s", str(sig_path)],
            input=data, capture_output=True, check=False,
        )
    if proc.returncode == 0:
        return True, "signature ok"
    detail = (proc.stderr or proc.stdout).decode(errors="replace").strip().splitlines()
    return False, "signature does not verify" + (f" ({detail[-1]})" if detail else "")


# ── policy and freeze state ──────────────────────────────────────────────────

def policy_state(policy_text: Optional[str], sig_text: Optional[str], allowed_signers: Path,
                 now: datetime) -> dict[str, Any]:
    st: dict[str, Any] = {"valid": False, "reasons": [], "policy": None}
    if not policy_text or not policy_text.strip():
        st["reasons"].append("no signed policy (ConfigMap cicd/bifrost-release-policy is missing or empty)")
        return st
    if not sig_text or not sig_text.strip():
        st["reasons"].append("policy.sig is missing")
        return st
    ok, msg = ssh_verify(policy_text.encode("utf-8"), sig_text, allowed_signers, NS_POLICY)
    if not ok:
        st["reasons"].append(msg)
        return st
    try:
        policy = json.loads(policy_text)
    except ValueError:
        st["reasons"].append("policy.yaml is not the canonical form release.sh policy sign writes")
        return st
    st["policy"] = policy
    if policy.get("version") != 1:
        st["reasons"].append(f"policy version {policy.get('version')!r} is not 1")
    signed_at, expires_at = parse_iso(policy.get("signed_at")), parse_iso(policy.get("expires_at"))
    if signed_at is None or expires_at is None:
        st["reasons"].append("policy has no signed_at / expires_at")
    else:
        if signed_at > now + CLOCK_SKEW:
            st["reasons"].append(f"policy signed_at {iso(signed_at)} is in the future")
        if expires_at <= now:
            st["reasons"].append(f"policy {policy.get('policy_id')} expired at {iso(expires_at)}")
        st["expires_at"] = iso(expires_at)
        st["remaining_hours"] = round((expires_at - now).total_seconds() / 3600, 1)
    st["valid"] = not st["reasons"]
    return st


def freeze_state(data: Optional[dict[str, str]], allowed_signers: Path,
                 seen_frozen_at: Optional[str] = None) -> dict[str, Any]:
    """frozen unless the ConfigMap says false and any earlier freeze was lifted by a signed text."""
    if data is None:
        return {"frozen": True, "reason": "freeze ConfigMap cicd/bifrost-release-freeze is missing or unreadable"}
    flag = (data.get("frozen") or "").strip().lower()
    frozen_at = (data.get("frozen_at") or "").strip()
    if flag == "true":
        return {"frozen": True, "frozen_at": frozen_at,
                "reason": f"frozen by {data.get('who') or 'unknown'} at {frozen_at or '?'}: {data.get('reason') or 'no reason given'}"}
    if flag != "false":
        return {"frozen": True, "reason": f"freeze flag is {flag or 'empty'!r}, not false"}
    seen = parse_iso(seen_frozen_at) if seen_frozen_at else None
    if not frozen_at:
        if seen is not None:
            return {"frozen": True, "reason": f"a freeze from {iso(seen)} was seen and its record is gone"}
        return {"frozen": False, "reason": "never frozen"}
    at = parse_iso(frozen_at)
    if at is None:
        return {"frozen": True, "reason": f"frozen_at {frozen_at!r} is not a timestamp"}
    if seen is not None and at < seen:
        return {"frozen": True, "reason": f"unfreeze is for {frozen_at}; a later freeze ({iso(seen)}) was seen"}
    text = data.get("unfreeze.txt") or ""
    if not text.startswith(f"unfreeze frozen_at={frozen_at} "):
        return {"frozen": True, "reason": f"no signed unfreeze for the freeze at {frozen_at}"}
    ok, msg = ssh_verify(text.encode("utf-8"), data.get("unfreeze.sig") or "", allowed_signers, NS_UNFREEZE)
    if not ok:
        return {"frozen": True, "reason": "unfreeze " + msg}
    return {"frozen": False, "frozen_at": frozen_at, "reason": "unfrozen by a signed text"}


def update_seen(seen_file: Optional[Path], data: Optional[dict[str, str]]) -> Optional[str]:
    """Return the newest frozen_at ever seen, recording a new one when the ConfigMap is frozen."""
    if seen_file is None:
        return None
    previous = seen_file.read_text(encoding="utf-8").strip() if seen_file.exists() else ""
    current = (data or {}).get("frozen_at", "").strip()
    cur_ts, prev_ts = parse_iso(current), parse_iso(previous)
    if (data or {}).get("frozen", "").strip().lower() == "true" and cur_ts is not None:
        if prev_ts is None or cur_ts > prev_ts:
            seen_file.parent.mkdir(parents=True, exist_ok=True)
            seen_file.write_text(current + "\n", encoding="utf-8")
            return current
    return previous or None


# ── changes ──────────────────────────────────────────────────────────────────

def parse_pair(text: str) -> tuple[str, str, str]:
    repo, sep, rng = text.partition("=")
    old, dots, new = rng.partition("..")
    if not sep or not dots or not repo:
        raise ValueError(f"bad pair {text!r} (want repo=<old>..<new>)")
    return repo.strip(), old.strip(), new.strip()


def changed_files(repo_dir: Path, old: str, new: str) -> list[str]:
    if not repo_dir.is_dir():
        raise RuntimeError(f"no checkout at {repo_dir}")
    for sha in (old, new):
        probe = subprocess.run(["git", "-C", str(repo_dir), "cat-file", "-e", f"{sha}^{{commit}}"],
                               capture_output=True, check=False)
        if probe.returncode != 0:
            raise RuntimeError(f"commit {sha} is not in {repo_dir} (git fetch origin there first)")
    proc = subprocess.run(["git", "-C", str(repo_dir), "diff", "--name-only", f"{old}..{new}"],
                          capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        raise RuntimeError(f"git diff {old}..{new} failed in {repo_dir}: {proc.stderr.strip()}")
    return [ln for ln in proc.stdout.splitlines() if ln.strip()]


def decide(pol: dict[str, Any], frz: dict[str, Any], action: str,
           changes: list[dict[str, Any]], blocks: Iterable[str] = ()) -> tuple[int, list[str]]:
    """(exit code, reasons). changes: {repo, old, new, files} or {repo, error}."""
    if frz.get("frozen"):
        return EXIT_FROZEN, [f"releases are frozen: {frz.get('reason')}"]
    reasons = list(pol.get("reasons") or [])
    policy = pol.get("policy") or {}
    if pol.get("valid"):
        if action not in (policy.get("allow") or []):
            reasons.append(f"{action} is not in the policy's allow list")
        conditions = policy.get("conditions") or {}
        table = policy.get("paths") or {}
        for ch in changes:
            if ch.get("error"):
                reasons.append(f"{ch['repo']}: cannot read the diff ({ch['error']})")
                continue
            for rule in PATH_RULES:
                if conditions.get(rule) is False:
                    continue
                hits = rule_hits(table, rule, ch["repo"], ch.get("files") or [])
                if hits:
                    shown = ", ".join(hits[:5]) + (f" (+{len(hits) - 5} more)" if len(hits) > 5 else "")
                    reasons.append(f"{ch['repo']} {ch['old'][:12]}..{ch['new'][:12]} hits {rule}: {shown}")
    reasons.extend(b for b in blocks if b)
    return (EXIT_OK, []) if not reasons else (EXIT_OWNER, reasons)


# ── release records (deployed commits) ───────────────────────────────────────

def load_records(path: Path) -> list[dict[str, Any]]:
    doc = json.loads(path.read_text(encoding="utf-8") or "{}")
    out = []
    for cm in doc.get("items") or []:
        raw = (cm.get("data") or {}).get("record.json")
        if not raw:
            continue
        try:
            out.append(json.loads(raw))
        except ValueError:
            continue
    out.sort(key=lambda r: r.get("completed_at") or "", reverse=True)
    return out


def pick_record(records: list[dict[str, Any]], lane: str = "", env: str = "", run: str = "") -> Optional[dict[str, Any]]:
    for rec in records:
        if run and rec.get("run") != run:
            continue
        if lane and rec.get("lane") != lane:
            continue
        if env and rec.get("env") != env:
            continue
        return rec
    return None


# ── CLI ──────────────────────────────────────────────────────────────────────

def _read_cm(path: Optional[str]) -> Optional[dict[str, str]]:
    """kubectl get configmap -o json output; an empty file or '-' means missing."""
    if not path or path == "-":
        return None
    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError:
        return None
    if not text.strip():
        return None
    try:
        doc = json.loads(text)
    except ValueError:
        return None
    return {str(k): str(v) for k, v in (doc.get("data") or {}).items()}


def _now(args: argparse.Namespace) -> datetime:
    return parse_iso(args.now) if getattr(args, "now", None) else utc_now()


def _policy_from_cm(cm: Optional[dict[str, str]], allowed: Path, now: datetime) -> dict[str, Any]:
    cm = cm or {}
    st = policy_state(cm.get("policy.yaml"), cm.get("policy.sig"), allowed, now)
    shipped = cm.get("allowed_signers")
    if st["valid"] and shipped is not None and sorted(anchor_lines_text(shipped)) != sorted(anchor_lines(allowed)):
        st["valid"] = False
        st["reasons"].append("allowed_signers in the ConfigMap differs from agent-config/release-policy/allowed_signers")
    return st


def anchor_lines_text(text: str) -> list[str]:
    return [ln for ln in text.splitlines() if ln.strip() and not ln.lstrip().startswith("#")]


def cmd_render(args: argparse.Namespace) -> int:
    template = parse_template(Path(args.template).read_text(encoding="utf-8"))
    paths = json.loads(Path(args.paths).read_text(encoding="utf-8"))
    policy = render_policy(template, paths, _now(args), args.days)
    Path(args.out).write_text(dump_policy(policy), encoding="utf-8")
    print(f"policy_id {policy['policy_id']}")
    print(f"expires_at {policy['expires_at']}")
    return EXIT_OK


def _print_policy(st: dict[str, Any]) -> None:
    policy = st.get("policy") or {}
    print(f"policy_id      {policy.get('policy_id', '-')}")
    print(f"expires_at     {st.get('expires_at', '-')}")
    print(f"remaining      {st.get('remaining_hours', '-')} h")
    print(f"valid          {'yes' if st['valid'] else 'no'}")
    for r in st["reasons"]:
        print(f"  - {r}")


def cmd_verify(args: argparse.Namespace) -> int:
    allowed = Path(args.allowed_signers)
    st = policy_state(Path(args.policy).read_text(encoding="utf-8"),
                      Path(args.sig).read_text(encoding="utf-8"), allowed, _now(args))
    _print_policy(st)
    return EXIT_OK if st["valid"] else EXIT_INVALID


def cmd_status(args: argparse.Namespace) -> int:
    allowed = Path(args.allowed_signers)
    freeze_cm = _read_cm(args.freeze_cm)
    seen = update_seen(Path(args.seen_file) if args.seen_file else None, freeze_cm)
    st = _policy_from_cm(_read_cm(args.policy_cm), allowed, _now(args))
    _print_policy(st)
    frz = freeze_state(freeze_cm, allowed, seen)
    print(f"frozen         {'yes' if frz['frozen'] else 'no'} ({frz['reason']})")
    if not st["valid"] or (st.get("remaining_hours") or 0) <= 48:
        print(f"sign a new one: {SIGN_COMMAND}")
    return EXIT_OK if st["valid"] and not frz["frozen"] else EXIT_INVALID


def cmd_check(args: argparse.Namespace) -> int:
    allowed = Path(args.allowed_signers)
    freeze_cm = _read_cm(args.freeze_cm)
    seen = update_seen(Path(args.seen_file) if args.seen_file else None, freeze_cm)
    frz = freeze_state(freeze_cm, allowed, seen)
    pol = _policy_from_cm(_read_cm(args.policy_cm), allowed, _now(args))
    changes = []
    for item in args.pair:
        repo, old, new = parse_pair(item)
        if not re.fullmatch(r"[0-9a-f]{40}", old) or not re.fullmatch(r"[0-9a-f]{40}", new):
            changes.append({"repo": repo, "error": f"want two 40-char SHAs, got {old!r}..{new!r}"})
            continue
        try:
            files = [] if old == new else changed_files(Path(args.root) / repo, old, new)
            changes.append({"repo": repo, "old": old, "new": new, "files": files})
        except RuntimeError as exc:
            changes.append({"repo": repo, "error": str(exc)})
    if not args.pair:
        args.block.append("no repo=old..new pairs: nothing to diff")
    code, reasons = decide(pol, frz, args.action, changes, args.block)
    policy_id = (pol.get("policy") or {}).get("policy_id", "-")
    if code == EXIT_OK:
        print(f"auto-approved by {policy_id} ({args.action}, {len(changes)} repo diff(s) clean)")
    else:
        print(f"waiting on the Owner for {args.action}:")
        for r in reasons:
            print(f"  - {r}")
        if code == EXIT_FROZEN:
            print("lift it (Owner, signed): bifrost-trade-infra/scripts/release/release.sh unfreeze")
        elif not pol.get("valid"):
            print(f"sign a policy (Owner): {SIGN_COMMAND}")
    return code


def cmd_deployed(args: argparse.Namespace) -> int:
    rec = pick_record(load_records(Path(args.records)), args.lane, args.env, args.run)
    if rec is None:
        print(f"no release record for lane={args.lane or '*'} env={args.env or '*'} run={args.run or '*'}",
              file=sys.stderr)
        return EXIT_USAGE
    for repo, build in sorted((rec.get("repos") or {}).items()):
        sha = (build or {}).get("sha", "")
        if re.fullmatch(r"[0-9a-f]{40}", sha or ""):
            print(f"{repo}={sha}")
    return EXIT_OK


def cmd_ci_repo(args: argparse.Namespace) -> int:
    paths = json.loads(Path(args.paths).read_text(encoding="utf-8"))
    return EXIT_OK if args.repo in (paths.get("ci_repos") or []) else EXIT_INVALID


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("render", help="write policy.yaml from the draft template and the path table")
    p.add_argument("--template", required=True)
    p.add_argument("--paths", required=True)
    p.add_argument("--days", type=int, default=None)
    p.add_argument("--out", required=True)
    p.add_argument("--now", default=None)
    p.set_defaults(fn=cmd_render)

    p = sub.add_parser("verify", help="check a local policy.yaml + policy.sig")
    p.add_argument("--policy", required=True)
    p.add_argument("--sig", required=True)
    p.add_argument("--allowed-signers", required=True)
    p.add_argument("--now", default=None)
    p.set_defaults(fn=cmd_verify)

    for name, fn in (("status", cmd_status), ("check", cmd_check)):
        p = sub.add_parser(name)
        p.add_argument("--policy-cm", default="-", help="kubectl get configmap -o json (empty file = missing)")
        p.add_argument("--freeze-cm", default="-")
        p.add_argument("--allowed-signers", required=True)
        p.add_argument("--seen-file", default=None, help="newest frozen_at ever seen")
        p.add_argument("--now", default=None)
        if name == "check":
            p.add_argument("--action", required=True, help="a name from the policy's allow list")
            p.add_argument("--root", required=True, help="workspace root holding one checkout per repo")
            p.add_argument("--pair", action="append", default=[], help="repo=<old sha>..<new sha>")
            p.add_argument("--block", action="append", default=[], help="another reason to wait for the Owner")
        p.set_defaults(fn=fn)

    p = sub.add_parser("deployed", help="repo=sha lines of the newest matching release record")
    p.add_argument("--records", required=True, help="kubectl get cm -l bifrost.io/release-record -o json")
    p.add_argument("--lane", default="")
    p.add_argument("--env", default="")
    p.add_argument("--run", default="")
    p.set_defaults(fn=cmd_deployed)

    p = sub.add_parser("ci-repo", help="exit 0 when the repo has a ci-* gate")
    p.add_argument("--paths", required=True)
    p.add_argument("repo")
    p.set_defaults(fn=cmd_ci_repo)

    args = ap.parse_args(argv)
    try:
        return args.fn(args)
    except (OSError, ValueError) as exc:
        print(f"policy_check: {exc}", file=sys.stderr)
        return EXIT_USAGE


if __name__ == "__main__":
    sys.exit(main())
