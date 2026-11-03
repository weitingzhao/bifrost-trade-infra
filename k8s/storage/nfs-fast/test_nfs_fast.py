#!/usr/bin/env python3
"""Invariants of the TD-444 step 5 manifests (runbook §3.2 "由仓库测试保证", §3.6, §3.7).

Run: python3 -m unittest k8s/storage/nfs-fast/test_nfs_fast.py
"""

from __future__ import annotations

import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import gen  # noqa: E402

PRIVATE = [
    re.compile(r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b"),                 # IPv4 addresses
    re.compile(r"pvc-[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"),  # live PV names
    re.compile(r"ubt-k3s-\d+"),                                            # node names
    re.compile(r"/Users/"),                                                # local home paths
]


def docs(path: Path) -> list[dict]:
    return [d for d in yaml.safe_load_all(path.read_text()) if d]


class Manifests(unittest.TestCase):
    def test_generated_files_are_current(self):
        r = subprocess.run([sys.executable, str(HERE / "gen.py"), "--check"], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_dryrun_differs_only_in_name(self):
        for d in sorted(p for p in HERE.iterdir() if (p / "pvc.yaml").exists()):
            real, stand = docs(d / "pvc.yaml"), docs(d / "pvc-dryrun.yaml")
            self.assertEqual(len(real), len(stand), d.name)
            for a, b in zip(real, stand):
                self.assertEqual(b["metadata"]["name"], "td444-dryrun-" + a["metadata"]["name"])
                b2 = yaml.safe_load(yaml.safe_dump(b))
                b2["metadata"]["name"] = a["metadata"]["name"]
                self.assertEqual(a, b2, f"{d.name}: {a['metadata']['name']}")

    def test_pv_and_pvc_agree(self):
        for v in gen.VOLUMES:
            d = HERE / v["group"]
            pvs = {p["metadata"]["name"]: p for p in docs(d / "pv.yaml")}
            pvcs = {(p["metadata"]["namespace"], p["metadata"]["name"]): p for p in docs(d / "pvc.yaml")}
            p, c = pvs[v["pv"]], pvcs[(v["ns"], v["name"])]
            self.assertEqual(c["spec"]["volumeName"], v["pv"])
            self.assertEqual(p["spec"]["claimRef"], {"namespace": v["ns"], "name": v["name"]})  # no uid
            self.assertEqual(p["spec"]["storageClassName"], c["spec"]["storageClassName"])
            self.assertEqual(p["spec"]["capacity"]["storage"], c["spec"]["resources"]["requests"]["storage"])
            self.assertEqual(p["spec"]["accessModes"], c["spec"]["accessModes"])
            self.assertEqual(p["spec"]["persistentVolumeReclaimPolicy"], "Retain")
            self.assertEqual(p["spec"]["mountOptions"], ["nfsvers=3", "hard"])
            self.assertEqual(p["spec"]["nfs"]["server"], "@NAS_IP@")
            self.assertEqual(c["metadata"].get("labels", {}), v["labels"])

    def test_rollback_matches_pvc_except_class_and_volume(self):
        for v in gen.VOLUMES:
            if not v["old_class"]:
                continue
            d = HERE / v["group"]
            new = {p["metadata"]["name"]: p for p in docs(d / "pvc.yaml")}[v["name"]]
            old = {p["metadata"]["name"]: p for p in docs(d / "rollback-pvc.yaml")}[v["name"]]
            self.assertEqual(old["spec"]["volumeName"], f"@OLD_PV_{v['key']}@")
            self.assertEqual(old["spec"]["storageClassName"], v["old_class"])
            for k in ("accessModes", "volumeMode", "resources"):
                self.assertEqual(old["spec"][k], new["spec"][k])
            self.assertEqual(old["metadata"], new["metadata"])

    def test_recovery_points_at_recovery_pv(self):
        rec_pv = docs(HERE / "reg" / "recovery-pv.yaml")[0]
        rec_pvc = docs(HERE / "reg" / "recovery-pvc.yaml")[0]
        self.assertEqual(rec_pvc["spec"]["volumeName"], rec_pv["metadata"]["name"])
        self.assertEqual(rec_pv["spec"]["claimRef"], {"namespace": "cicd", "name": "registry-data"})
        self.assertTrue(rec_pv["spec"]["nfs"]["path"].startswith("/volume1/k3s-cold/td444-recovery/"))

    def test_probes_use_two_nodes_and_real_identities(self):
        for v in gen.VOLUMES:
            jobs = [d for d in docs(HERE / v["group"] / f"probe-{v['key'].lower()}.yaml")
                    if d["kind"] == "Job" and d["metadata"]["name"].startswith(f"td444-probe-{v['key'].lower()}-")]
            self.assertEqual(len(jobs), 2 * len(v["probes"]), v["key"])
            for j in jobs:
                spec = j["spec"]["template"]["spec"]
                role = j["metadata"]["name"][-1]
                self.assertEqual(spec["nodeSelector"]["kubernetes.io/hostname"],
                                 "@PROBE_NODE_A@" if role == "w" else "@PROBE_NODE_B@")
                self.assertEqual(j["metadata"]["namespace"], "default")

    def test_no_private_values_in_repository_files(self):
        for p in HERE.rglob("*"):
            if p.is_file() and p.suffix in (".yaml", ".py", ".md", ".example"):
                text = p.read_text()
                if p.name == "test_nfs_fast.py":
                    continue
                for pat in PRIVATE:
                    self.assertIsNone(pat.search(text), f"{p.relative_to(HERE)} matches {pat.pattern}")

    def test_render_fills_every_token(self):
        site = "\n".join([
            "NAS_IP=10.0.0.9", "PROBE_NODE_A=node-a", "PROBE_NODE_B=node-b",
            "MARKET_DATA_IMAGE=registry.example/bifrost-market-data@sha256:" + "0" * 64,
            *[f"OLD_PV_{v['key']}=pvc-00000000-0000-0000-0000-{i:012d}" for i, v in enumerate(gen.VOLUMES) if v["old_class"]],
        ])
        with tempfile.TemporaryDirectory() as tmp:
            sp = Path(tmp) / "site.env"
            sp.write_text(site + "\n")
            out = Path(tmp) / "out"
            r = subprocess.run([sys.executable, str(HERE / "render.py"), "--site", str(sp), "--run-id", "t1",
                                "--groups", "daily,finance,monitoring,reg,arc", "--out", str(out)], capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            for f in out.rglob("*.yaml"):
                self.assertIsNone(re.search(r"@[A-Z][A-Z0-9_]*@", f.read_text()), str(f))
            bad = Path(tmp) / "bad.env"
            bad.write_text("NAS_IP=not-an-ip\n")
            r = subprocess.run([sys.executable, str(HERE / "render.py"), "--site", str(bad), "--run-id", "t1",
                                "--groups", "daily", "--out", str(Path(tmp) / "out2")], capture_output=True, text=True)
            self.assertNotEqual(r.returncode, 0)
            self.assertFalse((Path(tmp) / "out2").exists())


if __name__ == "__main__":
    unittest.main()
