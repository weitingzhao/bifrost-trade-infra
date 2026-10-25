"""PV0 contract and deliberately broken graphs; no runtime/network."""
import copy
import json
from pathlib import Path
import unittest

from validate_plan_view import DEFAULT, unique_object, validate


class PlanViewTest(unittest.TestCase):
    def setUp(self):
        self.doc = json.loads(DEFAULT.read_text())

    def node(self, name):
        return next(i for i in self.doc["items"] if i["plan_node_id"] == name)

    def test_mapping_and_local_sources(self):
        self.assertEqual(validate(self.doc), 12)
        root = Path(__file__).resolve().parents[2]
        for source in self.doc["sources"]:
            self.assertTrue((root / source["path"]).is_file(), source)
        path = sorted((i for i in self.doc["items"] if i["lane_kind"] == "mainline"), key=lambda i: i["mainline_order"])
        self.assertEqual([i["plan_node_id"] for i in path], ["4.1", "4.2", "4.4", "4.10"])
        self.assertEqual(len(self.node("4.10")["acceptance"]), 5)

    def test_design_and_parallel_work_are_not_serialized(self):
        for name in ("4.3", "4.4"):
            blocking = [e for e in self.node(name)["depends_on"] if e["relation"] == "blocks"]
            self.assertEqual([(e["node"], e["milestone"], e["required_for"]) for e in blocking], [("4.1", "prod", "implementation")])
        for name in ("4.1", "4.5.pv", "4.6"):
            self.assertFalse(any(e["relation"] == "blocks" for e in self.node(name)["depends_on"]))

    def test_cycle_is_refused(self):
        edge = copy.deepcopy(self.node("4.2")["depends_on"][0])
        edge.update(node="4.2", milestone="accepted")
        self.node("4.1")["depends_on"].append(edge)
        with self.assertRaisesRegex(ValueError, "cycle"):
            validate(self.doc)

    def test_dangling_node_milestone_and_source_are_refused(self):
        for field, value in (("node", "4.404"), ("milestone", "missing"), ("root", "R3"), ("sources", ["missing"])):
            with self.subTest(field=field):
                doc = copy.deepcopy(self.doc)
                doc["items"][1]["depends_on"][0][field] = value
                with self.assertRaises(ValueError):
                    validate(doc)

    def test_duplicate_order_self_link_unknown_field_and_version(self):
        cases = [lambda d: d["items"][1].update(mainline_order=1),
                 lambda d: d["items"][1]["depends_on"][0].update(node="4.2"),
                 lambda d: d["items"][0].update(execution="done"),
                 lambda d: d.update(v=2),
                 lambda d: d.update(adoption="adopted"),
                 lambda d: d["items"][0]["evidence"][0].update(live_verified=True),
                 lambda d: d["items"][0].update(parent="4.1"),
                 lambda d: d["items"][2].update(anchor_node_id="missing")]
        for change in cases:
            doc = copy.deepcopy(self.doc)
            change(doc)
            with self.assertRaises(ValueError):
                validate(doc)

    def test_related_links_do_not_create_false_cycles(self):
        edge = copy.deepcopy(self.node("4.2")["depends_on"][0])
        edge.update(node="4.2", milestone="accepted", relation="related")
        self.node("4.1")["depends_on"].append(edge)
        validate(self.doc)

    def test_duplicate_json_key_is_refused(self):
        with self.assertRaisesRegex(ValueError, "duplicate JSON key"):
            json.loads('{"v":1,"v":2}', object_pairs_hook=unique_object)


if __name__ == "__main__":
    unittest.main()
