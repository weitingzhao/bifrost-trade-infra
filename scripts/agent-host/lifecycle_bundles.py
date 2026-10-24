"""Run directories and bundles for the local sweep (W-31 4.6 S2; CUT-lifecycle-2026-10-24.md
§2 principle 8, R12, §4.3 items 2 and 5; review 539 A7).

A run that deletes anything in a repository first writes <backup root>/<machine>/<repo>/<run id>/,
made with mkdir and never reused, so two runs on one day keep both. In it:

  unique.bundle     commits no ref the remote holds reaches: the reflog and pseudo-ref
                    commits of what is deleted, with their whole history (no prerequisites),
                    so a fresh empty repository restores them from this file alone; that is
                    checked before anything is removed (review 551 C1). The last copy of
                    those objects; nothing here ever deletes it (D-L4 moves such bundles to
                    persistent storage).
  redundant.bundle  the rest of what is deleted beyond the remote's main and tags: the tips
                    (branch tips, worktree HEADs) and the reflog commits that a remote ref
                    other than main reached. Every commit in it was on a ref the remote held,
                    and the bundle keeps them if the remote drops that ref during the run.
                    It may go after LIFECYCLE_BUNDLE_DAYS (90, never less) when a check then
                    shows every head still reachable from the remote's refs.
  refs.tsv          kind, name, sha, bundle ref of every deleted ref, worktree HEAD and
                    archived reflog commit
  manifest.json     the run, what it planned and did, each bundle's kind, heads,
                    prerequisites, size and sha256
  actions.log       one line per deletion, appended as it is done

The redundant bundle is thin against the remote's main and tags, so it restores into a clone
of the remote; the manifest records the prerequisites the bundle's own header lists.
Restore: git fetch <bundle> 'refs/lifecycle-archive/*:refs/restored/*'.
While a bundle is written, its heads are refs/lifecycle-archive/<run id>/<u|r><n> in the
repository, created only where no ref stands and removed by their sha afterwards. A run that
dies between the two leaves them; they keep their objects alive and are reported, not removed.
Bundles from before S2 (<root>/<date>/<repo>.bundle) carry no manifest and are never touched.
"""

from __future__ import annotations

import calendar
import hashlib
import json
import os
import re
import shutil
import stat
import tempfile
import time
from typing import Dict, List, Optional, Tuple

from disk_guard_state import write_report
from lifecycle_git import GitError, git, without_copy

NAME = re.compile(r"^[A-Za-z0-9._-]{1,128}$")
MIN_DAYS = 90
ARCHIVE_NS = "refs/lifecycle-archive/"


class BundleError(Exception):
    pass


def _private_chain(root: str, parts: List[str]) -> str:
    """root/part/... as directories of this user, none a symlink; the last one is made with
    mkdir and must not exist (a run directory is never reused)."""
    cur = root
    os.makedirs(root, mode=0o700, exist_ok=True)
    for i, p in enumerate(parts):
        if not NAME.match(p) or p in (".", ".."):
            raise BundleError(f"{p!r} is not a name a run directory may use")
        cur = os.path.join(cur, p)
        last = i == len(parts) - 1
        try:
            os.mkdir(cur, 0o700)
        except FileExistsError:
            if last:
                raise BundleError(f"{cur} exists: a run directory is never reused")
        st = os.lstat(cur)
        if stat.S_ISLNK(st.st_mode) or not stat.S_ISDIR(st.st_mode) or st.st_uid != os.geteuid():
            raise BundleError(f"{cur} is not a directory of this user (a symlink is not followed)")
    return cur


def new_run_dir(root: str, machine: str, repo: str, run_id: str) -> str:
    return _private_chain(root, [machine, repo, run_id])


def sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def list_heads(env: Dict[str, str], repo: str, path: str) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for line in git(env, repo, "bundle", "list-heads", path).splitlines():
        sha, _, ref = line.partition(" ")
        out[ref] = sha
    return out


