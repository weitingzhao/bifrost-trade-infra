"""W-31 offline contracts: isolation, image identity and on-demand migration."""
from pathlib import Path
import subprocess
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[1]


def docs(path):
    return list(yaml.safe_load_all((ROOT / path).read_text()))


class AgentRuntimeInfraTests(unittest.TestCase):
    def test_rendered_migration_and_redis_contracts(self):
        for env in ("prod", "stg"):
            namespace = "bifrost-platform-" + env
            rendered = yaml.safe_load_all(subprocess.check_output(
                ["kubectl", "kustomize", "k8s/overlays/platform-" + env], cwd=ROOT, text=True))
            objects = {(d["kind"], d["metadata"]["name"]): d for d in rendered}
            api = objects["Deployment", "platform-api"]["spec"]["template"]["spec"]["containers"][0]
            cron = objects["CronJob", "agentrt-migrate"]
            self.assertEqual(cron["metadata"]["namespace"], namespace)
            self.assertTrue(cron["spec"]["suspend"])
            pod = cron["spec"]["jobTemplate"]["spec"]["template"]["spec"]
            self.assertEqual(pod["serviceAccountName"], "default")
            self.assertFalse(pod["automountServiceAccountToken"])
            self.assertEqual(pod["initContainers"][0]["name"], "wait-pg")
            self.assertGreaterEqual(cron["spec"]["jobTemplate"]["spec"]["activeDeadlineSeconds"], 840)
            container = pod["containers"][0]
            self.assertEqual(container["image"], api["image"])
            self.assertEqual(container["command"], ["/usr/local/bin/platform-api"])
            self.assertEqual(container["args"], ["agentrt-migrate"])
            values = {e["name"]: e.get("value") for e in container["env"]}
            self.assertEqual(values["AGENTRT_ENV"], env)
            self.assertEqual(values["PGUSER"], "agentrt_owner_" + env)
            self.assertEqual(values["PGDATABASE"], "bifrost_platform" + ("" if env == "prod" else "_" + env))
            self.assertEqual(values["PGHOST"], "bifrost-postgres-rw.data.svc.cluster.local")
            self.assertEqual(values["PGSSLMODE"], "require")
            password = next(e for e in container["env"] if e["name"] == "PGPASSWORD")
            self.assertEqual(password["valueFrom"]["secretKeyRef"], {"name": "agentrt-db-owner", "key": "password"})
            redis = objects["Deployment", "redis-agents"]
            self.assertEqual(redis["spec"]["replicas"], 1)
            self.assertEqual(redis["spec"]["strategy"]["type"], "Recreate")
            r = redis["spec"]["template"]["spec"]["containers"][0]
            flags = dict(zip(r["args"][::2], r["args"][1::2]))
            self.assertEqual(flags["--appendonly"], "yes")
            self.assertEqual(flags["--appendfsync"], "everysec")
            self.assertEqual(flags["--maxmemory"], "256mb")
            self.assertEqual(flags["--maxmemory-policy"], "noeviction")
            self.assertEqual(flags["--requirepass"], "$(REDIS_PASSWORD)")
            self.assertEqual(r["volumeMounts"], [{"name": "data", "mountPath": "/data"}])
            self.assertEqual(objects["PersistentVolumeClaim", "redis-agents"]["spec"]["resources"]["requests"]["storage"], "1Gi")
            self.assertEqual(objects["Service", "redis-agents"]["spec"]["type"], "ClusterIP")
            self.assertFalse(any(d["kind"] == "Secret" for d in objects.values()))
            peers = objects["NetworkPolicy", "redis-agents-ingress"]["spec"]["ingress"][0]["from"]
            self.assertEqual(len(peers), 1)
            self.assertNotIn("namespaceSelector", peers[0])
            expr = peers[0]["podSelector"]["matchExpressions"]
            self.assertEqual(expr, [{"key": "app.kubernetes.io/name", "operator": "In", "values": ["platform-api", "platform-workers"]}])

    def test_postgres_peers_pair_namespace_and_pod_selectors(self):
        policy = next(d for d in docs("k8s/data/postgres-ingress-network-policy.yaml")
                      if d["metadata"]["name"] == "postgres-agentrt-ingress")
        rule = policy["spec"]["ingress"][0]
        self.assertEqual(rule["ports"], [{"protocol": "TCP", "port": 5432}])
        self.assertEqual(len(rule["from"]), 2)
        self.assertEqual({p["namespaceSelector"]["matchLabels"]["kubernetes.io/metadata.name"] for p in rule["from"]},
                         {"bifrost-platform-prod", "bifrost-platform-stg"})
        for peer in rule["from"]:
            self.assertEqual(set(peer["podSelector"]["matchExpressions"][0]["values"]),
                             {"platform-api", "platform-workers", "agentrt-migrate"})

    def test_backup_and_database_ownership(self):
        databases = {d["spec"]["name"]: d for d in docs("k8s/data/databases.yaml")}
        for env in ("prod", "stg", "dev"):
            db = "bifrost_platform" + ("" if env == "prod" else "_" + env)
            self.assertEqual(databases[db]["spec"]["owner"], "agentrt_owner_" + env)
            self.assertEqual(databases[db]["metadata"]["labels"]["bifrost.io/role"], "agentrt")
        cron = docs("k8s/data/logical-backup/cronjob-backup.yaml")[0]
        env = cron["spec"]["jobTemplate"]["spec"]["template"]["spec"]["containers"][0]["env"]
        targets = next(e["value"] for e in env if e["name"] == "TARGETS").split()
        self.assertIn("bifrost_platform:agentrt", targets)
        self.assertEqual(len(targets), 8)

    def test_job_policy_allows_default_sa_in_both_namespaces(self):
        policy = docs("k8s/overlays/platform-prod/config/actuation-policy.yaml")[0]
        self.assertEqual(policy["jobs"]["namespaces"]["bifrost-platform-prod"], "C")
        self.assertEqual(policy["jobs"]["namespaces"]["bifrost-platform-stg"], "B")
        self.assertIn("default", policy["admission"]["job_service_accounts"])
        bindings = docs("k8s/platform-rbac/20-prod.yaml")
        bound = {d["metadata"]["namespace"] for d in bindings
                 if d.get("roleRef", {}).get("name") == "bifrost-platform-job-actuator"}
        self.assertTrue({"bifrost-platform-prod", "bifrost-platform-stg"} <= bound)


if __name__ == "__main__":
    unittest.main()
