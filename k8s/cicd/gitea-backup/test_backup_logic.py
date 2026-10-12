"""Execute production bash logic with offline fixtures; no Docker/network/keys.
SQLite and tar are real; fake git/gitea/age model tool outputs and I/O faults.
"""

from datetime import datetime, timezone, timedelta
from pathlib import Path
import os
import shutil
import sqlite3
import subprocess
import sys
import time

import pytest

HERE = Path(__file__).resolve().parent
STAMP = "2026-10-12T120000Z"
KEY = "age1testpublickey"


@pytest.fixture
def fixture(tmp_path):
    bins = tmp_path / "bin"
    bins.mkdir()
    data, backup, work, hooks = [
        tmp_path / n for n in ("data", "backup", "work", "hooks")
    ]
    for p in (data, backup, work, hooks):
        p.mkdir()
    (data / "gitea/conf").mkdir(parents=True)
    db = data / "gitea/gitea.db"
    con = sqlite3.connect(db)
    con.executescript(
        "CREATE TABLE user(id INTEGER, name TEXT, lower_name TEXT, is_admin INTEGER); INSERT INTO user VALUES(1,'Admin','admin',1); CREATE TABLE repository(owner_id INTEGER, lower_name TEXT); INSERT INTO repository VALUES(1,'alpha');"
    )
    con.commit()
    con.close()
    repo = data / "git/repositories/admin/alpha.git"
    repo.mkdir(parents=True)
    (repo / "refs.txt").write_text(
        "refs/heads/main=" + "a" * 40 + "\nrefs/tags/v1=" + "b" * 40 + "\n"
    )
    (data / "gitea/conf/app.ini").write_text(
        f"[database]\nPATH = {db}\n[repository]\nROOT = {data}/git/repositories\n[server]\nHTTP_ADDR = 0.0.0.0\n"
    )
    recipient = tmp_path / "recipient"
    recipient.write_text(KEY)
    script = bins / "fake.py"
    script.write_text(r"""
import sys, os, sqlite3, shutil, time, datetime
from pathlib import Path
name=Path(sys.argv[0]).name
args=sys.argv[1:]
if name == 'sqlite3':
    uri=args[0]; c=sqlite3.connect(uri, uri=uri.startswith('file:'))
    for arg in args[1:]:
        if arg.startswith('.backup '):
            dest=arg[8:]; Path(dest).unlink(missing_ok=True)
            out=sqlite3.connect(dest); c.backup(out); out.close()
        elif not arg.startswith('.'):
            for row in c.execute(arg): print('|'.join(str(v) for v in row))
    c.close()
elif name == 'git':
    if args[0]=='clone':
        assert args[1]=='--mirror' and args[2].startswith('http://127.0.0.1:3000/')
        rel=args[2].split(':3000/')[1]
        shutil.copytree(Path(os.environ['GITEA__repository__ROOT'])/rel, args[3])
    else:
        p=Path(args[0].split('=',1)[1]); op=args[1]
        if op=='fsck':
            sys.exit(1 if (p/'broken').exists() else 0)
        elif op=='for-each-ref':
            print((p/'refs.txt').read_text(),end='')
elif name == 'gitea':
    if args[0]=='web':
        while True: time.sleep(1)
    else: print('throwaway-token')
elif name == 'environment-to-ini':
    p=Path(args[args.index('--config')+1]); p.write_text(p.read_text().replace('HTTP_ADDR = 0.0.0.0','HTTP_ADDR = 127.0.0.1'))
elif name == 'curl': pass
elif name == 'age':
    dest=Path(args[args.index('-o')+1])
    if os.environ.get('FAKE_AGE_FAIL') or (os.environ.get('FAKE_MANIFEST_FULL') and 'MANIFEST' in str(dest)):
        dest.write_bytes(b'partial'); sys.exit(1)
    if '-d' in args:
        b=Path(args[-1]).read_bytes()
        if not b.startswith(b'age-encryption.org/v1\n-> '): sys.exit(1)
        # Test format only. Real authentication/truncation exercised in Docker.
        dest.write_bytes(b.split(b'\n',3)[3])
    else:
        data=sys.stdin.buffer.read()
        dest.write_bytes(b'not ciphertext' if os.environ.get('FAKE_BAD_HEADER') else b'age-encryption.org/v1\n-> fake\n'+b'x'*80+b'\n'+data)
elif name == 'date':
    d=datetime.datetime.strptime(os.environ['FAKE_STAMP'],'%Y-%m-%dT%H%M%SZ').replace(tzinfo=datetime.timezone.utc)
    if '-d' in args: d=datetime.datetime.strptime(args[args.index('-d')+1],'%Y-%m-%d').replace(tzinfo=datetime.timezone.utc)
    fmt=args[-1][1:]
    print(int(d.timestamp()) if fmt=='%s' else d.strftime(fmt))
elif name in ('cp','mv','chmod','sha256sum'):
    fault=os.environ.get('FAIL_COMMAND','')
    if fault and name==fault.split(':')[0] and any(fault.split(':',1)[1] in a for a in args): sys.exit(1)
    if name=='sha256sum' and '-c' in args and os.environ.get('SHA_REJECT_COMMENTS'):
        checked=Path(args[args.index('-c')+1]).read_text()
        if any(line.startswith('#') for line in checked.splitlines()): sys.exit(1)
    os.execv(os.environ['REAL_'+name.upper()], [name]+args)
elif name == 'awk':
    if any(a.startswith('/proc/net/tcp') for a in args): sys.exit(0)
    os.execv(os.environ['REAL_AWK'],[name]+args)
""")
    for name in (
        "sqlite3",
        "git",
        "gitea",
        "environment-to-ini",
        "curl",
        "age",
        "date",
        "cp",
        "mv",
        "chmod",
        "sha256sum",
        "awk",
    ):
        p = bins / name
        p.write_text(f"#!{sys.executable}\n" + script.read_text())
        p.chmod(0o755)
    env = dict(
        os.environ,
        DATA_DIR=str(data),
        BACKUP_DIR=str(backup),
        WORK_DIR=str(work),
        RECIPIENT_FILE=str(recipient),
        REQUIRE_MOUNT="0",
        FAKE_STAMP=STAMP,
        GITEA_BACKUP_TEST_HOOK_DIR=str(hooks),
        PATH=str(bins) + os.pathsep + os.environ["PATH"],
    )
    for name in ("cp", "mv", "chmod", "sha256sum", "awk"):
        env["REAL_" + name.upper()] = shutil.which(name)
    return dict(
        data=data,
        backup=backup,
        work=work,
        hooks=hooks,
        recipient=recipient,
        env=env,
        repo=repo,
    )