def header(path: str) -> Tuple[Dict[str, str], List[str]]:
    """({ref: sha}, prerequisite shas) as the bundle file's own header lists them."""
    refs: Dict[str, str] = {}
    pre: List[str] = []
    with open(path, "rb") as f:
        first = f.readline()
        if first not in (b"# v2 git bundle\n", b"# v3 git bundle\n"):
            raise BundleError(f"{path}: not a v2 or v3 bundle")
        for raw in iter(f.readline, b""):
            line = raw.decode("utf-8", "surrogateescape").rstrip("\n")
            if line == "":
                return refs, pre
            if line.startswith("@"):
                continue
            if line.startswith("-"):
                pre.append(line[1:].split(" ", 1)[0])
            else:
                sha, _, ref = line.partition(" ")
                refs[ref] = sha
    raise BundleError(f"{path}: the header does not end")


def verify_alone(env: Dict[str, str], path: str, heads: Dict[str, str]) -> None:
    """The bundle restores every head into a fresh empty repository, with nothing else."""
    t = tempfile.mkdtemp(prefix="lifecycle-verify-")
    try:
        git(env, t, "init", "-q", "--bare", "v.git")
        v = os.path.join(t, "v.git")
        git(env, v, "bundle", "verify", "-q", path)
        git(env, v, "fetch", "-q", "--no-tags", path, "refs/lifecycle-archive/*:refs/restored/*")
        for sha in heads.values():
            git(env, v, "cat-file", "-e", sha + "^{commit}")
    except GitError as e:
        raise BundleError(f"{path} does not restore alone: {e}")
    finally:
        shutil.rmtree(t, ignore_errors=True)


def make_bundle(env: Dict[str, str], repo: str, run_dir: str, run_id: str, kind: str,
                heads: List[str], prereqs: List[str]) -> Dict[str, object]:
    """Write <run_dir>/<kind>.bundle holding heads beyond prereqs, verified (the unique one
    with no prereqs, and in an empty repository). The entry for the manifest; its "file" is
    None when prereqs already reach every head."""
    beyond = set(without_copy(env, repo, list(dict.fromkeys(heads)), prereqs)) if heads else set()
    heads = [h for h in dict.fromkeys(heads) if h in beyond]  # a head on main or a tag adds nothing
    entry: Dict[str, object] = {"kind": kind, "file": None, "heads": {}, "prerequisites": [],
                                "thin_against": sorted(set(prereqs))}
    if not heads:
        entry["why_none"] = "nothing beyond the remote's main and tags"
        return entry
    refs = {f"{ARCHIVE_NS}{run_id}/{kind[0]}{i}": sha for i, sha in enumerate(heads)}
    git(env, repo, "update-ref", "--stdin", stdin="".join(f"create {r} {s}\n" for r, s in refs.items()))
    final = os.path.join(run_dir, f"{kind}.bundle")
    tmp = final + ".tmp"
    try:
        spec = "".join(f"{r}\n" for r in refs) + "".join(f"^{p}\n" for p in sorted(set(prereqs)))
        git(env, repo, "bundle", "create", "-q", tmp, "--stdin", stdin=spec)
        git(env, repo, "bundle", "verify", "-q", tmp)
        got, actual = header(tmp)
        if got != refs or list_heads(env, repo, tmp) != refs:
            raise BundleError(f"{tmp}: its heads are not the ones written")
        if not prereqs and actual:
            raise BundleError(f"{tmp}: a bundle meant to stand alone requires {len(actual)} commits")
        if not prereqs:
            verify_alone(env, tmp, refs)
        entry["prerequisites"] = sorted(actual)
        if os.path.lexists(final):
            raise BundleError(f"{final} exists")
        os.rename(tmp, final)
        os.chmod(final, 0o600)
    finally:
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass
        try:
            git(env, repo, "update-ref", "--stdin", stdin="".join(f"delete {r} {s}\n" for r, s in refs.items()))
            entry["leftover_refs"] = []
        except GitError as e:
            entry["leftover_refs"] = sorted(refs)  # they keep the objects alive: reported, not retried
            entry["leftover_error"] = str(e)
    entry.update(file=os.path.basename(final), heads=refs, bytes=os.path.getsize(final), sha256=sha256(final))
    return entry


def write_manifest(run_dir: str, manifest: Dict[str, object]) -> None:
    write_report(os.path.join(run_dir, "manifest.json"), manifest)


