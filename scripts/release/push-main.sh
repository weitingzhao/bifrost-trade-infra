#!/usr/bin/env bash
# Push a commit to a repo's main the way CI will judge it (TD-341).
#
#   push-main.sh [--no-lineage <reason>] [--skip-tests <reason>] <checkout> [<commit>]
#                                          <commit> defaults to the checkout's HEAD
#
# 1. The release window must be closed (release.sh window), checked again
#    right before the push.
# 2. The commit must fast-forward origin/main (fetched first).
# 3. Every commit of origin/main..<commit> carries its lineage, a Change-Id
#    and a Claude-Session trailer (TD-400), or the push is refused naming
#    each one that does not. --no-lineage <reason> pushes them anyway (the
#    Owner's own commits, say) and prints the reason with them.
# 4. For a repo whose CI runs the code-health ratchet, scan.sh runs on a
#    fresh worktree of exactly <commit> (not the working tree, which may hold
#    other sessions' edits), so a metric over its baseline (a file over 800
#    lines, say) is refused here instead of turning main red.
# 5. The repo's fast tests run on that same clean worktree (TD-413), and a
#    failure refuses the push: infra's pytest of scripts/release,
#    scripts/agentrt and scripts/agent-host; platform's go vet ./... and
#    go test of the packages origin/main..<commit> touches. Their exit code
#    is read as it is, never through a pipe (twice a pusher's pipe hid a red
#    test, LESSONS 186). --skip-tests <reason> skips them and prints why.
#    The worktree has the workspace's repositories beside it, as the tests
#    read them.
# 6. git push origin <commit>:refs/heads/main.
# 7. The repo's shared checkout in the workspace (<workspace>/<repo>, where
#    every session's MCP servers and dev builds run from) follows main
#    (TD-408): it is fast-forwarded to <commit> when it is on main with no
#    tracked changes, has the same origin and is not the checkout pushed
#    from; otherwise it is left as it is and the reason is said. The push has
#    happened by then: nothing here fails it, and nothing here waits on the
#    network or a hook.
#
# preflight.js refuses a direct `git push` to main, so this is the way an
# agent pushes main. The full suites and lint stay in the pusher's own
# routine and CI. The scan uses the baselines of the infra checkout this
# script lives in; CI uses infra main's.
set -euo pipefail

usage() {
  echo "usage: push-main.sh [--no-lineage <reason>] [--skip-tests <reason>] <checkout> [<commit>]" >&2
  exit 2
}
die() {
  echo "push-main: $*" >&2
  exit 1
}
NO_LINEAGE=""
SKIP_TESTS=""
args=()
while [[ $# -gt 0 ]]; do
  case "$1" in
    --no-lineage)
      [[ $# -ge 2 && -n "${2//[[:space:]]/}" ]] || die "--no-lineage needs a reason"
      NO_LINEAGE="$2"
      shift 2
      ;;
    --no-lineage=*)
      NO_LINEAGE="${1#--no-lineage=}"
      [[ -n "${NO_LINEAGE//[[:space:]]/}" ]] || die "--no-lineage needs a reason"
      shift
      ;;
    --skip-tests)
      [[ $# -ge 2 && -n "${2//[[:space:]]/}" ]] || die "--skip-tests needs a reason"
      SKIP_TESTS="$2"
      shift 2
      ;;
    --skip-tests=*)
      SKIP_TESTS="${1#--skip-tests=}"
      [[ -n "${SKIP_TESTS//[[:space:]]/}" ]] || die "--skip-tests needs a reason"
      shift
      ;;
    -*) usage ;;
    *)
      args+=("$1")
      shift
      ;;
  esac
