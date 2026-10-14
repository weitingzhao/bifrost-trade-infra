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
            self.assertFalse(any(d["kind"] == "CronJob" for d in objects.values()))
            job = docs("k8s/agentrt-migrate/" + env + "/job.yaml")[0]
            self.assertEqual(job["kind"], "Job")
            self.assertEqual(job["metadata"]["namespace"], namespace)
            self.assertEqual(job["metadata"]["generateName"], "agentrt-migrate-")
            self.assertNotIn("name", job["metadata"])
            self.assertEqual(job["spec"]["backoffLimit"], 0)
            self.assertEqual(job["spec"]["ttlSecondsAfterFinished"], 604800)
            self.assertEqual(job["spec"]["template"]["metadata"]["labels"]["app.kubernetes.io/name"], "agentrt-migrate")
            pod = job["spec"]["template"]["spec"]
            self.assertEqual(pod["serviceAccountName"], "default")
            self.assertFalse(pod["automountServiceAccountToken"])
            self.assertEqual(pod["initContainers"][0]["name"], "wait-pg")
            self.assertGreaterEqual(job["spec"]["activeDeadlineSeconds"], 840)
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
            redis_pod = redis["spec"]["template"]["spec"]
            self.assertEqual(redis_pod["securityContext"], {
                "runAsNonRoot": True, "runAsUser": 999, "runAsGroup": 999, "fsGroup": 999})
            expressions = redis_pod["affinity"]["nodeAffinity"]["requiredDuringSchedulingIgnoredDuringExecution"]["nodeSelectorTerms"]
            self.assertEqual(expressions, [{"matchExpressions": [{
                "key": "bifrost.io/workload-pool", "operator": "In",
                "values": ["prod-pool", "general"] if env == "prod" else ["general"]}]}])
            r = redis_pod["containers"][0]
            self.assertEqual(r["securityContext"], {
                "allowPrivilegeEscalation": False, "capabilities": {"drop": ["ALL"]}})
            self.assertEqual(r["command"], ["sh", "-c"])
            flags = dict(zip(r["args"][2::2], r["args"][3::2]))
            self.assertEqual(flags["--appendonly"], "yes")
            self.assertEqual(flags["--appendfsync"], "everysec")
            self.assertEqual(flags["--maxmemory"], "256mb")
            self.assertEqual(flags["--maxmemory-policy"], "noeviction")
            self.assertNotIn("--requirepass", flags)
            self.assertNotIn("$(REDIS_PASSWORD)", r["args"])
            # Execute the real wrapper with an empty or absent password. With no
            # redis-server on PATH this would be 127 if it reached exec instead.
            for empty_env in ({"PATH": "/nonexistent"}, {"PATH": "/nonexistent", "REDIS_PASSWORD": ""}):
                result = subprocess.run(["/bin/sh", "-c", *r["args"]], env=empty_env,
                                        capture_output=True, text=True)
                self.assertEqual(result.returncode, 1)
                self.assertIn("REDIS_PASSWORD must not be empty", result.stderr)
            self.assertIn('exec redis-server "$@" --requirepass "$REDIS_PASSWORD"', r["args"][0])
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

    def test_database_ownership(self):
        databases = {d["spec"]["name"]: d for d in docs("k8s/data/databases.yaml")}
        for env in ("prod", "stg", "dev"):
            db = "bifrost_platform" + ("" if env == "prod" else "_" + env)
            self.assertEqual(databases[db]["spec"]["owner"], "agentrt_owner_" + env)
            self.assertEqual(databases[db]["metadata"]["labels"]["bifrost.io/role"], "agentrt")
    def test_migration_jobs_are_outside_argo_sources(self):
        migration_path = Path("k8s/agentrt-migrate")
        for path in (ROOT / "k8s").rglob("*.yaml"):
            for app in docs(path.relative_to(ROOT)):
                if not isinstance(app, dict) or app.get("kind") != "Application":
                    continue
                sources = app["spec"].get("sources", []) + [app["spec"].get("source", {})]
                for source in sources:
                    if "bifrost-trade-infra" not in source.get("repoURL", ""):
                        continue
                    source_path = Path(source.get("path", "."))
                    self.assertFalse(migration_path == source_path or source_path in migration_path.parents,
                                     str(path.relative_to(ROOT)))

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
