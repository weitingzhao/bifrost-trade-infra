#!/usr/bin/env python3
"""Cluster-state backup stays age ciphertext on nfs-cold (LANE-A2R).

Static (default): the CronJob exists, the script shells out to age, the PVC
is nfs-cold, and nothing in the backup script writes Secret or ConfigMap
YAML, or an etcd snapshot, onto the target as plaintext. A snapshot path
reaches the target directory only through age. Source sha256 is computed
before that encryption. The age recipient in git is the Owner's published
public key. The private key is not in this repo; this check does not look
for it and does not talk to the cluster.

Live (``--live``; needs KUBECONFIG, read-only): a successful Job finished
less than 36 hours ago, its backup container log contains today's UTC
verification line, and the target directory (a local read-only view of the
PVC, never a newly created pod or mount) has today's MANIFEST and no
``etcd-snapshot-*`` file that does not end in ``.age``. The log and the
MANIFEST contents are not printed here.

Usage: python3 scripts/check_cluster_state_backup.py [--live] [--self-test]
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Homebrew python3 on the dev Mac has no PyYAML; /usr/bin/python3 does.
# Re-exec so `make check-cluster-state-backup` works without a virtualenv.
try:
    import yaml
except ImportError:
    _fallback = Path("/usr/bin/python3")
    if _fallback.is_file() and Path(sys.executable).resolve() != _fallback.resolve():
        os.execv(str(_fallback), [str(_fallback), *sys.argv])
    raise

ROOT = Path(__file__).resolve().parents[1]
BACKUP = ROOT / "k8s/data/cluster-state-backup"
RULE = ROOT / "k8s/monitoring/bifrost-cluster-state-rules.yaml"
RUNBOOK = ROOT / "docs/runbooks/cluster-state-restore.md"

# Owner public key, LANE-A2 (2026-10-07). Not a secret.
RECIPIENT = "age10s4l6p55wh22gsmr3ga40lad7269hn8yt356m5kuhcyg67c80ayqutqxkf"
AGE_SHA = "cbe24006683f8eb669266162894b9a522a1af52f2665fbc63a4bb032ed26ac10"
KUBECTL_SHA = "90f75ea6ecc9ea5633262e1c0b83a40560003b30fc94a04cb099404fcef0c224"
STALE_SECONDS = 36 * 3600

REDIRECT = re.compile(r'(?:^|[\s;|&])>{1,2}\s*(?:"([^"]*)"|(\S+))')
SECRET_LOG = re.compile(r"(?m)^(kind:\s*Secret\b|AGE-SECRET-KEY-)")


def code_of(line: str) -> str:
    code = line.split("#", 1)[0]
    return re.sub(r"'[^']*'", "''", code)


def redirect_targets(line: str) -> list[str]:
    targets = []
    for match in REDIRECT.finditer(code_of(line)):
        target = match.group(1) if match.group(1) is not None else match.group(2)
        if target.startswith("&") or target in {"/dev/null"}:
            continue
        targets.append(target)
    return targets


_SNAPSHOT_SRC = ("$newest", "${newest}", "$SNAPSHOT_DIR", "${SNAPSHOT_DIR}", "/snapshots")
_TARGET_DIR = ("$WORK", "${WORK}", "$BACKUP_ROOT", "${BACKUP_ROOT}", "$DAILY", "$MONTHLY", "$MTMP", "/backup")
_COPY = re.compile(r"(?:^|[;&|]\s*)(?:cp|mv|dd|install|rsync|ln|cat)\b")


def _age_writer(code: str) -> bool:
    return "-o" in code and re.search(r"(?:^|[;&|(]\s*)age\b", code) is not None


def snapshot_target_problems(text: str) -> list[str]:
    """Every snapshot written into the target directory has to go through age.

    Copying ciphertext (``*.age``) onward is a different path: the source is
    not the hostPath snapshot. A plaintext ``cp`` of ``$newest`` (or of
    ``$SNAPSHOT_DIR``) into the target is always a failure.
    """
    problems: list[str] = []
    for lineno, line in enumerate(text.splitlines(), 1):
        code = code_of(line).strip()
        if not code or _age_writer(code):
            continue
        mentions_src = any(mark in code for mark in _SNAPSHOT_SRC)
        mentions_target = any(mark in code for mark in _TARGET_DIR)
        writes = _COPY.search(code) is not None or redirect_targets(line) != []
        if mentions_src and mentions_target and writes:
            problems.append(
                f"backup.sh:{lineno}: plaintext snapshot copied to the target without age"
            )
        if re.search(r"\bcp\b", code) and "-a" in code and "$DAILY" in code:
            problems.append(f"backup.sh:{lineno}: cp -a of a daily directory")
    return problems


def script_problems(text: str) -> list[str]:
    """Plaintext-to-disk and age-use checks for backup.sh."""
    problems: list[str] = []
    if "age-keygen" in text or "AGE-SECRET-KEY-" in text:
        problems.append("backup.sh mentions key generation or a private key")
    if "not age-wrapped" in text or "exact copy" in text:
        problems.append("backup.sh still describes a plaintext snapshot copy")
    if re.search(r"(?m)^\s*set\s+-[^\n]*x|set\s+-o\s+xtrace\b", text):
        problems.append("backup.sh enables xtrace (commands would hit the log)")
    if re.search(r"(?m)^\s*tee\b", text) or re.search(r"[|&]\s*tee\b", text):
        problems.append("backup.sh tees output to a file")
    required = (
        'age -r "$RECIPIENT" -o "$tmp"',
        'kubectl get secrets --all-namespaces -o yaml | encrypt_stdin',
        "export_platform_state | encrypt_stdin",
        'encrypt_stdin "$WORK/server-token.age" < "$TOKEN_FILE"',
        'encrypt_stdin "$WORK/$snap_age" < "$newest"',
        'src_sum=$(sha256_of "$newest")',
        "plaintext_sha256",
        "plaintext_bytes",
        "ciphertext_sha256",
        "allowed_backup_name",
        "age_header_ok",
        'rm -f "$tmp"',
    )
    for snippet in required:
        if snippet not in text:
            problems.append(f"backup.sh is missing {snippet!r}")
    hash_at = text.find('src_sum=$(sha256_of "$newest")')
    enc_at = text.find('encrypt_stdin "$WORK/$snap_age" < "$newest"')
    if hash_at < 0 or enc_at < 0 or hash_at > enc_at:
        problems.append("backup.sh does not hash the snapshot before encryption")
    # The recipient is rejected before any kubectl get of secrets.
    reject_at = text.find("placeholder AGE_RECIPIENT")
    secrets_at = text.find("kubectl get secrets")
    if reject_at < 0 or secrets_at < 0 or reject_at > secrets_at:
        problems.append("backup.sh does not reject a placeholder recipient before reading secrets")
    for lineno, line in enumerate(text.splitlines(), 1):
        code = code_of(line)
        if "kubectl" in code and redirect_targets(line):
            problems.append(f"backup.sh:{lineno}: kubectl output is redirected to a file")
        for target in redirect_targets(line):
            if re.search(r"\.ya?ml\b", target) and not target.endswith(".age"):
                problems.append(f"backup.sh:{lineno}: redirect writes YAML ({target})")
            if "token" in target and not target.endswith(".age"):
                problems.append(f"backup.sh:{lineno}: redirect writes the server token ({target})")
            base = target.rstrip("/").rsplit("/", 1)[-1]
            if base.startswith("etcd-snapshot-") and not base.endswith(".age"):
                problems.append(f"backup.sh:{lineno}: redirect writes a plaintext snapshot ({target})")
        if re.search(r"\bcp\b", code) and re.search(r"token|secret|\.ya?ml", code, re.I):
            problems.append(f"backup.sh:{lineno}: cp of a secret, token, or yaml file")
    problems += snapshot_target_problems(text)
    return problems


def tools_problems(text: str) -> list[str]:
    problems: list[str] = []
    if AGE_SHA not in text or KUBECTL_SHA not in text:
        problems.append("fetch-tools.sh does not pin the age and kubectl checksums")
    if "sha256sum -c" not in text:
        problems.append("fetch-tools.sh does not verify checksums")
    if "tar -xzf age.tar.gz age/age" not in text:
        problems.append("fetch-tools.sh does not unpack only the age binary")
    if "age-keygen" in text or "AGE-SECRET-KEY-" in text:
        problems.append("fetch-tools.sh mentions key generation or a private key")
    return problems


def load_docs(directory: Path) -> list[tuple[str, dict]]:
    out: list[tuple[str, dict]] = []
    for path in sorted(directory.glob("*.yaml")):
        for doc in yaml.safe_load_all(path.read_text()):
            if isinstance(doc, dict) and doc.get("kind"):
                out.append((path.name, doc))
    return out


def manifest_problems(directory: Path) -> list[str]:
    docs = load_docs(directory)
    problems: list[str] = []
    by_kind = {}
    for name, doc in docs:
        by_kind.setdefault(doc["kind"], []).append((name, doc))

    cronjobs = [d for _, d in by_kind.get("CronJob", [])]
    if len(cronjobs) != 1 or cronjobs[0]["metadata"]["name"] != "cluster-state-backup":
        problems.append("CronJob cluster-state-backup is missing")
        return problems
    cron = cronjobs[0]
    if cron["metadata"].get("namespace") != "kube-system":
        problems.append("CronJob is not in kube-system")
    if cron["spec"].get("schedule") != "15 5 * * *":
        problems.append(f"CronJob schedule is {cron['spec'].get('schedule')!r}, want 05:15 UTC")
    if cron["spec"].get("timeZone") != "Etc/UTC":
        problems.append("CronJob timeZone is not Etc/UTC")
    pod = cron["spec"]["jobTemplate"]["spec"]["template"]["spec"]
    if pod.get("serviceAccountName") != "cluster-state-backup":
        problems.append("CronJob ServiceAccount is not cluster-state-backup")
    if (pod.get("nodeSelector") or {}).get("kubernetes.io/hostname") != "ubt-k3s-01":
        problems.append("CronJob nodeSelector is not ubt-k3s-01")
    tolerations = pod.get("tolerations") or []
    if not any(t.get("key") == "node-role.kubernetes.io/control-plane" for t in tolerations):
        problems.append("CronJob has no control-plane toleration")
    mounts = {m["name"]: m for c in pod.get("containers") or [] for m in c.get("volumeMounts") or []}
    volumes = {v["name"]: v for v in pod.get("volumes") or []}
    snap = volumes.get("snapshots") or {}
    host = (snap.get("hostPath") or {})
    if host.get("path") != "/var/lib/rancher/k3s/server/db/snapshots":
        problems.append("CronJob does not mount the k3s etcd snapshot directory")
    snap_mount = mounts.get("snapshots") or {}
    if snap_mount.get("readOnly") is not True:
        problems.append("etcd snapshot mount is not read-only")
    token_mount = mounts.get("server-token") or {}
    if token_mount.get("readOnly") is not True:
        problems.append("server token mount is not read-only")
    claim = ((volumes.get("backup") or {}).get("persistentVolumeClaim") or {}).get("claimName")
    if claim != "cluster-state-backup":
        problems.append("CronJob does not use PVC cluster-state-backup")
    env = {e["name"]: e.get("value") for c in pod["containers"] if c["name"] == "backup" for e in c.get("env") or []}
    if env.get("KEEP_DAILY") != "30" or env.get("KEEP_MONTHLY") != "12":
        problems.append("retention is not daily 30 and monthly 12")
    if ((volumes.get("recipient") or {}).get("configMap") or {}).get("name") != "cluster-state-backup-recipient":
        problems.append("CronJob does not mount the recipient ConfigMap")

    pvcs = [d for _, d in by_kind.get("PersistentVolumeClaim", [])]
    if not any(
        d["metadata"]["name"] == "cluster-state-backup" and d["spec"].get("storageClassName") == "nfs-cold"
        for d in pvcs
    ):
        problems.append("PVC cluster-state-backup on nfs-cold is missing")

    roles = [d for _, d in by_kind.get("ClusterRole", [])]
    if len(roles) != 1:
        problems.append("expected one ClusterRole")
    else:
        rules = roles[0].get("rules") or []
        if rules != [{
            "apiGroups": [""],
            "resources": ["secrets", "configmaps"],
            "verbs": ["get", "list"],
        }]:
            problems.append(f"ClusterRole is not exactly get/list on secrets and configmaps: {rules}")

    cms = [d for _, d in by_kind.get("ConfigMap", [])]
    recipients = [d for d in cms if d["metadata"]["name"] == "cluster-state-backup-recipient"]
    if len(recipients) != 1 or (recipients[0].get("data") or {}).get("recipient") != RECIPIENT:
        problems.append("recipient ConfigMap does not hold the Owner age public key")
    return problems


def rule_problems(path: Path) -> list[str]:
    if not path.is_file():
        return ["PrometheusRule file is missing"]
    doc = yaml.safe_load(path.read_text())
    problems: list[str] = []
    if doc.get("kind") != "PrometheusRule":
        problems.append("cluster-state rules file is not a PrometheusRule")
        return problems
    alerts = [
        rule.get("alert")
        for group in (doc.get("spec") or {}).get("groups") or []
        for rule in group.get("rules") or []
    ]
    if "BifrostClusterStateBackupStale" not in alerts:
        problems.append("alert BifrostClusterStateBackupStale is missing")
    expr = "\n".join(
        rule.get("expr") or ""
        for group in doc["spec"]["groups"]
        for rule in group["rules"]
        if rule.get("alert") == "BifrostClusterStateBackupStale"
    )
    for snippet in (
        "kube_cronjob_status_last_successful_time",
        'namespace="kube-system"',
        'cronjob="cluster-state-backup"',
        "129600",
    ):
        if snippet not in expr:
            problems.append(f"stale alert expr is missing {snippet}")
    return problems


def runbook_problems(path: Path) -> list[str]:
    if not path.is_file():
        return ["restore runbook is missing"]
    text = path.read_text()
    problems = []
    for snippet in (
        "--cluster-reset",
        "--cluster-reset-restore-path",
        "age --decrypt",
        "plaintext_sha256",
        "MANIFEST",
        "解密后先对照 MANIFEST 的 plaintext_sha256，通过之后才执行 k3s 恢复",
    ):
        if snippet not in text:
            problems.append(f"runbook is missing {snippet}")
    if "SHA256SUMS" in text:
        problems.append("runbook still verifies a plaintext snapshot via SHA256SUMS")
    if "没有 age 加密" in text:
        problems.append("runbook still says the snapshot is not age-encrypted")
    return problems


def check(root: Path) -> list[str]:
    backup = root / "k8s/data/cluster-state-backup"
    problems: list[str] = []
    script = backup / "backup.sh"
    tools = backup / "fetch-tools.sh"
    if not script.is_file():
        return ["backup.sh is missing"]
    problems += script_problems(script.read_text())
    if not tools.is_file():
        problems.append("fetch-tools.sh is missing")
    else:
        problems += tools_problems(tools.read_text())
    problems += manifest_problems(backup)
    rule = root / "k8s/monitoring/bifrost-cluster-state-rules.yaml"
    problems += rule_problems(rule)
    problems += runbook_problems(root / "docs/runbooks/cluster-state-restore.md")
    readme = backup / "README.md"
    if not readme.is_file():
        problems.append("cluster-state-backup README is missing")
    elif "downloads age and kubectl at runtime" not in readme.read_text():
        problems.append("README does not document the init-container download risk")
    # The shared alerting file is not this lane's. Refuse to have grown a copy of the alert there
    # only when this function is pointed at the repo (self-test trees have no such file).
    shared = root / "k8s/monitoring/bifrost-alerting-rules.yaml"
    if shared.is_file() and "BifrostClusterStateBackup" in shared.read_text():
        problems.append("BifrostClusterStateBackup must not be added to bifrost-alerting-rules.yaml")
    return problems


def parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def kubectl(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["kubectl", *args],
        capture_output=True,
        text=True,
        stdin=subprocess.DEVNULL,
        timeout=60,
        check=False,
    )


def target_tree_problems(root: Path, today: str) -> list[str]:
    """Read a backup tree. Flag plaintext snapshot names and a missing MANIFEST."""
    problems: list[str] = []
    manifest = root / "daily" / today / "MANIFEST"
    if not manifest.is_file():
        problems.append(f"today's MANIFEST is missing under {root}/daily/{today}")
    if not root.is_dir():
        return problems
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        dirnames[:] = [
            name for name in dirnames if not os.path.islink(os.path.join(dirpath, name))
        ]
        for name in filenames:
            if name.startswith("etcd-snapshot-") and not name.endswith(".age"):
                problems.append(
                    "etcd-snapshot file on the target does not end in .age: "
                    + os.path.join(dirpath, name)
                )
    return problems


def find_readonly_dir(nfs_path: str) -> Path | None:
    """Locate the PVC directory on an existing local path. Never mounts it."""
    override = os.environ.get("CLUSTER_STATE_BACKUP_DIR")
    if override:
        path = Path(override)
        return path if path.is_dir() else None
    leaf = Path(nfs_path).name
    if not leaf or leaf in {".", "/"}:
        return None
    candidates = [
        Path(nfs_path),
        Path("/Volumes/k3s-cold") / leaf,
        Path("/volume1/k3s-cold") / leaf,
        Path("/mnt/k3s-cold") / leaf,
    ]
    for cand in candidates:
        if cand.is_dir():
            return cand
    return None


def live_target_problems() -> list[str]:
    """Read the PVC through kubectl get and a local directory. No pod, no mount."""
    pvc = kubectl("get", "pvc", "-n", "kube-system", "cluster-state-backup", "-o", "json")
    if pvc.returncode != 0:
        detail = pvc.stderr.strip() or "kubectl failed"
        return [f"cannot read PVC cluster-state-backup: {detail}"]
    try:
        meta = json.loads(pvc.stdout)
    except json.JSONDecodeError:
        return ["PVC cluster-state-backup is not JSON"]
    volume = (meta.get("spec") or {}).get("volumeName") or ""
    if not volume:
        return ["PVC cluster-state-backup has no volumeName; not creating a pod to read it"]
    pv = kubectl("get", "pv", volume, "-o", "json")
    if pv.returncode != 0:
        detail = pv.stderr.strip() or "kubectl failed"
        return [f"cannot read PV {volume}: {detail}"]
    try:
        spec = json.loads(pv.stdout).get("spec") or {}
    except json.JSONDecodeError:
        return [f"PV {volume} is not JSON"]
    nfs = spec.get("nfs") or {}
    path = nfs.get("path") or ""
    if not path:
        return [f"PV {volume} has no nfs.path; not mounting it"]
    root = find_readonly_dir(path)
    if root is None:
        server = nfs.get("server") or "?"
        return [
            f"target dir {server}:{path} is not on a local read-only path; "
            "not creating a pod or mount to read it"
        ]
    today = datetime.now(timezone.utc).date().isoformat()
    return target_tree_problems(root, today)


def live_check() -> list[str]:
    """Read-only. Does not print job logs or MANIFEST contents."""
    problems: list[str] = []
    jobs = kubectl(
        "get", "jobs", "-n", "kube-system",
        "-l", "app.kubernetes.io/name=cluster-state-backup",
        "-o", "json",
    )
    if jobs.returncode != 0:
        return [f"kubectl get jobs failed: {jobs.stderr.strip()}"]
    newest: tuple[datetime, str] | None = None
    for item in json.loads(jobs.stdout).get("items") or []:
        status = item.get("status") or {}
        if not status.get("succeeded"):
            continue
        stamp = status.get("completionTime") or status.get("startTime")
        if not stamp:
            continue
        when = parse_time(stamp)
        name = item["metadata"]["name"]
        if newest is None or when > newest[0]:
            newest = (when, name)
    if newest is None:
        return ["no successful cluster-state-backup Job (a manual run counts; CronJob lastSuccessfulTime is not required)"]
    when, name = newest
    age = datetime.now(timezone.utc) - when
    if age >= timedelta(seconds=STALE_SECONDS):
        problems.append(f"newest success {name} is {age} old, not under 36h")
    logs = kubectl("logs", "-n", "kube-system", f"job/{name}", "-c", "backup")
    if logs.returncode != 0:
        problems.append(f"kubectl logs job/{name} -c backup failed: {logs.stderr.strip()}")
        return problems
    today = datetime.now(timezone.utc).date().isoformat()
    needle = f"verified daily/{today} snapshot_sha256=ok age_header=ok"
    if needle not in logs.stdout:
        problems.append(f"job {name} log has no verification line for daily/{today}")
    if SECRET_LOG.search(logs.stdout):
        problems.append(f"job {name} log contains secret material; not printing it")
    problems += live_target_problems()
    return problems


def self_test() -> int:
    bad = script_problems("kubectl get secrets -A -o yaml > /tmp/secrets.yaml\n")
    if not any("redirect" in item or "YAML" in item for item in bad):
        print(f"self-test FAILED: plaintext redirect not flagged: {bad}")
        return 1
    if not script_problems("age-keygen -o /tmp/key\n"):
        print("self-test FAILED: key generation not flagged")
        return 1
    plain_cp = script_problems('cp -f "$newest" "$WORK/etcd-snapshot-node"\n')
    if not any("plaintext snapshot copied to the target without age" in item for item in plain_cp):
        print(f"self-test FAILED: plaintext snapshot cp not flagged: {plain_cp}")
        return 1
    host_cp = 'cp "$SNAPSHOT_DIR/etcd-snapshot-node" "$BACKUP_ROOT/daily/etcd-snapshot-node"\n'
    if not any("plaintext snapshot" in item for item in script_problems(host_cp)):
        print("self-test FAILED: snapshot dir cp not flagged")
        return 1
    aged = 'age -r "$RECIPIENT" -o "$WORK/etcd-snapshot-node.age" < "$newest"\n'
    if snapshot_target_problems(aged):
        print(f"self-test FAILED: age write flagged: {snapshot_target_problems(aged)}")
        return 1
    via_fn = 'encrypt_stdin "$WORK/$snap_age" < "$newest"\n'
    if snapshot_target_problems(via_fn):
        print(f"self-test FAILED: encrypt_stdin of the snapshot flagged: {snapshot_target_problems(via_fn)}")
        return 1
    good = script_problems((BACKUP / "backup.sh").read_text())
    if good:
        print("self-test FAILED: backup.sh rejected:")
        for item in good:
            print(f"  {item}")
        return 1
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        day = root / "daily" / "2026-10-07"
        day.mkdir(parents=True)
        (day / "MANIFEST").write_text("timestamp 2026-10-07T00:00:00Z\n", encoding="utf-8")
        (day / "etcd-snapshot-node").write_bytes(b"not a snapshot")
        flagged = target_tree_problems(root, "2026-10-07")
        if not any("does not end in .age" in item for item in flagged):
            print(f"self-test FAILED: plaintext snapshot file not flagged: {flagged}")
            return 1
        (day / "etcd-snapshot-node").unlink()
        (day / "etcd-snapshot-node.age.partial").write_bytes(b"partial")
        partial = target_tree_problems(root, "2026-10-07")
        if not any("does not end in .age" in item for item in partial):
            print(f"self-test FAILED: snapshot temp name not flagged: {partial}")
            return 1
        (day / "etcd-snapshot-node.age.partial").unlink()
        (day / "etcd-snapshot-node.age").write_bytes(b"age-encryption.org/v1\n")
        clean = target_tree_problems(root, "2026-10-07")
        if clean:
            print(f"self-test FAILED: ciphertext tree rejected: {clean}")
            return 1
        (day / "MANIFEST").unlink()
        missing = target_tree_problems(root, "2026-10-07")
        if not any("MANIFEST" in item for item in missing):
            print(f"self-test FAILED: missing MANIFEST not flagged: {missing}")
            return 1
    tree = check(ROOT)
    if tree:
        print("self-test FAILED: tree rejected:")
        for item in tree:
            print(f"  {item}")
        return 1
    print("self-test ok")
    return 0


def main(argv: list[str]) -> int:
    if "--self-test" in argv:
        return self_test()
    problems = check(ROOT)
    if "--live" in argv:
        problems += live_check()
    for item in problems:
        print(item)
    if problems:
        print(f"cluster-state-backup: {len(problems)} problem(s)")
        return 1
    if "--live" in argv:
        print(
            "cluster-state-backup: static ok, live success is under 36h, "
            "today's MANIFEST exists, no plaintext snapshot"
        )
    else:
        print("cluster-state-backup: cronjob, age, nfs-cold, snapshot ciphertext only")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