done
[[ ${#args[@]} -ge 1 && ${#args[@]} -le 2 ]] || usage
DIR="${args[0]}"
REF="${args[1]:-HEAD}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
SCAN="${PUSH_MAIN_SCAN:-$HERE/../../agent-config/scripts/code-health/scan.sh}"
WINDOW="${PUSH_MAIN_WINDOW:-$HERE/release.sh}"
# The repos whose CI pipeline has a code-health task (k8s/cicd/tekton:
# pipeline-ci-platform, pipeline-ci-frontend, pipeline-ci-python,
# task-research-lint-test). Keep in step with those.
GATED=" bifrost-platform bifrost-trade-frontend bifrost-research bifrost-trade-api bifrost-trade-core bifrost-trade-worker "

top="$(git -C "$DIR" rev-parse --show-toplevel 2>/dev/null)" || die "$DIR is not a git checkout"
commit="$(git -C "$top" rev-parse --verify --quiet "$REF^{commit}")" || die "$REF is not a commit in $top"
url="$(git -C "$top" remote get-url origin)" || die "$top has no remote origin"
trimmed="${url%/}"
repo="$(basename "${trimmed%.git}")"
repo="${repo##*:}"

# github_repo <address> — the repository a GitHub address names, lower case;
# nothing for any other address. URL or scp form, any scheme, user or port,
# host in any case, trailing / and .git dropped. preflight.js githubRepoOf is
# the same function: both answer every input in
# agent-config/scripts/agent-guard/github-repo-cases.json alike (review 243
# A5, 244 item 9), so only printable ASCII is read (Python's and JS's regexes
# and case rules differ outside it), no regex flags, ASCII whitespace stripped.
github_repo() {
  python3 - "$1" <<'PY'
import re, sys
u = sys.argv[1].strip(" \t\n\r\f\v")
if re.search(r"[^\x20-\x7e]", u):
    sys.exit(0)
m = re.match(r"^[A-Za-z][A-Za-z0-9+.-]*://(?:[^@/]*@)?([^/:]+)(?::[0-9]*)?(/.*)?$", u)
if m:
    host, rest = m.group(1), m.group(2) or ""
else:
    m = re.match(r"^(?:[^@/:]+@)?([^/:]+):(.*)$", u)
    if not m:
        sys.exit(0)
    host, rest = m.group(1), m.group(2)
if host.lower() not in ("github.com", "www.github.com", "ssh.github.com"):
    sys.exit(0)
parts = [p for p in rest.split("/") if p]
if len(parts) >= 2:
    print(re.sub(r"\.[gG][iI][tT]$", "", parts[1]).lower())
PY
}

# A repository Gitea holds as its primary is pushed to Gitea; GitHub follows
# from the cluster (k8s/cicd/github-sync), never from here
# (CUT-gitea-primary-2026-10-17 step 0g). Every address the push would go to
# is checked, pushurl and pushInsteadOf included (review 243 A2).
PRIMARY_LIST="${PUSH_MAIN_PRIMARY_LIST:-$HERE/../../agent-config/gitea-primary.txt}"
if [[ -f "$PRIMARY_LIST" ]]; then
  primaries="$(sed -e 's/#.*//' -e 's/[[:space:]]//g' "$PRIMARY_LIST" | tr '[:upper:]' '[:lower:]')"
  if [[ -n "$primaries" ]]; then
    push_urls="$(git -C "$top" remote get-url --push --all origin)" || die "cannot read the push addresses of origin in $top"
    repo_lc="$(printf '%s' "$repo" | tr '[:upper:]' '[:lower:]')"
    while IFS= read -r push_url; do
      [[ -n "$push_url" ]] || continue
      if LC_ALL=C grep -q -- '[^ -~]' <<<"$push_url"; then
        die "origin of $repo pushes to an address with characters outside printable ASCII; cannot tell where it goes"
      fi
      gh="$(github_repo "$push_url")"
      [[ -n "$gh" ]] || continue
      if grep -qxF -- "$gh" <<<"$primaries" || grep -qxF -- "$repo_lc" <<<"$primaries"; then
        die "$repo has Gitea as its primary (agent-config/gitea-primary.txt) but origin pushes to $push_url: point origin at Gitea and push there; GitHub follows from the cluster"
      fi
    done <<<"$push_urls"
  fi
fi

window() {
  local rc=0
  "$WINDOW" window || rc=$?
  case "$rc" in
    0) ;;
    1) die "the release window is open; nothing pushed" ;;
    *) die "cannot read the release window (exit $rc); nothing pushed" ;;
  esac
}

