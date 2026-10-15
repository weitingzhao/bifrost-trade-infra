#!/usr/bin/env bash
# rule.sh — the agent runtime's rules (design v5 §5.2; Owner 2026-10-14 「规则 A」).
#
#   rule.sh show    <rule_id>       [--env stg|prod]              the rule in force (none: the strictest default holds)
#   rule.sh check   <file.yaml>     [--env stg|prod]              what the platform reads from it; writes nothing
#   rule.sh sign    <file.yaml>     [--env stg|prod] [--key f]    Owner: check, sign, hand in
#   rule.sh tighten <file.yaml>     [--env stg|prod]              hand in a tightening, unsigned
#
# A rule is YAML (agent-config/agentrt-rules/README.md). sign first asks the
# platform to read the file as it would (POST /rules/{id}/check: the closed
# parser, the version after the one in force, whether it only tightens) and
# stops if it does not read; then `ssh-keygen -Y sign -n bifrost-agentrt-rule`
# with the Owner's key (the release-policy key: the platform trusts its
# compiled-in fingerprint, releasepolicy.OwnerKeyFingerprint); then hands the
# exact text and the signature to POST /rules/{id}/sign. The signature covers
# the file byte for byte: edit, then sign again.
#
# --env stg (the default) talks to the STG platform, prod to PROD. The token
# is PLATFORM_STG_OPERATOR_TOKEN or PLATFORM_PROD_OPERATOR_TOKEN, from the
# environment or bifrost-trade-infra/.env; it goes to curl in a mode-600
# config file, never on a command line.
#
# Exit: 0 done, 1 the platform refused or could not be reached, 2 usage.
set -euo pipefail

here="$(cd "$(dirname "$0")" && pwd)"
infra="$(cd "${here}/../.." && pwd)"
ENV_FILE="${ENV_FILE:-${infra}/.env}"
KEY="${BIFROST_RELEASE_KEY:-${HOME}/.ssh/bifrost_release_owner}"
NAMESPACE="bifrost-agentrt-rule"

die() { echo "rule.sh: $1" >&2; exit "${2:-1}"; }
usage() { sed -n '2,24p' "$0" | sed 's/^# \{0,1\}//'; exit 2; }

[[ $# -ge 2 ]] || usage
cmd="$1" arg="$2"
shift 2
env_name=stg
while [[ $# -gt 0 ]]; do
  case "$1" in
    --env) env_name="${2:?--env needs stg or prod}"; shift 2 ;;
    --key) KEY="${2:?--key needs a path}"; shift 2 ;;
    *) usage ;;
  esac
done
case "${env_name}" in
  stg) api="${PLATFORM_STG_API:-http://192.168.10.73:30878}"; token_key=PLATFORM_STG_OPERATOR_TOKEN ;;
  prod) api="${PLATFORM_PROD_API:-http://192.168.10.100:30876}"; token_key=PLATFORM_PROD_OPERATOR_TOKEN ;;
  *) die "--env is stg or prod" 2 ;;
esac

token() {
  local value="${!token_key:-}" line
  if [[ -z "${value}" && -f "${ENV_FILE}" ]]; then
    line="$(grep -E "^${token_key}=" "${ENV_FILE}" | tail -1 || true)"
    line="${line#*=}"; line="${line%\"}"; line="${line#\"}"
    value="${line}"
  fi
  [[ -n "${value}" ]] || die "missing ${token_key} (environment or ${ENV_FILE})" 2
  case "${value}" in *\"*|*$'\n'*|*$'\r'*) die "${token_key} cannot be passed to curl safely" 2 ;; esac
  printf '%s' "${value}"
}

# call METHOD PATH [BODY]: prints the response body; fails on anything but 200.
call() {
  local method="$1" path="$2" body="${3:-}" cfg out code
  cfg="$(mktemp)"; out="$(mktemp)"
  chmod 600 "${cfg}" "${out}"
  {
    printf 'header = "Authorization: Bearer %s"\n' "$(token)"
    printf 'header = "X-Bifrost-Session: rule-sh"\n'
    printf 'header = "Content-Type: application/json"\n'
    printf 'url = "%s/api/v1/agentrt%s"\n' "${api%/}" "${path}"
    printf 'request = "%s"\nsilent\nshow-error\noutput = "%s"\n' "${method}" "${out}"
  } >"${cfg}"
  if [[ -n "${body}" ]]; then
    code="$(curl --config "${cfg}" --write-out '%{http_code}' --data-binary @- <<<"${body}")" || { rm -f "${cfg}" "${out}"; die "${method} ${path}: no answer from ${api}"; }
  else
    code="$(curl --config "${cfg}" --write-out '%{http_code}')" || { rm -f "${cfg}" "${out}"; die "${method} ${path}: no answer from ${api}"; }
  fi
  rm -f "${cfg}"
  python3 -m json.tool "${out}" 2>/dev/null || cat "${out}"
  rm -f "${out}"
  [[ "${code}" == "200" ]] || die "${method} ${path}: HTTP ${code}"
}

rule_id_of() {
  local id
  # Everything after the first "rule_id:": ids have colons of their own
  # (job:verifier, standing-envelope:dev), so the line is not split on them.
  id="$(sed -n 's/^rule_id:[[:space:]]*//p' "$1" | head -n 1 | sed 's/[[:space:]]*$//')"
  [[ -n "${id}" ]] || die "$1 has no rule_id line" 2
  printf '%s' "${id}"
}

# body FILE [SIGFILE]: the JSON body with the file's exact text.
body() {
  python3 -c 'import json, sys
doc = {"text": open(sys.argv[1], encoding="utf-8").read()}
if len(sys.argv) > 2:
    doc["signature"] = open(sys.argv[2], encoding="utf-8").read()
print(json.dumps(doc))' "$@"
}

case "${cmd}" in
  show)
    call GET "/rules/${arg}" ;;
  check)
    [[ -f "${arg}" ]] || die "no file ${arg}" 2
    call POST "/rules/$(rule_id_of "${arg}")/check" "$(body "${arg}")" ;;
  sign)
    [[ -f "${arg}" ]] || die "no file ${arg}" 2
    [[ -f "${KEY}" ]] || die "no signing key at ${KEY} (ssh-keygen -t ed25519 -C bifrost-release-owner -f ${KEY})" 2
    id="$(rule_id_of "${arg}")"
    echo "== the platform reads ${arg} as:"
    call POST "/rules/${id}/check" "$(body "${arg}")"
    sig="${arg}.sig"
    rm -f "${sig}"
    echo "== signing ${arg} with ${KEY} (namespace ${NAMESPACE}; ssh-keygen asks for the passphrase or Touch ID)"
    ssh-keygen -Y sign -f "${KEY}" -n "${NAMESPACE}" "${arg}"
    echo "== handing it in"
    call POST "/rules/${id}/sign" "$(body "${arg}" "${sig}")" ;;
  tighten)
    [[ -f "${arg}" ]] || die "no file ${arg}" 2
    call POST "/rules/$(rule_id_of "${arg}")/tighten" "$(body "${arg}")" ;;
  *) usage ;;
esac
