"""Local protection snapshots and per-write verification; never reads credentials."""
import json
import os
from pathlib import Path
import sys

from protection_policy import plan

# Gitea 1.21.11 BranchProtection/CreateBranchProtectionOption. A POST adds
# server defaults; a PATCH may change updated_at, but nothing else implicitly.
DEFAULTS = {
    **dict.fromkeys(("enable_push", "enable_push_whitelist", "push_whitelist_deploy_keys",
                     "enable_merge_whitelist", "enable_status_check", "enable_approvals_whitelist",
                     "block_on_rejected_reviews", "block_on_official_review_requests",
                     "block_on_outdated_branch", "dismiss_stale_approvals", "require_signed_commits"), False),
    **{k: [] for k in ("push_whitelist_usernames", "push_whitelist_teams", "merge_whitelist_usernames",
                       "merge_whitelist_teams", "status_check_contexts", "approvals_whitelist_username",
                       "approvals_whitelist_teams")},
    "required_approvals": 0, "protected_file_patterns": "", "unprotected_file_patterns": "",
}
SCOPED = {"main", "agent/**", "land/prod/**"}
METADATA = {"created_at", "updated_at", "branch_name"}


class StateError(ValueError):
    """Only controlled messages/field names; safe to show without response values."""


def indexed(rows):
    if not isinstance(rows, list):
        raise StateError("cannot read branch rules")
    result = {}
    for row in rows:
        if not isinstance(row, dict):
            raise StateError("cannot read branch rule")
        name = row.get("rule_name")
        if not isinstance(name, str) or not name or name in result:
            raise StateError("missing or duplicate rule name")
        if set(row) - (DEFAULTS.keys() | METADATA | {"rule_name"}):
            raise StateError("unknown protection fields; manual inspection required")
        for key, value in row.items():
            if key in METADATA | {"rule_name"}:
                if not isinstance(value, str) or (key == "branch_name" and value != name):
                    raise StateError("invalid protection metadata")
            elif isinstance(DEFAULTS[key], list):
                if value is not None and (not isinstance(value, list) or not all(isinstance(v, str) for v in value)):
                    raise StateError("invalid protection list")
            elif type(value) is not type(DEFAULTS[key]):
                raise StateError("invalid protection field type")
        result[name] = row
    return result


def canonical(value):
    if isinstance(value, dict):
        return {k: canonical(v) for k, v in value.items()}
    if isinstance(value, list):
        return sorted(value)  # all rule field lists contain strings
    return value


def equal(a, b):
    return json.dumps(canonical(a), sort_keys=True) == json.dumps(canonical(b), sort_keys=True)


def settings(row):
    # Missing optional defaults and null optional lists have the same semantics.
    return {"rule_name": row["rule_name"], **{
        k: ([] if isinstance(default, list) and row.get(k) is None else row.get(k, default))
        for k, default in DEFAULTS.items()}}


def verify_step(before, action, after):
    old, new = indexed(before), indexed(after)
    method, name, body = action["method"], action["rule"], action["body"]
    names = set(old)
    if method == "POST":
        if name in old:
            raise StateError("POST target already existed")
        names.add(name)
    elif method == "DELETE":
        names.remove(name)
    elif method != "PATCH" or name not in old:
        raise StateError("invalid protection action")
    if names != set(new):
        raise StateError("readback rule existence differs")
    # API order is effective priority. Existing rules must retain relative order.
    survivors = set(old) & set(new)
    if [n for n in old if n in survivors] != [n for n in new if n in survivors]:
        raise StateError("readback priority changed")
    for rule in names:
        if rule != name:
            if not equal(old[rule], new[rule]):
                raise StateError("readback changed an unrelated rule")
        elif method == "PATCH":
            want = {**old[rule], **body}
            want.pop("updated_at", None)
            got = {k: v for k, v in new[rule].items() if k != "updated_at"}
            if not equal(want, got):
                bad = sorted(k for k in want.keys() | got.keys() if not equal(want.get(k), got.get(k))
                             or (k in want) != (k in got))
                raise StateError("READ BACK DIFFERS; PATCH fields: " + ", ".join(bad))
        elif method == "POST":
            if not equal(settings(body), settings(new[rule])):
                bad = sorted(k for k in DEFAULTS if not equal(settings(body)[k], settings(new[rule])[k]))
                raise StateError("READ BACK DIFFERS; POST fields: " + ", ".join(bad))
            # Explicit fields must be returned (do not accept missing/null as
            # an empty requested whitelist), even if they match a default.
            if not equal(body, {k: new[rule].get(k) for k in body}):
                bad = sorted(k for k in body if not equal(body[k], new[rule].get(k)))
                raise StateError("READ BACK DIFFERS; POST omitted fields: " + ", ".join(bad))


