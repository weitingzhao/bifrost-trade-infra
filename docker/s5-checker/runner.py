"""Image-owned S5 transport. Never import, build or launch tooling from R."""

import ctypes
import errno
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import resource
import signal
import subprocess
import sys
import tempfile

ROOT = Path("/opt/s5")
GIT_URL = "http://gitea.cicd.svc.cluster.local:3000/bifrost/"
FIELDS = (
    "schema env tenant repo task attempt op base A M0 R baselineTree resultTree "
    "uiSHA ruleVersion ruleDigest profileDigest checkerImageDigest toolchainDigest "
    "callersDigest typesDigest testsDigest reviewBindingDigest patchEvidenceDigest generation"
).split()
DIGESTS = (
    "ruleDigest profileDigest toolchainDigest callersDigest typesDigest testsDigest "
    "reviewBindingDigest patchEvidenceDigest"
).split()
GIT_FIELDS = "base A M0 R baselineTree resultTree uiSHA".split()


def canonical(value):
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode()


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def checked_json(raw):
    value = json.loads(raw)
    if canonical(value) != raw.encode():
        raise ValueError("S5_CI_IDENTITY: noncanonical or duplicate JSON")
    return value


def valid_hex(value, length):
    return (
        isinstance(value, str)
        and re.fullmatch("[0-9a-f]{" + str(length) + "}", value)
        and value != "0" * length
    )


def request(environ):
    key = checked_json(environ["S5_KEY"])
    if (
        set(key) != set(FIELDS)
        or key["schema"] != 2
        or key["repo"] != "bifrost-platform"
    ):
        raise ValueError("S5_BINDING: key schema")
    for name in GIT_FIELDS:
        if not valid_hex(key[name], 40):
            raise ValueError("S5_BINDING: Git identity")
    for name in DIGESTS:
        if not valid_hex(key[name], 64):
            raise ValueError("S5_BINDING: digest")
    image = key["checkerImageDigest"]
    if (
        not isinstance(image, str)
        or not image.startswith("sha256:")
        or not valid_hex(image[7:], 64)
    ):
        raise ValueError("S5_CI_IDENTITY: UNBUILT checker")
    for name in ("generation", "ruleVersion"):
        if type(key[name]) is not int or not 0 < key[name] <= 2**64 - 1:
            raise ValueError("S5_BINDING: counter")
    for name in ("env", "tenant", "task", "attempt", "op"):
        if not isinstance(key[name], str) or not re.fullmatch(
            r"[A-Za-z0-9][A-Za-z0-9_.:/-]{0,199}", key[name]
        ):
            raise ValueError("S5_BINDING: operation identity")
    expected = {
        "S5_BASE": key["M0"],
        "S5_REVISION": key["R"],
        "S5_UI": key["uiSHA"],
        "S5_KEY_DIGEST": digest(key),
        "S5_GENERATION": str(key["generation"]),
    }
    if any(environ.get(k) != v for k, v in expected.items()) or not environ.get(
        "S5_CI_UID"
    ):
        raise ValueError("S5_CI_IDENTITY: parameters")
    return key


def git(repo, *args):
    # No inherited config, hooks, helpers, redirects, replacement objects or credentials.
    env = {
        "PATH": "/usr/local/bin:/usr/bin:/bin",
        "HOME": "/nonexistent",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_NO_REPLACE_OBJECTS": "1",
    }
    cmd = [
        "git",
        "-c",
        "safe.directory=" + str(repo),
        "-c",
        "core.hooksPath=/dev/null",
        "-c",
        "credential.helper=",
        "-c",
        "http.followRedirects=false",
        "-c",
        "protocol.file.allow=never",
        "--git-dir=" + str(repo),
        *args,
    ]
    return (
        subprocess.run(cmd, env=env, check=True, capture_output=True, timeout=180)
        .stdout.decode()
        .strip()
    )


def identities(trees, key):
    repo = trees / "platform.git"
    expected = {
        "base-commit": (repo, "refs/s5/m0^{commit}", key["M0"]),
        "revision-commit": (repo, "refs/s5/revision^{commit}", key["R"]),
        "baseline-tree": (repo, "refs/s5/m0^{tree}", key["baselineTree"]),
        "result-tree": (repo, "refs/s5/revision^{tree}", key["resultTree"]),
        "ui-commit": (trees / "ui.git", "refs/s5/ui^{commit}", key["uiSHA"]),
    }
    actual = {
        name: git(repo, "rev-parse", "--verify", ref)
        for name, (repo, ref, _) in expected.items()
    }
    if any(actual[name] != want for name, (_, _, want) in expected.items()):
        raise ValueError("S5_BINDING: fetched commit/tree mismatch")
    for ref, want in [("base", key["base"]), ("a", key["A"])]:
        if git(repo, "rev-parse", "--verify", "refs/s5/" + ref + "^{commit}") != want:
            raise ValueError("S5_BINDING: source patch identity")
    return actual


