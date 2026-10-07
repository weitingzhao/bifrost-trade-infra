#!/bin/bash
# Compare the PITR drill cluster with the live cluster. Read-only on both:
# every psql runs with PGOPTIONS=-c default_transaction_read_only=on.
#
# Scope is tier 1 (public of bifrost_dev / bifrost_stg / bifrost_prod, and
# journal, research, ops_feedback, raw_broker on bifrost_golden_source) and
# tier 2 (raw_market.option_snapshot, raw_market.option_open_interest).
#
# Recovery point R is the "last completed transaction" log line from the drill
# pod (the end of WAL replay). Rows with a write-time at or before R must
# match. Rows on the live side after R are writes made after the recovery
# point and are not a failure. A difference inside the at-or-before-R slice
# fails. Tables with no timestamp fail only when the counts differ, because
# that difference cannot be attributed to later writes.
#
# Exit 0 when every table passes, 1 when a comparison fails or the drill is
# archiving, 2 when the drill is not ready. --self-test does not touch a
# cluster.
set -euo pipefail

DRILL_NS="${PITR_DRILL_NS:-pitr-drill}"
DRILL_CLUSTER="${PITR_DRILL_CLUSTER:-bifrost-postgres-pitr-drill}"
LIVE_NS="${PITR_LIVE_NS:-data}"
LIVE_CLUSTER="${PITR_LIVE_CLUSTER:-bifrost-postgres}"
export KUBECONFIG="${KUBECONFIG:-${HOME}/.kube/bifrost-k3s.yaml}"

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

cat > "${tmp}/brain.py" <<'PY'
#!/usr/bin/env python3
"""Judge and SQL builder for scripts/drills/pitr_verify.sh."""

from __future__ import annotations

import re
import sys

IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_TS_BODY = (
    r"[0-9]{4}-[0-9]{2}-[0-9]{2}[ T][0-9]{2}:[0-9]{2}:[0-9]{2}"
    r"(?:\.[0-9]+)?(?:Z|[ ]?[+-][0-9]{2}(?::?[0-9]{2})?)?"
)
TS_RE = re.compile("^" + _TS_BODY + "$")
LOG_RE = re.compile(r"last completed transaction was at log time\s+(" + _TS_BODY + r")")
UPDATE_COLS = {
    "updated_at",
    "updated_ts",
    "last_at",
    "account_updated_at",
    "modified_at",
    "positions_updated_at",
}

CATALOG_SQL = r"""
SELECT current_database(), n.nspname, c.relname,
       coalesce(cols.attname, ''), coalesce(cols.typname, '')
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
LEFT JOIN LATERAL (
  SELECT a.attname, t.typname
  FROM pg_attribute a
  JOIN pg_type t ON t.oid = a.atttypid
  WHERE a.attrelid = c.oid
    AND a.attnum > 0
    AND NOT a.attisdropped
    AND t.typname IN ('timestamptz', 'timestamp', 'date')
  ORDER BY
    CASE a.attname
      WHEN 'fetched_at' THEN 10
      WHEN 'created_at' THEN 20
      WHEN 'captured_at' THEN 30
      WHEN 'inserted_at' THEN 40
      WHEN 'issued_at' THEN 50
      WHEN 'occurred_at' THEN 60
      WHEN 'settled_at' THEN 70
      WHEN 'started_at' THEN 80
      WHEN 'at' THEN 90
      WHEN 'ts' THEN 100
      WHEN 'updated_ts' THEN 200
      WHEN 'last_at' THEN 210
      WHEN 'updated_at' THEN 220
      WHEN 'account_updated_at' THEN 230
      WHEN 'modified_at' THEN 240
      ELSE CASE
        WHEN a.attname IN (
          'expires_at', 'expiry', 'exit_date', 'exit_by', 'ttl_at', 'pin_until',
          'retired_at', 'replied_at', 'finished_at', 'first_seen', 'last_seen',
          'trade_date', 'report_date', 'entry_date', 'as_of', 'as_of_session',
          'available_for_trading_date', 'settle_date_target', 'snapshot_ts',
          'last_trade_ts', 'exec_time', 'greeks_asof', 'opened_at', 'intended_at',
          'cancelled_at', 'approved_at', 'executed_at', 'reviewed_at',
          'first_pinned', 'entered_on', 'positions_updated_at'
        ) THEN 500
        WHEN t.typname = 'date' THEN 400
        ELSE 300
      END
    END,
    a.attname
  LIMIT 1
) cols ON true
WHERE c.relkind IN ('r', 'p')
  AND NOT c.relispartition
  AND (
    (current_database() <> 'bifrost_golden_source' AND n.nspname = 'public')
    OR (
      current_database() = 'bifrost_golden_source'
      AND n.nspname IN ('journal', 'research', 'ops_feedback', 'raw_broker')
    )
    OR (
      current_database() = 'bifrost_golden_source'
      AND n.nspname = 'raw_market'
      AND c.relname IN ('option_snapshot', 'option_open_interest')
    )
  )
ORDER BY 1, 2, 3;
"""


