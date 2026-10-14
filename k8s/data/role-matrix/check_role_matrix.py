#!/usr/bin/env python3
"""Read-only compare of live PostgreSQL grants to the D13 role matrix.

The live path reads pg_database.datacl, pg_namespace.nspacl and pg_class.relacl
(plus role membership) and applies the same ACL rules the unit tests cover:
PUBLIC expansion, TEMP (`T`) is not CONNECT, grant-option stars, inheritance,
and the database owner's implicit membership in pg_database_owner.

Every session is opened with default_transaction_read_only=on. Exit 0 when the
live grants match the matrix, 1 when they differ, 2 on usage or a read error.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

DATABASES = (
    "bifrost_dev",
    "bifrost_golden_source",
    "bifrost_prod",
    "bifrost_stg",
)
DML_ORDER = ("delete", "insert", "update")
TABLE_DML = {"a": "insert", "w": "update", "d": "delete"}
READ_ONLY_OPTIONS = "-c default_transaction_read_only=on -c statement_timeout=120000"

# Null-ACL defaults (PostgreSQL 17). A non-null ACL is used as written:
# owner rights that were revoked stay revoked.
_NULL_DEFAULTS = {
    "database": {"owner": {"C", "c", "T"}, "public": {"c", "T"}},
    "schema": {"owner": {"U", "C"}, "public": {"U"}},
    "table": {"owner": {"a", "r", "w", "d", "D", "x", "t", "m"}, "public": set()},
}
_SUPERUSER = {
    "database": {"C", "c", "T"},
    "schema": {"U", "C"},
    "table": {"a", "r", "w", "d", "D", "x", "t", "m"},
}


def parse_acl(text: str) -> list[tuple[str | None, set[str]]]:
    """Parse a PostgreSQL aclitem array. An empty grantee is PUBLIC.

    `*` after a privilege letter is WITH GRANT OPTION; the privilege still counts.
    """
    body = text.strip()
    if body.startswith("{") and body.endswith("}"):
        body = body[1:-1]
    if body == "":
        return []
    items: list[tuple[str | None, set[str]]] = []
    for raw in _split_acl_items(body):
        grantee, privs, _grantor = _parse_acl_item(raw)
        items.append((grantee, privs))
    return items


def _split_acl_items(body: str) -> list[str]:
    items: list[str] = []
    buf: list[str] = []
    quoted = False
    i = 0
    while i < len(body):
        ch = body[i]
        if ch == '"':
            if quoted and i + 1 < len(body) and body[i + 1] == '"':
                buf.append('"')
                i += 2
                continue
            quoted = not quoted
            i += 1
            continue
        if ch == "," and not quoted:
            items.append("".join(buf))
            buf = []
            i += 1
            continue
        buf.append(ch)
        i += 1
    if quoted:
        raise ValueError("unbalanced quote in acl: " + body)
    items.append("".join(buf))
    return items


def _parse_acl_item(raw: str) -> tuple[str | None, set[str], str]:
    # grantee=privs/grantor, grantee empty for PUBLIC. Names may contain '=' only
    # when they arrived quoted; the splitter already unquoted them.
    eq = raw.find("=")
    slash = raw.rfind("/")
    if eq < 0 or slash < eq:
        raise ValueError("malformed acl item: " + raw)
    grantee = raw[:eq] or None
    priv_text = raw[eq + 1 : slash]
    grantor = raw[slash + 1 :]
    privs: set[str] = set()
    i = 0
    while i < len(priv_text):
        privs.add(priv_text[i])
        if i + 1 < len(priv_text) and priv_text[i + 1] == "*":
            i += 2
        else:
            i += 1
    return grantee, privs, grantor


def inherited_roles(role: str, members: list[tuple[str, str, bool]]) -> set[str]:
    """Roles whose privileges `role` uses. inherit_option false does not walk."""
    parents: dict[str, set[str]] = {}
    for member, parent, inherit in members:
        if inherit:
            parents.setdefault(member, set()).add(parent)
    seen: set[str] = set()
    stack = [role]
    while stack:
        cur = stack.pop()
        for parent in parents.get(cur, ()):
            if parent not in seen:
                seen.add(parent)
                stack.append(parent)
    return seen


def effective_privileges(
    role: str,
    acl: str | None,
    *,
    kind: str,
    owner: str,
    superuser: bool,
    database_owner: str,
    members: list[tuple[str, str, bool]],
) -> set[str]:
    """Privilege letters this role has on one database, schema, or table."""
    if kind not in _NULL_DEFAULTS:
        raise ValueError("unknown acl kind: " + kind)
    if superuser:
        return set(_SUPERUSER[kind])
    who = {role} | inherited_roles(role, members)
    # In this database the owner stands in for pg_database_owner.
    if database_owner in who:
        who.add("pg_database_owner")
    granted: set[str] = set()
    if acl is None:
        defaults = _NULL_DEFAULTS[kind]
        if owner == "pg_database_owner":
            if role == database_owner:
                granted |= defaults["owner"]
        elif role == owner or owner in who:
            granted |= defaults["owner"]
        granted |= defaults["public"]
        return granted
    for grantee, privs in parse_acl(acl):
        if grantee is None or grantee in who:
            granted |= privs
    return granted


def _dml_set(letters: set[str]) -> set[str]:
    return {name for letter, name in TABLE_DML.items() if letter in letters}


def privileges_from_catalog(catalog: dict) -> dict:
    """Turn a catalog snapshot into the same shape the matrix uses.

    catalog keys: roles [{name, superuser}], members [(member, parent, inherit)],
    databases {name: {owner, acl}}, schemas {db: [{name, owner, acl}]},
    tables {db: [{schema, owner, acl}]}. acl None means a SQL NULL.
    """
    members = [(m, p, bool(inh)) for m, p, inh in catalog.get("members", ())]
    roles_in = {row["name"]: bool(row.get("superuser")) for row in catalog["roles"]}
    out_roles: dict[str, dict] = {}
    schema_names: dict[str, set[str]] = {}
    for role, is_super in roles_in.items():
        connect: set[str] = set()
        grants: dict[str, dict[str, dict]] = {}
        for db, meta in catalog["databases"].items():
            letters = effective_privileges(
                role,
                meta.get("acl"),
                kind="database",
                owner=meta["owner"],
                superuser=is_super,
                database_owner=meta["owner"],
                members=members,
            )
            if "c" in letters:
                connect.add(db)
            schema_grants: dict[str, dict] = {}
            for schema in catalog.get("schemas", {}).get(db, ()):
                s_letters = effective_privileges(
                    role,
                    schema.get("acl"),
                    kind="schema",
                    owner=schema["owner"],
                    superuser=is_super,
                    database_owner=meta["owner"],
                    members=members,
                )
                dml: set[str] = set()
                for table in catalog.get("tables", {}).get(db, ()):
                    if table["schema"] != schema["name"]:
                        continue
                    t_letters = effective_privileges(
                        role,
                        table.get("acl"),
                        kind="table",
                        owner=table["owner"],
                        superuser=is_super,
                        database_owner=meta["owner"],
                        members=members,
                    )
                    dml |= _dml_set(t_letters)
                schema_grants[schema["name"]] = {
                    "create": "C" in s_letters,
                    "dml": dml,
                }
            grants[db] = schema_grants
        out_roles[role] = {"superuser": is_super, "connect": connect, "grants": grants}
    for db, schemas in catalog.get("schemas", {}).items():
        schema_names[db] = {schema["name"] for schema in schemas}
    return {"roles": out_roles, "schemas": schema_names}


def load_matrix(text: str) -> dict:
    """Load the role-matrix YAML subset this file writes (no anchors, no tags)."""
    data = _parse_yaml(text)
    if not isinstance(data, dict):
        raise ValueError("matrix root must be a mapping")
    databases = list(data.get("databases") or [])
    schemas = {
        db: list(names) for db, names in (data.get("schemas") or {}).items()
    }
    roles: dict[str, dict] = {}
    for name, body in (data.get("roles") or {}).items():
        body = body or {}
        connect = set(body.get("connect") or [])
        grants: dict[str, dict[str, dict]] = {}
        for db, schema_map in (body.get("grants") or {}).items():
            grants[db] = {}
            for schema, cell in (schema_map or {}).items():
                cell = cell or {}
                grants[db][schema] = {
                    "create": bool(cell.get("create", False)),
                    "dml": set(cell.get("dml") or []),
                }
        roles[name] = {
            "superuser": bool(body.get("superuser", False)),
            "connect": connect,
            "grants": grants,
        }
    return {"databases": databases, "schemas": schemas, "roles": roles}


def compare(expected: dict, actual: dict) -> list[str]:
    """Lines describing drift. Empty means the live grants match the matrix."""
    drifts: list[str] = []
    exp_schemas = {db: set(names) for db, names in expected["schemas"].items()}
    act_schemas = actual["schemas"]
    for db in sorted(set(exp_schemas) | set(act_schemas)):
        for name in sorted(act_schemas.get(db, set()) - exp_schemas.get(db, set())):
            drifts.append(f"unexpected-schema database={db} schema={name}")
        for name in sorted(exp_schemas.get(db, set()) - act_schemas.get(db, set())):
            drifts.append(f"missing-schema database={db} schema={name}")
    exp_roles = expected["roles"]
    act_roles = actual["roles"]
    for name in sorted(set(act_roles) - set(exp_roles)):
        drifts.append(f"unexpected-role role={name}")
    for name in sorted(set(exp_roles) - set(act_roles)):
        drifts.append(f"missing-role role={name}")
    known_schemas = {
        db: exp_schemas.get(db, set()) & act_schemas.get(db, set())
        for db in exp_schemas
    }
    for name in sorted(set(exp_roles) & set(act_roles)):
        exp = exp_roles[name]
        act = act_roles[name]
        if bool(act.get("superuser")) != bool(exp.get("superuser")):
            drifts.append(
                "superuser role={role} expected={exp} actual={act}".format(
                    role=name,
                    exp=str(bool(exp.get("superuser"))).lower(),
                    act=str(bool(act.get("superuser"))).lower(),
                )
            )
        exp_connect = set(exp.get("connect") or [])
        act_connect = set(act.get("connect") or [])
        for db in sorted(act_connect - exp_connect):
            drifts.append(
                f"connect role={name} database={db} expected=false actual=true"
            )
        for db in sorted(exp_connect - act_connect):
            drifts.append(
                f"connect role={name} database={db} expected=true actual=false"
            )
        if exp.get("superuser"):
            continue
        for db, schema_names in sorted(known_schemas.items()):
            exp_db = (exp.get("grants") or {}).get(db, {})
            act_db = (act.get("grants") or {}).get(db, {})
            for schema in sorted(schema_names):
                exp_cell = exp_db.get(schema) or {"create": False, "dml": set()}
                act_cell = act_db.get(schema) or {"create": False, "dml": set()}
                if bool(exp_cell.get("create")) != bool(act_cell.get("create")):
                    drifts.append(
                        "schema role={role} database={db} schema={schema} "
                        "privilege=create expected={exp} actual={act}".format(
                            role=name,
                            db=db,
                            schema=schema,
                            exp=str(bool(exp_cell.get("create"))).lower(),
                            act=str(bool(act_cell.get("create"))).lower(),
                        )
                    )
                exp_dml = set(exp_cell.get("dml") or [])
                act_dml = set(act_cell.get("dml") or [])
                if exp_dml != act_dml:
                    drifts.append(
                        "schema role={role} database={db} schema={schema} "
                        "privilege=dml expected=[{exp}] actual=[{act}]".format(
                            role=name,
                            db=db,
                            schema=schema,
                            exp=_fmt_dml(exp_dml),
                            act=_fmt_dml(act_dml),
                        )
                    )
    return drifts


def _fmt_dml(names: set[str]) -> str:
    return ",".join(name for name in DML_ORDER if name in names)


def _parse_yaml(text: str) -> dict:
    lines = text.splitlines()
    root: dict = {}
    stack: list[tuple[int, object]] = [(-1, root)]

    def parent_for(indent: int) -> object:
        while stack and stack[-1][0] >= indent:
            stack.pop()
        if not stack:
            raise ValueError("yaml indent underflow")
        return stack[-1][1]

    def next_content(start: int) -> tuple[int, str] | None:
        for j in range(start, len(lines)):
            stripped = lines[j].strip()
            if stripped and not stripped.startswith("#"):
                return _indent(lines[j]), stripped
        return None

    i = 0
    while i < len(lines):
        raw = lines[i]
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            i += 1
            continue
        indent = _indent(raw)
        container = parent_for(indent)
        if stripped.startswith("- "):
            if not isinstance(container, list):
                raise ValueError("list item outside a list: " + stripped)
            container.append(_scalar(stripped[2:].strip()))
            i += 1
            continue
        if ":" not in stripped:
            raise ValueError("expected key: " + stripped)
        if not isinstance(container, dict):
            raise ValueError("key outside a mapping: " + stripped)
        key, _, rest = stripped.partition(":")
        key = key.strip()
        rest = rest.strip()
        if rest == "":
            peeked = next_content(i + 1)
            if peeked is None or peeked[0] <= indent:
                container[key] = {}
                i += 1
                continue
            child: object = [] if peeked[1].startswith("- ") else {}
            container[key] = child
            stack.append((indent, child))
            i += 1
            continue
        if rest.startswith("["):
            container[key] = _flow_list(rest)
        else:
            container[key] = _scalar(rest)
        i += 1
    return root


def _indent(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def _scalar(token: str):
    if token in ("true", "false"):
        return token == "true"
    if len(token) >= 2 and token[0] == token[-1] and token[0] in ("'", '"'):
        return token[1:-1]
    if token.isdigit():
        return int(token)
    return token


def _flow_list(token: str) -> list:
    if not (token.startswith("[") and token.endswith("]")):
        raise ValueError("expected a flow list: " + token)
    inner = token[1:-1].strip()
    if inner == "":
        return []
    return [_scalar(part.strip()) for part in inner.split(",")]


def _psql(database: str, sql: str, *, via: str) -> list[str]:
    if via == "kubectl":
        pod = _primary_pod()
        cmd = [
            "kubectl",
            "-n",
            "data",
            "exec",
            "-i",
            pod,
            "-c",
            "postgres",
            "--",
            "env",
            "PGOPTIONS=" + READ_ONLY_OPTIONS,
            "psql",
            "-U",
            "postgres",
            "-d",
            database,
            "-X",
            "-v",
            "ON_ERROR_STOP=1",
            "-At",
            "-c",
            sql,
        ]
        env = os.environ.copy()
    elif via == "psql":
        cmd = [
            "psql",
            "-d",
            database,
            "-X",
            "-v",
            "ON_ERROR_STOP=1",
            "-At",
            "-c",
            sql,
        ]
        env = os.environ.copy()
        env["PGOPTIONS"] = READ_ONLY_OPTIONS
    else:
        raise SystemExit(2)
    proc = subprocess.run(cmd, env=env, capture_output=True, text=True)
    if proc.returncode != 0:
        sys.stderr.write(proc.stderr)
        raise SystemExit(2)
    return [line for line in proc.stdout.splitlines() if line != ""]


_PRIMARY: str | None = None


def _primary_pod() -> str:
    global _PRIMARY
    if _PRIMARY:
        return _PRIMARY
    env = os.environ.copy()
    env.setdefault("KUBECONFIG", str(Path.home() / ".kube" / "bifrost-k3s.yaml"))
    proc = subprocess.run(
        [
            "kubectl",
            "-n",
            "data",
            "get",
            "pod",
            "-l",
            "cnpg.io/cluster=bifrost-postgres,cnpg.io/instanceRole=primary",
            "-o",
            "jsonpath={.items[0].metadata.name}",
        ],
        env=env,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0 or not proc.stdout.strip():
        sys.stderr.write(proc.stderr or "no CNPG primary pod\n")
        raise SystemExit(2)
    _PRIMARY = proc.stdout.strip()
    return _PRIMARY


_CATALOG_SQL = """
SELECT 'ROLE' || E'\\t' || rolname || E'\\t' || rolsuper::text
  FROM pg_roles WHERE rolcanlogin
