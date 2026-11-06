#!/bin/sh
# Run only after apply-manifest-check.sh has validated the normalized List.
# apply builds the same ownership plan, then rechecks each migration immediately.
set -eu
mode=${1:?mode}
rendered=${2:?normalized List}
objects=${3:?objects result}
KUBECTL=${KUBECTL:-kubectl}
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT

classify() {
  ownership=ssa
  if [ "$eligible" = true ]; then
    "$KUBECTL" get "$kind" "$name" -n "$ns" --ignore-not-found -o json --show-managed-fields > "$work/live.json"
  fi
  if "$KUBECTL" apply --server-side --field-manager=bifrost-applier --dry-run=server -f "$work/object.json" > /dev/null 2> "$work/error"; then
    return
  fi
  # Only recognized SSA conflicts may enter the migration path. Errors such as
  # admission failures, missing permissions or transport failures remain errors.
  managers=$(sed -n 's/.*conflict with "\([^"]*\)".*/\1/p' "$work/error" | sort -u)
  if [ "$eligible" != true ] || [ -z "$managers" ]; then
    cat "$work/error" >&2
    return 1
  fi
  "$KUBECTL" get "$kind" "$name" -n "$ns" -o json --show-managed-fields > "$work/live.json"
  printf '%s\n' "$managers" > "$work/managers"
  while IFS= read -r manager; do
    if ! jq -e --arg m "$manager" '
      .metadata as $meta |
      [$meta.managedFields[]? | select(.manager == $m)] as $entries |
      ($entries | length > 0) and
      ($entries | all(
        .manager == "kubectl-client-side-apply" or
        .manager == "kubectl-last-applied" or
        (.manager == "kubectl" and .operation == "Update" and
         ($meta.annotations | has("kubectl.kubernetes.io/last-applied-configuration")))
      ))
    ' "$work/live.json" > /dev/null; then
      echo "refusing ownership conflict with manager ${manager} on ${ns}/${kind}/${name}" >&2
      return 1
    fi
  done < "$work/managers"
  ownership=migrate
}

jq '. | map(. + {ownership:"ssa"})' "$objects" > "$work/plan.json"
count=$(jq '.items | length' "$rendered")
i=0
while [ "$i" -lt "$count" ]; do
  jq --argjson i "$i" '.items[$i]' "$rendered" > "$work/object.json"
  ns=$(jq -r '.metadata.namespace' "$work/object.json")
  kind=$(jq -r '.kind' "$work/object.json")
  name=$(jq -r '.metadata.name' "$work/object.json")
  eligible=false
  # The policy checker has already verified group/kind against cicd_resources.
  case "$ns/$kind" in
    cicd/Pipeline|cicd/Task|cicd/TriggerTemplate|cicd/TriggerBinding|cicd/EventListener) eligible=true ;;
  esac
  classify
  jq --arg ns "$ns" --arg kind "$kind" --arg name "$name" --arg ownership "$ownership" '
    map(if .namespace == $ns and .kind == $kind and .name == $name
        then . + {ownership:$ownership} else . end)
  ' "$work/plan.json" > "$work/next.json"
  mv "$work/next.json" "$work/plan.json"
  i=$((i + 1))
done
cp "$work/plan.json" "$objects"
i=0
while [ "$i" -lt "$count" ]; do
  jq --argjson i "$i" '.items[$i]' "$rendered" > "$work/object.json"
  ns=$(jq -r '.metadata.namespace' "$work/object.json")
  kind=$(jq -r '.kind' "$work/object.json")
  name=$(jq -r '.metadata.name' "$work/object.json")
  planned=$(jq -r --arg ns "$ns" --arg kind "$kind" --arg name "$name" '.[] | select(.namespace == $ns and .kind == $kind and .name == $name) | .ownership' "$objects")
  set --
  if [ "$planned" = migrate ]; then
    eligible=true
    classify
    # A vanished conflict needs no force. A new foreign manager fails classify.
    if [ "$ownership" = migrate ]; then set -- --force-conflicts; fi
  fi
  if [ "$mode" = plan ]; then
    rc=0
    "$KUBECTL" diff --server-side --field-manager=bifrost-applier "$@" -f "$work/object.json" || rc=$?
    [ "$rc" -le 1 ] || exit "$rc"
  else
    "$KUBECTL" apply --server-side --field-manager=bifrost-applier "$@" -f "$work/object.json"
    if [ "$planned" = migrate ]; then
      "$KUBECTL" annotate "$kind" "$name" -n "$ns" kubectl.kubernetes.io/last-applied-configuration-
    fi
  fi
  i=$((i + 1))
done
