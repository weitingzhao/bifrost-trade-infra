#!/usr/bin/env bash
# Point DEV's backend :dev tags at what STG runs (worker + the four API images DEV deploys).
#
# Since TD-34 DEV runs its own :dev tags and STG/PROD delivers never touch them. The frontend and
# the API have DEV-only builds that push :dev; the worker has none, so without this DEV's worker
# froze at the copy TD-34 made — before TD-04, reading the account snapshot from the per-env
# Redis instead of redis-ib (empty Accounts on DEV, 2026-10-02). Run this after an STG release
# when DEV should catch up. It never touches :stg / :prod or the frontend's :dev.
#
#   scripts/registry/dev-sync-backend-images.sh              copy :stg → :dev, print old and new digests
#   SRC=sha256:<digest> IMAGES=bifrost-worker scripts/…      put one image back (rollback)
#   RESTART=1 scripts/…                                      then restart the DEV deployments whose
#                                                            pods do not run the current :dev
set -euo pipefail

REGISTRY="${REGISTRY:-http://192.168.10.73:30500}"
SRC="${SRC:-stg}"
read -r -a IMAGES <<<"${IMAGES:-bifrost-worker bifrost-api-account bifrost-api-market bifrost-api-monitor bifrost-api-research}"
ACCEPT='application/vnd.oci.image.index.v1+json, application/vnd.oci.image.manifest.v1+json, application/vnd.docker.distribution.manifest.list.v2+json, application/vnd.docker.distribution.manifest.v2+json'

digest_of() {
  curl -fsS -I -H "Accept: $ACCEPT" "$REGISTRY/v2/$1/manifests/$2" \
    | awk -F': ' 'tolower($1)=="docker-content-digest"{print $2}' | tr -d '\r'
}

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

for img in "${IMAGES[@]}"; do
  old="$(digest_of "$img" dev || true)"
  ctype="$(curl -fsS -D "$tmp/h" -o "$tmp/m" -H "Accept: $ACCEPT" "$REGISTRY/v2/$img/manifests/$SRC" \
    && awk -F': ' 'tolower($1)=="content-type"{print $2}' "$tmp/h" | tr -d '\r')"
  [[ -n "$ctype" ]] || { echo "ERROR: $img:$SRC not found" >&2; exit 1; }
  curl -fsS -X PUT -H "Content-Type: $ctype" --data-binary @"$tmp/m" "$REGISTRY/v2/$img/manifests/dev" >/dev/null
  new="$(digest_of "$img" dev)"
  src_digest="$(digest_of "$img" "$SRC")"
  [[ "$new" == "$src_digest" ]] || { echo "ERROR: $img:dev is $new, expected $src_digest" >&2; exit 1; }
  if [[ "$old" == "$new" ]]; then
    echo "$img:dev unchanged ($new)"
  else
    echo "$img:dev ${old:-<none>} → $new"
  fi
done

if [[ "${RESTART:-0}" == 1 ]]; then
  export KUBECONFIG="${KUBECONFIG:-$HOME/.kube/bifrost-k3s.yaml}"
  # DEV pulls :dev with imagePullPolicy Always (dev-images-pull-always.patch.yaml), so a restart
  # is what picks the new digests up. Restart only a deployment whose pods run something other
  # than the current :dev — that also catches a tag synced earlier without a restart.
  pods="$(kubectl -n bifrost-dev get pods -o jsonpath='{range .items[*]}{.metadata.name} {.status.containerStatuses[*].imageID}{"\n"}{end}')"
  stale=()
  for img in "${IMAGES[@]}"; do
    case "$img" in
      bifrost-worker) d=daemon ;;
      bifrost-api-*) d="${img#bifrost-}" ;;
      *) continue ;;
    esac
    want="$(digest_of "$img" dev)"
    running="$(awk -v p="$d-" 'index($1, p) == 1 {$1 = ""; print}' <<<"$pods")"
    if [[ -n "$running" ]] && ! grep -qv "@$want" <<<"$(tr ' ' '\n' <<<"$running" | grep '@')"; then
      echo "$d already runs $img:dev ($want)"
    else
      stale+=("$d")
    fi
  done
  if (( ${#stale[@]} == 0 )); then
    echo "nothing to restart: every DEV deployment already runs the current :dev"
  else
    for d in "${stale[@]}"; do kubectl -n bifrost-dev rollout restart "deploy/$d"; done
    for d in "${stale[@]}"; do kubectl -n bifrost-dev rollout status "deploy/$d" --timeout=240s; done
  fi
fi