UNION ALL
SELECT 'MEM' || E'\\t' || member.rolname || E'\\t' || parent.rolname || E'\\t' || m.inherit_option::text
  FROM pg_auth_members m
  JOIN pg_roles member ON member.oid = m.member
  JOIN pg_roles parent ON parent.oid = m.roleid
UNION ALL
SELECT 'DB' || E'\\t' || datname || E'\\t' || pg_get_userbyid(datdba) || E'\\t' || coalesce(datacl::text, '<null>')
  FROM pg_database
 WHERE datname IN ('bifrost_dev','bifrost_golden_source','bifrost_prod','bifrost_stg')
""".strip()

_OBJECTS_SQL = """
SELECT 'SCHEMA' || E'\\t' || nspname || E'\\t' || pg_get_userbyid(nspowner) || E'\\t' || coalesce(nspacl::text, '<null>')
  FROM pg_namespace
 WHERE nspname NOT LIKE 'pg\\_%' ESCAPE '\\' AND nspname <> 'information_schema'
UNION ALL
SELECT 'TABLE' || E'\\t' || n.nspname || E'\\t' || pg_get_userbyid(c.relowner) || E'\\t' || coalesce(c.relacl::text, '<null>')
  FROM pg_class c
  JOIN pg_namespace n ON n.oid = c.relnamespace
 WHERE c.relkind IN ('r','p','v','m','f')
   AND n.nspname NOT LIKE 'pg\\_%' ESCAPE '\\'
   AND n.nspname <> 'information_schema'