def kind_of(column: str, typname: str) -> str:
    if not column:
        return "none"
    if column in UPDATE_COLS:
        return "upd"
    if typname == "date":
        return "date"
    return "ts"


def quote_ident(name: str) -> str:
    if not IDENT.fullmatch(name):
        raise ValueError(f"unsafe identifier {name!r}")
    return '"' + name + '"'


def sql_ts(recovery: str) -> str:
    if not TS_RE.fullmatch(recovery):
        raise ValueError(f"unsafe recovery point {recovery!r}")
    return "TIMESTAMPTZ '" + recovery + "'"


def statement(db: str, schema: str, table: str, column: str, typname: str, recovery: str) -> str:
    for part in (db, schema, table):
        if not IDENT.fullmatch(part):
            raise ValueError(f"unsafe identifier {part!r}")
    if column and not IDENT.fullmatch(column):
        raise ValueError(f"unsafe identifier {column!r}")
    kind = kind_of(column, typname)
    prefix = "|".join((db, schema, table, column, kind))
    rel = quote_ident(schema) + "." + quote_ident(table)
    if kind == "none":
        select_body = "count(*)::text || '|0|0||'"
    else:
        col = quote_ident(column)
        ts = sql_ts(recovery)
        if kind == "date":
            le = f"{col} < ({ts})::date OR {col} IS NULL"
            band = f"{col} = ({ts})::date"
            after = f"{col} > ({ts})::date"
            max_expr = f"coalesce(to_char(max({col}) FILTER (WHERE {{pred}}), 'YYYY-MM-DD'), '')"
        else:
            le = f"{col} <= {ts} OR {col} IS NULL"
            band = "FALSE"
            after = f"{col} > {ts}"
            max_expr = (
                "coalesce(to_char((max({col}) FILTER (WHERE {{pred}})) AT TIME ZONE 'UTC',"
                " 'YYYY-MM-DD\"T\"HH24:MI:SS.US\"Z\"'), '')"
            ).format(col=col)
        le_max = max_expr.format(pred=le)
        all_max = max_expr.format(pred="TRUE")
        select_body = (
            f"(count(*) FILTER (WHERE {le}))::text || '|' || "
            f"(count(*) FILTER (WHERE {band}))::text || '|' || "
            f"(count(*) FILTER (WHERE {after}))::text || '|' || "
            f"{le_max} || '|' || {all_max}"
        )
    return (
        "SELECT '" + prefix + "|' || CASE WHEN to_regclass('" + schema + "." + table + "') IS NULL "
        "THEN 'MISSING|0|0|0||' ELSE (SELECT 'OK|' || " + select_body + " FROM " + rel + ") END;"
    )


def sql_for_catalog(catalog_text: str, recovery: str) -> dict[str, str]:
    by_db: dict[str, list[str]] = {}
    for line in catalog_text.splitlines():
        if not line.strip():
            continue
        db, schema, table, column, typname = line.split("\t")
        by_db.setdefault(db, []).append(statement(db, schema, table, column, typname, recovery))
    return {db: "\n".join(stmts) + "\n" for db, stmts in by_db.items()}