# The workspace the shared checkouts are in: the parent of this infra
# repository's main worktree (its shared checkout, wherever this script runs
# from: a lane's worktree shares it).
shared_root() {
  if [[ -n "${PUSH_MAIN_SHARED_ROOT:-}" ]]; then
    printf '%s\n' "$PUSH_MAIN_SHARED_ROOT"
    return
  fi
  local main
  main="$(git -C "$HERE" worktree list --porcelain 2>/dev/null | sed -n '1s/^worktree //p')"
  [[ -n "$main" ]] && dirname "$main"
}

# follow — the repo's shared checkout follows main to $commit (TD-408), or
# is left as it is with the reason. It never fails the push, and it waits on
# nothing beyond this machine (review td400-1 B2): a commit the shared
# checkout lacks is fetched from the checkout pushed from (a lane's worktree
# shares its objects already), and no hook runs.
follow() {
  local root shared said head branch out
  root="$(shared_root || true)"
  if [[ -z "$root" ]]; then
    echo "push-main: the workspace of the shared checkouts is not known; no shared checkout followed"
    return 0
  fi
  shared="$root/$repo"
  said="push-main: shared checkout $shared"
  if [[ ! -d "$shared" ]] || [[ "$(git -C "$shared" rev-parse --show-toplevel 2>/dev/null)" != "$(cd "$shared" && pwd -P)" ]]; then
    echo "$said: none there; nothing followed"
    return 0
  fi
  if [[ "$(git -C "$shared" remote get-url origin 2>/dev/null)" != "$url" ]]; then
    echo "$said: its origin is not $url; left as it is"
    return 0
  fi
  if [[ "$(cd "$shared" && pwd -P)" == "$(cd "$top" && pwd -P)" ]]; then
    head="$(git -C "$shared" rev-parse --verify --quiet HEAD 2>/dev/null || true)"
    if [[ "$head" == "$commit" ]]; then
      echo "$said: is the checkout pushed from, at $commit"
    else
      echo "$said: is the checkout pushed from; left as it is (its HEAD is ${head:0:12}, not $commit)"
    fi
    return 0
  fi
  if ! git -C "$shared" cat-file -e "$commit^{commit}" 2>/dev/null; then
    git -C "$shared" -c core.hooksPath=/dev/null fetch --quiet --no-tags "$top" "$commit" >/dev/null 2>&1 || true
  fi
  # Every check after the fetch, right before the merge (review td400-1 A2:
  # what held before a fetch may not hold after it).
  head="$(git -C "$shared" rev-parse --verify --quiet HEAD 2>/dev/null || true)"
  branch="$(git -C "$shared" symbolic-ref --quiet --short HEAD 2>/dev/null || true)"
  if [[ "$branch" != "main" ]]; then
    echo "$said: not on main; left as it is"
    return 0
  fi
  if [[ "$head" == "$commit" ]]; then
    echo "$said: already at $commit"
    return 0
  fi
  if [[ -n "$(git -C "$shared" status --porcelain --untracked-files=no 2>/dev/null || echo unreadable)" ]]; then
    echo "$said: has tracked changes; left as it is at ${head:0:12}"
    return 0
  fi
  if ! git -C "$shared" cat-file -e "$commit^{commit}" 2>/dev/null; then
    echo "$said: cannot get $commit from $top; left as it is at ${head:0:12}"
    return 0
  fi
  if ! git -C "$shared" merge-base --is-ancestor HEAD "$commit" 2>/dev/null; then
    echo "$said: its main has commits that are not on main; left as it is at ${head:0:12}"
    return 0
  fi
  # --no-overwrite-ignore: an ignored file the commit adds is a session's own
  # (review td400-1 A1); the merge stops instead of replacing it.
  if out="$(git -C "$shared" -c core.hooksPath=/dev/null merge --ff-only --no-overwrite-ignore --quiet "$commit" 2>&1)"; then
    echo "$said: fast-forwarded to $commit"
  else
    echo "$said: the fast-forward failed; left as it is at ${head:0:12}: $(tr '\n' ' ' <<<"$out")"
  fi
  return 0
}

