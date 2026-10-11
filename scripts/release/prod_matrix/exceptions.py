"""Exception loading and exact matching. Expired rows stay loaded and do not match."""

from __future__ import annotations

from datetime import date, datetime, timezone

from canon import REQUEST_FAMILY, MatrixExit


def parse_today(value: str | None) -> date:
    if not value:
        return datetime.now(timezone.utc).date()
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        raise MatrixExit(2, f"--today: invalid date {value!r}") from None


def prepare(exceptions: list[dict], today: date) -> list[dict]:
    prepared = []
    for index, row in enumerate(exceptions):
        if row["request_family"] != REQUEST_FAMILY:
            raise MatrixExit(2, f"prod_write_exceptions.json: exceptions[{index}].request_family: only authz is valid")
        try:
            expires = datetime.strptime(row["expires"], "%Y-%m-%d").date()
        except ValueError:
            raise MatrixExit(2, f"prod_write_exceptions.json: exceptions[{index}].expires: invalid date") from None
        item = dict(row)
        item["expired"] = expires < today
        prepared.append(item)
    return prepared


def _same_context(left: dict, right: dict) -> bool:
    return (
        left["kind"] == right["kind"]
        and left["user"] == right["user"]
        and list(left["groups"]) == list(right["groups"])
        and left["uid"] == right["uid"]
        and left["extra"] == right["extra"]
        and left["source"] == right["source"]
    )


def matches(exception: dict, ctx: dict, question: dict) -> bool:
    if exception.get("expired"):
        return False
    if not _same_context(exception["identity"], ctx):
        return False
    namespace = "" if question.get("scope") == "cluster" else question["namespace"]
    exc_namespace = "" if exception["scope"] == "cluster" else exception["namespace"]
    return (
        exception["group"] == question["group"]
        and exception["resource"] == question["resource"]
        and exception["subresource"] == question["subresource"]
        and exception["scope"] == question["scope"]
        and exc_namespace == namespace
        and exception["name"] == question["name"]
        and exception["verb"] == question["verb"]
        and exception["request_family"] == REQUEST_FAMILY
    )


def match_risk(exception: dict, ctx: dict) -> bool:
    if exception.get("expired"):
        return False
    if not _same_context(exception["identity"], ctx):
        return False
    return (
        exception["group"] == ""
        and exception["resource"] == ""
        and exception["subresource"] == ""
        and exception["name"] == ""
        and exception["verb"] == ""
        and exception["request_family"] == REQUEST_FAMILY
    )


def covers_cell(entry: dict, cell: dict) -> bool:
    if entry["group"] != cell["group"] or entry["resource"] != cell["resource"]:
        return False
    if entry["subresource"] != cell["subresource"]:
        return False
    if entry["scope"] != cell["scope"]:
        return False
    if entry["namespace"] == "*":
        return True
    return entry["namespace"] == cell["namespace"]


def cells_of(resources: list[dict], namespaces: list[str]) -> list[dict]:
    cells = []
    seen = set()
    for resource in resources:
        scopes = [("cluster", "")] if not resource["namespaced"] else [("namespaced", ns) for ns in namespaces]
        for scope, namespace in scopes:
            key = (resource["group"], resource["resource"], resource["subresource"], scope, namespace)
            if key in seen:
                continue
            seen.add(key)
            cells.append(
                {
                    "group": resource["group"],
                    "resource": resource["resource"],
                    "subresource": resource["subresource"],
                    "scope": scope,
                    "namespace": namespace,
                    "named_subresource": resource["named_subresource"],
                }
            )
    cells.sort(key=lambda item: (item["group"], item["namespace"], item["resource"], item["subresource"]))
    return cells


def questions_covering(questions: list[dict], cell: dict) -> list[dict]:
    found = []
    for question in questions:
        if question.get("wildcard"):
            continue
        if question["group"] != cell["group"] or question["resource"] != cell["resource"]:
            continue
        if question["subresource"] != cell["subresource"] or question["scope"] != cell["scope"]:
            continue
        namespace = "" if question["scope"] == "cluster" else question["namespace"]
        if namespace != cell["namespace"]:
            continue
        found.append(question)
    return found


def surface_reason(cell: dict, questions: list[dict], nontargets: list[dict]) -> str | None:
    """At most one reason per cell. Named subresources use the third reason when unasked."""
    if any(covers_cell(entry, cell) for entry in nontargets):
        return None
    covering = questions_covering(questions, cell)
    if not covering:
        if cell["named_subresource"]:
            return "named-subresource-not-asked"
        return "not-asked"
    if all(question["name"] == "" for question in covering):
        return "names-not-enumerated"
    return None


def target_namespaces(questions: list[dict]) -> list[str]:
    found = set()
    for question in questions:
        if question.get("scope") == "namespaced" and question.get("namespace"):
            found.add(question["namespace"])
    return sorted(found)


def asked_pairs(questions: list[dict]) -> set[tuple[str, str, str]]:
    return {(question["group"], question["resource"], question["subresource"]) for question in questions if not question.get("wildcard")}


def assert_asked_discovered(questions: list[dict], resources: list[dict]) -> None:
    discovered = {(item["group"], item["resource"], item["subresource"]) for item in resources}
    missing = sorted(pair for pair in (asked_pairs(questions) - discovered) if pair[2])
    if missing:
        group, resource, sub = missing[0]
        raise MatrixExit(2, f"bundle: missing a subresource: {group}/{resource}/{sub}")
