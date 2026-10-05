#!/usr/bin/env bash
# Restore drill for the logical backups written by backup.sh (phase 0 W5).
#
# Starts a throwaway PostgreSQL in an emptyDir (never touches the CNPG
# cluster), restores every dump of one backup run, and requires each table's
# row count to equal the count manifest.tsv recorded inside the dump snapshot.
# Writes a report to <HOT_DIR>/drills/<stamp>.txt and exits non-zero on any
# mismatch, so the CronJob's last success time is the drill's health.
#
# Usage: drill.sh [<run dir name>|latest]   (default: LATEST)
# Env:   HOT_DIR (default /backup/hot), COLD_DIR (to drill a weekly copy set
#        SOURCE=cold), PGDATA_DIR (default /tmp/drill-pgdata). Runs as uid 26.
set -uo pipefail

HOT_DIR="${HOT_DIR:-/backup/hot}"
COLD_DIR="${COLD_DIR:-/backup/cold}"
SOURCE="${SOURCE:-hot}"
PGDATA_DIR="${PGDATA_DIR:-/tmp/drill-pgdata}"
SOCK="${PGDATA_DIR%/*}/drill-sock"
which="${1:-latest}"

if [[ "$SOURCE" == cold ]]; then base="$COLD_DIR/weekly"; else base="$HOT_DIR/daily"; fi
if [[ "$which" == latest ]]; then
  if [[ "$SOURCE" == cold ]]; then
    which="$(ls -1 "$base" | grep -E '^[0-9]{4}-' | sort | tail -1)"
  else
    which="$(cat "$HOT_DIR/LATEST" 2>/dev/null)"
  fi
fi
run="$base/$which"
stamp="$(date -u +%Y-%m-%dT%H%M%SZ)"
report_dir="$HOT_DIR/drills"
report="$(mktemp)"

say() { printf '%s\n' "$*" | tee -a "$report"; }
finish() {
  local verdict="$1"
  say "VERDICT: $verdict"
  pg_ctl -D "$PGDATA_DIR" -m immediate stop >/dev/null 2>&1
  if [[ -d "$report_dir" && -w "$report_dir" ]]; then
    cp "$report" "$report_dir/$stamp-$SOURCE-$which.txt" && echo "report: $report_dir/$stamp-$SOURCE-$which.txt"
  fi
  [[ "$verdict" == PASS ]]
  exit $?
}

say "restore drill $stamp  source=$SOURCE run=$which"
[[ -n "$which" && -d "$run" ]] || { say "no backup run found at $run"; finish FAIL; }
say "status: $(cat "$run/STATUS" 2>/dev/null)"

( cd "$run" && sha256sum -c --quiet SHA256SUMS ) >>"$report" 2>&1 \
  && say "checksums: ok" || { say "checksums: MISMATCH"; finish FAIL; }

rm -rf "$PGDATA_DIR" "$SOCK"; mkdir -p "$SOCK"
initdb -D "$PGDATA_DIR" -U postgres -A trust --no-sync >/dev/null || { say "initdb failed"; finish FAIL; }
pg_ctl -D "$PGDATA_DIR" -w -l "$PGDATA_DIR/server.log" \
  -o "-c listen_addresses='' -k $SOCK -c fsync=off -c full_page_writes=off" start >/dev/null \
  || { say "postgres did not start"; finish FAIL; }
export PGHOST="$SOCK" PGUSER=postgres
unset PGPASSWORD PGSSLMODE

fail=0
for dump in "$run"/*.dump; do
  target="$(basename "$dump" .dump)"          # <db>.<schema>
  db="${target%%.*}"
  psql -X -q -d postgres -tAc "SELECT 1 FROM pg_database WHERE datname='$db'" | grep -q 1 \
    || createdb "$db"
  # Extensions the source database had (types such as vector live outside the dumped schema).
  while IFS=$'\t' read -r t ext ver; do
    [[ "$t" == "$target" && "$ext" != plpgsql ]] || continue
    psql -X -q -d "$db" -c "CREATE EXTENSION IF NOT EXISTS \"$ext\" WITH SCHEMA public" >/dev/null 2>&1 \
      || say "[$target] note: extension $ext unavailable in drill image"
  done < <(tail -n +2 "$run/extensions.tsv")

  # A fresh database already has schema public; skip that one CREATE SCHEMA.
  # Views go in a second pass: Trade's public views read the FDW schema
  # market, which is not part of the backup (core DDL recreates it), so a
  # view that cannot be created on its own is reported, not failed.
  schema="${target#*.}"
  full="$(mktemp)" toc="$(mktemp)" views="$(mktemp)"
  view_re=' (VIEW|MATERIALIZED VIEW|MATERIALIZED VIEW DATA) '
  pg_restore -l "$dump" | grep -v " SCHEMA - $schema " >"$full"
  [[ "$schema" == public ]] || pg_restore -l "$dump" >"$full"
  grep -E "$view_re" "$full" >"$views"
  grep -v -E "$view_re" "$full" >"$toc"
  if ! pg_restore -d "$db" --no-owner --no-acl --exit-on-error -L "$toc" "$dump" >>"$report" 2>&1; then
    say "[$target] pg_restore FAILED"; fail=1; continue
  fi
  nviews="$(grep -c . "$views" || true)"
  if ((nviews)); then
    vfail=0
    while IFS= read -r entry; do
      printf '%s\n' "$entry" >"$toc"
      pg_restore -d "$db" --no-owner --no-acl --exit-on-error -L "$toc" "$dump" >>"$report" 2>&1 || vfail=$((vfail + 1))
    done <"$views"
    say "[$target] views: $((nviews - vfail)) of $nviews restored; $vfail depend on objects outside this dump"
  fi

  n=0; bad=0
  while IFS=$'\t' read -r t table rows; do
    [[ "$t" == "$target" ]] || continue
    got="$(psql -X -q -d "$db" -tAc "SELECT count(*) FROM $table" 2>&1)"
    n=$((n + 1))
    if [[ "$got" != "$rows" ]]; then
      say "[$target] $table: manifest $rows, restored $got"; bad=$((bad + 1))
    fi
  done < <(tail -n +2 "$run/manifest.tsv")
  if ((bad)); then fail=1; say "[$target] FAIL: $bad of $n tables differ"
  else say "[$target] ok: $n tables, row counts equal"; fi
done

((fail)) && finish FAIL
finish PASS
