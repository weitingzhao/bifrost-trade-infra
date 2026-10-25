#!/usr/bin/env python3
"""PV0 offline contract validator; it never imports or adopts a runtime plan."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

DEFAULT = Path(__file__).resolve().parents[1] / "work/multi-agent/PLAN-VIEW-R4-v1.json"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def fields(value, expected, label):
    require(isinstance(value, dict), f"{label}: expected object")
    require(set(value) == set(expected.split()), f"{label}: unknown or missing fields")


def text(value, label):
    require(isinstance(value, str) and bool(value.strip()), f"{label}: empty text")


def array(value, label):
    require(isinstance(value, list), f"{label}: expected array")


def validate(doc):
    fields(doc, "v kind tenant root plan_version adoption source_commit decisions sources items", "artifact")
    require(type(doc["v"]) is int and doc["v"] == 1 and doc["kind"] == "agentrt.plan_view/v1", "unknown protocol")
    require(doc["tenant"] == "dev" and doc["root"] == "R4", "PV0 only maps tenant dev / root R4")
    require(type(doc["plan_version"]) is int and doc["plan_version"] >= 1, "invalid plan version")
    require(doc["adoption"] == "proposed", "offline artifact cannot claim runtime adoption")
    text(doc["source_commit"], "source_commit")
    require(doc["decisions"] == {"D-PV1": "A", "D-PV2": "A", "D-PV3": "A"}, "unexpected decisions")
    array(doc["sources"], "sources")
    sources = {}
    for source in doc["sources"]:
        fields(source, "id path locator basis", "source")
        for key in source:
            text(source[key], "source." + key)
        require(source["id"] not in sources, "duplicate source")
        sources[source["id"]] = source

    def refs(values, label):
        array(values, label)
        require(bool(values) and all(isinstance(v, str) and v in sources for v in values), f"{label}: dangling source")

    array(doc["items"], "items")
    require(0 < len(doc["items"]) <= 500, "node limit")
    items, orders = {}, set()
    for item in doc["items"]:
        fields(item, "plan_node_id parent ordinal title work_id lane_kind mainline_order anchor_node_id milestones depends_on next_responsible acceptance estimate bindings evidence", "item")
        node = item["plan_node_id"]
        text(node, "node")
        require(node not in items, "duplicate node")
        items[node] = item
        for key in ("title", "work_id"):
            text(item[key], key)
        require(type(item["ordinal"]) is int and item["ordinal"] > 0, "invalid ordinal")
        require(item["lane_kind"] in ("mainline", "branch", "support"), "invalid lane")
        if item["lane_kind"] == "mainline":
            order = item["mainline_order"]
            require(type(order) is int and order > 0 and order not in orders, "duplicate/invalid mainline order")
            orders.add(order)
            require(item["anchor_node_id"] is None, "mainline has an anchor")
        else:
            require(item["mainline_order"] is None, "support/branch has mainline order")
        array(item["milestones"], "milestones")
        require(item["milestones"] and all(isinstance(m, str) and m for m in item["milestones"]), "invalid milestones")
        require(len(set(item["milestones"])) == len(item["milestones"]), "duplicate milestone")
        fields(item["next_responsible"], "kind actor_ref seat_ref provider", "responsible")
        require(item["next_responsible"]["kind"] in ("owner", "crew_seat", "vendor_executor", "review"), "invalid responsibility")
        require(item["next_responsible"]["actor_ref"] or item["next_responsible"]["seat_ref"], "missing responsible identity")
        fields(item["estimate"], "work_days review_rounds source confidence reason", "estimate")
        estimate = item["estimate"]
        require(estimate["confidence"] in ("low", "medium"), "uncalibrated confidence")
        require(type(estimate["review_rounds"]) is int and estimate["review_rounds"] >= 1, "review omitted")
        days = estimate["work_days"]
        require(days is None or (isinstance(days, list) and len(days) == 2 and
                all(type(n) in (int, float) for n in days) and 0 <= days[0] <= days[1]), "invalid estimate range")
        refs([estimate["source"]], "estimate")
        text(estimate["reason"], "estimate reason")
        # Runtime IDs are unknown offline. PV1 resolves logical IDs and validates
        # tenant/step ownership transactionally before it can add bindings.
        require(item["bindings"] == [], "PV0 cannot assert unverified runtime bindings")
        array(item["acceptance"], "acceptance")
        require(item["acceptance"], "missing acceptance")
        acceptance_ids = set()
        for acceptance in item["acceptance"]:
            fields(acceptance, "id milestone criterion rule_ref evidence_required target_environment sources", "acceptance")
            require(acceptance["id"] not in acceptance_ids, "duplicate acceptance")
            acceptance_ids.add(acceptance["id"])
            require(acceptance["milestone"] in item["milestones"], "acceptance milestone missing")
            for key in ("id", "criterion", "rule_ref", "target_environment"):
                text(acceptance[key], key)
            array(acceptance["evidence_required"], "evidence_required")
            require(acceptance["evidence_required"], "no evidence requirements")
            for value in acceptance["evidence_required"]:
                text(value, "evidence requirement")
            refs(acceptance["sources"], "acceptance")
        array(item["evidence"], "evidence")
        require(item["evidence"], "missing current evidence")
        for evidence in item["evidence"]:
            fields(evidence, "source milestone classification assessment observed_at live_verified", "evidence")
            refs([evidence["source"]], "evidence")
            require(evidence["milestone"] in item["milestones"], "evidence milestone missing")
            require(evidence["classification"] in ("repository_evidence", "legacy_evidence", "owner_statement"), "invalid evidence class")
            require(evidence["live_verified"] is False, "offline evidence claims live verification")
            text(evidence["assessment"], "assessment")
            text(evidence["observed_at"], "observed_at")

    require({f"4.{i}" for i in range(1, 11)} <= set(items), "round 4 mapping incomplete")
    require(orders == set(range(1, len(orders) + 1)), "mainline order has gaps")
    graph, parents = {}, {}
    for node, item in items.items():
        parent = item["parent"]
        require(parent == doc["root"] or parent in items, "dangling parent")
        parents[node] = [] if parent == doc["root"] else [parent]
        if item["lane_kind"] != "mainline":
            anchor = item["anchor_node_id"]
            require(anchor in items and items[anchor]["lane_kind"] == "mainline", "dangling/non-mainline anchor")
        graph[node] = []
        array(item["depends_on"], "depends_on")
        edges = set()
        for edge in item["depends_on"]:
            fields(edge, "root node milestone required_for relation reason sources", "edge")
            require(edge["root"] == doc["root"] and edge["node"] in items, "dangling/cross-root dependency")
            require(edge["node"] != node, "self dependency")
            require(edge["relation"] in ("blocks", "related"), "invalid relation")
            require(edge["milestone"] in items[edge["node"]]["milestones"], "missing prerequisite milestone")
            require(edge["required_for"] in item["milestones"], "missing target milestone")
            key = tuple(edge[k] for k in ("node", "milestone", "required_for", "relation"))
            require(key not in edges, "duplicate edge")
            edges.add(key)
            text(edge["reason"], "edge reason")
            refs(edge["sources"], "edge")
            if edge["relation"] == "blocks":
                graph[node].append(edge["node"])

    def acyclic(graph):
        visiting, visited = set(), set()

        def visit(node):
            require(node not in visiting, "cycle detected")
            if node in visited:
                return
            visiting.add(node)
            for dependency in graph[node]:
                visit(dependency)
            visiting.remove(node)
            visited.add(node)

        for node in graph:
            visit(node)

    acyclic(graph)
    acyclic(parents)
    return len(items)


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, f"duplicate JSON key: {key}")
        result[key] = value
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("artifact", nargs="?", type=Path, default=DEFAULT)
    args = parser.parse_args()
    try:
        doc = json.loads(args.artifact.read_text(), object_pairs_hook=unique_object)
        count = validate(doc)
    except (OSError, ValueError, TypeError, KeyError) as error:
        parser.exit(1, f"FAIL: {error}\n")
    print(f"PASS: {count} nodes; references and blocking graph valid; not adopted")


if __name__ == "__main__":
    main()
