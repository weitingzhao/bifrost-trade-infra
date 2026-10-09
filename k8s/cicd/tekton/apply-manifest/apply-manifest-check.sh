#!/bin/sh
# Check a rendered manifest against actuation-policy.yaml.
# Usage: apply-manifest-check.sh <policy.yaml> <rendered.yaml> <objects.json>
# Prints the highest tier on stdout. Refuses cluster-scoped objects, Argo-tracked
# objects, a Deployment whose name is the policy daemon_deployment, unknown
# namespaces, and kinds the policy does not list for that namespace.
set -eu

policy=${1:?policy}
rendered=${2:?rendered}
out=${3:?objects-out}

delivery_ns=$(awk '
  $0 ~ /^delivery:/ {d=1; next}
  d && $0 ~ /^[^ #]/ {d=0}
  d && $0 ~ /^  namespace:/ {print $2; exit}
' "$policy")
daemon=$(awk '
  $0 ~ /^apply:/ {a=1; next}
  a && $0 ~ /^[^ #]/ {a=0}
  a && $0 ~ /^  daemon_deployment:/ {print $2; exit}
' "$policy")

ns_tiers=$(mktemp)
kinds=$(mktemp)
cicd_kinds=$(mktemp)
trap 'rm -f "$ns_tiers" "$kinds" "$cicd_kinds"' EXIT

awk '
  $0 ~ /^apply:/ {a=1; next}
  a && $0 ~ /^[^ #]/ {a=0}
  a && $0 ~ /^  namespaces:/ {n=1; next}
  a && n && $0 ~ /^  [^ ]/ {n=0}
  a && n && $0 ~ /^    [A-Za-z0-9]/ {
    key=$1
    sub(/:$/, "", key)
    print key, $2
  }
' "$policy" > "$ns_tiers"

awk '
  $0 ~ /^apply:/ {a=1; next}
  a && $0 ~ /^[^ #]/ {a=0}
  a && $0 ~ /^  resources:/ {s=1; next}
  a && s && $0 ~ /^  [^ ]/ {s=0}
  a && s && $0 ~ /^      kind:/ {print $2}
' "$policy" > "$kinds"

awk '
  $0 ~ /^apply:/ {a=1; next}
  a && $0 ~ /^[^ #]/ {a=0}
  a && $0 ~ /^  cicd_resources:/ {s=1; next}
  a && s && $0 ~ /^  [^ ]/ {s=0}
  a && s && $0 ~ /^      kind:/ {print $2}
' "$policy" > "$cicd_kinds"

tier_of() {
  awk -v ns="$1" '$1 == ns {print $2; found=1} END {exit !found}' "$ns_tiers"
}

kind_ok() {
  file=$kinds
  if [ "$1" = "$delivery_ns" ]; then
    file=$cicd_kinds
  fi
  grep -qx "$2" "$file"
}

json=$(mktemp)
: > "$json"
first=1
highest=B

flush_doc() {
  doc=$1
  [ -s "$doc" ] || return 0
  kind=$(awk '/^kind:/{print $2; exit}' "$doc")
  [ -n "$kind" ] || return 0
  name=$(awk '/^metadata:/{m=1; next} m && /^[^ ]/{exit} m && /^  name:/{print $2; exit}' "$doc")
  ns=$(awk '/^metadata:/{m=1; next} m && /^[^ ]/{exit} m && /^  namespace:/{print $2; exit}' "$doc")
  if [ -z "$ns" ]; then
    echo "object ${kind}/${name} has no namespace; cluster-scoped objects are refused" >&2
    exit 1
  fi
  if grep -q 'argocd.argoproj.io/tracking-id' "$doc"; then
    echo "object ${ns}/${kind}/${name} is managed by Argo; use gitops_sync_app" >&2
    exit 1
  fi
  if [ "$kind" = "Deployment" ] && [ "$name" = "$daemon" ]; then
    echo "rendered Deployment ${name} is tier X and cannot be applied" >&2
    exit 1
  fi
  tier=$(tier_of "$ns") || {
    echo "namespace of ${kind}/${name} is not in the apply allow-list" >&2
    exit 1
  }
  if ! kind_ok "$ns" "$kind"; then
    echo "kind ${kind} is not allowed in that namespace" >&2
    exit 1
  fi
  case "$tier" in
    C|D|X) highest=$tier ;;
  esac
  if [ "$first" -eq 0 ]; then
    printf ',' >> "$json"
  fi
  first=0
  printf '{"namespace":"%s","kind":"%s","name":"%s","tier":"%s"}' "$ns" "$kind" "$name" "$tier" >> "$json"
}

current=$(mktemp)
: > "$current"
while IFS= read -r line || [ -n "${line}" ]; do
  case "$line" in
    ---*)
      flush_doc "$current"
      : > "$current"
      ;;
    *)
      printf '%s\n' "$line" >> "$current"
      ;;
  esac
done < "$rendered"
flush_doc "$current"
rm -f "$current"

{
  printf '['
  cat "$json"
  printf ']\n'
} > "$out"
rm -f "$json"
printf '%s\n' "$highest"
