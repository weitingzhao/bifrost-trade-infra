#!/usr/bin/env bash
# Daily logical dump of hand-entered data (phase 0 W5).
#
# One custom-format pg_dump per <database>:<schema> target. Each target is
# dumped from an exported snapshot, and the same snapshot is used to count
# rows into manifest.tsv, so the restore drill can demand exact equality.
#
# Layout under HOT_DIR (NAS k3s-hot, claim data/logical-backup-hot):
#   daily/<UTC stamp>/<db>.<schema>.dump  manifest.tsv  extensions.tsv
#                     SHA256SUMS  STATUS (OK | PARTIAL: <failed targets>)
#   daily/.partial-<stamp>/   while a run is writing
#   drills/                   restore drill reports (written by drill.sh)
#   LATEST                    name of the newest OK daily dir
# COLD_DIR (NAS k3s-cold, claim data/logical-backup-cold) keeps weekly/<stamp>/
# copies forever.
#
# Env: PGHOST PGUSER PGPASSWORD PGSSLMODE (libpq), TARGETS, HOT_DIR, COLD_DIR,
#      KEEP_DAILY (default 14), WEEKLY_EVERY_DAYS (default 7),
#      REQUIRE_MOUNT (default 1: refuse to write unless HOT_DIR / COLD_DIR are
#      mountpoints, so a missing NAS volume never fills the node's disk).
set -uo pipefail

: "${TARGETS:?TARGETS is required (space separated db:schema)}"
HOT_DIR="${HOT_DIR:-/backup/hot}"
COLD_DIR="${COLD_DIR:-/backup/cold}"
KEEP_DAILY="${KEEP_DAILY:-14}"
WEEKLY_EVERY_DAYS="${WEEKLY_EVERY_DAYS:-7}"

log() { printf '%s %s\n' "$(date -u +%FT%TZ)" "$*"; }
die() { log "FATAL: $*"; exit 2; }

REQUIRE_MOUNT="${REQUIRE_MOUNT:-1}"
is_mount() { awk -v p="$1" '$5 == p { found = 1 } END { exit !found }' /proc/self/mountinfo; }

[[ -d "$HOT_DIR" && -w "$HOT_DIR" ]] || die "HOT_DIR $HOT_DIR is not a writable directory (NAS mount missing?)"
if [[ "$REQUIRE_MOUNT" == 1 ]] && ! is_mount "$HOT_DIR"; then
  die "HOT_DIR $HOT_DIR is not a mountpoint; refusing to write"
fi
cold_ok=1
if [[ ! -d "$COLD_DIR" || ! -w "$COLD_DIR" ]] || { [[ "$REQUIRE_MOUNT" == 1 ]] && ! is_mount "$COLD_DIR"; }; then
  cold_ok=0
fi

stamp="$(date -u +%Y-%m-%dT%H%M%SZ)"
daily="$HOT_DIR/daily"
work="$daily/.partial-$stamp"
final="$daily/$stamp"
[[ ! -e "$final" ]] || die "$final already exists"
mkdir -p "$daily" "$work" || die "cannot create $work"
# drill.sh runs as the postgres uid and writes its reports here.
install -d -m 1777 "$HOT_DIR/drills"

manifest="$work/manifest.tsv"
extensions="$work/extensions.tsv"
printf 'target\ttable\trows\n' >"$manifest"
printf 'target\textension\tversion\n' >"$extensions"

# dump_target <db> <schema>: returns 0 on success.
dump_target() {
  local db="$1" schema="$2" target="$1.$2"
  local out="$work/$target.dump" snap="" line

  coproc PSQL { psql -X -q -At -F $'\t' -v ON_ERROR_STOP=1 -d "$db" 2>&1; }
  # Own copies of the pipes: bash drops PSQL[*] as soon as psql exits.
  local in_fd out_fd pid="$PSQL_PID"
  exec {in_fd}>&"${PSQL[1]}" {out_fd}<&"${PSQL[0]}"
  eval "exec ${PSQL[1]}>&- ${PSQL[0]}<&-"

  printf '%s\n' \
    "BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;" \
    "SELECT pg_export_snapshot();" >&"$in_fd"
  IFS= read -r -t 60 snap <&"$out_fd" || true
  if [[ ! "$snap" =~ ^[0-9A-F]+-[0-9A-F]+-[0-9]+$ ]]; then
    log "[$target] could not export snapshot: ${snap:-<no answer>}"
    exec {in_fd}>&- {out_fd}<&-; wait "$pid" 2>/dev/null
    return 1
  fi

  local rc=0
  pg_dump -d "$db" --snapshot="$snap" -n "$schema" -Fc -Z 6 -f "$out" || rc=$?

  # Row counts inside the same snapshot. Plain and partition leaf tables only:
  # those are what carry TABLE DATA entries in the dump.
  printf '%s\n' \
    "SELECT format('%I.%I', n.nspname, c.relname)," \
    "       (xpath('/row/n/text()', query_to_xml(format('SELECT count(*) AS n FROM %I.%I', n.nspname, c.relname), false, true, '')))[1]::text" \
    "FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace" \
    "WHERE n.nspname = '$schema' AND c.relkind = 'r' ORDER BY 1;" \
    "SELECT extname, extversion FROM pg_extension ORDER BY 1;" \
    "SELECT '__END__';" \
    "COMMIT;" '\q' >&"$in_fd"
  exec {in_fd}>&-

  local section=tables
  while IFS= read -r -t 600 line <&"$out_fd"; do
    case "$line" in
      __END__) break ;;
      ERROR:*|FATAL:*|psql:*) log "[$target] $line"; rc=1 ;;
      *)
        if [[ "$section" == tables && "$line" == *.*$'\t'* ]]; then
          printf '%s\t%s\n' "$target" "$line" >>"$manifest"
        elif [[ "$line" == *$'\t'* ]]; then
          section=extensions
          printf '%s\t%s\n' "$target" "$line" >>"$extensions"
        fi ;;
    esac
  done
  exec {out_fd}<&-
  wait "$pid" 2>/dev/null || rc=1
  [[ $rc -eq 0 ]] || return 1

  # The dump must be readable and complete: one TABLE DATA entry per counted
  # table, and nothing outside the schema (user mappings carry passwords).
  local toc tables data
  toc="$(pg_restore -l "$out")" || { log "[$target] pg_restore -l failed"; return 1; }
  if grep -q 'USER MAPPING' <<<"$toc"; then
    log "[$target] dump contains a USER MAPPING; refusing to keep it"; rm -f "$out"; return 1
  fi
  tables="$(awk -F'\t' -v t="$target" '$1==t' "$manifest" | wc -l | tr -d ' ')"
  data="$(grep -c ' TABLE DATA ' <<<"$toc" || true)"
  if [[ "$tables" != "$data" ]]; then
    log "[$target] TOC has $data TABLE DATA entries but the schema has $tables tables"; return 1
  fi
  log "[$target] ok: $tables tables, $(du -h "$out" | cut -f1)"
  return 0
}

