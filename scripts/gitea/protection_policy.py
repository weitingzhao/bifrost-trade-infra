"""Gitea branch baseline and conservative overlap check (S6-7). No I/O beyond JSON."""
import json
import sys

# Gitea 1.21 branch rules are gobwas globs with "/" as the separator: * and ?
# do not cross a "/", ** does, [...] / [!...] is one character (only ! negates;
# ^ is a character like any other, as in gobwas), {a,b} picks one, a backslash
# takes the next character as it is. A rule clashes when it can match "main"
# or some branch "agent/<more>" or "land/prod/<more>" whose next part can start a branch name (git
# refuses a part that starts with "." and the characters below anywhere).


def expand(p):
    """The rule without braces: every choice of every {a,b} (nested too)."""
    out, i, prefix = [], 0, ""
    while i < len(p):
        c = p[i]
        if c == "\\" and i + 1 < len(p):
            prefix += p[i:i + 2]
            i += 2
            continue
        if c == "[":
            j = p.find("]", i + 2)
            if j == -1:
                prefix += c
                i += 1
                continue
            prefix += p[i:j + 1]
            i = j + 1
            continue
        if c == "{":
            depth, j, parts, start = 1, i + 1, [], i + 1
            while j < len(p) and depth:
                if p[j] == "\\":
                    j += 2
                    continue
                if p[j] == "{":
                    depth += 1
                elif p[j] == "}":
                    depth -= 1
                    if depth == 0:
                        parts.append(p[start:j])
                        break
                elif p[j] == "," and depth == 1:
                    parts.append(p[start:j])
                    start = j + 1
                j += 1
            if depth:
                prefix += c
                i += 1
                continue
            rest = expand(p[j + 1:])
            return [prefix + a + r for part in parts for a in expand(part) for r in rest]
        prefix += c
        i += 1
    return [prefix]


def tokens(p):
    out, i = [], 0
    while i < len(p):
        c = p[i]
        if c == "\\" and i + 1 < len(p):
            out.append(("lit", p[i + 1]))
            i += 2
        elif c == "*" and p[i + 1:i + 2] == "*":
            out.append(("any",))
            i += 2
        elif c == "*":
            out.append(("seg",))
            i += 1
        elif c == "?":
            out.append(("one",))
            i += 1
        elif c == "[" and p.find("]", i + 2) != -1:
            j = p.find("]", i + 2)
            body, neg = p[i + 1:j], False
            if body[:1] == "!":
                body, neg = body[1:], True
            out.append(("class", body, neg))
            i = j + 1
        else:
            out.append(("lit", c))
            i += 1
    return out


def in_class(body, c):
    k = 0
    while k < len(body):
        if k + 2 < len(body) and body[k + 1] == "-":
            if body[k] <= c <= body[k + 2]:
                return True
            k += 3
        else:
            if body[k] == c:
                return True
            k += 1
    return False


def closure(ts, states):
    todo, seen = list(states), set(states)
    while todo:
        i = todo.pop()
        if i < len(ts) and ts[i][0] in ("seg", "any") and i + 1 not in seen:
            seen.add(i + 1)
            todo.append(i + 1)
    return seen


def step(ts, states, c):
    nxt = set()
    for i in states:
        if i == len(ts):
            continue
        t = ts[i]
        if t[0] == "lit" and t[1] == c or t[0] == "one" and c != "/" or t[0] == "class" and in_class(t[1], c) != t[2]:
            nxt.add(i + 1)
        elif t[0] == "seg" and c != "/" or t[0] == "any":
            nxt.add(i)
    return closure(ts, nxt)


def run(ts, text):
    states = closure(ts, {0})
    for c in text:
        states = step(ts, states, c)
    return states


NOT_IN_A_BRANCH = set(" ~^:?*[\\\x7f") | {chr(c) for c in range(32)}
STARTS = [chr(c) for c in range(33, 127) if chr(c) not in NOT_IN_A_BRANCH and chr(c) not in "./"]


def clash(rule):
    for p in expand(rule):
        ts = tokens(p)
        # Git permits Unicode branch names. Include every literal/class boundary
        # and its neighbors so a narrower non-ASCII rule cannot escape the scan.
        points = {128, 0x10FFFF}
        for token in ts:
            if token[0] in ("lit", "class"):
                for char in token[1]:
                    points.update((ord(char) - 1, ord(char), ord(char) + 1))
        starts = STARTS + [chr(n) for n in points if 127 < n <= 0x10FFFF]
        if len(ts) in run(ts, "main"):
            return True
        # Conservatively refuse any reachable valid branch-part prefix.
        for prefix in ("agent/", "land/prod/"):
            after = run(ts, prefix)
            if any(step(ts, after, c) for c in starts):
                return True
    return False


