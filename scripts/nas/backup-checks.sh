# shellcheck shell=bash
# Completion and integrity checks shared by td444-move.sh (runbook §3.3 own manifests) and
# backup-rollup/rollup.sh (runbook §5.1 completion table). Sourced, never run alone; the
# caller provides log(). Every check returns 0 only on positive evidence: an empty source,
# a listing that failed, or a manifest that does not cover every file is a failure. Listings
# go to files and their exit status is checked (no process substitution that hides errors).
#
# Kinds: logical (B1; also finance once its owner confirmed the format), gitea (B2),
# cluster-state (B3 daily + monthly), registry (registry-check.py next to this file: blob
# hashes and the manifest graph from every expected digest and tag; the caller names the
# expected list in BC_REG_DIGESTS), minio (fails closed: no offline evidence proves MinIO
# objects complete, runbook §3.8 item 2).

BC_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
BC_REG_DIGESTS=${BC_REG_DIGESTS:-}

bc_list() { # bc_list <out file> <find args...>: find into a file, failing on any find error
  local out=$1; shift
  find "$@" > "$out" 2> "$out.err" || { log "listing failed: $(head -3 "$out.err")"; rm -f "$out.err"; return 1; }
  rm -f "$out.err"
}

check_logical() { # LATEST names a daily run, STATUS=OK, SHA256SUMS non-empty and verified (backup.sh:143-162)
  local d=$1 l
  l=$(cat "$d/LATEST" 2> /dev/null) || { log "$d: no LATEST"; return 1; }
  [[ $l =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{6}Z$ ]] || { log "$d: LATEST is not a run stamp"; return 1; }
  [[ $(cat "$d/daily/$l/STATUS" 2> /dev/null) == OK ]] || { log "$d: LATEST run $l is not STATUS=OK"; return 1; }
  [[ -s $d/daily/$l/SHA256SUMS ]] || { log "$d: $l has no SHA256SUMS"; return 1; }
  (cd "$d/daily/$l" && sha256sum -c --quiet --strict SHA256SUMS) || { log "$d: SHA256SUMS of $l failed"; return 1; }
}

check_gitea() { # LATEST names a run whose STATUS is exactly OK and whose two ciphertext sums verify
  local d=$1 l sums
  l=$(cat "$d/LATEST" 2> /dev/null) || { log "$d: no LATEST"; return 1; }
  [[ $l =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{6}Z$ ]] || { log "$d: LATEST is not a run stamp"; return 1; }
  [[ $(cat "$d/$l/STATUS" 2> /dev/null) == OK ]] || { log "$d: LATEST run $l is not STATUS=OK"; return 1; }
  sums=$(grep -v '^#' "$d/$l/SHA256SUMS" 2> /dev/null) || { log "$d: $l has no SHA256SUMS"; return 1; }
  [[ $(printf '%s\n' "$sums" | awk '{print $2}' | LC_ALL=C sort | tr '\n' ' ') == "MANIFEST.tsv.age data.tar.age " ]] \
    || { log "$d: $l SHA256SUMS does not list exactly the two ciphertexts"; return 1; }
  (cd "$d/$l" && printf '%s\n' "$sums" | sha256sum -c --quiet --strict -) || { log "$d: SHA256SUMS of $l failed"; return 1; }
}