def parse_side(text: str) -> dict[tuple[str, str, str], dict[str, str]]:
    rows: dict[tuple[str, str, str], dict[str, str]] = {}
    for line in text.splitlines():
        if not line.strip():
            continue
        parts = line.split("|")
        if len(parts) != 11:
            raise ValueError(f"bad row ({len(parts)} fields): {line}")
        db, schema, table, column, kind, status, le, band, after, max_le, max_all = parts
        rows[(db, schema, table)] = {
            "column": column,
            "kind": kind,
            "status": status,
            "le": le,
            "band": band,
            "after": after,
            "max_le": max_le,
            "max_all": max_all,
        }
    return rows


def _n(value: str) -> int:
    return int(value or "0")


def judge(live: dict[str, str] | None, drill: dict[str, str] | None) -> tuple[bool, str]:
    """Fail only when the at-or-before-R slice differs by more than later writes."""
    if live is None:
        return False, "missing on live"
    if drill is None:
        return False, "missing on drill"
    if live["status"] == "MISSING" and drill["status"] == "MISSING":
        return False, "missing on both"
    if live["status"] == "MISSING":
        return False, "missing on live"
    if drill["status"] == "MISSING":
        return False, "missing on drill"
    kind = live["kind"]
    live_le, drill_le = _n(live["le"]), _n(drill["le"])
    live_band, drill_band = _n(live["band"]), _n(drill["band"])
    live_after, drill_after = _n(live["after"]), _n(drill["after"])
    if kind == "none":
        if live_le == drill_le:
            return True, ""
        return False, "no timestamp column; count difference is not attributable to later writes"
    if kind in {"ts", "upd"} and drill_after:
        return False, "drill has rows after the recovery point"
    if kind == "ts":
        if live_le != drill_le:
            return False, "row count at or before the recovery point differs"
        if live["max_le"] != drill["max_le"]:
            return False, "max timestamp at or before the recovery point differs"
        if drill["max_all"] and live["max_all"] and drill["max_all"] > live["max_all"]:
            return False, "drill max is newer than live"
        if live_after:
            return True, f"live is ahead by {live_after} rows written after the recovery point"
        return True, ""
    if kind == "upd":
        if live_le > drill_le:
            return False, "live has more rows at or before the recovery point than the drill"
        vanished = drill_le - live_le
        if vanished > live_after:
            return False, "rows missing on live exceed post-recovery timestamp touches"
        if drill["max_all"] and live["max_all"] and drill["max_all"] > live["max_all"]:
            return False, "drill max is newer than live"
        if live_after or vanished:
            return True, f"post-recovery touches {live_after}; rows moved off the old timestamp {vanished}"
        return True, ""
    if live_le != drill_le:
        return False, "rows before the recovery date differ"
    if drill_after > live_after:
        return False, "drill has more rows after the recovery date than live"
    if drill_band > live_band:
        return False, "drill has more rows on the recovery date than live"
    if drill["max_all"] and live["max_all"] and drill["max_all"] > live["max_all"]:
        return False, "drill max is newer than live"
    ahead = (live_band - drill_band) + (live_after - drill_after)
    if ahead:
        return True, f"live is ahead by {ahead} rows on or after the recovery date"
    return True, ""


def totals(row: dict[str, str]) -> int:
    if row["status"] == "MISSING":
        return 0
    return _n(row["le"]) + _n(row["band"]) + _n(row["after"])


