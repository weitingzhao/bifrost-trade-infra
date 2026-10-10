"""Plan order for scripts/k3s/rolling-reboot.sh. No live cluster, no SSH.

kubectl and ssh are stubs. The stub's CNPG answers are the only source of the
primary node; the node role is not.
"""

from __future__ import annotations

import os
import re
import stat
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "k3s" / "rolling-reboot.sh"

NODE_RE = re.compile(r"^node \d+/\d+ (\S+) role=(\S+)\s*$", re.M)

ORDER_PRIMARY_ON_02 = [
    ("ubt-k3s-05", "general"),
    ("ubt-k3s-06", "general"),
    ("ubt-k3s-01", "control-plane"),
    ("ubt-k3s-04", "data"),
    ("ubt-k3s-02", "prod"),
]
ORDER_PRIMARY_ON_04 = [
    ("ubt-k3s-05", "general"),
    ("ubt-k3s-06", "general"),
    ("ubt-k3s-01", "control-plane"),
    ("ubt-k3s-02", "prod"),
    ("ubt-k3s-04", "data"),
]

KUBECTL_STUB = textwrap.dedent(
    '''\
    #!/usr/bin/env python3
    import json, os, sys

    args = sys.argv[1:]
    log_path = os.environ["STUB_LOG"]
    state_path = os.environ["FAKE_STATE"]
    with open(log_path, "a", encoding="utf-8") as fh:
        fh.write(" ".join(args) + "\\n")

    def initial():
        primary_pod = os.environ.get("FAKE_PRIMARY_POD", "bifrost-postgres-1")
        primary_node = os.environ["FAKE_PRIMARY_NODE"]
        replica_pod = os.environ.get("FAKE_REPLICA_POD", "bifrost-postgres-3")
        replica_node = os.environ.get("FAKE_REPLICA_NODE", "ubt-k3s-04")
        include = os.environ.get("FAKE_INCLUDE_REPLICA", "1") == "1"
        lag = float(os.environ.get("FAKE_LAG", "0"))
        pods = {primary_pod: primary_node}
        roles = {primary_pod: "primary"}
        lags = {}
        if include:
            pods[replica_pod] = replica_node
            roles[replica_pod] = "replica"
            lags[replica_pod] = lag
        return {
            "primary_pod": primary_pod,
            "target": primary_pod,
            "pods": pods,
            "roles": roles,
            "instances": int(os.environ.get("FAKE_INSTANCES", "2")),
            "ready": int(os.environ.get("FAKE_READY", "2")),
            "phase": "Cluster in healthy state",
            "lag": lags,
            "move_after_drains": int(os.environ.get("FAKE_MOVE_AFTER_DRAINS", "0")),
            "move_to": os.environ.get("FAKE_MOVE_TO", ""),
            "drains": 0,
            "node_gets": {},
        }

    def load():
        if os.path.exists(state_path) and os.path.getsize(state_path) > 0:
            with open(state_path, encoding="utf-8") as fh:
                return json.load(fh)
        state = initial()
        save(state)
        return state

    def save(state):
        tmp = state_path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(state, fh)
        os.replace(tmp, state_path)

    def opt(flag):
        if flag in args:
            i = args.index(flag)
            if i + 1 < len(args):
                return args[i + 1]
        return ""

    def pod_items(state):
        items = []
        for name, node in state["pods"].items():
            items.append({
                "metadata": {
                    "name": name,
                    "labels": {
                        "cnpg.io/cluster": "bifrost-postgres",
                        "cnpg.io/instanceRole": state["roles"][name],
                    },
                },
                "spec": {"nodeName": node},
                "status": {
                    "phase": "Running",
                    "conditions": [{"type": "Ready", "status": "True"}],
                },
            })
        return {"items": items}

    def lag_line(value):
        number = float(value)
        shown = str(int(number)) if number.is_integer() else str(number)
        return "streaming|" + shown

    state = load()
    cmd = args[0] if args else ""

    if cmd in ("delete", "apply", "patch", "replace", "scale"):
        sys.exit(97)

    if cmd == "cordon" and os.environ.get("FAKE_FAIL_CORDON") == "1":
        sys.exit(99)

    if cmd == "cordon":
        sys.exit(0)

    if cmd == "uncordon":
        sys.exit(0)

    if cmd == "drain":
        state["drains"] = int(state.get("drains") or 0) + 1
        move_after = int(state.get("move_after_drains") or 0)
        move_to = state.get("move_to") or ""
        if move_after and state["drains"] == move_after and move_to:
            state["pods"][state["primary_pod"]] = move_to
        save(state)
        sys.exit(0)

    if cmd == "cnpg" and "promote" in args:
        inst = args[-1]
        if inst not in state["pods"]:
            sys.exit(1)
        state["primary_pod"] = inst
        state["target"] = inst
        for name in list(state["roles"]):
            if name == inst:
                state["roles"][name] = "primary"
                state["lag"].pop(name, None)
            else:
                state["roles"][name] = "replica"
                state["lag"][name] = 0
        save(state)
        sys.exit(0)

    if cmd == "exec":
        sql = args[-1]
        if "application_name = '" in sql:
            name = sql.split("application_name = '", 1)[1].split("'", 1)[0]
            if state["roles"].get(name) == "replica" and name in state["lag"]:
                print(lag_line(state["lag"][name]))
        else:
            for name in sorted(n for n, role in state["roles"].items() if role == "replica"):
                print(lag_line(state["lag"].get(name, 0)))
        sys.exit(0)

    if cmd == "get" and len(args) > 1 and args[1] == "pods" and "-A" in args:
        print('{"items":[]}')
        sys.exit(0)

    if cmd == "get" and len(args) > 1 and args[1] == "pods":
        print(json.dumps(pod_items(state)))
        sys.exit(0)

    if cmd == "get" and len(args) > 1 and args[1] == "pod":
        name = args[2]
        node = state["pods"].get(name)
        if not node:
            sys.exit(1)
        print(node)
        sys.exit(0)

    if cmd == "get" and len(args) > 1 and args[1] == "node":
        node = args[2]
        gets = state.setdefault("node_gets", {})
        gets[node] = int(gets.get(node) or 0) + 1
        save(state)
        print("False" if gets[node] == 1 else "True")
        sys.exit(0)

    if cmd == "get" and len(args) > 1 and args[1] == "cluster":
        jp = opt("-o")
        fields = {
            "jsonpath={.status.currentPrimary}": state["primary_pod"],
            "jsonpath={.status.targetPrimary}": state["target"],
            "jsonpath={.status.phase}": state["phase"],
            "jsonpath={.status.instances}": state["instances"],
            "jsonpath={.status.readyInstances}": state["ready"],
        }
        if jp not in fields:
            sys.stderr.write("unhandled cluster field %s\\n" % jp)
            sys.exit(98)
        print(fields[jp])
        sys.exit(0)

    sys.stderr.write("unhandled kubectl: %s\\n" % " ".join(args))
    sys.exit(98)
    '''
)