cs_run() { # cs_run <dir> daily|monthly: exact file set, MANIFEST covers exactly the four ciphertexts
  local run=$1 kind=$2 names want got tmp
  names=$(cd "$run" && ls -1A | LC_ALL=C sort | tr '\n' ' ') || return 1
  # LC_ALL=C order: upper case first, so a daily run reads MANIFEST STATUS etcd-snapshot-…
  want='^MANIFEST '
  [[ $kind == daily ]] && want+='STATUS '
  want+='etcd-snapshot-[^ ]+\.age platform-state\.yaml\.age secrets\.yaml\.age server-token\.age $'
  [[ $names =~ $want ]] || { log "$run: unexpected file set: $names"; return 1; }
  if [[ $kind == daily && $(cat "$run/STATUS") != OK ]]; then log "$run: STATUS is not OK"; return 1; fi
  grep -Eq '^timestamp [0-9]{4}-[0-9]{2}-[0-9]{2}T' "$run/MANIFEST" || { log "$run: MANIFEST has no timestamp"; return 1; }
  tmp=$(mktemp)
  awk '$1 == "file" { b = ""; s = ""; for (i = 3; i < NF; i++) { if ($i == "ciphertext_bytes") b = $(i+1); if ($i == "ciphertext_sha256") s = $(i+1) } print $2, b, s }' \
    "$run/MANIFEST" | LC_ALL=C sort > "$tmp" || { rm -f "$tmp"; return 1; }
  got=$(awk '{print $1}' "$tmp" | tr '\n' ' ')
  want=$(cd "$run" && ls -1 ./*.age | sed 's#^\./##' | LC_ALL=C sort | tr '\n' ' ')
  [[ $got == "$want" ]] || { log "$run: MANIFEST lists '$got', the run holds '$want'"; rm -f "$tmp"; return 1; }
  local name bytes sum rc=0
  while read -r name bytes sum; do
    [[ $bytes =~ ^[0-9]+$ && $sum =~ ^[0-9a-f]{64}$ ]] || { log "$run: MANIFEST line for $name is incomplete"; rc=1; break; }
    [[ $(stat -c %s "$run/$name") == "$bytes" ]] || { log "$run: $name size differs from MANIFEST"; rc=1; break; }
    [[ $(sha256sum "$run/$name" | cut -d' ' -f1) == "$sum" ]] || { log "$run: $name sha256 differs from MANIFEST"; rc=1; break; }
  done < "$tmp"
  rm -f "$tmp"
  return "$rc"
}

check_cluster_state() { # at least one verified daily and one verified monthly; every run verifies
  local d=$1 tmp run n_daily=0 n_monthly=0 rc=0
  tmp=$(mktemp)
  bc_list "$tmp" "$d/daily" "$d/monthly" -mindepth 1 -maxdepth 1 -type d ! -name '.*' || { rm -f "$tmp"; return 1; }
  while read -r run; do
    case $run in
      "$d"/daily/????-??-??) cs_run "$run" daily || rc=1; n_daily=$((n_daily + 1)) ;;
      "$d"/monthly/????-??) cs_run "$run" monthly || rc=1; n_monthly=$((n_monthly + 1)) ;;
      *) log "$run: not a daily or monthly run name"; rc=1 ;;
    esac
  done < "$tmp"
  rm -f "$tmp"
  ((n_daily > 0 && n_monthly > 0)) || { log "$d: needs at least one daily and one monthly run (found $n_daily, $n_monthly)"; return 1; }
  return "$rc"
}

check_registry() { # registry-check.py: blob hashes, and from every expected digest and tag the graph a pull reads
  local root=$1/docker/registry/v2
  [[ -n $BC_REG_DIGESTS && -s $BC_REG_DIGESTS ]] || { log "$1: no expected digest list (<repository>@sha256:<hex> lines)"; return 1; }
  command -v python3 > /dev/null || { log "$1: python3 is needed for the registry check"; return 1; }
  [[ -f $BC_DIR/registry-check.py ]] || { log "registry-check.py is not next to backup-checks.sh"; return 1; }
  python3 -I "$BC_DIR/registry-check.py" --root "$root" --expect "$BC_REG_DIGESTS" 2>&1 | while IFS= read -r line; do log "$line"; done
  return "${PIPESTATUS[0]}"
}

wal_walk() { # wal_walk <first> <last> <segment size>: every segment name from first to last
  local first=$1 last=$2 per log seg t
  per=$(( 0x100000000 / $3 ))
  log=$(( 16#${first:8:8} )); seg=$(( 16#${first:16:8} ))
  t=$(( 16#${last:8:8} * per + 16#${last:16:8} ))
  ((seg < per && 16#${last:16:8} < per)) || return 1
  while (( log * per + seg <= t )); do
    printf '%s%08X%08X\n' "${first:0:8}" "$log" "$seg"
    seg=$((seg + 1)); if ((seg == per)); then seg=0; log=$((log + 1)); fi
  done
}

check_minio() { # fails closed (runbook §3.8 item 2)
  # backup.info text and WAL directory names are no evidence that the objects of the base
  # backup and of each WAL segment are complete; until a check reads them back (or decodes
  # and verifies them), a MinIO source is never a valid generation
  log "$1: MinIO objects cannot be proven complete offline (no object read-back); not a valid generation (runbook §3.8 item 2)"
  return 1
}

check_kind() { # check_kind <kind> <dir>
  case $1 in
    logical|finance) check_logical "$2" ;;
    gitea) check_gitea "$2" ;;
    cluster-state) check_cluster_state "$2" ;;
    registry) check_registry "$2" ;;
    minio) check_minio "$2" ;;
    monitoring|plain) return 0 ;;
    *) log "unknown kind $1"; return 1 ;;
  esac
}
