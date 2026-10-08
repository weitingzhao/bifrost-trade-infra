#!/usr/bin/env bash
# release.sh policy verify (LANE-RP): a good signature passes; tampered, foreign-key,
# expired, unsigned-anchor and missing files fail. No cluster. The key is a throwaway
# ed25519 made in a temp dir and deleted on exit; it is not the Owner's key.
set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
INFRA="$(cd "${HERE}/../.." && pwd)"
RELEASE="${HERE}/release.sh"
TMP="$(mktemp -d)"
trap 'rm -rf "${TMP}"' EXIT
export BIFROST_RELEASE_HOME="${TMP}/home"
export BIFROST_RELEASE_ALLOWED_SIGNERS="${TMP}/allowed_signers"

fail=0 passed=0
expect() {  # expect <exit code> <name> <command...>
  local want="$1" name="$2" rc=0
  shift 2
  "$@" >"${TMP}/out.txt" 2>&1 || rc=$?
  if [[ "${rc}" -eq "${want}" ]]; then
    passed=$((passed + 1))
  else
    fail=$((fail + 1))
    echo "FAIL ${name}: exit ${rc}, want ${want}"
    sed 's/^/    /' "${TMP}/out.txt"
  fi
}

ssh-keygen -q -t ed25519 -N '' -C test -f "${TMP}/key"
ssh-keygen -q -t ed25519 -N '' -C other -f "${TMP}/other"
printf 'owner namespaces="bifrost-release-policy,bifrost-release-unfreeze" %s\n' "$(cat "${TMP}/key.pub")" \
  >"${BIFROST_RELEASE_ALLOWED_SIGNERS}"

render() {  # render <dir> <now>
  mkdir -p "$1"
  python3 "${HERE}/policy_check.py" render \
    --template "${INFRA}/agent-config/work/release-approval/release-policy.draft.yaml" \
    --paths "${INFRA}/agent-config/release-policy/paths.json" --now "$2" --out "$1/policy.yaml" >/dev/null
}
sign_with() {  # sign_with <key> <dir>
  ssh-keygen -q -Y sign -f "$1" -n bifrost-release-policy "$2/policy.yaml"
  mv "$2/policy.yaml.sig" "$2/policy.sig"
}

now="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
render "${TMP}/good" "${now}"
sign_with "${TMP}/key" "${TMP}/good"
expect 0 "valid policy" "${RELEASE}" policy verify --policy "${TMP}/good/policy.yaml" --sig "${TMP}/good/policy.sig"
grep -q "valid          yes" "${TMP}/out.txt" || { fail=$((fail + 1)); echo "FAIL valid policy: no 'valid yes' line"; }

cp -R "${TMP}/good" "${TMP}/tampered"
python3 - "${TMP}/tampered/policy.yaml" <<'PY'
import json, sys
p = sys.argv[1]
d = json.load(open(p))
d["allow"].append("bifrost-deliver-prod")
open(p, "w").write(json.dumps(d, indent=2, sort_keys=True) + "\n")
PY
expect 1 "tampered policy" "${RELEASE}" policy verify --policy "${TMP}/tampered/policy.yaml" --sig "${TMP}/tampered/policy.sig"

render "${TMP}/foreign" "${now}"
sign_with "${TMP}/other" "${TMP}/foreign"
expect 1 "signed by another key" "${RELEASE}" policy verify --policy "${TMP}/foreign/policy.yaml" --sig "${TMP}/foreign/policy.sig"

render "${TMP}/expired" "2020-01-01T00:00:00Z"
sign_with "${TMP}/key" "${TMP}/expired"
expect 1 "expired policy" "${RELEASE}" policy verify --policy "${TMP}/expired/policy.yaml" --sig "${TMP}/expired/policy.sig"
grep -q "expired at 2020-01-08" "${TMP}/out.txt" || { fail=$((fail + 1)); echo "FAIL expired policy: reason not printed"; }

printf '# no key yet\n' >"${TMP}/empty_signers"
expect 1 "no trust anchor" env BIFROST_RELEASE_ALLOWED_SIGNERS="${TMP}/empty_signers" \
  "${RELEASE}" policy verify --policy "${TMP}/good/policy.yaml" --sig "${TMP}/good/policy.sig"

expect 2 "missing files" "${RELEASE}" policy verify --policy "${TMP}/nowhere/policy.yaml"

mkdir -p "${BIFROST_RELEASE_HOME}/policy"
ln -s "${TMP}/good" "${BIFROST_RELEASE_HOME}/policy/current"
expect 0 "default path is the last signed policy" "${RELEASE}" policy verify

