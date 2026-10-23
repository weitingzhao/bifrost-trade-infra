"""issue_index_check.py: every rule of the business issue index, on rows written to a temp profile (W-31 3.2).

    python3 -m pytest -q scripts/agentrt/test_issue_index_check.py
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("issue_index_check", HERE / "issue_index_check.py")
iic = importlib.util.module_from_spec(spec)
spec.loader.exec_module(iic)

A1 = "sha256:" + "a" * 64
A2 = "sha256:" + "b" * 64
HEAD = "| " + " | ".join(iic.COLUMNS) + " |\n|" + "---|" * len(iic.COLUMNS) + "\n"


def row(**kw: str) -> str:
    base = {"编号": "BI-1", "收到": "2026-10-23", "来源与入口": "太太（Owner 转述，统筹线程）", "摘要": "页面头上看不到数据日期",
            "状态": "待评估", "业务对接 / 建设承接": "参谋长席位 / 统筹线程", "接单": "—", "交付": "—", "业务结论": "—",
            "当前正文": A1, "下一步（谁·什么·上限）": "统筹线程·评估·10-23 12:00"}
    base.update(kw)
    return "| " + " | ".join(base[c] for c in iic.COLUMNS) + " |\n"


def profile(tmp_path: Path, *rows: str, header: str = HEAD) -> Path:
    p = tmp_path / "PROFILE-x.md"
    p.write_text("# x\n\n## 八、改动记录\n\n| a |\n|---|\n| b |\n\n" + iic.SECTION + "\n\n说明一行。\n\n" + header + "".join(rows)
                 + "\n## 十、别的\n\n| BI-9 | not in the index |\n", encoding="utf-8")
    return p


def problems(p: Path) -> list[str]:
    return iic.check(p)


def test_the_repository_profiles_pass():
    files = sorted(iic.CREW.glob("PROFILE-*.md"))
    assert files, "no profile found"
    for f in files:
        assert iic.check(f) == [], f
    assert iic.main([]) == 0


def test_a_good_index_passes_and_rows_outside_the_section_are_not_read(tmp_path):
    p = profile(tmp_path, row(), row(编号="BI-2", 状态="推进中", 接单="M-140", 当前正文=A2),
                row(编号="BI-3", 状态="待试用", 接单="M-141", 交付="STG platform-frontend abc1234"),
                row(编号="BI-4", 状态="已结束", 业务结论=f"已解决：太太原话 {A2}，2026-10-24，统筹线程"),
                row(编号="BI-5", 状态="已结束", 业务结论="不采纳（太太撤回）"))
    assert problems(p) == []


def test_an_empty_index_and_a_profile_without_one_pass(tmp_path):
    assert problems(profile(tmp_path)) == []
    other = tmp_path / "PROFILE-y.md"
    other.write_text("# y\n\nno index here\n", encoding="utf-8")
    assert problems(other) == []


@pytest.mark.parametrize("kw, says", [
    ({"编号": "B-1"}, "is not BI-<n>"),
    ({"状态": "完成"}, "is not one of"),
    ({"状态": "推进中"}, "with no mission in 接单"),
    ({"状态": "待试用", "接单": "M-7"}, "with no delivery"),
    ({"状态": "已结束"}, "closed without a verdict"),
    ({"状态": "已结束", "业务结论": "已解决：她说好了"}, "without the artifact of the user's words"),
    ({"状态": "已结束", "业务结论": f"部分解决 {A2}"}, "without the artifact of the user's words"),
    ({"当前正文": "sha256:abc"}, "is not sha256:<64 hex>"),
    ({"摘要": "见 /Users/someone/notes"}, "holds a local path"),
    ({"下一步（谁·什么·上限）": "令牌 rsu_abcdefghijkl"}, "shaped like a token"),
])
def test_each_rule_names_the_row(tmp_path, kw, says):
    got = problems(profile(tmp_path, row(**kw)))
    assert len(got) == 1 and says in got[0] and "PROFILE-x.md:" in got[0], got


def test_a_number_twice_and_a_mission_on_two_rows(tmp_path):
    got = problems(profile(tmp_path, row(), row()))
    assert any("BI-1 is already the row" in g for g in got), got
    got = problems(profile(tmp_path, row(状态="推进中", 接单="M-9"), row(编号="BI-2", 状态="推进中", 接单="M-9")))
    assert any("names M-9, which BI-1 names too" in g for g in got), got


def test_a_changed_header_or_a_short_row_is_refused(tmp_path):
    got = problems(profile(tmp_path, row(), header="| 编号 | 状态 |\n|---|---|\n"))
    assert len(got) == 1 and "columns" in got[0]
    got = problems(profile(tmp_path, "| BI-1 | 2026-10-23 | 太太 |\n"))
    assert len(got) == 1 and "cells" in got[0]


def test_the_four_answers(tmp_path, capsys):
    p = profile(tmp_path, row(编号="BI-3", 状态="待试用", 接单="M-141", 交付="STG platform-frontend abc1234"))
    assert iic.main(["--file", str(p), "--id", "BI-3"]) == 0
    out = capsys.readouterr().out
    assert "为谁解决：太太（Owner 转述，统筹线程）" in out
    assert "谁接单：M-141" in out and "交付到哪：STG platform-frontend abc1234" in out
    assert "还欠什么反馈：欠使用者的业务结论" in out
    assert iic.main(["--file", str(p), "--id", "BI-4"]) == 1


def test_exit_status_follows_the_problems(tmp_path, capsys):
    bad = profile(tmp_path, row(状态="完成"))
    assert iic.main(["--file", str(bad)]) == 1
    assert "is not one of" in capsys.readouterr().out
