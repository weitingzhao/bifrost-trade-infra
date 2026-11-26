"""The residual scan's citation pattern.

Origin: 2026-11-24, round 1 of the laws' residual scan counted fifteen
citations of laws that do not exist; twelve were 「合法 0」 (a lawful zero) and
two 「合法 126 字节」, and 「读法 0」 in three more, words ending in 法 read as 「法 N」.
"""
import importlib.util
import pathlib
import re

spec = importlib.util.spec_from_file_location("residual_scan", pathlib.Path(__file__).with_name("residual_scan.py"))
scan = importlib.util.module_from_spec(spec)
spec.loader.exec_module(scan)


def cites(text):
    return re.findall(scan.CITE, text)


def test_citations_are_found():
    # The positive control: every form the scan is for.
    assert cites("（法 46）") == ["46"]
    assert cites("按法50办") == ["50"]
    assert cites("law 85, #729") == ["85"]
    assert cites("Law 28 says") == ["28"]
    assert cites("OWNER_LAW #12") == ["12"]


def test_words_ending_in_fa_are_not_citations():
    assert cites("合法 0 保留") == []
    assert cites("合法 126 字节正文") == []
    assert cites("算法 2 和方法 3") == []
    assert cites("立法 1 轮") == []
    assert cites("两份读法 0 分歧") == []


def test_exceptions_are_read_from_the_file(tmp_path):
    f = tmp_path / "exceptions.txt"
    f.write_text("# comment\nbifrost-platform:a/b.go:46  # why\n\n")
    assert scan.exceptions(f) == {"bifrost-platform:a/b.go:46"}
    assert scan.exceptions(tmp_path / "missing.txt") == set()


def test_exceptions_may_name_a_class(tmp_path):
    # 2026-11-25, round 1's last scan: 51 citations of repealed laws were all
    # in applied migrations, tests with their own registers and the parser's
    # examples; one line per class, with its reason, instead of 51.
    allowed = {"bifrost-platform:api/x/migrations/*.sql:*", "bifrost-platform:a.go:85"}
    hit = lambda repo, path, law: scan.excepted({"repo": repo, "path": path, "law": law}, allowed)
    assert hit("bifrost-platform", "api/x/migrations/0029_a.sql", "28")
    assert hit("bifrost-platform", "a.go", "85")
    # The positive control's other side: another law, path or repo is not excepted.
    assert not hit("bifrost-platform", "a.go", "86")
    assert not hit("bifrost-platform", "api/x/other.go", "28")
    assert not hit("bifrost-trade-infra", "api/x/migrations/0029_a.sql", "28")


def test_law_codes():
    # Origin: 2026-11-25, the laws are written LAW-k (k from number 86).
    assert scan.code("86") == "LAW-1" and scan.code("89") == "CORE-1" and scan.code("98") == "LAW-13" and scan.code("85") == ""
    # From round 2 a law's code is in its record and says its level.
    laws = [{"law": "86"}, {"law": "99", "code": "DAO-1"}, {"law": "100", "code": "ZONE-1"}]
    assert scan.code_map(laws) == {"LAW-1": "86", "DAO-1": "99", "ZONE-1": "100"}
    assert re.findall(scan.CODE, "see LAW-10, DAO-1, CORE-1 and ZONE-2, not LAW-0 or law-1") == ["LAW-10", "DAO-1", "CORE-1", "ZONE-2"]


def test_a_dated_rule_anchored_to_a_law_is_not_a_shadow(monkeypatch):
    # Origin: 2026-11-25, round 2: an Owner-dated line that names its LAW-k
    # (a restatement, or a RULE naming the LAW it executes) has a home; one
    # without is a shadow (the positive control).
    class P:
        stdout = ("origin/main:agent-config/CLAUDE.md:10:- **交单要短（Owner 2026-11-12，LAW-7）**\n"
                  "origin/main:agent-config/CLAUDE.md:11:- **业务优先（Owner 2026-09-26）**\n")
    monkeypatch.setattr(scan.subprocess, "run", lambda *a, **k: P())
    got = scan.shadow()
    assert [x["line"] for x in got] == [11]


def test_owner_asks_pattern():
    """Origin: 2026-11-25, audit's round-2 pain check found CLAUDE.md §5's undated
    「架构级决策等 Owner 确认」 by eye; the owner-ask list must catch that kind of line."""
    for hit in ("→ 列 2–3 个选项 + 推荐，等 Owner 确认", "改名属架构级变更、先问 Owner", "交 Owner 定", "由 Owner 批"):
        assert scan.OWNER_ASK.search(hit), hit
    for miss in ("Owner 是法官，盘道、立法", "Owner 的特权必须有"):
        assert not scan.OWNER_ASK.search(miss), miss


