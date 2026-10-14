"""restore.sh refusals that test_backup_logic.py does not reach (TD-339).

The backup comes from the production backup.sh with the offline fixture; the archive is then replaced
by one built here where a test needs unsafe members. The fixture's fake age only models the file
format: "<three header lines><plaintext>".
"""

from pathlib import Path
import hashlib
import io
import os
import subprocess
import sys
import tarfile

import pytest

from test_backup_logic import HERE, STAMP, fixture, run  # noqa: F401  (fixture is a pytest fixture)

FAKE_AGE_HEADER = b"age-encryption.org/v1\n-> fake\n" + b"x" * 80 + b"\n"
SUCCESS = "Decrypted, plaintext sha256 checked, extracted to"


def backed_up(f):
    r = run(f)
    assert r.returncode == 0, r.stdout + r.stderr
    return f["backup"] / STAMP


def restore(f, run_dir, target):
    return subprocess.run(
        ["bash", str(HERE / "restore.sh"), str(run_dir), str(f["recipient"]), str(target)],
        env=f["env"],
        text=True,
        capture_output=True,
        timeout=60,
    )


def writable(path):
    path.parent.chmod(0o700)
    if path.exists():
        path.chmod(0o600)
    return path


def replace_archive(run_dir, members):
    """Put an archive with the given member names in place and keep both checksums valid."""
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tar:
        for name in members:
            info = tarfile.TarInfo(name)
            data = b"x"
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    plain = buf.getvalue()
    cipher = FAKE_AGE_HEADER + plain
    writable(run_dir / "data.tar.age").write_bytes(cipher)
    sums = writable(run_dir / "SHA256SUMS")
    lines = []
    for line in sums.read_text().splitlines():
        if line.endswith("  data.tar.age"):
            line = hashlib.sha256(cipher).hexdigest() + "  data.tar.age"
        elif line.startswith("# plaintext_sha256 data.tar "):
            line = "# plaintext_sha256 data.tar " + hashlib.sha256(plain).hexdigest()
        lines.append(line)
    sums.write_text("\n".join(lines) + "\n")


def replace_tool(f, name, body):
    tool = Path(f["env"]["PATH"].split(os.pathsep)[0]) / name
    tool.write_text(f"#!{sys.executable}\n" + body)
    tool.chmod(0o755)


def nothing_restored(target):
    assert not target.exists() and not target.is_symlink()
    sidecar = Path(str(target) + ".MANIFEST.tsv")
    assert not sidecar.exists() and not sidecar.is_symlink()


def test_a_replaced_archive_with_safe_members_restores(fixture):
    # The control for the two tests below: the same replacement, harmless names.
    f = fixture
    run_dir = backed_up(f)
    replace_archive(run_dir, ["git/repositories/admin/alpha.git/HEAD", "gitea/conf/app.ini"])
    target = f["work"] / "restored"
    r = restore(f, run_dir, target)
    assert r.returncode == 0, r.stdout + r.stderr
    assert SUCCESS in r.stdout
    assert (target / "git/repositories/admin/alpha.git/HEAD").read_text() == "x"


@pytest.mark.parametrize("member", ["../escaped", "git/../../escaped", "/tmp/gitea-restore-absolute-member", "a/.."])
def test_an_unsafe_member_is_refused_before_anything_is_extracted(fixture, member):
    f = fixture
    run_dir = backed_up(f)
    replace_archive(run_dir, ["git/repositories/admin/alpha.git/HEAD", member])
    target = f["work"] / "restored"
    r = restore(f, run_dir, target)
    assert r.returncode != 0
    assert "FATAL: unsafe archive member" in r.stderr
    assert SUCCESS not in r.stdout
    nothing_restored(target)
    assert not (f["work"] / "escaped").exists()


@pytest.mark.parametrize("code", [2, 127])
def test_a_member_check_that_cannot_run_is_not_a_pass(fixture, code):
    # TD-339: "grep found nothing" and "grep did not run" used to look the same to the script.
    f = fixture
    run_dir = backed_up(f)
    replace_tool(f, "grep", f"import sys\nsys.exit({code})\n")
    target = f["work"] / "restored"
    r = restore(f, run_dir, target)
    assert r.returncode != 0, r.stdout + r.stderr
    assert "FATAL: archive member check could not run" in r.stderr
    assert SUCCESS not in r.stdout
    nothing_restored(target)