def fetch(trees, key):
    for name, refs in [
        (
            "platform",
            {"base": key["base"], "a": key["A"], "m0": key["M0"], "revision": key["R"]},
        ),
        ("ui", {"ui": key["uiSHA"]}),
    ]:
        repo = trees / (name + ".git")
        repo.mkdir(parents=True, exist_ok=False)
        git(repo, "init", "--bare")
        git(
            repo,
            "fetch",
            "--no-tags",
            GIT_URL + "bifrost-" + name + ".git",
            *[sha + ":refs/s5/" + ref for ref, sha in refs.items()],
        )
    identities(trees, key)


def sandbox_child():
    """Linux/amd64 only; syscall network denial is inherited by suite children.

    No dependency on NetworkPolicy convergence. The image-owned checker must
    run behavior code in its own child and collect assertions outside that child.
    This wrapper never considers candidate stdout/files a test report.
    """
    if platform.system() != "Linux" or platform.machine() != "x86_64":
        raise RuntimeError("unsupported S5 sandbox")
    os.setgroups([])
    os.setgid(65532)
    os.setuid(65532)
    resource.setrlimit(resource.RLIMIT_CPU, (240, 240))
    resource.setrlimit(resource.RLIMIT_FSIZE, (1048576, 1048576))
    resource.setrlimit(resource.RLIMIT_NOFILE, (128, 128))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    libc = ctypes.CDLL(None, use_errno=True)

    class Filter(ctypes.Structure):
        _fields_ = [
            ("code", ctypes.c_ushort),
            ("jt", ctypes.c_ubyte),
            ("jf", ctypes.c_ubyte),
            ("k", ctypes.c_uint),
        ]

    class Program(ctypes.Structure):
        _fields_ = [("length", ctypes.c_ushort), ("filters", ctypes.POINTER(Filter))]

    # Fail closed for non-x86_64 (including 32-bit and x32 syscall ABIs).
    code = [
        (0x20, 0, 0, 4),
        (0x15, 1, 0, 0xC000003E),
        (0x06, 0, 0, 0x80000000),
        (0x20, 0, 0, 0),
        (0x35, 0, 1, 0x40000000),
        (0x06, 0, 0, 0x80000000),
    ]
    # socket family, ptrace, namespace/mount escape and io_uring networking.
    for nr in [
        41,
        42,
        43,
        44,
        45,
        46,
        47,
        48,
        49,
        50,
        51,
        52,
        53,
        54,
        55,
        101,
        109,
        112,
        165,
        166,
        272,
        288,
        299,
        307,
        308,
        310,
        311,
        425,
        426,
        427,
    ]:
        code.extend([(0x15, 0, 1, nr), (0x06, 0, 0, 0x00050000 | errno.EPERM)])
    code.append((0x06, 0, 0, 0x7FFF0000))
    filters = (Filter * len(code))(*[Filter(*entry) for entry in code])
    prog = Program(len(code), filters)
    if libc.prctl(38, 1, 0, 0, 0) or libc.prctl(22, 2, ctypes.byref(prog), 0, 0):
        raise OSError(ctypes.get_errno(), "S5 seccomp setup failed")


def evidence_bindings(key, uid):
    names = (
        "repo base A M0 R baselineTree resultTree ruleVersion ruleDigest checkerImageDigest "
        "toolchainDigest callersDigest typesDigest testsDigest uiSHA reviewBindingDigest patchEvidenceDigest generation"
    ).split()
    result = {n: key[n] for n in names}
    result.update(
        schema=2, policyDigest=key["profileDigest"], ciUID=uid, keyDigest=digest(key)
    )
    return result


