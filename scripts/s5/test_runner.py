import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    "s5runner", ROOT / "docker/s5-checker/runner.py"
)
r = importlib.util.module_from_spec(spec)
spec.loader.exec_module(r)


def key():
    v = dict(zip(r.FIELDS, ["a" * 64] * len(r.FIELDS)))
    v.update(
        schema=2,
        env="dev",
        tenant="dev",
        repo="bifrost-platform",
        task="task-1",
        attempt="attempt-1",
        op="op-1",
        ruleVersion=3,
        generation=1,
        checkerImageDigest="sha256:" + "a" * 64,
    )
    for i, name in enumerate(r.GIT_FIELDS, 1):
        v[name] = str(i) * 40
    return v


def environ(k):
    return {
        "S5_KEY": r.canonical(k).decode(),
        "S5_BASE": k["M0"],
        "S5_REVISION": k["R"],
        "S5_UI": k["uiSHA"],
        "S5_KEY_DIGEST": r.digest(k),
        "S5_GENERATION": str(k["generation"]),
        "S5_CI_UID": "uid",
    }


@pytest.mark.parametrize("field", r.FIELDS)
def test_key_is_complete_and_bound(field):
    k = key()
    assert r.request(environ(k)) == k
    env = environ(k)
    del k[field]
    env["S5_KEY"] = r.canonical(k).decode()
    with pytest.raises((ValueError, KeyError)):
        r.request(env)


@pytest.mark.parametrize(
    "field",
    ["S5_BASE", "S5_REVISION", "S5_UI", "S5_KEY_DIGEST", "S5_GENERATION", "S5_CI_UID"],
)
def test_actual_parameters_cannot_be_replaced(field):
    env = environ(key())
    env[field] = ""
    with pytest.raises(ValueError):
        r.request(env)


def test_generation_uint64_and_unbuilt():
    k = key()
    assert (
        r.digest(k)
        == "a063d6646b03777223c75015de4a8ce14f2f0620d8f1c0e481fcc963be6259db"
    )
    k["generation"] = 2**64 - 1
    assert r.request(environ(k)) == k
    for generation in [0, -1, 2**64, True, 1.0]:
        k["generation"] = generation
        with pytest.raises(ValueError):
            r.request(environ(k))
    k = key()
    k["checkerImageDigest"] = "sha256:" + "0" * 64
    with pytest.raises(ValueError, match="UNBUILT"):
        r.request(environ(k))
    env = environ(key())
    env["S5_KEY"] = env["S5_KEY"].replace('"schema":2', '"schema":1,"schema":2')
    with pytest.raises(ValueError, match="duplicate"):
        r.request(env)


def local_git(repo, *args, data=None):
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "test",
        "GIT_AUTHOR_EMAIL": "test@example.invalid",
        "GIT_COMMITTER_NAME": "test",
        "GIT_COMMITTER_EMAIL": "test@example.invalid",
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_CONFIG_NOSYSTEM": "1",
    }
    return (
        subprocess.check_output(
            ["git", "--git-dir=" + str(repo), *args], input=data, env=env
        )
        .decode()
        .strip()
    )


def git_trees(tmp_path):
    trees = tmp_path / "trees"
    trees.mkdir()
    repo = trees / "platform.git"
    local_git(repo, "init", "--bare")
    # Poison files in R are data. No checkout, import or execution is required.
    before = local_git(repo, "hash-object", "-w", "--stdin", data=b"original\n")
    after = local_git(repo, "hash-object", "-w", "--stdin", data=b'{"passed":true}\n')
    tree0 = local_git(
        repo, "mktree", data=f"100644 blob {before}\tpassed.json\n".encode()
    )
    tree1 = local_git(
        repo, "mktree", data=f"100644 blob {after}\tpassed.json\n".encode()
    )
    m0 = local_git(repo, "commit-tree", tree0, data=b"base\n")
    rev = local_git(repo, "commit-tree", tree1, "-p", m0, data=b"replay\n")
    for name, sha in [("base", m0), ("a", rev), ("m0", m0), ("revision", rev)]:
        local_git(repo, "update-ref", "refs/s5/" + name, sha)
    ui = trees / "ui.git"
    local_git(ui, "init", "--bare")
    uitree = local_git(ui, "mktree", data=b"")
    uisha = local_git(ui, "commit-tree", uitree, data=b"ui\n")
    local_git(ui, "update-ref", "refs/s5/ui", uisha)
    k = key()
    k.update(
        base=m0, A=rev, M0=m0, R=rev, baselineTree=tree0, resultTree=tree1, uiSHA=uisha
    )
    return trees, k, before, after