def run(f):
    return subprocess.run(
        ["bash", str(HERE / "backup.sh")],
        env=f["env"],
        text=True,
        capture_output=True,
        timeout=45,
    )


def start(f):
    return subprocess.Popen(
        ["bash", str(HERE / "backup.sh")],
        env=f["env"],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def wait_ready(f, key):
    for _ in range(200):
        if (f["hooks"] / (key + ".ready")).exists():
            return
        time.sleep(0.025)
    raise AssertionError("handshake not reached: " + key)


def seed_old(f, stamp="2026-10-11T120000Z", status="OK"):
    p = f["backup"] / stamp
    p.mkdir()
    (p / "STATUS").write_text(status + "\n")
    (f["backup"] / "LATEST").write_text(stamp + "\n")
    return p


def failed_unchanged(f, result, before):
    assert result.returncode != 0, result.stdout + result.stderr
    assert (f["backup"] / "LATEST").read_text() == before
    assert not any(
        p.is_file() and p.read_text() == "OK\n"
        for p in (f["backup"] / (STAMP + ".partial")).glob("STATUS")
    )
    assert not (f["backup"] / STAMP / "STATUS").exists()
    assert not (f["backup"] / ".lock").exists()


def test_normal_archive_precedes_stage_mutation(fixture):
    f = fixture
    f["env"]["SHA_REJECT_COMMENTS"] = "1"
    r = run(f)
    assert r.returncode == 0, r.stdout + r.stderr
    p = f["backup"] / STAMP
    assert {x.name for x in p.iterdir()} == {
        "data.tar.age",
        "MANIFEST.tsv.age",
        "SIZES.tsv",
        "SHA256SUMS",
        "VERIFIED",
        "STATUS",
    }
    assert (
        p / "VERIFIED"
    ).read_text() == "1 repositories and 2 refs matched over HTTP\n"
    target = f["work"] / "restored"
    r = subprocess.run(
        ["bash", str(HERE / "restore.sh"), str(p), str(f["recipient"]), str(target)],
        env=f["env"],
        capture_output=True,
        text=True,
    )
    assert r.returncode == 0, r.stderr
    assert "HTTP_ADDR = 0.0.0.0" in (target / "gitea/conf/app.ini").read_text()
    assert not list(f["work"].glob("run.*"))


@pytest.mark.parametrize(
    "kind", ["database_only", "disk_only", "repository_root_missing"]
)
def test_set_mismatch_after_three_stages(fixture, kind):
    f = fixture
    seed_old(f)
    before = (f["backup"] / "LATEST").read_text()
    if kind == "database_only":
        shutil.rmtree(f["repo"])
    elif kind == "repository_root_missing":
        shutil.rmtree(f["data"] / "git")
    else:
        shutil.copytree(f["repo"], f["repo"].parent / "extra.git")
    r = run(f)
    failed_unchanged(f, r, before)
    assert "after 3 stages" in r.stderr
    assert r.stderr.count("Repository set mismatch, attempt") == 3
    assert ("extra.git" if kind == "disk_only" else "alpha.git") in r.stderr


def test_set_retry_then_equal(fixture):
    f = fixture
    (f["hooks"] / "wait-after-db-1").touch()
    p = start(f)
    wait_ready(f, "after-db-1")
    con = sqlite3.connect(f["data"] / "gitea/gitea.db")
    con.execute("INSERT INTO repository VALUES(1,'beta')")
    con.commit()
    con.close()
    shutil.copytree(f["repo"], f["repo"].parent / "beta.git")
    (f["hooks"] / "after-db-1.release").touch()
    out, err = p.communicate(timeout=45)
    assert p.returncode == 0, out + err
    assert "attempt 1" in err and "attempt 2" not in err
    assert "2 repositories" in (f["backup"] / STAMP / "VERIFIED").read_text()


def test_lock_held_fails_at_once(fixture):
    f = fixture
    lock = f["backup"] / ".lock"
    lock.mkdir()
    epoch = (
        datetime.strptime(STAMP, "%Y-%m-%dT%H%M%SZ")
        .replace(tzinfo=timezone.utc)
        .timestamp()
    )
    os.utime(lock, (epoch, epoch))
    r = run(f)
    assert r.returncode != 0 and "holds the NAS lock" in r.stderr
    assert lock.exists()


def test_stale_lock_reported_and_broken(fixture):
    f = fixture
    lock = f["backup"] / ".lock"
    lock.mkdir()
    os.utime(lock, (0, 0))
    r = run(f)
    assert r.returncode == 0, r.stderr
    assert "older than 3 hours" in r.stderr
    assert not lock.exists()


@pytest.mark.parametrize("newest", [STAMP, "2026-11-12T120000Z"])
def test_non_monotonic_refused_before_retention(fixture, newest):
    f = fixture
    seed_old(f, newest)
    old = seed_old(f, "2025-01-01T000000Z")
    before = (f["backup"] / "LATEST").read_text()
    r = run(f)
    assert r.returncode != 0
    assert (f["backup"] / "LATEST").read_text() == before
    assert (f["backup"] / newest / "STATUS").read_text() == "OK\n"
    assert (
        "clock not monotonic" in r.stderr and newest in r.stderr and STAMP in r.stderr
    )
    assert old.exists()


def test_partial_never_reused(fixture):
    f = fixture
    seed_old(f)
    p = f["backup"] / (STAMP + ".partial")
    p.mkdir()
    (p / "sentinel").touch()
    r = run(f)
    assert r.returncode != 0 and "name already taken" in r.stderr
    assert (p / "sentinel").exists()


@pytest.mark.parametrize(
    "key", ["manifest", "nas-manifest", "sums", "status", "latest"]
)
def test_checked_write_failures_no_ok_no_rotation(fixture, key):
    f = fixture
    seed_old(f)
    old = seed_old(f, "2025-01-01T000000Z")
    before = (f["backup"] / "LATEST").read_text()
    (f["hooks"] / ("fail-" + key)).touch()
    r = run(f)
    failed_unchanged(f, r, before)
    assert old.exists()


@pytest.mark.parametrize(
    "fault", ["sha256sum:data.tar.age", "mv:LATEST.", "chmod:LATEST.", "cp:VERIFIED"]
)
def test_real_tool_write_failure_rolls_back(fixture, fault):
    f = fixture
    old = seed_old(f)
    before = (f["backup"] / "LATEST").read_text()
    f["env"]["FAIL_COMMAND"] = fault
    r = run(f)
    failed_unchanged(f, r, before)
    assert old.exists()


def test_manifest_ciphertext_full_write_removed(fixture):
    f = fixture
    seed_old(f)
    before = (f["backup"] / "LATEST").read_text()
    f["env"]["FAKE_MANIFEST_FULL"] = "1"
    r = run(f)
    failed_unchanged(f, r, before)
    assert not list((f["backup"] / (STAMP + ".partial")).glob("*.age*"))


@pytest.mark.parametrize(
    "value",
    [
        None,
        "",
        "AGE_RECIPIENT",
        "AGE-SECRET-KEY-123",
        "PRIVATE KEY",
        "age1PRIVATE",
        "age1!bad",
    ],
)
def test_recipient_refusals(fixture, value):
    f = fixture
    if value is None:
        f["recipient"].unlink()
    else:
        f["recipient"].write_text(value)
    r = run(f)
    assert r.returncode != 0 and "recipient" in r.stderr
    assert not list(f["backup"].iterdir())


def test_non_age_output_removed(fixture):
    f = fixture
    seed_old(f)
    before = (f["backup"] / "LATEST").read_text()
    f["env"]["FAKE_BAD_HEADER"] = "1"
    r = run(f)
    failed_unchanged(f, r, before)
    assert "age header rejected" in r.stderr
    assert not list((f["backup"] / (STAMP + ".partial")).glob("*.age*"))


def test_retention_seven_plus_four_latest_and_partial(fixture):
    f = fixture
    origin = datetime(2026, 10, 12, 12, tzinfo=timezone.utc)
    names = []
    for day in range(1, 45):
        name = (origin - timedelta(days=day)).strftime("%Y-%m-%dT%H%M%SZ")
        seed_old(f, name)
        names.append(name)
    stale = f["backup"] / "2025-01-01T000000Z.partial"
    fresh = f["backup"] / "2026-10-11T100000Z.partial"
    for p in (stale, fresh):
        p.mkdir()
    os.utime(stale, (0, 0))
    epoch = origin.timestamp()
    os.utime(fresh, (epoch, epoch))
    r = run(f)
    assert r.returncode == 0, r.stderr
    # Anchored trailing windows [day 0..6], [7..13], [14..20], [21..27].
    want = {STAMP, *names[:6], names[6], names[13], names[20]}
    got = {p.name for p in f["backup"].iterdir() if (p / "STATUS").is_file()}
    assert got == want
    assert (f["backup"] / (f["backup"] / "LATEST").read_text().strip()).exists()
    assert not stale.exists() and fresh.exists()


def test_missing_object_fails_after_three_copies(fixture):
    f = fixture
    seed_old(f)
    before = (f["backup"] / "LATEST").read_text()
    (f["repo"] / "broken").touch()
    r = run(f)
    failed_unchanged(f, r, before)
    assert "failed git fsck after 3 copies" in r.stderr


def test_zero_repositories_fails(fixture):
    f = fixture
    con = sqlite3.connect(f["data"] / "gitea/gitea.db")
    con.execute("DELETE FROM repository")
    con.commit()
    con.close()
    r = run(f)
    assert r.returncode != 0 and "zero repositories" in r.stderr


@pytest.mark.parametrize("key", ["manifest", "sums", "status", "latest"])
def test_builtin_write_error_no_ok_latest_unchanged(fixture, key):
    """Block the actual redirection with a directory, not an early failpoint."""
    f = fixture
    old = seed_old(f)
    before = (f["backup"] / "LATEST").read_text()
    (f["hooks"] / ("wait-" + key)).touch()
    p = start(f)
    wait_ready(f, key)
    if key == "manifest":
        dest = next(f["work"].glob("run.*")) / "MANIFEST.tsv"
    elif key == "latest":
        dest = f["backup"] / ("LATEST." + STAMP + ".tmp")
    else:
        dest = (
            f["backup"]
            / (STAMP + ".partial")
            / ("SHA256SUMS" if key == "sums" else "STATUS")
        )
    dest.mkdir()
    (f["hooks"] / (key + ".release")).touch()
    out, err = p.communicate(timeout=45)
    result = subprocess.CompletedProcess(p.args, p.returncode, out, err)
    failed_unchanged(f, result, before)
    assert "directory" in err.lower()
    assert old.exists()


def test_newer_partial_also_prevents_clock_rollback(fixture):
    f = fixture
    old = seed_old(f)
    before = (f["backup"] / "LATEST").read_text()
    newer = f["backup"] / "2026-11-01T000000Z.partial"
    newer.mkdir()
    r = run(f)
    failed_unchanged(f, r, before)
    assert "clock not monotonic" in r.stderr
    assert "2026-11-01T000000Z" in r.stderr
    assert old.exists() and newer.exists()
