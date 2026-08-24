#!/usr/bin/env bash
# RETIRED Wave 6 — ops_audit_log table dropped; clone no longer preserves audit rows.
# Use scripts/verify_wave6_ops_audit_retired.sh instead.
echo "SKIP: verify_clone_audit_preservation.sh retired (Wave 6); use verify_wave6_ops_audit_retired.sh"
exit 0

# --- legacy script below (not executed) ---
# (Wave 2 requirement — pg_dump excludes public.ops_audit_log data, then
#  data_clone.go backs up target audit rows and replays them post-restore).
#
# Two-stage flow around the Owner's `trigger_data_clone`:
#
#   1) BEFORE clone — plant a canary row in the target env:
#        ./scripts/verify_clone_audit_preservation.sh dev seed
#
#   2) Owner triggers the clone via Ops Console → Data → "Clone from PROD".
#
#   3) AFTER clone — confirm the canary survived:
#        ./scripts/verify_clone_audit_preservation.sh dev verify
#
# Exits non-zero on regression. Cleans up the canary on `verify --clean`.

set -euo pipefail

TARGET_ENV="${1:-}"
STAGE="${2:-}"
CLEAN="${3:-}"

if [[ -z "$TARGET_ENV" || -z "$STAGE" ]]; then
  cat <<USAGE
Usage: $0 <target-env> <seed|verify> [--clean]
  target-env: dev | stg    (do NOT run against prod)
  stage:      seed  — insert canary row before Owner triggers clone
              verify — check canary still present after clone completes
  --clean:    (verify only) delete the canary row after successful check
USAGE
  exit 2
fi

case "$TARGET_ENV" in
  dev)  TARGET_DB="bifrost_dev"  ;;
  stg)  TARGET_DB="bifrost_stg"  ;;
  *)    echo "FATAL: target-env must be 'dev' or 'stg' (never 'prod')" >&2; exit 2 ;;
esac

STATE_DIR="${STATE_DIR:-$HOME/.bifrost-dev/state}"
mkdir -p "$STATE_DIR"
CANARY_FILE="$STATE_DIR/wave2-clone-canary-$TARGET_ENV.txt"

export KUBECONFIG="${KUBECONFIG:-$HOME/.kube/bifrost-k3s.yaml}"
PRIMARY="$(kubectl get cluster bifrost-postgres -n data -o jsonpath='{.status.currentPrimary}')"
if [[ -z "$PRIMARY" ]]; then
  echo "FATAL: cannot resolve CNPG primary pod" >&2
  exit 3
fi

psql_target() {
  kubectl exec -n data "$PRIMARY" -c postgres -- \
    psql -U postgres -d "$TARGET_DB" -tAc "$1"
}

CANARY_TAG="wave2_clone_canary_$(date -u +%Y%m%dT%H%M%SZ)_${TARGET_ENV}"

case "$STAGE" in
  seed)
    # Sanity: ops_audit_log must exist (Wave 2+; Wave 4 may be partitioned timestamptz)
    HAS_TABLE="$(psql_target "SELECT to_regclass('public.ops_audit_log') IS NOT NULL")"
    if [[ "$HAS_TABLE" != "t" ]]; then
      echo "FATAL: public.ops_audit_log missing in $TARGET_DB — run db-init with core >= 0.11.0 first" >&2
      exit 4
    fi

    # timestamp column is timestamptz (Wave 4) or legacy double; DEFAULT handles both.
    # -tAc mixes RETURNING output with the command tag ("INSERT 0 1"); grab the
    # first purely-numeric line so state files stay `source`-safe.
    ROW_ID="$(psql_target "
INSERT INTO ops_audit_log (operator, source_ip, action, target, command_id, outcome, detail, request_id)
VALUES ('wave2-verify-script', '127.0.0.1', 'clone.audit.canary', '$TARGET_ENV',
        '$CANARY_TAG', 'seeded', 'Canary row planted to prove clone preserves target audit trail',
        '$CANARY_TAG')
RETURNING id;
" | awk '/^[0-9]+$/ {print; exit}')"

    if [[ -z "$ROW_ID" ]]; then
      echo "FATAL: INSERT into ops_audit_log returned empty id" >&2
      exit 5
    fi

    BEFORE_COUNT="$(psql_target "SELECT count(*) FROM ops_audit_log")"
    printf 'canary_tag=%s\ncanary_id=%s\nbefore_count=%s\nseeded_at_utc=%s\n' \
      "$CANARY_TAG" "$ROW_ID" "$BEFORE_COUNT" "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" \
      > "$CANARY_FILE"

    echo "seeded canary in $TARGET_DB.ops_audit_log:"
    echo "  id=$ROW_ID  tag=$CANARY_TAG  total_rows_before=$BEFORE_COUNT"
    echo "state file: $CANARY_FILE"
    echo
    echo "Next: Owner triggers trigger_data_clone → then run:"
    echo "  $0 $TARGET_ENV verify"
    ;;

  verify)
    if [[ ! -f "$CANARY_FILE" ]]; then
      echo "FATAL: canary state $CANARY_FILE not found — did you run '$0 $TARGET_ENV seed' before the clone?" >&2
      exit 6
    fi
    # shellcheck disable=SC1090
    source "$CANARY_FILE"

    echo "expecting canary_id=$canary_id  tag=$canary_tag  before_count=$before_count"

    AFTER_COUNT="$(psql_target "SELECT count(*) FROM ops_audit_log")"
    CANARY_STILL="$(psql_target "
SELECT count(*) FROM ops_audit_log
WHERE id = $canary_id AND command_id = '$canary_tag'
")"

    echo "after_clone: total_rows=$AFTER_COUNT  canary_present=$CANARY_STILL"

    FAIL=0
    if [[ "$CANARY_STILL" != "1" ]]; then
      echo "FAIL: canary row $canary_id / $canary_tag missing after clone — target audit trail was overwritten"
      FAIL=1
    fi
    if [[ "$AFTER_COUNT" -lt "$before_count" ]]; then
      echo "FAIL: total audit rows regressed from $before_count to $AFTER_COUNT (target audit lost)"
      FAIL=1
    fi

    # Cross-check: no PROD-only signature bled through. We detect this loosely
    # by looking for operators only ever seen in the prod audit trail — best
    # effort, prints info only unless the source_ip column shows a private
    # subnet that DEV/STG never uses.
    LEAKED="$(psql_target "
SELECT count(*) FROM ops_audit_log
WHERE outcome IN ('promoted', 'deliver-prod') OR source_ip LIKE '10.%' OR detail ILIKE '%prod cutover%'
")"
    echo "info: possible prod-shape rows in target=$LEAKED (should be 0 or historical)"

    if [[ "$FAIL" -eq 0 ]]; then
      echo "clone audit preservation: PASS"
      if [[ "$CLEAN" == "--clean" ]]; then
        psql_target "DELETE FROM ops_audit_log WHERE id = $canary_id AND command_id = '$canary_tag'" >/dev/null
        rm -f "$CANARY_FILE"
        echo "canary row cleaned up."
      else
        echo "keep canary in place, or re-run with '--clean' to remove it."
      fi
      exit 0
    else
      echo "clone audit preservation: FAIL"
      exit 1
    fi
    ;;

  *)
    echo "FATAL: unknown stage '$STAGE' (expected 'seed' or 'verify')" >&2
    exit 2
    ;;
esac