def test_git_identities_are_measured_not_copied(tmp_path):
    trees, k, _, _ = git_trees(tmp_path)
    actual = r.identities(trees, k)
    assert actual["base-commit"] == k["M0"] and actual["result-tree"] == k["resultTree"]
    for field in ["base", "A", "M0", "R", "baselineTree", "resultTree", "uiSHA"]:
        with pytest.raises(ValueError, match="identity|mismatch"):
            r.identities(trees, {**k, field: "f" * 40})


@pytest.mark.parametrize(
    "mutation",
    [
        "",
        "empty",
        "fail",
        "false",
        "wrong-tree",
        "fake-digest",
        "wrong-blob",
        "oversize",
    ],
)
def test_supervisor_only_accepts_image_checker_output(tmp_path, monkeypatch, mutation):
    trees, k, before, after = git_trees(tmp_path)
    root = tmp_path / "image"
    (root / "bin").mkdir(parents=True)
    materials = {
        n: k[n]
        for n in [
            "profileDigest",
            "toolchainDigest",
            "callersDigest",
            "typesDigest",
            "testsDigest",
            "uiSHA",
        ]
    }
    (root / "materials.json").write_bytes(r.canonical(materials))
    e = r.evidence_bindings(k, "uid")
    e.update(
        files=[{"path": "passed.json", "beforeBlob": before, "afterBlob": after}],
        findings=[],
        passed=True,
    )
    if mutation == "false":
        e["passed"] = False
    if mutation == "wrong-tree":
        e["resultTree"] = "f" * 40
    if mutation == "fake-digest":
        e["keyDigest"] = "f" * 64
    if mutation == "wrong-blob":
        e["files"][0]["afterBlob"] = "f" * 40
    if mutation == "oversize":
        e["files"][0]["path"] = "x" * 4000
    # Only the TEST image supplies a stub. Production always uses the fixed binary.
    binary = root / "bin/s5check"
    body = (
        "#!"
        + sys.executable
        + '\nimport json,sys\nrequest=json.load(sys.stdin)\nassert request["platformGitDir"].endswith("platform.git")\n'
    )
    if mutation == "fail":
        body += "sys.exit(1)\n"
    elif mutation != "empty":
        body += "sys.stdout.write(" + repr(r.canonical(e).decode()) + ")\n"
    binary.write_text(body)
    binary.chmod(0o755)
    monkeypatch.setattr(r, "ROOT", root)
    # macOS cannot exercise Linux seccomp/setuid/mounts. Replace only those
    # kernel boundaries, retaining the real Git reader and result validation.
    monkeypatch.setattr(r, "sandbox_child", lambda: None)
    monkeypatch.setattr(
        r.os, "statvfs", lambda _: type("RO", (), {"f_flag": os.ST_RDONLY})()
    )
    results = tmp_path / "results"
    if mutation:
        with pytest.raises((ValueError, json.JSONDecodeError)):
            r.check(trees, k, "uid", results)
        assert not list(results.glob("*"))
    else:
        r.check(trees, k, "uid", results)
        assert (results / "evidence-digest").read_text() == r.digest(e)
        assert (results / "base-commit").read_text() == k["M0"]
        assert r.checked_json((results / "evidence").read_text()) == e


def test_writable_tree_mount_is_rejected(tmp_path, monkeypatch):
    monkeypatch.setattr(r.os, "statvfs", lambda _: type("RW", (), {"f_flag": 0})())
    with pytest.raises(ValueError, match="read-only"):
        r.check(tmp_path, key(), "uid", tmp_path / "results")


@pytest.mark.skipif(
    sys.platform != "linux" or os.geteuid() != 0,
    reason="requires Linux/amd64 root sandbox fixture",
)
def test_kernel_sandbox_denies_network():
    proc = subprocess.run(
        ["/usr/local/bin/python3", "-c", "import socket; socket.socket()"],
        preexec_fn=r.sandbox_child,
        capture_output=True,
    )
    assert proc.returncode != 0 and b"Operation not permitted" in proc.stderr
