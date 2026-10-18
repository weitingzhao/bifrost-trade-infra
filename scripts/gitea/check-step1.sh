#!/usr/bin/env bash
# check-step1.sh — read only: what the Owner set up in section 1 of
# OWNER-STEPS-gitea-primary.md, as Gitea 1.21 reports it, against what the
# Gitea-primary cut needs (CUT-gitea-primary-2026-10-17 §5 「第 1 步」):
#
#   accounts  bifrost-mbp (not an administrator), agentd-agent-06 and
#             agentd-agent-06-stg exist
#   teams     bifrost/maintainers: all repositories, Code write, no unit
#             above write, not an owners' or admin team; members weitingzhao
#             and bifrost-mbp. bifrost/agentd-write: all repositories, Code
#             write, every other unit none; members the two agentd users.
#             The external wiki and external issue tracker units only show a
#             link to another site and grant nothing; Gitea gives them read
#             on a new team, and they are not counted
#   probe     bifrost/primary-probe: regular (not a mirror), private, a main
#             branch; its branch rules (main, agent/**) are listed when there
#   template  bifrost/repo-template, when there: a template repository
#
# Prints one ok or FAIL line per item and exits 1 on any FAIL. It reads with
# the admin token from Secret cicd/gitea-bootstrap (lib.sh: port-forward,
# token in a header, no proxy, no redirect) and changes nothing.
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
# shellcheck source=lib.sh
source "$HERE/lib.sh"
OWNER_LOGIN="${OWNER_LOGIN:-weitingzhao}"
gitea_connect
work="$(mktemp -d)"
trap 'gitea_cleanup; rm -rf "${work}"' EXIT

get() { # NAME PATH — the answer into a file, or a note that it was not readable
  gitea_api GET "$2" > "${work}/$1.json" 2> "${work}/$1.err" || echo null > "${work}/$1.json"
}

get mbp "/users/bifrost-mbp"
get a06 "/users/agentd-agent-06"
get a06stg "/users/agentd-agent-06-stg"
get teams "/orgs/${GITEA_ORG}/teams?limit=50"
for name in maintainers agentd-write; do
  id="$(python3 -c 'import json,sys; t=[x for x in (json.load(open(sys.argv[1])) or []) if x.get("name")==sys.argv[2]]; print(t[0]["id"] if t else "")' "${work}/teams.json" "${name}")"
  if [[ -n "${id}" ]]; then get "members-${name}" "/teams/${id}/members?limit=50"; else echo null > "${work}/members-${name}.json"; fi
done
get probe "/repos/${GITEA_ORG}/primary-probe"
get probe-main "/repos/${GITEA_ORG}/primary-probe/branches/main"
get probe-branches "/repos/${GITEA_ORG}/primary-probe/branches?limit=50"
get probe-rules "/repos/${GITEA_ORG}/primary-probe/branch_protections"
get template "/repos/${GITEA_ORG}/repo-template"

python3 - "${work}" "${OWNER_LOGIN}" "${GITEA_ORG}" << 'PY'
import json, os, sys
work, owner, org = sys.argv[1:4]
def load(name):
    try:
        return json.load(open(os.path.join(work, name + ".json")))
    except ValueError:
        return None
fails = 0
def report(ok, what, detail=""):
    global fails
    print("%-5s %s%s" % ("ok" if ok else "FAIL", what, (" — " + detail) if detail else ""))
    fails += not ok

mbp = load("mbp")
report(isinstance(mbp, dict) and mbp.get("login") == "bifrost-mbp" and not mbp.get("is_admin"),
       "account bifrost-mbp, not an administrator", "missing" if not mbp else ("IS an administrator" if mbp.get("is_admin") else ""))
for key, login in (("a06", "agentd-agent-06"), ("a06stg", "agentd-agent-06-stg")):
    u = load(key)
    report(isinstance(u, dict) and u.get("login") == login, "account " + login, "" if u else "missing")

teams = {t.get("name"): t for t in (load("teams") or []) if isinstance(t, dict)}
def team(name, members, other_units):
    t = teams.get(name)
    if not t:
        report(False, "team %s/%s" % (org, name), "missing")
        return
    units = t.get("units_map") or {}
    problems = []
    if not t.get("includes_all_repositories"):
        problems.append("not all repositories")
    if str(t.get("permission")) in ("admin", "owner"):
        problems.append("permission is %s" % t.get("permission"))
    if units.get("repo.code") != "write":
        problems.append("Code is %s, not write" % units.get("repo.code"))
    for unit, level in sorted(units.items()):
        if unit in ("repo.code", "repo.ext_issues", "repo.ext_wiki"):
            continue
        if other_units == "none" and level != "none":
            problems.append("%s is %s, not none" % (unit, level))
        if other_units == "at most read" and level not in ("none", "read"):
            problems.append("%s is %s" % (unit, level))
    report(not problems, "team %s/%s: all repositories, Code write, other units %s" % (org, name, other_units), "; ".join(problems))
    got = sorted(m.get("login") for m in (load("members-" + name) or []) if isinstance(m, dict))
    report(got == sorted(members), "team %s/%s members %s" % (org, name, ", ".join(sorted(members))), "" if got == sorted(members) else "has: " + (", ".join(got) or "nobody"))
team("maintainers", [owner, "bifrost-mbp"], "at most read")
team("agentd-write", ["agentd-agent-06", "agentd-agent-06-stg"], "none")

probe = load("probe")
if isinstance(probe, dict):
    report(probe.get("mirror") is False and probe.get("private") is True, "repository %s/primary-probe: regular and private" % org,
           "" if probe.get("mirror") is False and probe.get("private") is True else "mirror %s, private %s" % (probe.get("mirror"), probe.get("private")))
    branches = sorted(b.get("name") for b in (load("probe-branches") or []) if isinstance(b, dict))
    report(isinstance(load("probe-main"), dict), "repository %s/primary-probe has a main branch" % org,
           "" if isinstance(load("probe-main"), dict) else "branches: %s; default branch %s" % (", ".join(branches) or "none (empty repository)", probe.get("default_branch")))
    rules = sorted(r.get("rule_name") or r.get("branch_name") for r in (load("probe-rules") or []) if isinstance(r, dict))
    print("info  primary-probe branch rules: %s" % (", ".join(rules) or "none yet (section 1 part 2)"))
else:
    report(False, "repository %s/primary-probe", "missing")
tpl = load("template")
if isinstance(tpl, dict):
    report(tpl.get("template") is True and tpl.get("mirror") is False, "repository %s/repo-template is a template" % org)
else:
    print("info  repository %s/repo-template: not made yet (section 1 part 2)" % org)
print("== section 1 as far as it goes: all as expected" if not fails else "== %d FAIL line(s)" % fails)
sys.exit(1 if fails else 0)
PY