# Round 3 (2026-11-25, ISSUE-104): the Owner's words leave the code; the scan
# counts the lines that still carry them and the issue references that point
# at nothing.
def test_owner_words_pattern():
    hit = ["// Owner 2026-11-25: keep them apart", "# (Owner 11-25) phone first", 'the Owner said: "do it"', "the Owner：「删」"]
    miss = ["owner_said is a type", "the Owner decides (LAW-9 三)", "Owner-facing page", "ISSUE-104",
            # 2026-11-26: code naming the Owner, not quoting him
            'answerer{who: "the Owner", actor: "owner"}', 'reversibleWhy = "is not a new file (ask the Owner): "',
            "claims the Owner's approval: \"${phrase}\""]
    for line in hit:
        assert scan.OWNER_WORDS.search(line), line
    for line in miss:
        assert not scan.OWNER_WORDS.search(line), line


# 2026-11-26, owner-words sweep of infra: git grep -E on macOS does not know \b,
# so the scan counted 367 lines where git grep -P counted 585. The scan greps
# with the same engine as the pattern (PCRE); this runs the real git grep.
def test_owner_words_git_grep_matches_like_python(tmp_path):
    import subprocess
    lines = ["// Owner 11-25 said so", "# (Owner 2026-11-25) phone first", "owner_said is a type"]
    (tmp_path / "a.go").write_text("\n".join(lines) + "\n")
    git = lambda *a: subprocess.run(["git", "-C", str(tmp_path), *a], capture_output=True, text=True, check=False)
    git("init", "-q"); git("add", "a.go")
    got = git("grep", "--cached", "-nP", scan.OWNER_WORDS.pattern).stdout.splitlines()
    want = [l for l in lines if scan.OWNER_WORDS.search(l)]
    # positive control: Python finds two; git grep must find the same two, the \b one included
    assert len(want) == 2 and len(got) == 2, got


def test_issue_refs_are_classified(monkeypatch):
    out = "origin/main:a.go:3:// see ISSUE-3 and ISSUE-999\norigin/main:b.md:1:closed ISSUE-12\n"
    monkeypatch.setattr(scan, "repos", lambda: [scan.pathlib.Path("/x/bifrost-platform")])
    monkeypatch.setattr(scan.subprocess, "run", lambda *a, **k: type("P", (), {"stdout": out})())
    got = {(r["issue"], r["stale"]) for r in scan.issue_refs({"ISSUE-3": "open", "ISSUE-12": "dropped"})}
    # positive control: an open issue is fine; a dropped one and one that does not exist are stale
    assert got == {("ISSUE-3", False), ("ISSUE-999", True), ("ISSUE-12", True)}


def test_kind_of():
    # 2026-11-26: applied migrations and DDL steps that ran are history, apart from the target
    assert scan.kind_of("api/internal/agentrt/migrations/0001_core.sql") == "history"
    assert scan.kind_of("scripts/release/db-steps.d/sql/x.sql") == "history"
    assert scan.kind_of("scripts/release/db-steps.d/2026-10-04-a.md") == "history"
    assert scan.kind_of("api/internal/agentrt/migrate/migrate.go") == "code"  # positive control
    assert [scan.kind_of(p) for p in ("api/x_test.go", "src/__tests__/a.ts", "scripts/laws/test_x.py", "docs/A.md", "k8s/a.yaml", "api/x.go")] == \
        ["test", "test", "test", "doc", "config", "code"]


# Patrol (ISSUE-104, 2026-11-25): who still writes the Owner's words into code. The commit's Claude-Session
# trailer names the session; a commit without one is "" (made outside an agent session).
def test_who_added_reads_the_session_trailer(monkeypatch):
    def run(args, **k):
        if "blame" in args:
            return type("P", (), {"stdout": "abcdef1234567890 3 3 1\nauthor x\n"})()
        return type("P", (), {"stdout": "2026-11-25T10:00:00-06:00\nlocal_6ab1ad67-09a8-4522-9b4a-a03125b10b2c\n\n"})()
    monkeypatch.setattr(scan.subprocess, "run", run)
    got = scan.who_added("bifrost-platform", "a.go", 3, cache={})
    assert got == {"commit": "abcdef123456", "date": "2026-11-25", "session": "local_6ab1ad67-09a8-4522-9b4a-a03125b10b2c"}
    # positive control: a line git cannot blame names no commit
    monkeypatch.setattr(scan.subprocess, "run", lambda *a, **k: type("P", (), {"stdout": ""})())
    assert scan.who_added("bifrost-platform", "gone.go", 1, cache={})["commit"] == ""