def validate_evidence(evidence, key, uid):
    want = evidence_bindings(key, uid)
    if set(evidence) != set(want) | {"files", "findings", "passed"} or any(
        evidence.get(n) != v for n, v in want.items()
    ):
        raise ValueError("S5_BINDING: checker evidence")
    if (
        evidence["passed"] is not True
        or evidence["findings"] != []
        or not isinstance(evidence["files"], list)
    ):
        raise ValueError("S5_BEHAVIOR: checker rejected candidate")
    seen = set()
    for f in evidence["files"]:
        if set(f) != {"path", "beforeBlob", "afterBlob"} or not isinstance(
            f["path"], str
        ):
            raise ValueError("S5_BINDING: evidence files")
        if (
            f["path"] in seen
            or f["path"].startswith("/")
            or ".." in f["path"].split("/")
            or not f["path"]
        ):
            raise ValueError("S5_BINDING: evidence path")
        seen.add(f["path"])
        if not valid_hex(f["beforeBlob"], 40) or not valid_hex(f["afterBlob"], 40):
            raise ValueError("S5_BINDING: evidence blobs")
    # Leave room for the other task results under Tekton's default 4 KiB limit.
    if len(canonical(evidence)) > 3000:
        raise ValueError("S5_EVIDENCE_MISSING: oversized evidence")


def check(trees, key, uid, results):
    if not os.statvfs(trees).f_flag & os.ST_RDONLY:
        raise ValueError("S5_CI_IDENTITY: tree mount must be read-only")
    actual = identities(trees, key)
    pins = checked_json((ROOT / "materials.json").read_text().strip())
    for name in [
        "profileDigest",
        "toolchainDigest",
        "callersDigest",
        "typesDigest",
        "testsDigest",
        "uiSHA",
    ]:
        if pins.get(name) != key[name]:
            raise ValueError("S5_BINDING: image materials " + name)
    results.mkdir(exist_ok=True)
    results.chmod(0o700)  # sandbox uid cannot forge Tekton result files
    req = {
        "schema": 2,
        "key": key,
        "ciUID": uid,
        "platformGitDir": str(trees / "platform.git"),
        "uiGitDir": str(trees / "ui.git"),
        "policyRoot": str(ROOT / "s5check"),
    }
    with tempfile.TemporaryDirectory(prefix="s5-", dir="/tmp") as work:
        os.chmod(work, 0o777)
        with tempfile.TemporaryFile() as stdout, tempfile.TemporaryFile() as stderr:
            proc = subprocess.Popen(
                [str(ROOT / "bin/s5check"), "--ci-request-stdin"],
                stdin=subprocess.PIPE,
                stdout=stdout,
                stderr=stderr,
                cwd=work,
                start_new_session=True,
                preexec_fn=sandbox_child,
                env={
                    "PATH": "/usr/local/bin:/usr/bin:/bin",
                    "HOME": work,
                    "TMPDIR": work,
                    "NODE_PATH": str(ROOT / "node_modules"),
                    "TZ": "UTC",
                    "LANG": "C.UTF-8",
                    "GIT_CONFIG_NOSYSTEM": "1",
                    "GIT_CONFIG_GLOBAL": "/dev/null",
                    "GIT_NO_REPLACE_OBJECTS": "1",
                },
            )
            try:
                proc.communicate(canonical(req), timeout=300)
            except subprocess.TimeoutExpired:
                os.killpg(proc.pid, signal.SIGKILL)
                proc.wait()
                raise ValueError("S5_BEHAVIOR: timeout") from None
            finally:
                # Reap/stop descendants even if the checker exited early.
                try:
                    os.killpg(proc.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            if proc.returncode != 0:
                raise ValueError("S5_BEHAVIOR: checker failed")
            stdout.seek(0)
            raw = stdout.read(3001).decode().strip()
    evidence = checked_json(raw)
    validate_evidence(evidence, key, uid)
    for file in evidence["files"]:
        for commit, blob in [
            (key["M0"], file["beforeBlob"]),
            (key["R"], file["afterBlob"]),
        ]:
            if (
                git(
                    trees / "platform.git",
                    "rev-parse",
                    "--verify",
                    commit + ":" + file["path"],
                )
                != blob
            ):
                raise ValueError("S5_BINDING: evidence blob differs from read tree")
    # Read again after checking; the mount must remain read-only throughout.
    if identities(trees, key) != actual:
        raise ValueError("S5_BINDING: tree changed")
    actual.update(
        {
            "key-digest": digest(key),
            "generation": str(key["generation"]),
            "evidence": canonical(evidence).decode(),
            "evidence-digest": digest(evidence),
        }
    )
    for name, value in actual.items():
        (results / name).write_text(value)


def main():
    key = request(os.environ)
    trees = Path("/workspace/trees")
    if sys.argv[1:] == ["fetch"]:
        fetch(trees, key)
    elif sys.argv[1:] == ["check"]:
        check(trees, key, os.environ["S5_CI_UID"], Path("/tekton/results"))
    else:
        raise ValueError("unknown S5 stage")


if __name__ == "__main__":
    main()
