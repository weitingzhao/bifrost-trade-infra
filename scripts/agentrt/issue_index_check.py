#!/usr/bin/env python3
"""The business issue index of a product profile is well formed (W-31 3.2-1 design, D1 B, Owner 2026-10-22).

    python3 scripts/agentrt/issue_index_check.py                      check every agent-config/work/crew/PROFILE-*.md
    python3 scripts/agentrt/issue_index_check.py --file <profile.md>  check one profile
    python3 scripts/agentrt/issue_index_check.py --id BI-1            the four answers for one issue

A product's business issues (DESIGN-screening-loop-2026-10-22.md) keep their body in the agent runtime (an artifact of
kind other, one per revision) and one row each in the profile's section 「九、问题索引」, a markdown table with the columns
below. This repository is public: the row holds a summary and ids, never the user's words.

What a row must hold (exit 1 names each row and rule it breaks):
  - its number BI-<n>, once in the file;
  - a state of five: 待评估, 推进中, 待试用, 已结束, 暂缓;
  - 推进中 and 待试用 name the mission that took it (M-<n>) in 接单; a mission is named by one row only;
  - 待试用 says where it was delivered (交付 not empty);
  - 已结束 has a 业务结论 that starts with 已解决, 部分解决, 现有能力满足 or 不采纳; 已解决 and 部分解决 also name the
    artifact that holds the user's words (sha256:<64 hex>) and the day (YYYY-MM-DD): mission done is the engineering
    verdict only, the business one is the user's (design §五);
  - 当前正文 is the artifact id of the current body, sha256:<64 hex>;
  - no local path and nothing shaped like a token.
What it cannot see: the body itself (in the runtime), whether the words are really the user's, two sessions writing at
once. Those stay conventions of the design.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CREW = ROOT / "agent-config" / "work" / "crew"
SECTION = "## 九、问题索引"
COLUMNS = ["编号", "收到", "来源与入口", "摘要", "状态", "业务对接 / 建设承接", "接单", "交付", "业务结论", "当前正文",
           "下一步（谁·什么·上限）"]
STATES = {"待评估", "推进中", "待试用", "已结束", "暂缓"}
VERDICTS = ("已解决", "部分解决", "现有能力满足", "不采纳")
EMPTY = {"", "—", "-"}
ARTIFACT = re.compile(r"sha256:[0-9a-f]{64}")
DAY = re.compile(r"20\d\d-\d\d-\d\d")
MISSION = re.compile(r"\bM-\d+\b")
LOCAL_PATH = re.compile(r"(/Users/|/private/|/home/|~/)")
TOKEN = re.compile(r"(\brsu_[A-Za-z0-9_-]{8,}|\bBearer\s+\S{8,}|\bgh[pousr]_[A-Za-z0-9]{8,}|\bgithub_pat_\w{8,}|\bsk-[A-Za-z0-9]{8,})")


def cells(line: str) -> list[str]:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def table(text: str) -> tuple[list[str] | None, list[tuple[int, list[str]]]]:
    """The header and the rows of the index table, each row with its line number; (None, []) without the section."""
    lines = text.splitlines()
    start = next((i for i, line in enumerate(lines) if line.strip() == SECTION), None)
    if start is None:
        return None, []
    header, rows = None, []
    for i in range(start + 1, len(lines)):
        line = lines[i]
        if line.startswith("## "):
            break
        if not line.lstrip().startswith("|"):
            if header is not None and rows:
                break
            continue
        row = cells(line)
        if header is None:
            header = row
        elif set("".join(row)) <= set("-: "):
            continue
        else:
            rows.append((i + 1, row))
    return header, rows


def check(path: Path) -> list[str]:
    """Every rule a row of path breaks, as 'file:line rule'."""
    text = path.read_text(encoding="utf-8")
    header, rows = table(text)
    if header is None:
        return []
    name = path.name
    if header != COLUMNS:
        return [f"{name}: the index's columns are {header}, not {COLUMNS}"]
    out: list[str] = []
    seen: dict[str, int] = {}
    missions: dict[str, str] = {}
    for line, row in rows:
        at = f"{name}:{line}"
        if len(row) != len(COLUMNS):
            out.append(f"{at} has {len(row)} cells, not {len(COLUMNS)}")
            continue
        r = dict(zip(COLUMNS, row))
        bi = r["编号"]
        if not re.fullmatch(r"BI-\d+", bi):
            out.append(f"{at} number {bi!r} is not BI-<n>")
        elif bi in seen:
            out.append(f"{at} {bi} is already the row at line {seen[bi]}")
        else:
            seen[bi] = line
        state = r["状态"]
        if state not in STATES:
            out.append(f"{at} {bi} state {state!r} is not one of {sorted(STATES)}")
        took = MISSION.findall(r["接单"])
        if state in {"推进中", "待试用"} and not took:
            out.append(f"{at} {bi} is {state} with no mission in 接单")
        for m in took:
            if m in missions and missions[m] != bi:
                out.append(f"{at} {bi} names {m}, which {missions[m]} names too")
            missions.setdefault(m, bi)
        if state == "待试用" and r["交付"] in EMPTY:
            out.append(f"{at} {bi} waits for a trial with no delivery (交付)")
        verdict = r["业务结论"]
        if state == "已结束":
            if not verdict.startswith(VERDICTS):
                out.append(f"{at} {bi} is closed without a verdict of {list(VERDICTS)}")
            elif verdict.startswith(("已解决", "部分解决")) and not (ARTIFACT.search(verdict) and DAY.search(verdict)):
                out.append(f"{at} {bi} says {verdict.split()[0]} without the artifact of the user's words and its day")
        if not ARTIFACT.fullmatch(r["当前正文"]):
            out.append(f"{at} {bi} current body {r['当前正文']!r} is not sha256:<64 hex>")
        whole = " | ".join(row)
        if LOCAL_PATH.search(whole):
            out.append(f"{at} {bi} holds a local path")
        if TOKEN.search(whole):
            out.append(f"{at} {bi} holds something shaped like a token")
    return out


def answers(path: Path, bi: str) -> str | None:
    """The four questions a new session answers for one issue (design §四), from its row; None when no row has it."""
    header, rows = table(path.read_text(encoding="utf-8"))
    for _, row in rows:
        if header == COLUMNS and len(row) == len(COLUMNS) and row[0] == bi:
            r = dict(zip(COLUMNS, row))
            owed = r["业务结论"] in EMPTY
            return "\n".join([
                f"{bi} · {r['状态']} · {path.name}",
                f"为谁解决：{r['来源与入口']}；{r['摘要']}",
                f"谁接单：{r['接单'] if r['接单'] not in EMPTY else '还没有接单'}（{r['业务对接 / 建设承接']}）",
                f"交付到哪：{r['交付'] if r['交付'] not in EMPTY else '还没有交付'}",
                f"还欠什么反馈：{'欠使用者的业务结论；' if owed else ''}{r['下一步（谁·什么·上限）']}",
                f"当前正文：{r['当前正文']}（get_artifact 读全文）",
            ])
    return None


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--file", type=Path, action="append", help="a profile to check (default: every PROFILE-*.md under work/crew)")
    ap.add_argument("--id", help="print the four answers for one issue, BI-<n>")
    args = ap.parse_args(argv)
    files = args.file or sorted(CREW.glob("PROFILE-*.md"))
    if args.id:
        for f in files:
            got = answers(f, args.id)
            if got is not None:
                print(got)
                return 0
        print(f"no row for {args.id} in {[f.name for f in files]}", file=sys.stderr)
        return 1
    problems = [p for f in files for p in check(f)]
    for p in problems:
        print(p)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