def save(path, org, repo, owner, rows):
    indexed(rows)
    # Exclusive create, private mode. Never replace an earlier snapshot/symlink.
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as handle:
        json.dump({"version": 1, "org": org, "repo": repo, "owner": owner, "rules": rows}, handle, indent=2)
        handle.write("\n")


def load(path, org, repo, owner):
    data = json.loads(Path(path).read_text())
    if (not isinstance(data, dict) or data.get("version") != 1
            or (data.get("org"), data.get("repo"), data.get("owner")) != (org, repo, owner)):
        raise StateError("snapshot identity differs")
    rows = data["rules"]
    indexed(rows)
    # Only states supported by this migration can be restored automatically.
    # In particular, unrelated rules cannot overlap any recreated scoped rule.
    plan(repo, owner, rows)
    return rows


def verify_snapshot(want, got):
    old, new = indexed(want), indexed(got)
    if set(old) != set(new) or any(not equal(settings(old[n]), settings(new[n])) for n in old):
        raise StateError("snapshot protection settings differ")
    # main, landing and agent are disjoint. plan() above proves no unrelated
    # rule can intersect them. Preserve all other rules' relative priority;
    # recreated scoped rules may have new creation timestamps without changing
    # the first matched rule for any branch.
    if [n for n in old if n not in SCOPED] != [n for n in new if n not in SCOPED]:
        raise StateError("snapshot effective priority differs")


def restore_plan(want, got):
    old, new = indexed(want), indexed(got)
    # Never overwrite unrelated concurrent edits or recreate overlapping rules.
    if {n for n in old if n not in SCOPED} != {n for n in new if n not in SCOPED}:
        raise StateError("unrelated rules changed; manual reconciliation required")
    for n in old.keys() - SCOPED:
        if not equal(old[n], new[n]):
            raise StateError("unrelated rule changed; manual reconciliation required")
    if [n for n in old if n not in SCOPED] != [n for n in new if n not in SCOPED]:
        raise StateError("unrelated priority changed; manual reconciliation required")
    actions = []
    # Restore earlier restrictions before removing protections created by S6.
    for name in ("main", "agent/**", "land/prod/**"):
        if name not in old:
            continue
        if name not in new:
            actions.append({"method": "POST", "rule": name, "body": settings(old[name])})
        else:
            body = {k: v for k, v in settings(old[name]).items()
                    if k != "rule_name" and not equal(v, settings(new[name])[k])}
            if body:
                actions.append({"method": "PATCH", "rule": name, "body": body})
    for name in ("land/prod/**", "agent/**", "main"):
        if name in new and name not in old:
            actions.append({"method": "DELETE", "rule": name, "body": None})
    return actions


def main():
    command, *args = sys.argv[1:]
    if command == "step":
        # API JSON may be pretty printed; consume three complete documents.
        decoder, remaining, values = json.JSONDecoder(), sys.stdin.read(), []
        while remaining.strip():
            value, end = decoder.raw_decode(remaining.lstrip())
            values.append(value)
            remaining = remaining.lstrip()[end:]
        before, action, after = values
        verify_step(before, action, after)
    elif command == "summary":
        rows = indexed(json.load(sys.stdin))
        print("current state: " + "; ".join(n + (" present" if n in rows else " absent")
                                            for n in sorted(SCOPED)) + f"; total rules={len(rows)}")
        print("current field values are withheld; inspect the private current.json and snapshot")
    else:
        path, org, repo, owner = args
        rows = json.load(sys.stdin)
        if command == "save":
            save(path, org, repo, owner, rows)
        elif command in ("restore", "verify"):
            before = load(path, org, repo, owner)
            if command == "verify":
                verify_snapshot(before, rows)
                print("PASS snapshot: settings, existence and effective priority restored")
            else:
                for action in restore_plan(before, rows):
                    print(json.dumps(action, separators=(",", ":")))
        else:
            raise StateError("unknown state command")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, TypeError, KeyError, OSError, RecursionError):
        # Responses/snapshots may contain reflected secrets. No raw values,
        # JSON parser fragments, OS path diagnostics or traceback on stdout.
        error = sys.exc_info()[1]
        reason = str(error) if isinstance(error, StateError) else "validation or snapshot I/O failed"
        print("FAIL protection state: " + reason + "; stop and inspect locally", file=sys.stderr)
        sys.exit(1)
