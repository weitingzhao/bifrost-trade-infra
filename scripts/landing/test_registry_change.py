"""What a commit may do to the registry of document consumers by itself (doc_consumers.registry_change).

Origin: 2026-11-14. Twice that day the Owner merged a registry commit by hand in Gitea
(a897dd87: one row's fingerprint; a87b82bb: one new row), because a commit that changed the
registry was red by construction: the check read the base's registry. He could see nothing
in either that the system could not. Step 1 lets the first kind land by itself and keeps
everything that is a judgement for a person. Each refused case below is a way the
protection could be loosened by a commit that also edits the registry.
"""
import copy
import runpy
from pathlib import Path

import pytest

D = runpy.run_path(str(Path(__file__).with_name("doc_consumers.py")))
P = D["P"]
OWN, OTHER = P["REPO"], "bifrost-platform"


def row(name, hits="sha256:" + "a" * 64, repo=None, **more):
    r = {"file": name, "class": "token", "effect": "test", "hits": hits, "why": "a fixture string", "checked_by": "someone"}
    if repo:
        r["repo"] = repo
    r.update(more)
    return r


BASE = [row("scripts/a.py"), row("scripts/reader.py", **{"class": "reader", "reads": ["docs/x.md"]}),
        row("src/page.tsx", repo=OTHER), row("scripts/gone.py")]
# What the candidate's trees still have a hit in.
FOUND, FOUND_OTHER = {"scripts/a.py": [(1, "x")], "scripts/reader.py": [(1, "x")]}, {"src/page.tsx": [(1, "x")]}


def change(edit):
    rows = copy.deepcopy(BASE)
    edit(rows)
    return rows


def find(rows, name):
    return next(r for r in rows if r["file"] == name)


def test_a_registry_that_did_not_change_passes():
    D["registry_change"](BASE, copy.deepcopy(BASE), {**FOUND, "scripts/gone.py": [(1, "x")]}, FOUND_OTHER)


def test_a_row_whose_hits_alone_changed_passes():
    # The a897dd87 kind: the platform page's line changed, the row follows it.
    rows = change(lambda rows: find(rows, "src/page.tsx").update(hits="sha256:" + "b" * 64))
    D["registry_change"](BASE, rows, {**FOUND, "scripts/gone.py": [(1, "x")]}, FOUND_OTHER)


def test_a_row_removed_whose_file_has_no_hit_left_passes():
    rows = change(lambda rows: rows.remove(find(rows, "scripts/gone.py")))
    D["registry_change"](BASE, rows, FOUND, FOUND_OTHER)


@pytest.mark.parametrize("name, edit, says", [
    # The class is what the protection reads: a reader called a mention is no longer protected.
    ("class with the hits", lambda rows: find(rows, "scripts/reader.py").update({"class": "mention", "hits": "sha256:" + "c" * 64}), "registry_row_changed scripts/reader.py"),
    ("class alone", lambda rows: find(rows, "scripts/reader.py").update({"class": "token"}), "registry_row_changed scripts/reader.py"),
    # A narrower read set lets a document it read be changed.
    ("reads", lambda rows: find(rows, "scripts/reader.py").update(reads=["docs/other.md"]), "registry_row_changed scripts/reader.py"),
    ("why", lambda rows: find(rows, "scripts/a.py").update(why="another reason"), "registry_row_changed scripts/a.py"),
    ("who checked it", lambda rows: find(rows, "scripts/a.py").update(checked_by="nobody"), "registry_row_changed scripts/a.py"),
    # A row taken out while its file still has hits is a file taken out of the protection.
    ("a row removed, its file still hit", lambda rows: rows.remove(find(rows, "scripts/a.py")), "registry_row_removed scripts/a.py"),
    ("the other repository's row removed, its file still hit", lambda rows: rows.remove(find(rows, "src/page.tsx")), "registry_row_removed src/page.tsx"),
    # A new row is a classification: step 1 leaves it to a person (a87b82bb was this kind).
    ("a row added", lambda rows: rows.append(row("scripts/new.py")), "registry_row_added scripts/new.py"),
    # The same file name in the other repository is another row.
    ("a row moved to the other repository", lambda rows: find(rows, "scripts/a.py").update(repo=OTHER), "registry_row_added scripts/a.py"),
], ids=lambda v: v if isinstance(v, str) and " " in v or isinstance(v, str) and v.isalpha() else None)
def test_what_is_a_judgement_is_refused(name, edit, says):
    with pytest.raises(P["PolicyError"]) as err:
        D["registry_change"](BASE, change(edit), FOUND, FOUND_OTHER)
    assert str(err.value) == says, name


def test_main_reads_the_candidates_registry_and_both_registries_for_readers():
    # The wiring, read off the source: the candidate's rows are verified, the change of the
    # registry is judged first, and a changed path is held to the readers of both.
    src = Path(__file__).with_name("doc_consumers.py").read_text()
    main = src[src.index("def judge():"):]  # the check as it was; main answers retired since 2026-11-16
    order = [main.index(s) for s in ('P["registry"](args.repo, args.base)', 'P["registry"](args.repo, args.revision)', "registry_change(base_rows, rows, found, found_platform)",
                                     'verify(rows, found, P["REPO"])', 'P["consumers"](args.repo, args.base, args.revision, args.purpose)', 'P["consumed"](rows, ')]
    assert order == sorted(order)