def render(live_rows: dict, drill_rows: dict) -> tuple[str, bool]:
    keys = sorted(set(live_rows) | set(drill_rows))
    header = (
        "result",
        "database",
        "schema",
        "table",
        "column",
        "live_rows",
        "drill_rows",
        "live_max",
        "drill_max",
        "after_recovery",
        "note",
    )
    body = []
    ok = True
    for key in keys:
        live = live_rows.get(key)
        drill = drill_rows.get(key)
        passed, note = judge(live, drill)
        ok = ok and passed
        sample = live or drill or {}
        after = ""
        if live and live["status"] != "MISSING":
            after = str(_n(live["after"]) + _n(live["band"]))
        body.append(
            (
                "PASS" if passed else "FAIL",
                key[0],
                key[1],
                key[2],
                sample.get("column", ""),
                "" if live is None else str(totals(live)),
                "" if drill is None else str(totals(drill)),
                "" if live is None else live.get("max_all", ""),
                "" if drill is None else drill.get("max_all", ""),
                after,
                note,
            )
        )
    widths = [len(item) for item in header]
    for row in body:
        widths = [max(widths[i], len(row[i])) for i in range(len(header))]
    lines = [
        "  ".join(header[i].ljust(widths[i]) for i in range(len(header))),
        "  ".join("-" * widths[i] for i in range(len(header))),
    ]
    lines.extend("  ".join(row[i].ljust(widths[i]) for i in range(len(header))) for row in body)
    failed = sum(1 for row in body if row[0] == "FAIL")
    lines.append(f"{len(body) - failed} passed, {failed} failed")
    return "\n".join(lines) + "\n", ok


def recovery_from_log(text: str) -> str:
    found = ""
    for line in text.splitlines():
        message = line
        if line.startswith("{"):
            try:
                import json

                obj = json.loads(line)
                record = obj.get("record") or {}
                message = str(record.get("message") or obj.get("msg") or "")
            except json.JSONDecodeError:
                message = line
        match = LOG_RE.search(message)
        if match:
            found = match.group(1).strip()
    return found


def self_test() -> int:
    failures: list[str] = []

    def check(label: str, live: dict[str, str] | None, drill: dict[str, str] | None, want: bool) -> None:
        passed, note = judge(live, drill)
        if passed != want:
            failures.append(f"{label}: got {passed} ({note})")

    base = {
        "column": "created_at",
        "kind": "ts",
        "status": "OK",
        "le": "10",
        "band": "0",
        "after": "0",
        "max_le": "2026-10-07T12:00:00.000000Z",
        "max_all": "2026-10-07T12:00:00.000000Z",
    }
    live_ahead = dict(base, after="3", max_all="2026-10-07T18:00:00.000000Z")
    check("later inserts pass", live_ahead, base, True)
    check("historical hole fails", dict(base, le="12"), base, False)
    check("equal passes", base, dict(base), True)
    none_live = {"column": "", "kind": "none", "status": "OK", "le": "4", "band": "0", "after": "0", "max_le": "", "max_all": ""}
    check("no clock equal", none_live, dict(none_live), True)
    check("no clock differs", dict(none_live, le="5"), none_live, False)
    upd_drill = dict(base, kind="upd", le="10")
    upd_live = dict(base, kind="upd", le="8", after="2", max_all="2026-10-07T18:00:00.000000Z")
    check("updates move the timestamp", upd_live, upd_drill, True)
    check("unexplained vanish", dict(upd_live, after="1"), upd_drill, False)
    check("drill newer than recovery", base, dict(base, after="1"), False)
    date_drill = {
        "column": "as_of",
        "kind": "date",
        "status": "OK",
        "le": "5",
        "band": "1",
        "after": "2",
        "max_le": "2026-10-06",
        "max_all": "2026-10-08",
    }
    date_live = dict(date_drill, band="2")
    check("same-day writes pass", date_live, date_drill, True)
    check("older date hole fails", dict(date_live, le="6"), date_drill, False)
    check("missing drill fails", base, None, False)
    try:
        statement("bifrost_prod", "public", "trade;drop", "created_at", "timestamptz", "2026-10-07T00:00:00Z")
        failures.append("unsafe identifier was accepted")
    except ValueError:
        pass
    sql = statement(
        "bifrost_prod", "public", "trade", "created_at", "timestamptz", "2026-10-07T00:00:00Z"
    )
    if "default_transaction_read_only" in sql or "INSERT " in sql.upper():
        failures.append("generated SQL is not a pure select")
    if 'FROM "public"."trade"' not in sql:
        failures.append("generated SQL did not quote the table")
    if "FILTER (WHERE " in sql and "(count(*) FILTER (WHERE " not in sql:
        failures.append("cast binds tighter than FILTER: " + sql)
    log = (
        '{"record":{"message":"last completed transaction was at log time '
        '2026-10-07 18:40:01.25+00"}}\n'
    )
    if recovery_from_log(log) != "2026-10-07 18:40:01.25+00":
        failures.append(f"log parse got {recovery_from_log(log)!r}")
    if failures:
        print("\n".join(failures), file=sys.stderr)
        return 1
    print("self-test ok")
    return 0