def write_refs(run_dir: str, rows: List[Tuple[str, str, str, str]]) -> None:
    path = os.path.join(run_dir, "refs.tsv")
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write("# kind\tname\tsha\tbundle ref\n")
        for row in rows:
            f.write("\t".join(row) + "\n")
        f.flush()
        os.fsync(f.fileno())


def log_action(run_dir: str, line: str) -> None:
    fd = os.open(os.path.join(run_dir, "actions.log"), os.O_WRONLY | os.O_CREAT | os.O_APPEND | os.O_NOFOLLOW, 0o600)
    try:
        os.write(fd, (time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()) + "\t" + line + "\n").encode())
        os.fsync(fd)
    finally:
        os.close(fd)


def leftover_archive_refs(env: Dict[str, str], repo: str, run_id: str) -> List[str]:
    """refs/lifecycle-archive/* another run left (it died between create and delete)."""
    text = git(env, repo, "for-each-ref", "--format=%(refname)", ARCHIVE_NS)
    return [r for r in text.splitlines() if r and not r.startswith(f"{ARCHIVE_NS}{run_id}/")]


def _age_days(created: object, now: float) -> Optional[float]:
    if not isinstance(created, str):
        return None
    try:
        t = calendar.timegm(time.strptime(created, "%Y-%m-%dT%H:%M:%SZ"))
    except ValueError:
        return None
    return None if t > now else (now - t) / 86400


def expire(env: Dict[str, str], repo: str, base: str, durable: List[str], now: float, days: float) -> List[Dict[str, object]]:
    """Remove redundant bundles older than days under base (<root>/<machine>/<repo>) whose
    every head the remote's refs still reach. Everything else stays, with the reason."""
    out: List[Dict[str, object]] = []
    if days < MIN_DAYS:
        raise BundleError(f"bundles are kept at least {MIN_DAYS} days")
    try:
        runs = sorted(os.listdir(base))
    except FileNotFoundError:
        return out
    except OSError as e:
        return [{"dir": base, "action": "keep", "reason": f"cannot list: {e.strerror or e}"}]
    for run in runs:
        d = os.path.join(base, run)
        mpath = os.path.join(d, "manifest.json")
        try:
            if stat.S_ISLNK(os.lstat(d).st_mode):
                continue
            with open(mpath, encoding="utf-8") as f:
                man = json.load(f)
            bundles = man["bundles"]
            if not isinstance(bundles, list):
                raise ValueError
        except FileNotFoundError:
            continue
        except (OSError, ValueError, KeyError, TypeError) as e:
            out.append({"dir": d, "action": "keep", "reason": f"manifest cannot be read ({type(e).__name__})"})
            continue
        changed = False
        for b in bundles:
            if not isinstance(b, dict) or not b.get("file"):
                continue
            res = {"dir": d, "file": b.get("file"), "kind": b.get("kind"), "action": "keep"}
            out.append(res)
            if b.get("expired_at"):
                res["reason"] = "expired earlier"
                continue
            if b.get("kind") != "redundant":
                res["reason"] = "holds commits no remote ref reached: kept, never expired"
                continue
            age = _age_days(man.get("created_at"), now)
            if age is None or age < days:
                res["reason"] = f"younger than {days:g} days" if age is not None else "created_at cannot be read"
                continue
            path = os.path.join(d, str(b["file"]))
            try:
                if os.path.basename(path) != b["file"] or stat.S_ISLNK(os.lstat(path).st_mode):
                    raise BundleError("not a plain file name")
                if sha256(path) != b.get("sha256"):
                    raise BundleError("its sha256 is not the one recorded")
                heads = list(list_heads(env, repo, path).values())
                if not heads or without_copy(env, repo, heads, durable):
                    raise BundleError("a head is no longer on a ref the remote holds")
                os.unlink(path)
            except (OSError, GitError, BundleError) as e:
                res["reason"] = str(e)
                continue
            b["expired_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now))
            res.update(action="removed", reason=f"redundant and {age:.0f} days old; every head is on the remote")
            changed = True
        if changed:
            write_manifest(d, man)
    return out