""".strip()


def read_catalog(*, via: str) -> dict:
    """Read catalog ACLs. Connects to bifrost_dev first: pg_database is global."""
    roles = []
    members = []
    databases: dict[str, dict] = {}
    for line in _psql("bifrost_dev", _CATALOG_SQL, via=via):
        parts = line.split("\t")
        kind = parts[0]
        if kind == "ROLE":
            roles.append({"name": parts[1], "superuser": parts[2] == "true"})
        elif kind == "MEM":
            members.append((parts[1], parts[2], parts[3] == "true"))
        elif kind == "DB":
            databases[parts[1]] = {
                "owner": parts[2],
                "acl": None if parts[3] == "<null>" else parts[3],
            }
    schemas: dict[str, list] = {}
    tables: dict[str, list] = {}
    for db in DATABASES:
        schemas[db] = []
        tables[db] = []
        for line in _psql(db, _OBJECTS_SQL, via=via):
            kind, name, owner, acl = line.split("\t", 3)
            parsed = None if acl == "<null>" else acl
            if kind == "SCHEMA":
                schemas[db].append({"name": name, "owner": owner, "acl": parsed})
            elif kind == "TABLE":
                tables[db].append({"schema": name, "owner": owner, "acl": parsed})
    return {
        "roles": roles,
        "members": members,
        "databases": databases,
        "schemas": schemas,
        "tables": tables,
    }


def main(argv: list[str]) -> int:
    matrix_path = ""
    via = "psql"
    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg == "--matrix":
            i += 1
            if i >= len(argv):
                sys.stderr.write("role-matrix: --matrix needs a file\n")
                return 2
            matrix_path = argv[i]
        elif arg == "--via":
            i += 1
            if i >= len(argv) or argv[i] not in ("kubectl", "psql"):
                sys.stderr.write("role-matrix: --via kubectl|psql\n")
                return 2
            via = argv[i]
        elif arg in ("-h", "--help"):
            sys.stderr.write(
                "usage: check_role_matrix.py --matrix expected.yaml [--via kubectl|psql]\n"
            )
            return 0
        else:
            sys.stderr.write("role-matrix: unknown argument: " + arg + "\n")
            return 2
        i += 1
    if not matrix_path:
        sys.stderr.write("role-matrix: --matrix is required\n")
        return 2
    expected = load_matrix(Path(matrix_path).read_text())
    actual = privileges_from_catalog(read_catalog(via=via))
    drifts = compare(expected, actual)
    print(f"role-matrix: {len(drifts)} difference(s)")
    for line in drifts:
        print(line)
    return 1 if drifts else 0


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv[1:]))
    except BrokenPipeError:
        raise SystemExit(1)
