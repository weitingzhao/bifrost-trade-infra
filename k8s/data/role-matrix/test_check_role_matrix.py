"""ACL parsing and matrix comparison. Fixtures are invented; no cluster."""

import unittest
from pathlib import Path

import check_role_matrix as crm

HERE = Path(__file__).resolve().parent


class ParseAclTests(unittest.TestCase):
    def test_public_connect_expands_to_every_role(self):
        letters = crm.effective_privileges(
            "app",
            "{=c/postgres,owner=CTc/postgres}",
            kind="database",
            owner="owner",
            superuser=False,
            database_owner="owner",
            members=[],
        )
        self.assertIn("c", letters)

    def test_public_temp_is_not_connect(self):
        letters = crm.effective_privileges(
            "app",
            "{=T/bifrost,bifrost=CTc/bifrost}",
            kind="database",
            owner="bifrost",
            superuser=False,
            database_owner="bifrost",
            members=[],
        )
        self.assertIn("T", letters)
        self.assertNotIn("c", letters)

    def test_grant_option_star_still_counts(self):
        letters = crm.effective_privileges(
            "app",
            "{app=C*/postgres}",
            kind="schema",
            owner="postgres",
            superuser=False,
            database_owner="postgres",
            members=[],
        )
        self.assertIn("C", letters)

    def test_inherit_yes_and_no(self):
        acl = "{writers=c/postgres}"
        inherited = crm.effective_privileges(
            "app",
            acl,
            kind="database",
            owner="postgres",
            superuser=False,
            database_owner="postgres",
            members=[("app", "writers", True)],
        )
        blocked = crm.effective_privileges(
            "app",
            acl,
            kind="database",
            owner="postgres",
            superuser=False,
            database_owner="postgres",
            members=[("app", "writers", False)],
        )
        self.assertIn("c", inherited)
        self.assertNotIn("c", blocked)

    def test_inherit_is_transitive(self):
        letters = crm.effective_privileges(
            "app",
            "{admins=c/postgres}",
            kind="database",
            owner="postgres",
            superuser=False,
            database_owner="postgres",
            members=[("app", "writers", True), ("writers", "admins", True)],
        )
        self.assertIn("c", letters)

    def test_truncate_letter_is_not_delete(self):
        self.assertEqual(crm._dml_set({"D", "r"}), set())
        self.assertEqual(crm._dml_set({"d", "a"}), {"delete", "insert"})

    def test_pg_database_owner_reaches_the_database_owner(self):
        acl = "{pg_database_owner=UC/pg_database_owner,=U/pg_database_owner}"
        owner_letters = crm.effective_privileges(
            "bifrost",
            acl,
            kind="schema",
            owner="pg_database_owner",
            superuser=False,
            database_owner="bifrost",
            members=[],
        )
        other_letters = crm.effective_privileges(
            "analytics_writer",
            acl,
            kind="schema",
            owner="pg_database_owner",
            superuser=False,
            database_owner="bifrost",
            members=[],
        )
        self.assertIn("C", owner_letters)
        self.assertNotIn("C", other_letters)
        self.assertIn("U", other_letters)

    def test_null_table_acl_defaults_to_owner_dml(self):
        catalog = {
            "roles": [
                {"name": "owner", "superuser": False},
                {"name": "other", "superuser": False},
            ],
            "members": [],
            "databases": {"bifrost_dev": {"owner": "owner", "acl": "{=T/owner,owner=CTc/owner}"}},
            "schemas": {
                "bifrost_dev": [{"name": "public", "owner": "owner", "acl": "{owner=UC/owner}"}]
            },
            "tables": {"bifrost_dev": [{"schema": "public", "owner": "owner", "acl": None}]},
        }
        actual = crm.privileges_from_catalog(catalog)
        self.assertEqual(
            actual["roles"]["owner"]["grants"]["bifrost_dev"]["public"]["dml"],
            {"insert", "update", "delete"},
        )
        self.assertEqual(actual["roles"]["other"]["grants"]["bifrost_dev"]["public"]["dml"], set())
        self.assertNotIn("bifrost_dev", actual["roles"]["other"]["connect"])


class CompareTests(unittest.TestCase):
    def test_schema_dml_is_the_union_across_tables(self):
        catalog = {
            "roles": [{"name": "app", "superuser": False}],
            "members": [],
            "databases": {
                "bifrost_golden_source": {
                    "owner": "bifrost",
                    "acl": "{=T/bifrost,bifrost=CTc/bifrost,app=c/bifrost}",
                }
            },
            "schemas": {
                "bifrost_golden_source": [
                    {"name": "raw_market", "owner": "data_writer", "acl": "{data_writer=UC/data_writer}"}
                ]
            },
            "tables": {
                "bifrost_golden_source": [
                    {
                        "schema": "raw_market",
                        "owner": "data_writer",
                        "acl": "{data_writer=arwdDxtm/data_writer,app=a/data_writer}",
                    },
                    {
                        "schema": "raw_market",
                        "owner": "data_writer",
                        "acl": "{data_writer=arwdDxtm/data_writer,app=w/data_writer}",
                    },
                ]
            },
        }
        actual = crm.privileges_from_catalog(catalog)
        expected = {
            "schemas": {"bifrost_golden_source": ["raw_market"]},
            "roles": {
                "app": {
                    "superuser": False,
                    "connect": {"bifrost_golden_source"},
                    "grants": {},
                }
            },
        }
        drifts = crm.compare(expected, actual)
        self.assertEqual(
            drifts,
            [
                "schema role=app database=bifrost_golden_source schema=raw_market "
                "privilege=dml expected=[] actual=[insert,update]"
            ],
        )

    def test_superuser_skips_schema_cells_but_not_connect(self):
        expected = {
            "schemas": {"bifrost_dev": ["public"]},
            "roles": {
                "postgres": {
                    "superuser": True,
                    "connect": {"bifrost_dev"},
                    "grants": {},
                }
            },
        }
        actual = {
            "schemas": {"bifrost_dev": {"public"}},
            "roles": {
                "postgres": {
                    "superuser": True,
                    "connect": set(),
                    "grants": {
                        "bifrost_dev": {"public": {"create": True, "dml": {"insert", "update", "delete"}}}
                    },
                }
            },
        }
        drifts = crm.compare(expected, actual)
        self.assertEqual(
            drifts,
            ["connect role=postgres database=bifrost_dev expected=true actual=false"],
        )

    def test_matrix_denies_the_known_d13_holes(self):
        matrix = crm.load_matrix((HERE / "expected.yaml").read_text())
        writer = matrix["roles"]["analytics_writer"]
        gs = writer["grants"]["bifrost_golden_source"]
        for schema in ("raw_market", "raw_broker", "ops_jobs"):
            self.assertNotIn(schema, gs)
        self.assertEqual(writer["connect"], {"bifrost_golden_source"})
        self.assertEqual(matrix["roles"]["market_reader"]["connect"], set())
        self.assertEqual(matrix["roles"]["market_reader"]["grants"], {})
        feedback = matrix["roles"]["feedback_writer"]["grants"]["bifrost_golden_source"]["ops_feedback"]
        self.assertEqual(feedback["dml"], {"insert", "update"})
        self.assertFalse(feedback["create"])
        self.assertEqual(matrix["roles"]["streaming_replica"]["connect"], set())


if __name__ == "__main__":
    unittest.main()