def main() -> int:
    args = sys.argv[1:]
    if args[:1] == ["--self-test"]:
        return self_test()
    if args[:1] == ["--catalog-sql"]:
        sys.stdout.write(CATALOG_SQL)
        return 0
    if args[:1] == ["--recovery-from-log"]:
        sys.stdout.write(recovery_from_log(open(args[1], encoding="utf-8", errors="replace").read()))
        return 0
    if args[:1] == ["--sql-for"]:
        # --sql-for RECOVERY CATALOG_TSV OUT_DIR
        recovery, catalog_path, out_dir = args[1], args[2], args[3]
        try:
            written = sql_for_catalog(open(catalog_path, encoding="utf-8").read(), recovery)
        except ValueError as exc:
            print(exc, file=sys.stderr)
            return 2
        if not written:
            print("catalog is empty", file=sys.stderr)
            return 2
        for db, sql in written.items():
            path = out_dir + "/" + db + ".sql"
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(sql)
            print(db)
        return 0
    if args[:1] == ["--judge"]:
        # --judge LIVE_TSV DRILL_TSV
        live = parse_side(open(args[1], encoding="utf-8").read())
        drill = parse_side(open(args[2], encoding="utf-8").read())
        text, ok = render(live, drill)
        sys.stdout.write(text)
        return 0 if ok else 1
    print("usage: brain.py --self-test|--catalog-sql|--judge ...", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
PY

if [[ "${1:-}" == "--self-test" ]]; then
  python3 "${tmp}/brain.py" --self-test
  exit
fi

pod_by_role() {
  local ns="$1" cluster="$2" role="$3"
  kubectl -n "${ns}" get pods \
    -l "cnpg.io/cluster=${cluster},cnpg.io/instanceRole=${role}" \
    --field-selector=status.phase=Running \
    -o jsonpath='{.items[0].metadata.name}'
}

psql_ro() {
  local ns="$1" pod="$2" db="$3"
  shift 3
  kubectl -n "${ns}" exec -i "${pod}" -c postgres -- \
    env PGOPTIONS='-c default_transaction_read_only=on -c statement_timeout=900000 -c TimeZone=UTC' \
    psql -U postgres -d "${db}" -X -v ON_ERROR_STOP=1 -At "$@"
}

drill_pod="$(pod_by_role "${DRILL_NS}" "${DRILL_CLUSTER}" primary || true)"
if [[ -z "${drill_pod}" ]]; then
  echo "no Running primary for ${DRILL_NS}/${DRILL_CLUSTER}" >&2
  exit 2
fi
live_pod="$(pod_by_role "${LIVE_NS}" "${LIVE_CLUSTER}" replica || true)"
if [[ -z "${live_pod}" ]]; then
  live_pod="$(pod_by_role "${LIVE_NS}" "${LIVE_CLUSTER}" primary || true)"
fi
if [[ -z "${live_pod}" ]]; then
  echo "no Running pod for ${LIVE_NS}/${LIVE_CLUSTER}" >&2
  exit 2
fi

recovering="$(psql_ro "${DRILL_NS}" "${drill_pod}" postgres -c "SELECT pg_is_in_recovery()" </dev/null)"
if [[ "${recovering}" != "f" ]]; then
  echo "drill is still in recovery (pg_is_in_recovery=${recovering})" >&2
  exit 2
fi

archive_row="$(psql_ro "${DRILL_NS}" "${drill_pod}" postgres -F $'\t' -c \
  "SELECT current_setting('archive_mode'), current_setting('archive_command'), archived_count::text FROM pg_stat_archiver" </dev/null)"
IFS=$'\t' read -r archive_mode archive_command archived_count <<<"${archive_row}"
if [[ "${archived_count}" != "0" ]] || [[ "${archive_command}" == *barman* ]] \
  || [[ "${archive_command}" == *s3://* ]] || [[ "${archive_command}" == *bifrost-postgres-backup* ]]; then
  echo "drill is archiving WAL (mode=${archive_mode} command=${archive_command} archived=${archived_count})" >&2
  exit 1
fi

recovery=""
recovery_source=""
if [[ -n "${PITR_RECOVERY_POINT:-}" ]]; then
  recovery="${PITR_RECOVERY_POINT}"
  recovery_source="PITR_RECOVERY_POINT"
else
  if ! kubectl -n "${DRILL_NS}" logs "${drill_pod}" -c postgres > "${tmp}/pg.log"; then
    echo "could not read drill logs" >&2
    exit 2
  fi
  recovery="$(python3 "${tmp}/brain.py" --recovery-from-log "${tmp}/pg.log")"
  if [[ -n "${recovery}" ]]; then
    recovery_source="postgres-log"
  else
    recovery="$(psql_ro "${DRILL_NS}" "${drill_pod}" postgres -c \
      "SELECT to_char(pg_postmaster_start_time() - interval '7 minutes', 'YYYY-MM-DD\"T\"HH24:MI:SS\"Z\"')" </dev/null)"
    recovery_source="postmaster-start-minus-7m"
    echo "warning: recovery log line not found; allowing writes in the 7 minutes before postmaster start" >&2
  fi
fi

python3 "${tmp}/brain.py" --catalog-sql > "${tmp}/catalog.sql"
: > "${tmp}/catalog.tsv"
for db in bifrost_dev bifrost_stg bifrost_prod bifrost_golden_source; do
  if ! psql_ro "${LIVE_NS}" "${live_pod}" "${db}" -F $'\t' -f - < "${tmp}/catalog.sql" >> "${tmp}/catalog.tsv"; then
    echo "catalog query failed on ${db}" >&2
    exit 2
  fi
done

mkdir -p "${tmp}/sql"
if ! python3 "${tmp}/brain.py" --sql-for "${recovery}" "${tmp}/catalog.tsv" "${tmp}/sql" > "${tmp}/dbs.txt"; then
  echo "could not build compare SQL for recovery point ${recovery}" >&2
  exit 2
fi
dbs=()
while IFS= read -r db; do
  [[ -n "${db}" ]] && dbs+=("${db}")
done < "${tmp}/dbs.txt"
if [[ "${#dbs[@]}" -eq 0 ]]; then
  echo "no tier-1 or tier-2 tables in the catalog" >&2
  exit 2
fi

: > "${tmp}/live.tsv"
: > "${tmp}/drill.tsv"
for db in "${dbs[@]}"; do
  if ! psql_ro "${LIVE_NS}" "${live_pod}" "${db}" -f - < "${tmp}/sql/${db}.sql" >> "${tmp}/live.tsv"; then
    echo "live compare query failed on ${db}" >&2
    exit 2
  fi
  if ! psql_ro "${DRILL_NS}" "${drill_pod}" "${db}" -f - < "${tmp}/sql/${db}.sql" >> "${tmp}/drill.tsv"; then
    echo "drill compare query failed on ${db}" >&2
    exit 2
  fi
done

echo "recovery_point=${recovery} source=${recovery_source} live_pod=${live_pod} drill_pod=${drill_pod}"
python3 "${tmp}/brain.py" --judge "${tmp}/live.tsv" "${tmp}/drill.tsv"