window

git -C "$top" fetch --quiet origin main
git -C "$top" merge-base --is-ancestor origin/main "$commit" ||
  die "$commit does not fast-forward origin/main of $repo; rebase onto it first"
if [[ "$(git -C "$top" rev-parse origin/main)" == "$commit" ]]; then
  echo "push-main: $repo main is already $commit"
  follow
  exit 0
fi

# Every commit the push adds carries its lineage (TD-400): a Change-Id and a
# Claude-Session trailer, which the commit hooks write (scripts/git-hooks);
# a worktree of a husky repository runs no hook, so its commits carry them
# only when written by hand. A cherry-pick or rebase keeps them.
# The log is read whole first: a git log that fails refuses the push
# (review td400-1 B1), rather than reading as no commit at all.
lineage="$(git -C "$top" log --format='%h%x1f%(trailers:key=Change-Id,valueonly,separator=%x2C)%x1f%(trailers:key=Claude-Session,valueonly,separator=%x2C)%x1f%s' "origin/main..$commit")" ||
  die "cannot read the trailers of origin/main..$commit in $top; nothing pushed"
missing=()
while IFS=$'\x1f' read -r short change session subject; do
  [[ -n "$short" ]] || continue
  lacks=()
  [[ -n "${change//[[:space:],]/}" ]] || lacks+=("Change-Id")
  [[ -n "${session//[[:space:],]/}" ]] || lacks+=("Claude-Session")
  if [[ ${#lacks[@]} -gt 0 ]]; then
    missing+=("$short (no ${lacks[*]}) $subject")
  fi
done <<<"$lineage"
if [[ ${#missing[@]} -gt 0 ]]; then
  if [[ -z "$NO_LINEAGE" ]]; then
    {
      echo "push-main: ${#missing[@]} commit(s) of origin/main..$commit carry no lineage (Change-Id and Claude-Session trailers); nothing pushed:"
      printf '  %s\n' "${missing[@]}"
      echo "  add them (git commit --amend --trailer, or rebase), or push with --no-lineage <reason> for commits made outside a Claude session"
    } >&2
    exit 1
  fi
  echo "push-main: --no-lineage: $NO_LINEAGE"
  echo "push-main: pushed without lineage, by that reason:"
  printf '  %s\n' "${missing[@]}"
elif [[ -n "$NO_LINEAGE" ]]; then
  echo "push-main: --no-lineage given ($NO_LINEAGE), but every commit carries its lineage"
fi

# The repos with fast tests here (TD-413); the others have none yet.
has_tests() {
  [[ "$repo" == "bifrost-trade-infra" || "$repo" == "bifrost-platform" ]]
}

# neighbours <dir> — the workspace's repositories beside the clean worktree
# in <dir>, as the tests find them in the workspace (platform's read
# ../bifrost-trade-infra and ../bifrost-ui): infra is the checkout this
# script lives in, the others the workspace's own; links only.
neighbours() {
  local dir="$1" root entry name
  [[ "$repo" == "bifrost-trade-infra" ]] || ln -s "$(cd "$HERE/../.." && pwd -P)" "$dir/bifrost-trade-infra"
  root="$(shared_root || true)"
  [[ -n "$root" && -d "$root" ]] || return 0
  for entry in "$root"/bifrost-* "$root/scripts"; do
    name="$(basename "$entry")"
    [[ -e "$entry" && "$name" != "$repo" && ! -e "$dir/$name" ]] || continue
    ln -s "$entry" "$dir/$name"
  done
}

# run_tests <worktree> — the repo's fast tests in the clean worktree, their
# exit code as it is.
run_tests() {
  local tree="$1" rc=0 p
  case "$repo" in
    bifrost-trade-infra)
      local paths=()
      for p in scripts/release scripts/agentrt scripts/agent-host; do
        [[ -d "$tree/$p" ]] && paths+=("$p")
      done
      if [[ ${#paths[@]} -eq 0 ]]; then
        echo "push-main: none of the test directories of $repo is there; no tests run"
        return 0
      fi
      echo "push-main: tests of $repo: python3 -m pytest -q ${paths[*]}"
      (cd "$tree" && python3 -m pytest -q -p no:cacheprovider "${paths[@]}") || rc=$?
      ;;
    bifrost-platform)
      if [[ ! -f "$tree/api/go.mod" ]]; then
        echo "push-main: $repo has no api/go.mod; no tests run"
        return 0
      fi
      echo "push-main: tests of $repo: go vet ./..."
      (cd "$tree/api" && go vet ./...) || rc=$?
      [[ "$rc" -eq 0 ]] || return "$rc"
      # A touched directory is tested when it is a package of this build
      # (go list ./..., as vet saw it): one whose files build constraints
      # all exclude is not (review td413-1 B1).
      local touched listed moddir dirs=() file dir
      touched="$(git -C "$top" diff --name-only "origin/main..$commit" -- 'api/*.go')" || return 1
      listed="$(cd "$tree/api" && go list -f '{{.Dir}}' ./...)" || return 1
      moddir="$(cd "$tree/api" && go list -m -f '{{.Dir}}')" || return 1
      while IFS= read -r file; do
        [[ -n "$file" ]] || continue
        dir="$(dirname "$file")"
        grep -qxF -- "$moddir${dir#api}" <<<"$listed" || continue
        dir=".${dir#api}/"
        [[ " ${dirs[*]:-} " == *" $dir "* ]] || dirs+=("$dir")
      done <<<"$touched"
      if [[ ${#dirs[@]} -eq 0 ]]; then
        echo "push-main: no Go package of $repo is touched; go vet only"
        return 0
      fi
      [[ -n "${AGENTRT_TEST_PG:-}" ]] || echo "push-main: AGENTRT_TEST_PG is not set: the database tests skip"
      echo "push-main: tests of $repo: go test ${dirs[*]}"
      (cd "$tree/api" && go test "${dirs[@]}") || rc=$?
      ;;
  esac
  return "$rc"
}

gated=false
[[ "$GATED" == *" $repo "* ]] && gated=true
testing=false
if has_tests && [[ -z "$SKIP_TESTS" ]]; then
  testing=true
fi
if $gated || $testing; then
  tmp="$(mktemp -d "${TMPDIR:-/tmp}/push-main.XXXXXX")"
  cleanup() {
    git -C "$top" worktree remove --force "$tmp/$repo" >/dev/null 2>&1 || true
    find "$tmp" -mindepth 1 -maxdepth 1 -type l -delete 2>/dev/null || true
    rmdir "$tmp" 2>/dev/null || true
  }
  trap cleanup EXIT
  git -C "$top" -c core.hooksPath=/dev/null worktree add --quiet --detach "$tmp/$repo" "$commit"
fi
if $gated; then
  rc=0
  bash "$SCAN" --root "$tmp" --repo "$repo" || rc=$?
  [[ "$rc" -eq 0 ]] || die "code-health refused $commit of $repo (exit $rc); nothing pushed"
else
  echo "push-main: $repo has no code-health task in CI; not scanned"
fi
if $testing; then
  neighbours "$tmp"
  started=$SECONDS
  rc=0
  run_tests "$tmp/$repo" || rc=$?
  [[ "$rc" -eq 0 ]] || die "the tests of $repo failed on $commit (exit $rc); nothing pushed"
  echo "push-main: the tests of $repo passed ($((SECONDS - started)) s)"
elif [[ -n "$SKIP_TESTS" ]]; then
  if has_tests; then
    echo "push-main: --skip-tests: $SKIP_TESTS; the tests of $repo were not run"
  else
    echo "push-main: --skip-tests given ($SKIP_TESTS), but $repo has no fast tests here"
  fi
else
  echo "push-main: $repo has no fast tests here; none run"
fi

window
git -C "$top" push origin "$commit:refs/heads/main"
echo "push-main: pushed $commit to $repo main"
follow