@pytest.mark.parametrize("kind", ["file", "dangling link", "directory"])
def test_something_already_at_the_manifest_path_is_refused_and_left_alone(fixture, kind):
    f = fixture
    run_dir = backed_up(f)
    target = f["work"] / "restored"
    sidecar = Path(str(target) + ".MANIFEST.tsv")
    if kind == "file":
        sidecar.write_text("mine\n")
    elif kind == "dangling link":
        sidecar.symlink_to(f["work"] / "nowhere")
    else:
        sidecar.mkdir()
    r = restore(f, run_dir, target)
    assert r.returncode != 0
    assert "FATAL: manifest path next to target must not exist" in r.stderr
    assert SUCCESS not in r.stdout
    assert not target.exists()
    if kind == "file":
        assert sidecar.read_text() == "mine\n"
    elif kind == "dangling link":
        assert sidecar.is_symlink() and not (f["work"] / "nowhere").exists()
    else:
        assert sidecar.is_dir() and list(sidecar.iterdir()) == []


@pytest.mark.parametrize("kind", ["directory", "dangling link"])
def test_something_already_at_the_target_is_refused(fixture, kind):
    f = fixture
    run_dir = backed_up(f)
    target = f["work"] / "restored"
    if kind == "directory":
        target.mkdir()
    else:
        target.symlink_to(f["work"] / "nowhere")
    r = restore(f, run_dir, target)
    assert r.returncode != 0
    assert "FATAL: target must not exist" in r.stderr
    assert SUCCESS not in r.stdout
    assert not (f["work"] / "nowhere").exists()
    assert not Path(str(target) + ".MANIFEST.tsv").exists()


# A tool that prints the right thing and then fails has still failed (TD-339, second round). Each wrapper
# passes the real tool's output through unchanged and then reports failure for the one call under test.
PRINTS_THEN_FAILS = {
    "cat": (
        "import subprocess, sys\nsubprocess.run(['/bin/cat', *sys.argv[1:]])\nsys.exit(1)\n",
        "FATAL: run STATUS could not be read",
    ),
    "sha256sum": (
        "import os, subprocess, sys\nargs = sys.argv[1:]\n"
        "rc = subprocess.run([os.environ['REAL_SHA256SUM'], *args]).returncode\n"
        "sys.exit(rc if '-c' in args else 1)\n",
        "FATAL: plaintext archive sha256 could not be computed",
    ),
    "awk": (
        "import os, subprocess, sys\nargs = sys.argv[1:]\n"
        "rc = subprocess.run([os.environ['REAL_AWK'], *args]).returncode\n"
        "sys.exit(1 if args[:1] == ['{print $1}'] else rc)\n",
        "FATAL: plaintext archive sha256 could not be computed",
    ),
}


@pytest.mark.parametrize("tool", sorted(PRINTS_THEN_FAILS))
def test_a_tool_that_prints_the_expected_value_and_then_fails_is_not_a_pass(fixture, tool):
    f = fixture
    run_dir = backed_up(f)
    body, message = PRINTS_THEN_FAILS[tool]
    replace_tool(f, tool, body)
    target = f["work"] / "restored"
    r = restore(f, run_dir, target)
    assert r.returncode != 0, r.stdout + r.stderr
    assert message in r.stderr
    assert SUCCESS not in r.stdout
    nothing_restored(target)


def test_a_target_ending_with_a_slash_is_refused(fixture):
    # "<target>.MANIFEST.tsv" would otherwise land inside the restored tree as ".MANIFEST.tsv".
    f = fixture
    run_dir = backed_up(f)
    target = f["work"] / "restored"
    r = subprocess.run(
        ["bash", str(HERE / "restore.sh"), str(run_dir), str(f["recipient"]), str(target) + "/"],
        env=f["env"],
        text=True,
        capture_output=True,
        timeout=60,
    )
    assert r.returncode != 0
    assert "FATAL: target must not end with a slash" in r.stderr
    assert SUCCESS not in r.stdout
    nothing_restored(target)