failed=()
for t in $TARGETS; do
  db="${t%%:*}"; schema="${t#*:}"
  [[ -n "$db" && -n "$schema" && "$db" != "$t" ]] || { log "bad target '$t'"; failed+=("$t"); continue; }
  dump_target "$db" "$schema" || failed+=("$t")
done

( cd "$work" && shopt -s nullglob && sha256sum -- *.dump manifest.tsv extensions.tsv >SHA256SUMS ) \
  || die "cannot write SHA256SUMS in $work"
if ((${#failed[@]})); then
  echo "PARTIAL: ${failed[*]}" >"$work/STATUS"
else
  echo OK >"$work/STATUS"
fi
mv "$work" "$final" || die "cannot finalize $final"
log "wrote $final ($(cat "$final/STATUS"))"

ok_dirs() { # newest first, only finished OK runs
  local d
  for d in $(ls -1 "$daily" 2>/dev/null | grep -E '^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{6}Z$' | sort -r); do
    [[ "$(cat "$daily/$d/STATUS" 2>/dev/null)" == OK ]] && echo "$d"
  done
}

if [[ "$(cat "$final/STATUS")" == OK ]]; then
  echo "$stamp" >"$HOT_DIR/LATEST.tmp" && mv "$HOT_DIR/LATEST.tmp" "$HOT_DIR/LATEST"
fi

# Weekly copy to cold: take the newest OK run when the newest weekly copy is
# WEEKLY_EVERY_DAYS or more older, so a missed day never skips a week.
if ((cold_ok)); then
  newest_ok="$(ok_dirs | head -1)"
  last_weekly="$(ls -1 "$COLD_DIR/weekly" 2>/dev/null | grep -E '^[0-9]{4}-' | sort | tail -1)"
  due=1
  if [[ -n "$last_weekly" && -n "$newest_ok" ]]; then
    age_days=$(( ( $(date -u -d "${newest_ok:0:10}" +%s) - $(date -u -d "${last_weekly:0:10}" +%s) ) / 86400 ))
    (( age_days < WEEKLY_EVERY_DAYS )) && due=0
  fi
  if [[ -n "$newest_ok" && $due -eq 1 ]]; then
    mkdir -p "$COLD_DIR/weekly"
    tmp="$COLD_DIR/weekly/.partial-$newest_ok"
    rm -rf "$tmp"
    if cp -r "$daily/$newest_ok" "$tmp" && ( cd "$tmp" && sha256sum -c --quiet SHA256SUMS ) \
       && mv "$tmp" "$COLD_DIR/weekly/$newest_ok"; then
      log "weekly copy -> cold weekly/$newest_ok"
    else
      log "weekly copy to cold FAILED"; failed+=("cold-weekly")
    fi
  fi
else
  log "COLD_DIR $COLD_DIR is not a writable mountpoint; weekly copy skipped"; failed+=("cold-mount")
fi

# Rotation: keep the newest KEEP_DAILY OK runs. PARTIAL runs survive until
# they are older than the oldest kept OK run. Abandoned .partial dirs go after a day.
mapfile -t keep < <(ok_dirs | head -n "$KEEP_DAILY")
if ((${#keep[@]} >= KEEP_DAILY)); then
  oldest_kept="${keep[-1]}"
  for d in $(ls -1 "$daily" | grep -E '^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{6}Z$'); do
    if [[ "$d" < "$oldest_kept" ]]; then
      rm -rf -- "${daily:?}/$d" && log "rotated out daily/$d"
    fi
  done
fi
find "$daily" -maxdepth 1 -name '.partial-*' -mmin +1440 -exec rm -rf -- {} + 2>/dev/null

if ((${#failed[@]})); then
  log "finished with failures: ${failed[*]}"
  exit 1
fi
log "finished OK"