SSH_STUB = "#!/bin/sh\nprintf '%s\\n' \"$*\" >> \"$SSH_LOG\"\nexit \"${FAKE_SSH_EXIT:-0}\"\n"

CURL_STUB = textwrap.dedent(
    '''\
    #!/usr/bin/env python3
    import os, sys
    args = sys.argv[1:]
    url = ""
    config = ""
    i = 0
    while i < len(args):
        item = args[i]
        if item == "--config" and i + 1 < len(args):
            config = args[i + 1]
            i += 2
            continue
        if item == "--url" and i + 1 < len(args):
            url = args[i + 1]
            i += 2
            continue
        if item.startswith("http://") or item.startswith("https://"):
            url = item
        i += 1
    auth = "no"
    if config and os.path.isfile(config):
        text = open(config, encoding="utf-8").read()
        if "Authorization: Bearer viewer-test-token" in text:
            auth = "yes"
    log = os.environ.get("CURL_LOG", "")
    if log:
        with open(log, "a", encoding="utf-8") as fh:
            fh.write("auth=%s url=%s\\n" % (auth, url))
    code = int(os.environ.get("FAKE_APPROVAL_CURL_EXIT", "0"))
    if code:
        sys.exit(code)
    sys.stdout.write(os.environ.get("FAKE_APPROVAL_JSON", ""))
    '''
)

VALID_APPROVAL = (
    '{"action":"rolling_reboot","status":"executed","expires_at":"2099-01-01T00:00:00Z"}'
)


