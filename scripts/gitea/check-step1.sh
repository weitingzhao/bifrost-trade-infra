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
#             branch; once it has branch rules, exactly main (agent/** no
#             more since TD-383)
#   template  bifrost/repo-template, when there: a template repository, the
#             same branch rule, and a gitea webhook to the CI
#             EventListener (EL_URL): POST, json, push, active
#   tags      the tag rule * (user OWNER_LOGIN, team maintainers) on both,
#             where the API can read tag rules; Gitea 1.21 cannot, and part 4's
#             probe pushes a tag to primary-probe instead
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
get probe-tags "/repos/${GITEA_ORG}/primary-probe/tag_protections"
get template "/repos/${GITEA_ORG}/repo-template"
get template-rules "/repos/${GITEA_ORG}/repo-template/branch_protections"
get template-tags "/repos/${GITEA_ORG}/repo-template/tag_protections"
get template-hooks "/repos/${GITEA_ORG}/repo-template/hooks"

python3 - "${work}" "${OWNER_LOGIN}" "${GITEA_ORG}" "${EL_URL:-http://el-bifrost-ci.cicd.svc.cluster.local:8080}" << 'PY'
import json, os, sys
work, owner, org, el_url = sys.argv[1:5]
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
else:
    report(False, "repository %s/primary-probe", "missing")

def branch_rules(repo, name):
    rules = sorted(r.get("rule_name") or r.get("branch_name") or "" for r in (load(name) or []) if isinstance(r, dict))
    if not rules:
        print("info  %s branch rules: none yet (section 1 part 2)" % repo)
    else:
        # agent/** is no longer protected (TD-383: the runtime deletes attempt branches)
        report(rules == ["main"], "%s/%s branch rules: main" % (org, repo), "" if rules == ["main"] else "has: " + ", ".join(rules))

def tag_rules(repo, name):
    rules = load(name)
    if not isinstance(rules, list):
        # Gitea 1.21 has no API for tag rules; section 1 part 4's probe pushes a tag to primary-probe.
        print("info  %s tag rules: not readable through this Gitea's API" % repo)
        return
    star = [r for r in rules if isinstance(r, dict) and r.get("name_pattern") == "*"]
    users = sorted(star[0].get("whitelist_usernames") or []) if star else []
    teams = sorted(star[0].get("whitelist_teams") or []) if star else []
    ok = users == [owner] and teams == ["maintainers"]
    report(ok, "%s/%s tag rule *: user %s and team maintainers" % (org, repo, owner),
           "" if ok else ("no * rule" if not star else "users %s; teams %s" % (", ".join(users) or "none", ", ".join(teams) or "none")))

def ci_hook():
    hooks = [h for h in (load("template-hooks") or []) if isinstance(h, dict)]
    ours = [h for h in hooks if (h.get("config") or {}).get("url", "").rstrip("/") == el_url.rstrip("/")]
    if not ours:
        urls = ", ".join((h.get("config") or {}).get("url", "?") for h in hooks)
        report(False, "%s/repo-template webhook to %s" % (org, el_url), "has: " + (urls or "no webhooks"))
        return
    h, problems = ours[0], []
    config = h.get("config") or {}
    if h.get("type") != "gitea":
        problems.append("type %s, not gitea" % h.get("type"))
    if not h.get("active"):
        problems.append("not active")
    if config.get("content_type") != "json":
        problems.append("content type %s, not json" % config.get("content_type"))
    if (config.get("http_method") or "post").lower() != "post":
        problems.append("method %s, not POST" % config.get("http_method"))
    if "push" not in (h.get("events") or []):
        problems.append("no push event (has: %s)" % ", ".join(h.get("events") or []))
    report(not problems, "%s/repo-template webhook to %s: gitea, POST, json, push, active" % (org, el_url), "; ".join(problems))

if isinstance(probe, dict):
    branch_rules("primary-probe", "probe-rules")
    tag_rules("primary-probe", "probe-tags")
tpl = load("template")
if isinstance(tpl, dict):
    report(tpl.get("template") is True and tpl.get("mirror") is False, "repository %s/repo-template is a template" % org)
    branch_rules("repo-template", "template-rules")
    tag_rules("repo-template", "template-tags")
    ci_hook()
else:
    print("info  repository %s/repo-template: not made yet (section 1 part 2)" % org)
print("== section 1 as far as it goes: all as expected" if not fails else "== %d FAIL line(s)" % fails)
sys.exit(1 if fails else 0)
PY