# ── release.sh merge through the policy gate: a fake kubectl, a local bare origin ──
WS="${TMP}/ws"
mkdir -p "${TMP}/bin" "${WS}" "${TMP}/cm"
cat >"${TMP}/bin/kubectl" <<'SH'
#!/usr/bin/env bash
# get configmap <name> -o json -> $FAKE_CM/<name>.json (absent = NotFound); pipelineruns -> empty list
args=" $* "
if [[ "${args}" == *" get configmap "* ]]; then
  name="$(sed -E 's/.* get configmap ([^ ]+) .*/\1/' <<<"${args}")"
  if [[ -f "${FAKE_CM}/${name}.json" ]]; then cat "${FAKE_CM}/${name}.json"; exit 0; fi
  echo "Error from server (NotFound): configmaps \"${name}\" not found" >&2; exit 1
fi
if [[ "${args}" == *" get pipelineruns "* ]]; then echo '{"items": []}'; exit 0; fi
echo "fake kubectl: unexpected: $*" >&2; exit 9
SH
chmod +x "${TMP}/bin/kubectl"
touch "${TMP}/kubeconfig"
git init -q --bare "${TMP}/origin.git"
git clone -q "${TMP}/origin.git" "${WS}/bifrost-trade-infra" 2>/dev/null
G=(git -C "${WS}/bifrost-trade-infra" -c user.name=t -c user.email=t@example.invalid)
echo a >"${WS}/bifrost-trade-infra/README.md"
"${G[@]}" add README.md && "${G[@]}" commit -q -m one && "${G[@]}" push -q origin HEAD:refs/heads/main
"${G[@]}" fetch -q origin
echo b >"${WS}/bifrost-trade-infra/README.md"
"${G[@]}" commit -q -am docs
docs_sha="$("${G[@]}" rev-parse HEAD)"
mkdir -p "${WS}/bifrost-trade-infra/scripts/release"
echo x >"${WS}/bifrost-trade-infra/scripts/release/release.sh"
"${G[@]}" add scripts && "${G[@]}" commit -q -m anchor
anchor_sha="$("${G[@]}" rev-parse HEAD)"

python3 - "${TMP}/good" "${BIFROST_RELEASE_ALLOWED_SIGNERS}" "${TMP}/cm" <<'PY'
import json, sys
src, signers, out = sys.argv[1:4]
data = {"policy.yaml": open(f"{src}/policy.yaml").read(), "policy.sig": open(f"{src}/policy.sig").read(),
        "allowed_signers": open(signers).read()}
json.dump({"data": data}, open(f"{out}/bifrost-release-policy.json", "w"))
json.dump({"data": {"frozen": "false"}}, open(f"{out}/bifrost-release-freeze.json", "w"))
PY

merge() {
  env PATH="${TMP}/bin:${PATH}" FAKE_CM="${TMP}/cm" KUBECONFIG="${TMP}/kubeconfig" \
    BIFROST_WORKSPACE_ROOT="${WS}" BIFROST_RELEASE_DIR="${TMP}/snap" BIFROST_RELEASE_WINDOW_PUBLISH=0 \
    "${RELEASE}" merge bifrost-trade-infra "$@"
}
origin_main() { git -C "${TMP}/origin.git" rev-parse main; }

expect 3 "merge: anchor path waits" merge "${anchor_sha}"
grep -q "no_trust_anchor_change" "${TMP}/out.txt" || { fail=$((fail + 1)); echo "FAIL merge anchor: reason missing"; }
expect 0 "merge: clean docs commit auto-approved" merge "${docs_sha}"
grep -q "auto-approved by rp-" "${TMP}/out.txt" || { fail=$((fail + 1)); echo "FAIL merge docs: no auto-approved line"; }
[[ "$(origin_main)" == "${docs_sha}" ]] || { fail=$((fail + 1)); echo "FAIL merge docs: main not pushed"; }

python3 -c 'import json,sys; json.dump({"data": {"frozen": "true", "reason": "test", "frozen_at": "2026-10-08T00:00:00Z"}}, open(sys.argv[1], "w"))' \
  "${TMP}/cm/bifrost-release-freeze.json"
expect 3 "merge: frozen waits even with --owner-approved" merge "${anchor_sha}" --owner-approved "test"
[[ "$(origin_main)" == "${docs_sha}" ]] || { fail=$((fail + 1)); echo "FAIL frozen merge pushed"; }

python3 -c 'import json,sys; json.dump({"data": {"frozen": "false"}}, open(sys.argv[1], "w"))' "${TMP}/cm/bifrost-release-freeze.json"
rm -f "${BIFROST_RELEASE_HOME}/freeze-seen"
rm -f "${TMP}/cm/bifrost-release-policy.json"
expect 3 "merge: no policy waits" merge "${anchor_sha}"
expect 0 "merge: --owner-approved outside the policy" merge "${anchor_sha}" --owner-approved "Owner said yes in chat"
[[ "$(origin_main)" == "${anchor_sha}" ]] || { fail=$((fail + 1)); echo "FAIL owner-approved merge not pushed"; }
[[ ! -f "${BIFROST_RELEASE_HOME}/window.json" ]] || { fail=$((fail + 1)); echo "FAIL the window was left open"; }

echo "test_release_policy: ${passed} passed, ${fail} failed"
[[ "${fail}" -eq 0 ]]
