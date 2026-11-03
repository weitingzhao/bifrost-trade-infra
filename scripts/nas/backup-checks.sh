# shellcheck shell=bash
# Completion and integrity checks shared by td444-move.sh (runbook §3.3 own manifests) and
# backup-rollup/rollup.sh (runbook §5.1 completion table). Sourced, never run alone; the
# caller provides log(). Every check returns 0 only on positive evidence: an empty source,
# a listing that failed, or a manifest that does not cover every file is a failure. Listings
# go to files and their exit status is checked (no process substitution that hides errors).
#
# Kinds: logical (B1; also finance once its owner confirmed the format), gitea (B2),
# cluster-state (B3 daily + monthly), registry (blobs + every tag's manifest graph),
# minio (newest DONE base backup + every WAL segment after it on the same timeline).

BC_SEG_SIZE=${BC_SEG_SIZE:-16777216}   # WAL segment size; the cluster runs the default

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

declare -A BC_SEEN=()
reg_manifest() { # reg_manifest <v2 root> <repo> <digest>: revision link, blob, and every referenced digest
  local root=$1 repo=$2 dg=$3 hex ref rhex blob refs
  [[ -n ${BC_SEEN[$repo@$dg]:-} ]] && return 0
  BC_SEEN[$repo@$dg]=1
  hex=${dg#sha256:}
  [[ $dg =~ ^sha256:[0-9a-f]{64}$ ]] || { log "$repo: bad digest $dg"; return 1; }
  [[ $(cat "$root/repositories/$repo/_manifests/revisions/sha256/$hex/link" 2> /dev/null) == "$dg" ]] \
    || { log "$repo: manifest $dg has no revision link"; return 1; }
  blob="$root/blobs/sha256/${hex:0:2}/$hex/data"
  [[ -f $blob ]] || { log "$repo: manifest blob $dg missing"; return 1; }
  refs=$(grep -ao 'sha256:[0-9a-f]\{64\}' "$blob" | LC_ALL=C sort -u) || refs=""
  [[ -n $refs ]] || { log "$repo: manifest $dg references nothing"; return 1; }
  for ref in $refs; do
    rhex=${ref#sha256:}
    [[ -f $root/blobs/sha256/${rhex:0:2}/$rhex/data ]] || { log "$repo: $dg references missing blob $ref"; return 1; }
    if [[ -f $root/repositories/$repo/_manifests/revisions/sha256/$rhex/link ]]; then
      reg_manifest "$root" "$repo" "$ref" || return 1          # a child of an index
    elif [[ $(cat "$root/repositories/$repo/_layers/sha256/$rhex/link" 2> /dev/null) != "$ref" ]]; then
      log "$repo: $dg references $ref without a layer link"; return 1
    fi
  done
}

check_registry() { # every blob hashes to its name; every tag resolves to a complete manifest graph
  local root=$1/docker/registry/v2 tmp f want n=0 rc=0 repo dg
  tmp=$(mktemp)
  bc_list "$tmp" "$root/blobs/sha256" -mindepth 3 -maxdepth 3 -type f -name data || { rm -f "$tmp"; return 1; }
  while read -r f; do
    want=$(basename "$(dirname "$f")")
    [[ $(sha256sum "$f" | cut -d' ' -f1) == "$want" ]] || { log "blob $want hashes differently"; rc=1; }
    n=$((n + 1))
  done < "$tmp"
  ((n > 0)) || { log "$root: no blobs"; rc=1; }
  bc_list "$tmp" "$root/repositories" -path '*/_manifests/tags/*/current/link' -type f || { rm -f "$tmp"; return 1; }
  [[ -s $tmp ]] || { log "$root: no tags"; rc=1; }
  BC_SEEN=()
  while read -r f; do
    repo=${f#"$root/repositories/"}; repo=${repo%%/_manifests/*}
    dg=$(cat "$f")
    reg_manifest "$root" "$repo" "$dg" || { log "$repo: tag $(basename "$(dirname "$(dirname "$f")")") is not complete"; rc=1; }
  done < "$tmp"
  rm -f "$tmp"
  return "$rc"
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

check_minio() { # newest base backup whose backup.info says DONE, then every WAL segment after it
  local d=$1 tmp info begin="" b names first last tli missing=0
  tmp=$(mktemp)
  bc_list "$tmp" "$d" -mindepth 6 -maxdepth 6 -type f -path '*/base/*/backup.info/xl.meta' || { rm -f "$tmp"; return 1; }
  while read -r info; do
    grep -aq 'status=DONE' "$info" || continue
    b=$(grep -ao 'begin_wal=[0-9A-F]\{24\}' "$info" | head -1 | cut -d= -f2) || b=""
    [[ -n $b && $b > $begin ]] && begin=$b
  done < "$tmp"
  [[ -n $begin ]] || { log "$d: no base backup with backup.info status=DONE and a begin_wal"; rm -f "$tmp"; return 1; }
  bc_list "$tmp" "$d" -mindepth 5 -maxdepth 5 -type d -path '*/wals/*' || { rm -f "$tmp"; return 1; }
  names=$(sed -E 's#.*/##' "$tmp" | grep -E '^[0-9A-F]{24}(\.[a-z0-9]+)?$' | grep -v '\.partial$' | cut -c1-24 | LC_ALL=C sort -u) || names=""
  rm -f "$tmp"
  tli=${begin:0:8}
  if printf '%s\n' "$names" | awk -v t="$tli" 'NF && substr($0, 1, 8) > t { found = 1 } END { exit !found }'; then
    log "$d: WAL on a later timeline than $tli after the base backup; check it by hand"; return 1
  fi
  first=$begin
  last=$(printf '%s\n' "$names" | awk -v t="$tli" 'substr($0, 1, 8) == t' | tail -1)
  [[ -n $last && ! $last < $first ]] || { log "$d: no WAL from $begin on"; return 1; }
  tmp=$(mktemp)
  wal_walk "$first" "$last" "$BC_SEG_SIZE" > "$tmp" || { log "$d: WAL names outside the segment range"; rm -f "$tmp"; return 1; }
  while read -r b; do
    printf '%s\n' "$names" | grep -Fxq "$b" || { log "$d: WAL $b missing after base $begin"; missing=$((missing + 1)); }
  done < "$tmp"
  rm -f "$tmp"
  ((missing == 0)) || return 1
  log "$d: base backup from $begin and every WAL segment up to $last are present"
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
