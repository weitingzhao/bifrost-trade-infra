"""New nodes get the NFS client when they join (TD-517).

2026-11-04: ubt-k3s-07 joined without nfs-common and the nfs-fast provisioner
could not mount on it. 2026-11-24: ubt-k3s-06 rejoined the same way and CI pods
scheduled there failed FailedMount for about 20 hours (11 platform CI runs) until
card #746 installed the package. Both times the install script's node list was
hand-written and the join script did not install the client.
"""

from __future__ import annotations

import re
from pathlib import Path

K3S = Path(__file__).resolve().parent


def test_node_join_installs_nfs_common_and_mounts_before_joining():
    text = (K3S / "node-join.sh").read_text()
    nfs = text.index("apt-get install -y -qq nfs-common")
    mount = text.index("mount -t nfs -o ro")
    join = text.index("bash ~/install-agent.sh")
    assert nfs < mount < join, "nfs-common and the read-only mount must come before the k3s agent install"


def test_install_nfs_common_nodes_has_no_hand_written_node_list():
    text = (K3S / "install-nfs-common-nodes.sh").read_text()
    assert "kubectl get nodes" in text, "default node list must come from the cluster"
    assert not re.search(r'^\s*"vision@\d+\.\d+\.\d+\.\d+"\s*$', text, re.M), "hand-written node IPs are back"