def run(args: list[str], env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    merged = os.environ.copy()
    merged.pop("ROLLING_REBOOT_DOW", None)
    if env:
        merged.update(env)
    return subprocess.run(
        ["bash", str(SCRIPT), *args],
        cwd=ROOT,
        env=merged,
        text=True,
        capture_output=True,
        check=False,
    )


def nodes(text: str) -> list[tuple[str, str]]:
    return NODE_RE.findall(text)


def write_executable(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IEXEC)


class FakeCluster:
    def __init__(self, root: Path, **options: object) -> None:
        self.root = root
        self.log = root / "kubectl.log"
        self.ssh_log = root / "ssh.log"
        self.curl_log = root / "curl.log"
        self.state = root / "state.json"
        write_executable(root / "kubectl", KUBECTL_STUB)
        write_executable(root / "ssh", SSH_STUB)
        write_executable(root / "curl", CURL_STUB)
        (root / "admin.yaml").write_text("", encoding="utf-8")
        (root / "node-key").write_text("", encoding="utf-8")
        self.env = {
            "PATH": f"{root}{os.pathsep}{os.environ.get('PATH', '')}",
            "OWNER_KUBECONFIG": str(root / "admin.yaml"),
            "BIFROST_SSH_KEY": str(root / "node-key"),
            "FAKE_SSH_EXIT": str(options.get("ssh_exit", 0)),
            "STUB_LOG": str(self.log),
            "SSH_LOG": str(self.ssh_log),
            "CURL_LOG": str(self.curl_log),
            "FAKE_STATE": str(self.state),
            "FAKE_PRIMARY_NODE": str(options.get("primary_node", "ubt-k3s-02")),
            "FAKE_REPLICA_NODE": str(options.get("replica_node", "ubt-k3s-04")),
            "FAKE_PRIMARY_POD": str(options.get("primary_pod", "bifrost-postgres-1")),
            "FAKE_REPLICA_POD": str(options.get("replica_pod", "bifrost-postgres-3")),
            "FAKE_INSTANCES": str(options.get("instances", 2)),
            "FAKE_READY": str(options.get("ready", 2)),
            "FAKE_LAG": str(options.get("lag", 0)),
            "FAKE_INCLUDE_REPLICA": "1" if options.get("include_replica", True) else "0",
            "FAKE_MOVE_AFTER_DRAINS": str(options.get("move_after_drains", 0)),
            "FAKE_MOVE_TO": str(options.get("move_to", "")),
            "FAKE_FAIL_CORDON": "1" if options.get("fail_cordon", False) else "0",
            "READY_POLL_SECONDS": str(options.get("poll", 0)),
            "READY_TIMEOUT_SECONDS": str(options.get("timeout", 5)),
        }
        dow = options.get("dow")
        if dow is not None:
            self.env["ROLLING_REBOOT_DOW"] = str(dow)

    def kubectl_text(self) -> str:
        if not self.log.exists():
            return ""
        return self.log.read_text(encoding="utf-8")

    def ssh_text(self) -> str:
        if not self.ssh_log.exists():
            return ""
        return self.ssh_log.read_text(encoding="utf-8")

    def curl_text(self) -> str:
        if not self.curl_log.exists():
            return ""
        return self.curl_log.read_text(encoding="utf-8")


def arm_approval(
    env: dict[str, str],
    body: str = VALID_APPROVAL,
    curl_exit: str = "0",
) -> dict[str, str]:
    out = dict(env)
    out["PLATFORM_PROD_VIEWER_TOKEN"] = "viewer-test-token"
    out["PLATFORM_API"] = "http://platform.test"
    out["FAKE_APPROVAL_JSON"] = body
    out["FAKE_APPROVAL_CURL_EXIT"] = curl_exit
    return out


class RollingRebootPlanTests(unittest.TestCase):
    def test_script_promotes_with_cnpg_and_ignores_the_fixed_make_target(self) -> None:
        text = SCRIPT.read_text(encoding="utf-8")
        self.assertIn("cnpg promote", text)
        self.assertNotIn("k3s-switchover-postgres-primary", text)
        self.assertNotIn("switchover-postgres-primary.sh", text)
        self.assertNotIn("ubt-k3s-04:data-primary", text)
        self.assertNotIn("|data-primary", text)

    def test_primary_on_02_is_last_and_switchover_is_before_it(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fake = FakeCluster(Path(tmp), primary_node="ubt-k3s-02", replica_node="ubt-k3s-04")
            result = run(["--dry-run"], fake.env)
            called = fake.kubectl_text()
            ssh = fake.ssh_text()
            curl = fake.curl_text()
        self.assertEqual(result.returncode, 0, result.stderr)
        found = nodes(result.stdout)
        self.assertEqual(found, ORDER_PRIMARY_ON_02)
        self.assertEqual(found[-1][0], "ubt-k3s-02")
        self.assertIn(
            "order: ubt-k3s-05 ubt-k3s-06 ubt-k3s-01 ubt-k3s-04 ubt-k3s-02",
            result.stdout,
        )
        self.assertIn("switchover-before: ubt-k3s-02", result.stdout)
        self.assertIn("primary-node: ubt-k3s-02", result.stdout)
        self.assertLess(
            result.stdout.index("switchover:"),
            result.stdout.index("ubt-k3s-02 role=prod"),
        )
        self.assertIn("sole control plane", result.stdout)
        self.assertIn("about 10s", result.stdout)
        self.assertNotIn("--disable-eviction", result.stdout)
        self.assertNotIn("--force", result.stdout)
        self.assertIn("gpu-server", result.stdout)
        self.assertIn("jsonpath={.status.currentPrimary}", called)
        self.assertNotIn("cordon", called)
        self.assertNotIn("drain", called)
        self.assertNotIn("cnpg promote", called)
        self.assertNotIn("delete", called)
        self.assertNotIn("apply", called)
        self.assertEqual(ssh, "")
        self.assertEqual(curl, "")
        for name, _role in ORDER_PRIMARY_ON_02:
            self.assertIn(f"cordon {name}", result.stdout)
            self.assertIn(f"drain {name}", result.stdout)
            self.assertIn(f"reboot {name}", result.stdout)
            self.assertIn(f"uncordon {name}", result.stdout)
            self.assertIn(f"verify workloads on {name} are Ready", result.stdout)

    def test_primary_on_04_is_last(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fake = FakeCluster(Path(tmp), primary_node="ubt-k3s-04", replica_node="ubt-k3s-02")
            result = run(["--dry-run"], fake.env)
        self.assertEqual(result.returncode, 0, result.stderr)
        found = nodes(result.stdout)
        self.assertEqual(found, ORDER_PRIMARY_ON_04)
        self.assertEqual(found[-1], ("ubt-k3s-04", "data"))
        self.assertIn("switchover-before: ubt-k3s-04", result.stdout)
        self.assertNotIn("switchover-before: ubt-k3s-02", result.stdout)
        self.assertLess(
            result.stdout.index("switchover:"),
            result.stdout.index("ubt-k3s-04 role=data"),
        )

    def test_scrambled_node_list_still_puts_the_live_primary_last(self) -> None:
        spec = (
            "ubt-k3s-04:data,"
            "ubt-k3s-02:prod,"
            "ubt-k3s-06:general,"
            "ubt-k3s-01:control-plane,"
            "ubt-k3s-05:general"
        )
        with tempfile.TemporaryDirectory() as tmp:
            fake = FakeCluster(Path(tmp), primary_node="ubt-k3s-04")
            result = run(["--dry-run", "--nodes", spec], fake.env)
        self.assertEqual(result.returncode, 0, result.stderr)
        found = nodes(result.stdout)
        self.assertEqual(found, ORDER_PRIMARY_ON_04)
        self.assertLess(
            result.stdout.index("switchover:"),
            result.stdout.index("role=data"),
        )

    def test_role_label_does_not_decide_who_is_last(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fake = FakeCluster(Path(tmp), primary_node="ubt-k3s-04")
            result = run(
                ["--dry-run", "--nodes", "ubt-k3s-04:data,zzz-general:general"],
                fake.env,
            )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            nodes(result.stdout),
            [("zzz-general", "general"), ("ubt-k3s-04", "data")],
        )
        self.assertLess(
            result.stdout.index("switchover:"),
            result.stdout.index("ubt-k3s-04 role=data"),
        )

    def test_data_primary_role_is_rejected(self) -> None:
        result = run(["--dry-run", "--nodes", "ubt-k3s-04:data-primary"])
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("unknown role", result.stderr)
        self.assertIn("data-primary", result.stderr)

    def test_primary_outside_the_reboot_list_stops(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fake = FakeCluster(Path(tmp), primary_node="ubt-k3s-02")
            result = run(
                ["--dry-run", "--nodes", "ubt-k3s-05:general,ubt-k3s-06:general"],
                fake.env,
            )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("ubt-k3s-02", result.stderr)
        self.assertNotIn("cordon", fake.kubectl_text())

    def test_primary_moves_mid_run_and_the_remaining_order_is_recomputed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fake = FakeCluster(
                Path(tmp),
                primary_node="ubt-k3s-02",
                replica_node="ubt-k3s-04",
                move_after_drains=1,
                move_to="ubt-k3s-06",
                dow="6",
                poll=0,
                timeout=5,
            )
            result = run(["--execute", "--approval", "appr_ok"], arm_approval(fake.env))
            log = fake.kubectl_text()
            curl = fake.curl_text()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertNotIn("viewer-test-token", result.stdout + result.stderr)
        self.assertIn("auth=yes url=http://platform.test/api/v1/approvals/appr_ok", curl)
        self.assertNotIn("viewer-test-token", curl)
        self.assertIn(
            "remaining-order: ubt-k3s-05 ubt-k3s-06 ubt-k3s-01 ubt-k3s-04 ubt-k3s-02",
            result.stdout,
        )
        self.assertIn(
            "remaining-order: ubt-k3s-01 ubt-k3s-02 ubt-k3s-04 ubt-k3s-06",
            result.stdout,
        )
        self.assertIn("switchover-before: ubt-k3s-06", result.stdout)
        self.assertIn("replicas caught up", result.stdout)
        cordons = [line for line in log.splitlines() if line.startswith("cordon ")]
        self.assertEqual(
            cordons,
            [
                "cordon ubt-k3s-05",
                "cordon ubt-k3s-01",
                "cordon ubt-k3s-02",
                "cordon ubt-k3s-04",
                "cordon ubt-k3s-06",
            ],
        )
        promote = "cnpg promote -n data bifrost-postgres bifrost-postgres-3"
        self.assertIn(promote, log)
        self.assertLess(log.index("cordon ubt-k3s-02"), log.index(promote))
        self.assertLess(log.index(promote), log.index("cordon ubt-k3s-06"))
        self.assertIn("rolling-reboot: complete", result.stdout)

    def test_replica_not_caught_up_stops_before_the_primary_node(self) -> None:
        spec = "ubt-k3s-04:data:192.168.10.75,ubt-k3s-02:prod:192.168.10.70"
        with tempfile.TemporaryDirectory() as tmp:
            fake = FakeCluster(
                Path(tmp),
                primary_node="ubt-k3s-02",
                replica_node="ubt-k3s-04",
                lag=30,
                dow="6",
                poll=1,
                timeout=2,
            )
            result = run(
                ["--execute", "--approval", "appr_ok", "--nodes", spec],
                arm_approval(fake.env),
            )
            log = fake.kubectl_text()
            ssh = fake.ssh_text()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("not caught up", result.stderr)
        self.assertIn("ubt-k3s-02", result.stderr)
        self.assertIn("cordon ubt-k3s-04", log)
        self.assertNotIn("cordon ubt-k3s-02", log)
        self.assertNotIn("cnpg promote", log)
        self.assertNotIn("uncordon ubt-k3s-02", log)
        self.assertIn("192.168.10.75", ssh)
        self.assertNotIn("192.168.10.70", ssh)
        self.assertNotIn("rolling-reboot: complete", result.stdout)

    def test_single_instance_stops_before_the_primary_node(self) -> None:
        spec = "ubt-k3s-04:data:192.168.10.75,ubt-k3s-02:prod:192.168.10.70"
        with tempfile.TemporaryDirectory() as tmp:
            fake = FakeCluster(
                Path(tmp),
                primary_node="ubt-k3s-02",
                instances=1,
                ready=1,
                include_replica=False,
                dow="6",
                poll=0,
                timeout=5,
            )
            result = run(
                ["--execute", "--approval", "appr_ok", "--nodes", spec],
                arm_approval(fake.env),
            )
            log = fake.kubectl_text()
            ssh = fake.ssh_text()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("only 1 CNPG instance", result.stderr)
        self.assertIn("ubt-k3s-02", result.stderr)
        self.assertIn("cordon ubt-k3s-04", log)
        self.assertNotIn("cordon ubt-k3s-02", log)
        self.assertNotIn("cnpg promote", log)
        self.assertNotIn("192.168.10.70", ssh)

    def test_execute_refused_on_weekday_does_not_cordon(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fake = FakeCluster(Path(tmp), dow="3")
            result = run(["--execute", "--approval", "appr_ok"], arm_approval(fake.env))
            called = fake.kubectl_text()
            ssh = fake.ssh_text()
            curl = fake.curl_text()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("REFUSED", result.stderr)
        self.assertIn("Saturday and Sunday", result.stderr)
        self.assertIn("auth=yes", curl)
        self.assertNotIn("viewer-test-token", result.stdout + result.stderr + curl)
        self.assertIn("jsonpath={.status.currentPrimary}", called)
        self.assertNotIn("cordon", called)
        self.assertNotIn("drain", called)
        self.assertNotIn("cnpg promote", called)
        self.assertEqual(ssh, "")

    def test_allow_weekday_warns_and_stops_when_the_first_step_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fake = FakeCluster(Path(tmp), dow="3", fail_cordon=True)
            result = run(
                ["--execute", "--approval", "appr_ok", "--allow-weekday"],
                arm_approval(fake.env),
            )
            called = fake.kubectl_text()
            ssh = fake.ssh_text()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("WARNING", result.stderr)
        self.assertIn("--allow-weekday", result.stderr)
        self.assertIn("cordon ubt-k3s-05", called)
        self.assertNotIn("drain", called)
        self.assertNotIn("uncordon", called)
        self.assertNotIn("cnpg promote", called)
        self.assertEqual(ssh, "")

    def test_execute_without_approval_does_not_cordon(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fake = FakeCluster(Path(tmp), dow="6")
            env = dict(fake.env)
            env["ENV_FILE"] = str(Path(tmp) / "no-such.env")
            result = run(["--execute"], env)
            called = fake.kubectl_text()
            curl = fake.curl_text()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("requires --approval", result.stderr)
        self.assertNotIn("cordon", called)
        self.assertEqual(curl, "")

    def test_execute_rejects_the_wrong_approval_and_does_not_cordon(self) -> None:
        cases = (
            (
                '{"action":"cordon_node","status":"executed","expires_at":"2099-01-01T00:00:00Z"}',
                "action=cordon_node",
            ),
            (
                '{"action":"rolling_reboot","status":"pending","expires_at":"2099-01-01T00:00:00Z"}',
                "status=pending",
            ),
            (
                '{"action":"rolling_reboot","status":"executed","expires_at":"2000-01-01T00:00:00Z"}',
                "expired",
            ),
        )
        for body, marker in cases:
            with self.subTest(marker=marker):
                with tempfile.TemporaryDirectory() as tmp:
                    fake = FakeCluster(Path(tmp), dow="6")
                    result = run(
                        ["--execute", "--approval", "appr_bad"],
                        arm_approval(fake.env, body),
                    )
                    called = fake.kubectl_text()
                    curl = fake.curl_text()
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(marker, result.stderr)
                self.assertNotIn("cordon", called)
                self.assertNotIn("viewer-test-token", result.stdout + result.stderr + curl)

    def test_execute_rejects_an_unreadable_approval_and_does_not_cordon(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fake = FakeCluster(Path(tmp), dow="6")
            result = run(
                ["--execute", "--approval", "appr_missing"],
                arm_approval(fake.env, curl_exit="22"),
            )
            called = fake.kubectl_text()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("could not read approval", result.stderr)
        self.assertNotIn("cordon", called)

    # W-33 step 3: the node key has a passphrase and the default kubeconfig is
    # read-only.
    TWO_NODES = "ubt-k3s-04:data:192.168.10.75,ubt-k3s-02:prod:192.168.10.70"

    def test_reboot_ssh_asks_for_the_passphrase_and_schedules_the_reboot(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fake = FakeCluster(Path(tmp), dow="6")
            result = run(
                ["--execute", "--approval", "appr_ok", "--nodes", self.TWO_NODES],
                arm_approval(fake.env),
            )
            ssh = fake.ssh_text()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        lines = ssh.splitlines()
        self.assertEqual(len(lines), 2, ssh)
        for line in lines:
            self.assertIn("-F /dev/null", line)
            self.assertIn("IdentityAgent=none", line)
            self.assertIn("PreferredAuthentications=publickey", line)
            self.assertIn(f"-i {Path(tmp) / 'node-key'}", line)
            self.assertIn("sudo -n systemd-run --on-active=5 /usr/bin/systemctl reboot", line)
            self.assertNotIn("BatchMode", line)
            self.assertNotIn("apt-get", line)

    def test_dry_run_with_upgrade_prints_the_upgrade_step(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fake = FakeCluster(Path(tmp))
            result = run(["--dry-run", "--upgrade"], fake.env)
            ssh = fake.ssh_text()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("upgrade: on", result.stdout)
        self.assertNotIn("--force", result.stdout)
        self.assertEqual(ssh, "")
        for name, _role in ORDER_PRIMARY_ON_02:
            self.assertLess(
                result.stdout.index(f"drain {name}"),
                result.stdout.index(f"upgrade packages on {name}"),
            )
            self.assertLess(
                result.stdout.index(f"upgrade packages on {name}"),
                result.stdout.index(f"- reboot {name}"),
            )

    def test_upgrade_runs_before_the_reboot_in_the_same_session(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fake = FakeCluster(Path(tmp), dow="7")
            result = run(
                ["--execute", "--approval", "appr_ok", "--upgrade", "--nodes", self.TWO_NODES],
                arm_approval(fake.env),
            )
            ssh = fake.ssh_text()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        lines = ssh.splitlines()
        # One session per node: one passphrase prompt per node.
        self.assertEqual(len(lines), 2, ssh)
        for line in lines:
            self.assertIn("NEEDRESTART_MODE=l", line)
            self.assertIn("DEBIAN_FRONTEND=noninteractive", line)
            self.assertIn("--force-confold", line)
            self.assertIn("upgrade --with-new-pkgs && sudo -n systemd-run", line)
            self.assertLess(line.index("apt-get -q -o DPkg::Lock::Timeout=300 update"), line.index("upgrade --with-new-pkgs"))
            self.assertNotIn("dist-upgrade", line)
            self.assertNotIn("autoremove", line)

    def test_failed_upgrade_stops_before_the_next_node(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fake = FakeCluster(Path(tmp), dow="6", ssh_exit=100)
            result = run(
                ["--execute", "--approval", "appr_ok", "--upgrade", "--nodes", self.TWO_NODES],
                arm_approval(fake.env),
            )
            log = fake.kubectl_text()
            ssh = fake.ssh_text()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("upgrade or reboot failed on ubt-k3s-04 (ssh exit 100)", result.stderr)
        self.assertIn("cordon ubt-k3s-04", log)
        self.assertNotIn("uncordon", log)
        self.assertNotIn("cordon ubt-k3s-02", log)
        self.assertNotIn("192.168.10.70", ssh)
        self.assertNotIn("rolling-reboot: complete", result.stdout)

    def test_failed_reboot_ssh_stops_with_the_node_still_cordoned(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fake = FakeCluster(Path(tmp), dow="6", ssh_exit=255)
            result = run(
                ["--execute", "--approval", "appr_ok", "--nodes", self.TWO_NODES],
                arm_approval(fake.env),
            )
            log = fake.kubectl_text()
            ssh = fake.ssh_text()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("could not schedule the reboot on ubt-k3s-04 (ssh exit 255)", result.stderr)
        self.assertIn("cordon ubt-k3s-04", log)
        self.assertNotIn("uncordon", log)
        self.assertNotIn("get node", log)
        self.assertNotIn("cordon ubt-k3s-02", log)
        self.assertNotIn("192.168.10.70", ssh)
        self.assertNotIn("rolling-reboot: complete", result.stdout)

    def test_execute_without_the_owner_kubeconfig_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fake = FakeCluster(Path(tmp), dow="6")
            env = arm_approval(fake.env)
            env["OWNER_KUBECONFIG"] = str(Path(tmp) / "missing.yaml")
            env["KUBECONFIG"] = str(Path(tmp) / "admin.yaml")
            result = run(["--execute", "--approval", "appr_ok"], env)
            called = fake.kubectl_text()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("REFUSED: --execute needs the Owner kubeconfig", result.stderr)
        self.assertEqual(called, "")

    def test_execute_without_the_node_key_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fake = FakeCluster(Path(tmp), dow="6")
            env = arm_approval(fake.env)
            env["BIFROST_SSH_KEY"] = str(Path(tmp) / "missing-key")
            result = run(["--execute", "--approval", "appr_ok"], env)
            called = fake.kubectl_text()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("REFUSED: --execute needs the node key", result.stderr)
        self.assertEqual(called, "")


if __name__ == "__main__":
    unittest.main()
