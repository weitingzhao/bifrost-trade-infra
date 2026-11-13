"""scripts/k3s/node_table.py against a node list and a facts file. No cluster."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("node_table", ROOT / "scripts" / "k3s" / "node_table.py")
node_table = importlib.util.module_from_spec(spec)
spec.loader.exec_module(node_table)


def node(name, ip, cpu="16", mem="23866624Ki", **labels):
    return {
        "metadata": {"name": name, "labels": labels},
        "status": {
            "addresses": [{"type": "InternalIP", "address": ip}, {"type": "Hostname", "address": name}],
            "capacity": {"cpu": cpu, "memory": mem},
        },
    }


NODES = {
    "items": [
        node("ubt-k3s-07", "192.168.10.80", **{"bifrost.io/host-id": "ubt-k3s-07", "bifrost.io/workload-pool": "general"}),
        node(
            "ubt-k3s-02",
            "192.168.10.70",
            mem="15777944Ki",
            **{
                "bifrost.io/host-id": "mini-pc-a",
                "bifrost.io/workload-pool": "prod-pool",
                "bifrost.io/postgres-role": "primary",
                "storage.nfs/client": "true",
            },
        ),
        node(
            "ubt-k3s-01",
            "192.168.10.73",
            **{"node-role.kubernetes.io/control-plane": "true", "node-role.kubernetes.io/etcd": "true"},
        ),
    ]
}


def facts(tmp_path, table="", outside="Mac mini `.50` / `.52`、NAS `.20`"):
    path = tmp_path / "AGENT_FACTS.md"
    path.write_text(
        f"before\n{node_table.BEGIN}{table}{node_table.END}\n\n"
        f"{node_table.OUTSIDE_BEGIN}\n{outside}\n{node_table.OUTSIDE_END}\nafter\n"
    )
    return path


def run(tmp_path, path, *flags, nodes=NODES):
    nodes_file = tmp_path / "nodes.json"
    nodes_file.write_text(json.dumps(nodes))
    return node_table.main(["--nodes", str(nodes_file), "--facts", str(path), *flags])


def test_write_then_check_agrees(tmp_path, capsys):
    path = facts(tmp_path)
    assert run(tmp_path, path, "--write") == 0
    text = path.read_text()
    assert "| ubt-k3s-02 | 192.168.10.70 | mini-pc-a | prod-pool | 16 | 15.0 | 数据库主库标签、NFS 客户端 |" in text
    assert "| ubt-k3s-01 | 192.168.10.73 | — | — | 16 | 22.8 | 控制面、etcd |" in text
    assert text.startswith("before\n") and text.endswith("after\n")
    assert run(tmp_path, path, "--check") == 0
    assert "3 nodes match" in capsys.readouterr().out


def test_check_names_a_node_the_file_does_not_have(tmp_path, capsys):
    path = facts(tmp_path)
    run(tmp_path, path, "--write", nodes={"items": NODES["items"][1:]})
    assert run(tmp_path, path, "--check") == 1
    out = capsys.readouterr().out
    assert "ubt-k3s-07" in out and "file:    None" in out


def test_check_names_a_node_the_cluster_no_longer_has(tmp_path, capsys):
    path = facts(tmp_path)
    run(tmp_path, path, "--write")
    assert run(tmp_path, path, "--check", nodes={"items": NODES["items"][1:]}) == 1
    assert "cluster: None" in capsys.readouterr().out


def test_check_catches_a_changed_label(tmp_path):
    path = facts(tmp_path)
    run(tmp_path, path, "--write")
    moved = json.loads(json.dumps(NODES))
    moved["items"][1]["metadata"]["labels"]["bifrost.io/postgres-role"] = "standby"
    assert run(tmp_path, path, "--check", nodes=moved) == 1


def test_write_keeps_the_hand_written_note(tmp_path):
    path = facts(tmp_path)
    run(tmp_path, path, "--write")
    path.write_text(path.read_text().replace("| 控制面、etcd |  |", "| 控制面、etcd | 所有 NodePort 的访问地址 |"))
    assert run(tmp_path, path, "--write") == 0
    assert "| 控制面、etcd | 所有 NodePort 的访问地址 |" in path.read_text()
    assert run(tmp_path, path, "--check") == 0


def test_an_empty_node_list_is_refused(tmp_path):
    with pytest.raises(SystemExit, match="empty"):
        run(tmp_path, facts(tmp_path), "--check", nodes={"items": []})


def test_missing_markers_are_refused(tmp_path):
    path = tmp_path / "AGENT_FACTS.md"
    path.write_text("no markers here\n")
    with pytest.raises(SystemExit, match="exactly one"):
        run(tmp_path, path, "--check")


def targets(*ips):
    return {"data": {"activeTargets": [{"labels": {"job": "node-exporter", "instance": f"{ip}:9100"}} for ip in ips]}}


def test_targets_name_a_scraped_host_nobody_wrote_down(tmp_path, capsys):
    path = facts(tmp_path)
    run(tmp_path, path, "--write")
    tfile = tmp_path / "targets.json"
    tfile.write_text(json.dumps(targets("192.168.10.70", "192.168.10.50", "192.168.10.20", "192.168.10.79")))
    assert run(tmp_path, path, "--check", "--targets", str(tfile)) == 1
    out = capsys.readouterr().out
    assert "192.168.10.79" in out and "192.168.10.50" not in out and "192.168.10.70 is" not in out


def test_targets_pass_when_every_outside_host_is_listed(tmp_path):
    path = facts(tmp_path, outside="Mac mini `.50`、ubt-k3s-06 `.79`、NAS 192.168.10.20")
    run(tmp_path, path, "--write")
    tfile = tmp_path / "targets.json"
    tfile.write_text(json.dumps(targets("192.168.10.50", "192.168.10.20", "192.168.10.79")))
    assert run(tmp_path, path, "--check", "--targets", str(tfile)) == 0