LANDING_REPOS = {"bifrost-platform", "bifrost-trade-infra"}


def baseline(repo, owner):
    teams = [] if repo in LANDING_REPOS else ["maintainers"]
    main = {
        "rule_name": "main",
        "enable_push": True,
        "enable_push_whitelist": True,
        "push_whitelist_teams": teams,
        "push_whitelist_usernames": [owner] + (["agentrt-lander"] if repo in LANDING_REPOS else []),
        "push_whitelist_deploy_keys": False,
        "unprotected_file_patterns": "",
        "enable_merge_whitelist": True,
        "merge_whitelist_teams": teams,
        "merge_whitelist_usernames": [owner],
    }
    rules = [main]
    if repo in LANDING_REPOS:
        rules.insert(0, {**main, "rule_name": "land/prod/**",
                      "push_whitelist_usernames": ["agentrt-lander"],
                      "merge_whitelist_usernames": []})
    return rules


def differences(want, got):
    # Missing/null lists are unknown, not an empty whitelist. bool != int.
    bad = []
    for key, value in want.items():
        actual = got.get(key)
        if type(actual) is not type(value):
            bad.append(key)
        elif isinstance(value, list):
            if not all(isinstance(v, str) for v in actual) or sorted(actual) != sorted(value):
                bad.append(key)
        elif actual != value:
            bad.append(key)
    return bad


def plan(repo, owner, rows, check=False):
    if not isinstance(rows, list):
        raise ValueError("cannot read branch rules: expected a list")
    existing = {}
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("cannot read branch rule")
        name = row.get("rule_name") or row.get("branch_name")
        if not isinstance(name, str) or not name or name in existing:
            raise ValueError("missing or duplicate branch rule name")
        existing[name] = row
    # Exact land/prod/** is only exempt when we validate its full baseline.
    known = {"main", "agent/**"} | ({"land/prod/**"} if repo in LANDING_REPOS else set())
    if any(name not in known and clash(name) for name in existing):
        raise ValueError("STOPPED: overlapping rule could match main, agent/ or land/prod/ first")
    actions = []
    for want in baseline(repo, owner):
        name = want["rule_name"]
        got = existing.get(name)
        if got is None:
            if check:
                raise ValueError(f"{name}: missing protection")
            actions.append({"method": "POST", "rule": name, "body": want})
            continue
        bad = differences(want, got)
        # Only the known S0 -> S6 infra change may edit an existing rule.
        # PATCH this one field; keep status checks/reviews/other hardening intact.
        old = {**want, "push_whitelist_usernames": [owner]}
        if (not check and repo == "bifrost-trade-infra" and name == "main"
                and bad == ["push_whitelist_usernames"] and not differences(old, got)):
            actions.append({"method": "PATCH", "rule": name,
                            "body": {"push_whitelist_usernames": want["push_whitelist_usernames"]}})
        elif bad:
            raise ValueError(f"{name}: DIFFERS from the baseline; fields: {', '.join(bad)}; left as it is")
    if "agent/**" in existing:
        if check:
            raise ValueError("agent/**: must be absent (attempt branches must remain deletable; TD-383)")
        actions.append({"method": "DELETE", "rule": "agent/**", "body": None})
    return actions


if __name__ == "__main__":
    try:
        mode, repo, owner = sys.argv[1:]
        result = plan(repo, owner, json.load(sys.stdin), check=mode == "check")
        if mode == "check":
            print("PASS protection: main and landing whitelists verified; agent/** absent; no overlaps")
        else:
            for action in result:
                print(json.dumps(action, separators=(",", ":")))
    except (ValueError, TypeError, KeyError, RecursionError):
        # JSON/transport data can contain reflected credentials: only report
        # our controlled validation errors, never a raw response or traceback.
        error = sys.exc_info()[1]
        message = str(error) if type(error) is ValueError and not isinstance(error, json.JSONDecodeError) else "cannot parse branch rules"
        print("FAIL protection: " + message, file=sys.stderr)
        sys.exit(1)


