#!/bin/sh
# Check a normalized manifest List against actuation-policy.yaml.
# Usage: apply-manifest-check.sh <policy.yaml> <normalized.json> <objects.json>
# normalized.json is the JSON from `kubectl create --dry-run=client -o json`,
# slurped into one List. This script and `kubectl apply` must use that same file.
# Prints the highest tier on stdout.
set -eu

policy=${1:?policy}
rendered=${2:?normalized-json}
out=${3:?objects-out}
KUBECTL=${KUBECTL:-kubectl}

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
rows=$(mktemp)
trap 'rm -f "$ns_tiers" "$kinds" "$cicd_kinds" "$rows"' EXIT

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
  a && s && $0 ~ /group:/ {
    g=$0
    sub(/.*group: */, "", g)
    gsub(/"/, "", g)
    gsub(/ /, "", g)
    if (g=="") g="-"
    group=g
  }
  a && s && $0 ~ /^      kind:/ {print group, $2}
' "$policy" > "$kinds"

awk '
  $0 ~ /^apply:/ {a=1; next}
  a && $0 ~ /^[^ #]/ {a=0}
  a && $0 ~ /^  cicd_resources:/ {s=1; next}
  a && s && $0 ~ /^  [^ ]/ {s=0}
  a && s && $0 ~ /group:/ {
    g=$0
    sub(/.*group: */, "", g)
    gsub(/"/, "", g)
    gsub(/ /, "", g)
    if (g=="") g="-"
    group=g
  }
  a && s && $0 ~ /^      kind:/ {print group, $2}
' "$policy" > "$cicd_kinds"

jq -r '
  def group:
    if ((.apiVersion // "") | contains("/")) then (.apiVersion | split("/")[0]) else "" end;
  def walk:
    if type == "array" then .[] | walk
    elif (.kind == "List") then (.items // [])[] | walk
    else . end;
  [walk] | .[] |
    [
      (.metadata.namespace // ""),
      (.kind // ""),
      (.metadata.name // ""),
      group
    ] | @tsv
' "$rendered" > "$rows"

if [ ! -s "$rows" ]; then
  echo "normalized manifest has no objects" >&2
  exit 1
fi

tier_of() {
  awk -v ns="$1" '$1 == ns {print $2; found=1} END {exit !found}' "$ns_tiers"
}

kind_ok() {
  file=$kinds
  if [ "$1" = "$delivery_ns" ]; then
    file=$cicd_kinds
  fi
  awk -v group="$2" -v kind="$3" '$1 == group && $2 == kind {found=1} END {exit !found}' "$file"
}

rank_of() {
  case "$1" in
    B) printf 1 ;;
    C) printf 2 ;;
    D) printf 3 ;;
    X) printf 4 ;;
    *) printf 0 ;;
  esac
}

json=$(mktemp)
: > "$json"
first=1
highest=B
count=0

while IFS=$(printf '\t') read -r ns kind name group; do
  [ -n "$kind" ] || kind=""
  count=$((count + 1))
  if [ -z "$kind" ] || [ -z "$name" ]; then
    echo "object is missing kind or name" >&2
    exit 1
  fi
  if [ "$kind" = "List" ]; then
    echo "List was not expanded; refusing" >&2
    exit 1
  fi
  if [ -z "$ns" ]; then
    echo "object ${kind}/${name} has no namespace; cluster-scoped objects are refused" >&2
    exit 1
  fi
  tracked=$("$KUBECTL" get "$kind" "$name" -n "$ns" -o jsonpath='{.metadata.annotations.argocd\.argoproj\.io/tracking-id}' 2>/dev/null || true)
  if [ -n "$tracked" ]; then
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
  if [ -z "$group" ]; then
    group=-
  fi
  if ! kind_ok "$ns" "$group" "$kind"; then
    echo "kind ${kind} (group ${group}) is not allowed in that namespace" >&2
    exit 1
  fi
  if [ "$(rank_of "$tier")" -gt "$(rank_of "$highest")" ]; then
    highest=$tier
  fi
  if [ "$first" -eq 0 ]; then
    printf ',' >> "$json"
  fi
  first=0
  jq -n --arg ns "$ns" --arg kind "$kind" --arg name "$name" --arg tier "$tier" \
    '{namespace:$ns,kind:$kind,name:$name,tier:$tier}' >> "$json"
done < "$rows"

if [ "$count" -eq 0 ]; then
  echo "normalized manifest has no objects" >&2
  exit 1
fi

{
  printf '['
  cat "$json"
  printf ']\n'
} > "$out"
rm -f "$json"
printf '%s\n' "$highest"
