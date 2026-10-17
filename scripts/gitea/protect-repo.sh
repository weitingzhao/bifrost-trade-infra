#!/usr/bin/env bash
# protect-repo.sh --owner <login> <repo>... — the two branch rules of the
# Gitea-primary cut (§2.9, §3; batch step 5) on each converted repository,
# then read back and compared field by field:
#   main      push: team maintainers and <login>; merge (PR): the same
#   agent/**  push: team agentd-write and <login>; merge (PR): maintainers and <login>
# Both rules carry a merge whitelist: without one, code write is enough to
# merge a pull request into the branch (Gitea 1.21 IsUserMergeWhitelisted).
# The tag rule (*: maintainers and <login>) has no API in 1.21: the script
# prints the page to set it on. A rule that exists is edited to this, not
# duplicated. Another branch rule that could match main or an agent/ branch
# stops it for that repository before anything is changed: Gitea 1.21 takes
# the first rule that matches, so an older `**` or a narrower rule would
# decide instead of these (review 246 B9). A rule that can match neither stays
# (release/**, main?, ma[st]er; review 248 B7, 249 B4): the rule is read as
# Gitea 1.21 reads it, a glob with / as the separator. Exits 1 when a
# repository is stopped or a read-back differs.
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
# shellcheck source=lib.sh
source "$HERE/lib.sh"
owner=""
if [[ "${1:-}" == "--owner" && -n "${2:-}" ]]; then
  owner="$2"
  shift 2
fi
[[ -n "${owner}" && $# -ge 1 ]] || gitea_die "usage: protect-repo.sh --owner <your Gitea login> <repo>..."
# the read-back must hold every field that was set (lists in any order)
COMPARE_RULE='
import json, sys
want, got = json.loads(sys.argv[1]), json.load(sys.stdin)
norm = lambda v: sorted(v or []) if isinstance(v, list) else v
bad = [k for k, v in want.items() if (norm(got.get(k)) if isinstance(v, list) else got.get(k)) != norm(v)]
for k in bad:
    print(f"    {k}: want {want[k]!r}, Gitea has {got.get(k)!r}")
sys.exit(1 if bad else 0)
'
# the other rules that could match main or a branch under agent/ (review 249 B4)
OVERLAPPING_RULES='
import json, sys

# Gitea 1.21 branch rules are gobwas globs with "/" as the separator: * and ?
# do not cross a "/", ** does, [...] / [!...] is one character, {a,b} picks one,
# a backslash takes the next character as it is. A rule clashes when it can
# match "main" or some branch "agent/<more>".


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
            if body[:1] in ("!", "^"):
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


def clash(rule):
    for p in expand(rule):
        ts = tokens(p)
        if len(ts) in run(ts, "main"):
            return True
        # some state left after "agent/" can still take a character: a branch agent/<more> matches
        if any(i < len(ts) for i in run(ts, "agent/")):
            return True
    return False


names = [str(r.get("rule_name") or r.get("branch_name") or "") for r in json.load(sys.stdin)]
print(" ".join(sorted(n for n in names if n not in ("main", "agent/**") and clash(n))))
'
gitea_connect
fail=0
for repo in "$@"; do
  existing="$(gitea_api GET "/repos/${GITEA_ORG}/${repo}/branch_protections")" || gitea_die "cannot read the rules of ${repo}"
  others="$(python3 -c "${OVERLAPPING_RULES}" <<< "${existing}")" || gitea_die "cannot read the rules of ${repo}"
  if [[ -n "${others}" ]]; then
    echo "${repo}: STOPPED, nothing changed: these branch rules could match main or an agent/ branch first (${others}); remove them on the page or say why they stay, then run this again"
    fail=1
    continue
  fi
  for rule in main 'agent/**'; do
    if [[ "${rule}" == main ]]; then push_team=maintainers; else push_team=agentd-write; fi
    body="$(python3 - "${rule}" "${push_team}" "${owner}" << 'PY'
import json, sys
rule, team, owner = sys.argv[1:4]
print(json.dumps({
    "rule_name": rule,
    "enable_push": True,
    "enable_push_whitelist": True,
    "push_whitelist_teams": [team],
    "push_whitelist_usernames": [owner],
    "push_whitelist_deploy_keys": False,
    "enable_merge_whitelist": True,
    "merge_whitelist_teams": ["maintainers"],
    "merge_whitelist_usernames": [owner],
}))
PY
)"
    enc="$(python3 -c 'import sys, urllib.parse; print(urllib.parse.quote(sys.argv[1], safe=""))' "${rule}")"
    existing="$(gitea_api GET "/repos/${GITEA_ORG}/${repo}/branch_protections")" || gitea_die "cannot read the rules of ${repo}"
    if python3 -c 'import json,sys; sys.exit(0 if any(r.get("rule_name") == sys.argv[1] for r in json.load(sys.stdin)) else 1)' "${rule}" <<< "${existing}"; then
      gitea_api PATCH "/repos/${GITEA_ORG}/${repo}/branch_protections/${enc}" "${body}" > /dev/null || gitea_die "${repo} ${rule}: edit refused"
    else
      gitea_api POST "/repos/${GITEA_ORG}/${repo}/branch_protections" "${body}" > /dev/null || gitea_die "${repo} ${rule}: create refused"
    fi
    got="$(gitea_api GET "/repos/${GITEA_ORG}/${repo}/branch_protections/${enc}")" || gitea_die "${repo} ${rule}: cannot read it back"
    if python3 -c "${COMPARE_RULE}" "${body}" <<< "${got}"; then
      echo "${repo} ${rule}: set and read back"
    else
      echo "${repo} ${rule}: READ BACK DIFFERS"
      fail=1
    fi
  done
  echo "${repo}: now add the tag rule on the page: Gitea → ${GITEA_ORG}/${repo} → Settings → Tags → New rule: *, allowed: team maintainers and ${owner}"
done
exit "${fail}"
