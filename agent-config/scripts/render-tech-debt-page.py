#!/usr/bin/env python3
"""Render agent-config/TECH_DEBT.md and RATCHETS.md into the debt ledger page.

The two Markdown files are the only source. This script parses them and lays the
page out the way the round-1 ledger was laid out (Owner 2026-10-06: one layout for
every round), so a reader learns it once:

    待你签收 · 自上次以来 · stats · 先看这几条 · 主题 · 还债顺序 · 数据边界 · 需要你拍板 · 台账 (filters) · 防线 · 没覆盖到的 · 怎么做的

Ids listed in a wave's 已还 part, or in a theme but no longer in 条目, render struck
through: the plan keeps its progress although closed items are deleted from the file.

    python3 agent-config/scripts/render-tech-debt-page.py > /tmp/tech-debt.html

then publish the output to the "Trade 技术债台账" artifact.
"""
from __future__ import annotations

import json
import pathlib
import re
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent.parent
DEBT = HERE / "TECH_DEBT.md"
RATCHETS = HERE / "RATCHETS.md"
TD = re.compile(r"TD-\d+")


def sections(text: str, level: str) -> dict[str, str]:
    """Split on headings of one level ('## ' or '### '); keys keep the heading text."""
    out: dict[str, str] = {}
    parts = re.split(r"^" + re.escape(level) + r"(.+)$", text, flags=re.M)
    for i in range(1, len(parts), 2):
        out[parts[i].strip()] = parts[i + 1]
    return out


def section(secs: dict[str, str], prefix: str) -> str:
    return next((v for k, v in secs.items() if k.startswith(prefix)), "")


def bullets(body: str) -> list[str]:
    return [m.group(1).strip() for m in re.finditer(r"^- (.+)$", body, re.M)]


def parse_items(body: str) -> list[dict]:
    items = []
    for tid, block in sections(body, "### ").items():
        if not TD.fullmatch(tid):
            continue
        it: dict = {"id": tid, "evidence": [], "notes": []}
        head = re.search(r"^\*\*(P\d) · ([^·]+?) · (.+)\*\*$", block, re.M)
        if head:
            it["priority"], it["domain"], it["title"] = head.group(1), head.group(2).strip(), head.group(3).strip()
        lines = block.split("\n")
        key = None
        for ln in lines:
            m = re.match(r"^- \*\*(.+?)\*\*[:：]\s?(.*)$", ln)
            if m:
                key = m.group(1)
                val = m.group(2).strip()
                k = {"现在": "now", "下一步": "next", "Claim": "claim", "Measured": "measured", "Impact": "impact",
                     "Fix": "fix", "Ratchet": "ratchet", "状态": "state", "验收": "accept",
                     "验收结果": "accept_result"}.get(key)
                if key == "Evidence":
                    continue
                if k:
                    it[k] = val
                else:
                    it["notes"].append(f"{key}: {val}")
                continue
            m = re.match(r"^\s+- `([^`]*)`\s+—\s+`(.*)`\s*$", ln)
            if m and key == "Evidence":
                loc = m.group(1)
                fm = re.match(r"^(.*?):(\d+)$", loc)
                it["evidence"].append({"file": fm.group(1) if fm else loc, "line": int(fm.group(2)) if fm else None,
                                       "quote": m.group(2)})
                continue
            m = re.match(r"^- 审批 (.+?) · 代价 (\S+) · 风险 (\S+) · repos: (.*)$", ln)
            if m:
                it["gate"], it["cost"], it["risk"] = m.group(1), m.group(2), m.group(3)
                it["repos"] = [r.strip() for r in m.group(4).split(",") if r.strip()]
        it.setdefault("priority", "P3")
        it.setdefault("domain", "")
        it.setdefault("title", tid)
        it.setdefault("gate", "不用批")
        it["state_explicit"] = "state" in it
        it.setdefault("state", "未开始")
        it["state_key"] = re.split(r"[（(]", it["state"], 1)[0].strip()
        items.append(it)
    return items


def since_last(base: str, debt_now: str, ratchets_now: str) -> dict | None:
    """What changed in the two files since the commit the Owner last looked at (git is the baseline)."""
    root = HERE.parent

    def git(*args: str) -> str:
        r = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True)
        return r.stdout if r.returncode == 0 else ""

    old_debt = git("show", f"{base}:agent-config/TECH_DEBT.md")
    old_rat = git("show", f"{base}:agent-config/RATCHETS.md")
    if not old_debt:
        return None
    old = {x["id"]: x for x in parse_items(section(sections(old_debt, "## "), "条目"))}
    new = {x["id"]: x for x in parse_items(section(sections(debt_now, "## "), "条目"))}

    def rat_names(text: str) -> list[str]:
        body = section(sections(text, "## "), "现有防线")
        return [ln.strip().strip("|").split(" | ")[0].strip() for ln in body.split("\n")
                if ln.startswith("| ") and not ln.startswith("| 防线") and not ln.startswith("|---")]

    ro, rn = rat_names(old_rat), rat_names(ratchets_now)
    changes = []
    for tid in sorted(set(old) & set(new), key=lambda t: int(t[3:])):
        a, b = old[tid].get("state", "未开始"), new[tid].get("state", "未开始")
        if a != b and old[tid]["state_explicit"]:
            changes.append({"id": tid, "from": a, "to": b})
    log = git("log", "--format=%h %cs %s", f"{base}..HEAD", "--", "agent-config/TECH_DEBT.md", "agent-config/RATCHETS.md")
    return {
        "base": base,
        "added": [{"id": t, "title": new[t]["title"]} for t in sorted(set(new) - set(old), key=lambda t: int(t[3:]))],
        "closed": [{"id": t, "title": old[t]["title"]} for t in sorted(set(old) - set(new), key=lambda t: int(t[3:]))],
        "states": changes,
        "ratchets_added": [r for r in rn if r not in ro],
        "ratchets_removed": [r for r in ro if r not in rn],
        "commits": [ln for ln in log.split("\n") if ln.strip()],
    }


def parse(debt: str, ratchets: str) -> dict:
    top = sections(debt, "## ")
    data: dict = {}
    data["meta"] = (re.search(r"^更新：(.+)$", debt, re.M) or [None, ""])[1]
    data["summary"] = (re.search(r"^\*\*(未结[^\n]*)", debt, re.M) or [None, ""])[1].replace("**", "")

    data["themes"] = []
    for b in bullets(section(top, "主题")):
        m = re.match(r"^\*\*(.+?)\*\* — (.*?)\s*\(([^()]*)\)\s*$", b)
        if m:
            data["themes"].append({"t": m.group(1), "s": m.group(2), "ids": TD.findall(m.group(3))})

    data["signoff"] = []
    for b in bullets(section(top, "待你签收")):
        m = re.match(r"^\*\*(TD-\d+)\*\* — (.*)$", b)
        if m:
            data["signoff"].append({"id": m.group(1), "text": m.group(2)})
    seen = re.search(r"^上次查看：([0-9a-f]{7,40})(?:（([^）]*)）)?", debt, re.M)
    data["seen"] = {"sha": seen.group(1), "when": seen.group(2) or ""} if seen else None

    data["urgent"] = []
    for b in bullets(section(top, "先看这几条")):
        m = re.match(r"^\*\*(TD-\d+)\*\* — (.*)$", b)
        if m:
            data["urgent"].append({"id": m.group(1), "text": m.group(2)})

    data["waves"] = []
    for name, body in sections(section(top, "还债顺序"), "### ").items():
        goal = (re.search(r"^目标：(.+)$", body, re.M) or [None, ""])[1]
        ids = (re.search(r"^项：(.+)$", body, re.M) or [None, ""])[1]
        open_part, _, done_part = ids.partition("已还：")
        data["waves"].append({"n": name, "g": goal, "ids": TD.findall(open_part), "done": TD.findall(done_part)})

    data["boundaries"] = bullets(section(top, "数据边界"))

    data["decisions"] = []
    for q, body in sections(section(top, "需要你拍板"), "### ").items():
        rec = (re.search(r"^- 推荐：(.+)$", body, re.M) or [None, ""])[1]
        opts = (re.search(r"^- 选项：(.+)$", body, re.M) or [None, ""])[1]
        ids = (re.search(r"^- 项：(.+)$", body, re.M) or [None, ""])[1]
        data["decisions"].append({"q": q, "r": rec, "o": [o.strip() for o in opts.split(" · ") if o.strip()],
                                  "ids": TD.findall(ids)})

    data["items"] = parse_items(section(top, "条目"))
    data["gaps"] = bullets(section(top, "没覆盖到的"))
    data["method"] = section(top, "怎么做的").strip()
    t = re.search(r"(\d+) 条发现：(\d+) 条原样成立，(\d+) 条改了说法或优先级，(\d+) 条被推翻", data["method"])
    data["tally"] = [int(x) for x in t.groups()] if t else None

    rsec = sections(ratchets, "## ")
    rows = [ln for ln in section(rsec, "现有防线").split("\n") if ln.startswith("| ") and not ln.startswith("| 防线") and not ln.startswith("|---")]
    data["ratchets"] = [[c.strip() for c in r.strip().strip("|").split(" | ")] for r in rows]
    data["ratchet_plan"] = [k for k in sections(section(rsec, "待建防线"), "### ")]
    cov = [ln for ln in section(rsec, "各类债").split("\n") if ln.startswith("| ") and not ln.startswith("| 债的类别") and not ln.startswith("|---")]
    data["coverage"] = [[c.strip() for c in r.strip().strip("|").split(" | ")] for r in cov]
    return data


PAGE = r"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Trade 技术债台账</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500&family=Noto+Sans+SC:wght@400;500;700&display=swap">
<style>
:root{
  --bg:#f4f6f8; --panel:#ffffff; --sunk:#eceff3; --ink:#18202a; --ink2:#4a5562; --mute:#7a8592; --rule:#d9dfe6;
  --accent:#1f5f8b; --accent-soft:#e3eef6;
  --p0:#b42318; --p0-soft:#fdecea; --p1:#b54708; --p1-soft:#fef3e2; --p2:#355c7d; --p2-soft:#e8eff6; --p3:#6b7480; --p3-soft:#eef0f3;
  --ok:#1a7f4b; --ok-soft:#e5f4ec;
  --sans:"IBM Plex Sans","Noto Sans SC",system-ui,-apple-system,"PingFang SC",sans-serif;
  --mono:"IBM Plex Mono",ui-monospace,"SF Mono",Menlo,monospace;
}
@media (prefers-color-scheme: dark){:root:not([data-theme="light"]){
  --bg:#11161c; --panel:#171e26; --sunk:#1d252f; --ink:#e4e9ef; --ink2:#b3bdc8; --mute:#7f8a96; --rule:#2a3440;
  --accent:#7db4dc; --accent-soft:#1b2c3b;
  --p0:#f27a6d; --p0-soft:#3a1c1a; --p1:#f0a94f; --p1-soft:#36260f; --p2:#8db3d6; --p2-soft:#1c2a38; --p3:#9aa4af; --p3-soft:#232b34;
  --ok:#5fcf93; --ok-soft:#14301f; color-scheme:dark}}
:root[data-theme="dark"]{
  --bg:#11161c; --panel:#171e26; --sunk:#1d252f; --ink:#e4e9ef; --ink2:#b3bdc8; --mute:#7f8a96; --rule:#2a3440;
  --accent:#7db4dc; --accent-soft:#1b2c3b;
  --p0:#f27a6d; --p0-soft:#3a1c1a; --p1:#f0a94f; --p1-soft:#36260f; --p2:#8db3d6; --p2-soft:#1c2a38; --p3:#9aa4af; --p3-soft:#232b34;
  --ok:#5fcf93; --ok-soft:#14301f; color-scheme:dark}
*{box-sizing:border-box}
body{background:var(--bg);color:var(--ink);font-family:var(--sans);font-size:14px;line-height:1.6;margin:0}
.wrap{max-width:1180px;margin:0 auto;padding:28px 16px 64px}
h1{font-size:28px;line-height:1.25;margin:0 0 6px;font-weight:700;letter-spacing:-.01em;text-wrap:balance}
h2{font-size:18px;margin:44px 0 6px;font-weight:600;text-wrap:balance}
h2 + .sub{color:var(--ink2);margin:0 0 16px;max-width:72ch}
.meta{color:var(--mute);font-size:12.5px;font-family:var(--mono)}
.lede{font-size:15.5px;max-width:78ch;color:var(--ink);margin:18px 0 22px}
code,.mono{font-family:var(--mono);font-size:.92em}
code{background:var(--sunk);padding:1px 5px;border-radius:4px;word-break:break-word}
.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:1px;background:var(--rule);border:1px solid var(--rule);border-radius:10px;overflow:hidden}
.stat{background:var(--panel);padding:12px 14px;min-width:0}
.stat b{display:block;font-size:22px;font-weight:600;font-variant-numeric:tabular-nums}
.stat span{color:var(--ink2);font-size:12.5px}
.pbar{display:flex;height:8px;border-radius:4px;overflow:hidden;margin-top:8px}
.pbar i{display:block}
.urgent{display:grid;grid-template-columns:repeat(auto-fit,minmax(330px,1fr));gap:12px}
.ucard{background:var(--panel);border:1px solid var(--rule);border-left:3px solid var(--p0);border-radius:8px;padding:12px 14px;min-width:0}
.ucard .hd{display:flex;gap:8px;align-items:center;margin-bottom:4px;flex-wrap:wrap}
.ucard p{margin:0}
.prog{font-size:11.5px;color:var(--p1);background:var(--p1-soft);border-radius:999px;padding:1px 8px}
.pill{display:inline-flex;align-items:center;font-size:11.5px;font-weight:600;border-radius:999px;padding:1px 8px;white-space:nowrap}
.P0{color:var(--p0);background:var(--p0-soft)} .P1{color:var(--p1);background:var(--p1-soft)}
.P2{color:var(--p2);background:var(--p2-soft)} .P3{color:var(--p3);background:var(--p3-soft)}
.tid{font-family:var(--mono);font-size:12px;color:var(--accent);font-weight:500;cursor:pointer;background:none;border:0;padding:0}
.tid:hover{text-decoration:underline}
.tid.done{text-decoration:line-through;opacity:.55;cursor:default}
.tid.inprog{text-decoration:underline dotted var(--p1);text-underline-offset:3px}
.tid:focus-visible,button:focus-visible,select:focus-visible,input:focus-visible,summary:focus-visible{outline:2px solid var(--accent);outline-offset:2px;border-radius:4px}
.themes{display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:12px}
.theme{background:var(--panel);border:1px solid var(--rule);border-radius:8px;padding:14px 16px;min-width:0}
.theme h3{margin:0 0 6px;font-size:15px}
.theme p{margin:0 0 10px;color:var(--ink2)}
.ids{display:flex;flex-wrap:wrap;gap:4px 8px}
.waves{display:flex;flex-direction:column;gap:10px}
.wave{display:grid;grid-template-columns:230px 1fr;gap:16px;background:var(--panel);border:1px solid var(--rule);border-radius:8px;padding:14px 16px}
.wave h3{margin:0;font-size:14.5px}
.wave .cnt{color:var(--mute);font-size:12px;margin-top:2px}
.wave .wbar{display:flex;height:6px;border-radius:3px;overflow:hidden;background:var(--sunk);margin-top:8px}
.wave .wbar i{display:block;background:var(--ok)}
.wave p{margin:0 0 8px;color:var(--ink2)}
.dec{background:var(--panel);border:1px solid var(--rule);border-radius:8px;margin-bottom:8px}
.dec summary{cursor:pointer;padding:11px 14px;display:flex;gap:10px;align-items:baseline;list-style:none;flex-wrap:wrap}
.dec summary::-webkit-details-marker{display:none}
.dec summary::before{content:"›";color:var(--mute);transition:transform .15s;display:inline-block}
.dec[open] summary::before{transform:rotate(90deg)}
.dec .q{font-weight:600}
.dec .body{padding:0 14px 12px 30px}
.dec .rec{background:var(--accent-soft);border-radius:6px;padding:8px 10px;margin:4px 0 8px}
.dec ol{margin:0;padding-left:18px;color:var(--ink2);font-size:13px}
.filters{display:flex;flex-wrap:wrap;gap:8px;align-items:center;background:var(--panel);border:1px solid var(--rule);border-radius:8px;padding:10px 12px;position:sticky;top:0;z-index:5}
.filters select,.filters input{font:inherit;font-size:13px;color:var(--ink);background:var(--sunk);border:1px solid var(--rule);border-radius:6px;padding:5px 8px;min-width:0}
.filters input{flex:1 1 200px}
.seg{display:inline-flex;background:var(--sunk);border-radius:999px;padding:2px}
.seg button{font:inherit;font-size:12.5px;border:0;background:none;color:var(--ink2);padding:3px 10px;border-radius:999px;cursor:pointer}
.seg button[aria-pressed="true"]{background:var(--panel);color:var(--ink);box-shadow:0 0 0 1px var(--rule)}
.count{color:var(--mute);font-size:12.5px;margin-left:auto;font-variant-numeric:tabular-nums}
.ledger{margin-top:10px;display:flex;flex-direction:column;gap:6px}
.item{background:var(--panel);border:1px solid var(--rule);border-radius:8px}
.item>summary{cursor:pointer;list-style:none;display:grid;grid-template-columns:62px 40px 1fr auto;gap:10px;align-items:baseline;padding:9px 12px}
.item>summary::-webkit-details-marker{display:none}
.item .t{font-weight:500;min-width:0}
.tags{display:flex;gap:6px;flex-wrap:wrap;justify-content:flex-end}
.tag{font-size:11.5px;color:var(--ink2);background:var(--sunk);border-radius:4px;padding:0 6px;white-space:nowrap}
.tag.gate{color:var(--p1);background:var(--p1-soft)}
.item .body{padding:2px 14px 14px 124px;display:grid;gap:10px}
.item .body h4{margin:0;font-size:11.5px;color:var(--mute);font-weight:600;letter-spacing:.06em;text-transform:uppercase}
.item .body p{margin:2px 0 0;max-width:90ch}
.state{background:var(--p1-soft);border-radius:6px;padding:8px 10px}
.ev{list-style:none;margin:4px 0 0;padding:0;display:grid;gap:6px}
.ev li{background:var(--sunk);border-radius:6px;padding:6px 9px;min-width:0}
.ev .loc{font-family:var(--mono);font-size:11.5px;color:var(--accent);word-break:break-all}
.ev pre{margin:3px 0 0;font-family:var(--mono);font-size:12px;white-space:pre-wrap;word-break:break-word;color:var(--ink2)}
.item.flash{box-shadow:0 0 0 2px var(--accent)}
.scard{background:var(--panel);border:1px solid var(--rule);border-left:3px solid var(--ok);border-radius:8px;padding:12px 14px;min-width:0}
.scard .reply{margin-top:8px;font-size:12.5px;color:var(--ink2)}
.empty{background:var(--panel);border:1px dashed var(--rule);border-radius:8px;padding:12px 14px;color:var(--mute)}
.since{background:var(--panel);border:1px solid var(--rule);border-radius:8px;padding:12px 16px;display:grid;gap:10px}
.since h4{margin:0;font-size:12px;color:var(--mute);font-weight:600}
.since ul{margin:4px 0 0;padding-left:18px}
.st{font-size:11.5px;border-radius:999px;padding:1px 8px;white-space:nowrap;background:var(--sunk);color:var(--ink2)}
.st.s1{color:var(--p1);background:var(--p1-soft)} .st.s2{color:var(--p2);background:var(--p2-soft)} .st.s3{color:var(--ok);background:var(--ok-soft)}
.tablewrap{overflow-x:auto;border:1px solid var(--rule);border-radius:8px;background:var(--panel)}
table{border-collapse:collapse;width:100%;font-size:12.5px;min-width:900px}
th,td{text-align:left;vertical-align:top;padding:7px 10px;border-bottom:1px solid var(--rule)}
th{font-size:11.5px;color:var(--mute);font-weight:600;background:var(--sunk)}
td.c{font-weight:600;min-width:180px}
.v{font-size:11px;font-weight:600;border-radius:999px;padding:1px 7px;white-space:nowrap}
.v.yes,.v.blocking{color:var(--ok);background:var(--ok-soft)} .v.partial,.v.warning,.v.alert{color:var(--p1);background:var(--p1-soft)} .v.no,.v.manual{color:var(--p0);background:var(--p0-soft)}
.gaps{columns:2 360px;column-gap:28px;color:var(--ink2);padding-left:18px;margin:0}
.gaps li{break-inside:avoid;margin-bottom:6px}
.method{background:var(--panel);border:1px solid var(--rule);border-radius:8px;padding:14px 16px;color:var(--ink2)}
.method p{margin:0 0 8px}
details.more>summary{cursor:pointer;color:var(--accent);margin:10px 0}
@media (max-width:720px){
  .wave{grid-template-columns:1fr;gap:6px}
  .item>summary{grid-template-columns:56px 34px 1fr}
  .item .tags{grid-column:1/-1;justify-content:flex-start}
  .item .body{padding:2px 12px 12px}
  h1{font-size:23px}
}
@media (prefers-reduced-motion:reduce){*{transition:none!important;scroll-behavior:auto!important}}
</style>
</head>
<body>
<div class="wrap">
  <h1>Trade 技术债台账</h1>
  <div class="meta" id="meta"></div>
  <p class="lede" id="lede"></p>
  <h2>待你签收</h2>
  <p class="sub">验收已重跑通过、防线已到位的项。回复「签收 TD-n」或「打回 TD-n：原因」。</p>
  <div class="urgent" id="signoff"></div>

  <h2>自上次以来</h2>
  <p class="sub" id="since-sub"></p>
  <div class="since" id="since"></div>

  <h2>概况</h2>
  <div class="stats" id="stats"></div>

  <h2>先看这几条</h2>
  <p class="sub">正在造成错数据、让失败看起来像成功、或者碰到 D10 / 发布闸门的。</p>
  <div class="urgent" id="urgent"></div>

  <h2 id="themes-h">主题</h2>
  <p class="sub">点编号跳到台账里的那一项；划掉的已经还了。</p>
  <div class="themes" id="themes"></div>

  <h2>还债顺序</h2>
  <p class="sub">按波次还。绿条是这一波已还的比例；划掉的编号已还，带虚线的正在做。</p>
  <div class="waves" id="waves"></div>

  <h2>数据边界（接受并留座）</h2>
  <p class="sub">订阅或市场本身没有的数据：接受，页面留座写明原因；不算债，订阅或市场变化时重开。</p>
  <ul class="gaps" id="bounds"></ul>
  <h2>需要你拍板</h2>
  <p class="sub">涉及改表、改公开接口、跨仓库发版、安全或删除的，列选项和推荐，等你定。</p>
  <div id="decisions"></div>

  <h2>台账</h2>
  <p class="sub">只列没还完的。条目正文保留英文原文，标识符照抄。</p>
  <div class="filters" role="search">
    <div class="seg" id="prio" aria-label="Priority"></div>
    <select id="sta" aria-label="State"></select>
    <select id="dom" aria-label="Domain"></select>
    <select id="gate" aria-label="Owner gate"></select>
    <select id="repo" aria-label="Repo"></select>
    <input id="q" type="search" placeholder="搜索标题、说法、文件…" aria-label="Search">
    <span class="count" id="count"></span>
  </div>
  <div class="ledger" id="ledger"></div>

  <h2>防线</h2>
  <p class="sub">债还完之后留下来的：让同一类问题不能再回来的机械检查（<code>RATCHETS.md</code>）。</p>
  <div class="tablewrap"><table id="cov"><thead><tr><th>债的类别</th><th>挡住了吗</th><th>靠什么</th><th>缺口怎么补</th></tr></thead><tbody></tbody></table></div>
  <details class="more"><summary id="rat-sum"></summary>
    <div class="tablewrap"><table id="rat"><thead><tr><th>防线</th><th>位置</th><th>挡什么</th><th>强度</th><th>范围与缺口</th></tr></thead><tbody></tbody></table></div>
  </details>

  <h2>没覆盖到的</h2>
  <p class="sub">这些地方没查或只查了一部分，台账不代表它们没问题；下一轮从这里开始。</p>
  <ul class="gaps" id="gaps"></ul>

  <h2>怎么做的</h2>
  <div class="method" id="method"></div>
  <p class="meta" id="src" style="margin-top:14px"></p>
</div>

<script id="data" type="application/json">__DATA__</script>
<script>
(function(){
  var D = JSON.parse(document.getElementById('data').textContent);
  var L = D.items, byId = {}; L.forEach(function(x){ byId[x.id] = x });
  function el(tag, attrs, html){ var e = document.createElement(tag); if (attrs) for (var k in attrs) e.setAttribute(k, attrs[k]); if (html != null) e.innerHTML = html; return e }
  function esc(s){ return String(s == null ? '' : s).replace(/[&<>"]/g, function(c){ return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c] }) }
  function md(s){ return esc(s).replace(/`([^`]+)`/g, '<code>$1</code>').replace(/\*\*([^*]+)\*\*/g, '<b>$1</b>') }
  var SK = {'在做':'s1','观察中':'s2','待你签收':'s3'};
  function stPill(x){ return x.state_key && x.state_key !== '未开始' ? '<span class="st ' + (SK[x.state_key] || '') + '" title="' + esc(x.state) + '">' + esc(x.state_key) + '</span>' : '' }
  function active(x){ return x && x.state_key && x.state_key !== '未开始' }
  function idBtn(id){ var x = byId[id];
    if (!x) return '<button class="tid done" title="已还">' + esc(id) + '</button>';
    return '<button class="tid' + (active(x) ? ' inprog' : '') + '" data-go="' + esc(id) + '" title="' + esc(x.title + (active(x) ? ' — ' + x.state : '')) + '">' + esc(id) + '</button>' }

  document.getElementById('meta').textContent = D.meta;
  document.getElementById('src').textContent = D.src;
  var doneAll = []; D.waves.forEach(function(w){ doneAll = doneAll.concat(w.done) });
  document.getElementById('lede').innerHTML = md(D.summary + ' 按 ' + D.waves.length + ' 波偿还，计划内已还 ' + doneAll.length + ' 项；要你定的 ' + D.decisions.length + ' 件事在「需要你拍板」。');

  var so = document.getElementById('signoff');
  if (!D.signoff.length) so.outerHTML = '<div class="empty">暂无待签收的项。</div>';
  else D.signoff.forEach(function(x){ so.appendChild(el('div', {class:'scard'}, '<div class="hd">' + idBtn(x.id) + '</div><p>' + md(x.text) + '</p><div class="reply">回复：<code>签收 ' + esc(x.id) + '</code> 或 <code>打回 ' + esc(x.id) + '：原因</code></div>')) });
  var S = D.since, sv = document.getElementById('since');
  if (!S){ document.getElementById('since-sub').textContent = '还没有记录上次查看的提交。'; sv.outerHTML = '' }
  else {
    document.getElementById('since-sub').innerHTML = md('从你上次看过的提交 `' + S.base + '`' + (D.seen.when ? '（' + D.seen.when + '）' : '') + ' 到现在。看完回复「看过了」，基线移到当前提交。');
    var parts = [];
    function lst(h, arr, f){ if (arr.length) parts.push('<div><h4>' + h + ' · ' + arr.length + '</h4><ul>' + arr.map(function(a){ return '<li>' + f(a) + '</li>' }).join('') + '</ul></div>') }
    lst('新增', S.added, function(a){ return idBtn(a.id) + ' ' + esc(a.title) });
    lst('关闭（已签收）', S.closed, function(a){ return '<span class="tid done">' + esc(a.id) + '</span> ' + esc(a.title) });
    lst('状态变化', S.states, function(a){ return idBtn(a.id) + ' ' + esc(a.from) + ' → <b>' + esc(a.to) + '</b>' });
    lst('防线新增', S.ratchets_added, function(a){ return md(a) });
    lst('防线移除或放宽', S.ratchets_removed, function(a){ return md(a) });
    lst('提交', S.commits, function(a){ return '<span class="mono">' + esc(a) + '</span>' });
    sv.innerHTML = parts.length ? parts.join('') : '<div>从 <code>' + esc(S.base) + '</code> 起没有变化。</div>';
  }
  var pc = {P0:0,P1:0,P2:0,P3:0}; L.forEach(function(x){ pc[x.priority]++ });
  var gated = L.filter(function(x){ return x.gate !== '不用批' }).length;
  var bar = ['P0','P1','P2','P3'].map(function(p){ return '<i style="width:' + (pc[p] / Math.max(L.length,1) * 100) + '%;background:var(--' + p.toLowerCase() + ')"></i>' }).join('');
  var T = D.tally;
  [[L.length, '项未结<div class="pbar">' + bar + '</div>'],
   [pc.P0 + ' / ' + pc.P1, 'P0 / P1'],
   [(L.length - gated) + ' / ' + gated, '不用你批 / 要你批'],
   [T ? (T[1] + T[2]) + ' / ' + T[0] : '—', '条发现经得住反向核实（本轮）'],
   [doneAll.length + ' / ' + (doneAll.length + L.length), '计划内已还'],
   [L.filter(active).length, '在做 / 观察中 / 待签收'],
   [D.ratchets.length, '条现有防线'],
   [D.ratchet_plan.length, '条待建防线']
  ].forEach(function(a){ document.getElementById('stats').appendChild(el('div', {class:'stat'}, '<b>' + a[0] + '</b><span>' + a[1] + '</span>')) });

  var u = document.getElementById('urgent');
  D.urgent.forEach(function(x){ var it = byId[x.id] || {priority:'P3'};
    u.appendChild(el('div', {class:'ucard'}, '<div class="hd">' + idBtn(x.id) + '<span class="pill ' + it.priority + '">' + it.priority + '</span>' + stPill(it) + '</div><p>' + md(x.text) + '</p>')) });

  document.getElementById('themes-h').textContent = D.themes.length + ' 个主题';
  var th = document.getElementById('themes');
  D.themes.forEach(function(t){ th.appendChild(el('div', {class:'theme'}, '<h3>' + esc(t.t) + '</h3><p>' + md(t.s) + '</p><div class="ids">' + t.ids.map(idBtn).join('') + '</div>')) });

  var wv = document.getElementById('waves');
  D.waves.forEach(function(w){ var all = w.ids.length + w.done.length, prog = w.ids.filter(function(i){ return active(byId[i]) }).length;
    wv.appendChild(el('div', {class:'wave'}, '<div><h3>' + esc(w.n) + '</h3><div class="cnt">' + all + ' 项 · 已还 ' + w.done.length + ' · 在做 ' + prog + '</div><div class="wbar"><i style="width:' + (all ? w.done.length / all * 100 : 0) + '%"></i></div></div><div><p>' + md(w.g) + '</p><div class="ids">' + w.done.map(idBtn).join('') + w.ids.map(idBtn).join('') + '</div></div>')) });

  var bd = document.getElementById('bounds');
  (D.boundaries || []).forEach(function(g){ bd.appendChild(el('li', null, md(g))) });
  var dc = document.getElementById('decisions');
  D.decisions.forEach(function(o){ var d = el('details', {class:'dec'});
    d.innerHTML = '<summary><span class="q">' + esc(o.q) + '</span><span class="ids">' + o.ids.map(idBtn).join('') + '</span></summary><div class="body"><div class="rec"><b>推荐：</b>' + md(o.r) + '</div><ol>' + o.o.map(function(x){ return '<li>' + md(x) + '</li>' }).join('') + '</ol></div>';
    dc.appendChild(d) });

  function opts(sel, label, values){ sel.innerHTML = '<option value="">' + label + '</option>' + values.map(function(v){ return '<option value="' + esc(v) + '">' + esc(v) + '</option>' }).join('') }
  function uniq(f){ var s = {}; L.forEach(function(x){ [].concat(f(x) || []).forEach(function(v){ if (v) s[v] = 1 }) }); return Object.keys(s).sort() }
  opts(document.getElementById('sta'), '全部状态', ['未开始','在做','观察中','待你签收'].filter(function(k){ return L.some(function(x){ return x.state_key === k }) }));
  opts(document.getElementById('dom'), '全部领域', uniq(function(x){ return x.domain }));
  opts(document.getElementById('gate'), '全部审批', uniq(function(x){ return x.gate }));
  opts(document.getElementById('repo'), '全部仓库', uniq(function(x){ return x.repos }));
  var prio = '', pr = document.getElementById('prio');
  ['', 'P0', 'P1', 'P2', 'P3'].forEach(function(p){ var b = el('button', {type:'button', 'aria-pressed': p === '' ? 'true' : 'false'}, p || '全部'); b.onclick = function(){ prio = p; [].forEach.call(pr.children, function(c){ c.setAttribute('aria-pressed', c === b ? 'true' : 'false') }); render() }; pr.appendChild(b) });

  var lg = document.getElementById('ledger');
  var ORDER = {P0:0,P1:1,P2:2,P3:3};
  L.slice().sort(function(a, b){ return ORDER[a.priority] - ORDER[b.priority] || (+a.id.slice(3)) - (+b.id.slice(3)) }).forEach(function(x){
    var d = el('details', {class:'item', id:x.id});
    var ev = (x.evidence || []).map(function(e){ return '<li><div class="loc">' + esc(e.file) + (e.line ? ':' + e.line : '') + '</div><pre>' + esc(e.quote) + '</pre></li>' }).join('');
    function sec(h, v){ return v ? '<div><h4>' + h + '</h4><p>' + md(v) + '</p></div>' : '' }
    d.innerHTML = '<summary><span class="tid">' + esc(x.id) + '</span><span class="pill ' + x.priority + '">' + x.priority + '</span><span class="t">' + esc(x.title) + '</span><span class="tags">' + (x.now ? '<span class="prog">进行中</span>' : '') + '<span class="tag">' + esc(x.domain) + '</span>' + (x.risk ? '<span class="tag">风险 ' + esc(x.risk) + ' · 代价 ' + esc(x.cost) + '</span>' : '') + (x.gate !== '不用批' ? '<span class="tag gate">' + esc(x.gate) + '</span>' : '') + '</span></summary>' +
      '<div class="body"><div class="state"><p><b>状态：</b>' + md(x.state) + '</p>' + (x.accept ? '<p><b>验收：</b>' + md(x.accept) + '</p>' : '<p><b>验收：</b>还没写（进「待你签收」前必须有）</p>') + (x.accept_result ? '<p><b>验收结果：</b>' + md(x.accept_result) + '</p>' : '') + (x.now ? '<p><b>现在：</b>' + md(x.now) + '</p>' : '') + (x.next ? '<p><b>下一步：</b>' + md(x.next) + '</p>' : '') + '</div>' +
      sec('Claim', x.claim) + sec('Measured', x.measured) + sec('Impact', x.impact) + sec('Fix', x.fix) + sec('Ratchet', x.ratchet) +
      (x.notes || []).map(function(n){ return '<div><p>' + md(n) + '</p></div>' }).join('') +
      (ev ? '<div><h4>Evidence · ' + x.evidence.length + '</h4><ul class="ev">' + ev + '</ul></div>' : '') +
      '<div class="meta">repos: ' + esc((x.repos || []).join(', ')) + '</div></div>';
    d._x = x; d._text = (x.id + ' ' + x.title + ' ' + (x.claim || '') + ' ' + (x.fix || '') + ' ' + (x.evidence || []).map(function(e){ return e.file + ' ' + e.quote }).join(' ')).toLowerCase();
    lg.appendChild(d) });

  function render(){
    var sk = document.getElementById('sta').value, dm = document.getElementById('dom').value, g = document.getElementById('gate').value, r = document.getElementById('repo').value, q = document.getElementById('q').value.trim().toLowerCase(), n = 0;
    [].forEach.call(lg.children, function(d){ var x = d._x;
      var show = (!sk || x.state_key === sk) && (!prio || x.priority === prio) && (!dm || x.domain === dm) && (!g || x.gate === g) && (!r || (x.repos || []).indexOf(r) >= 0) && (!q || d._text.indexOf(q) >= 0);
      d.hidden = !show; if (show) n++ });
    document.getElementById('count').textContent = n + ' / ' + L.length;
  }
  ['sta','dom','gate','repo'].forEach(function(id){ document.getElementById(id).onchange = render });
  document.getElementById('q').oninput = render;
  render();

  document.addEventListener('click', function(e){ var b = e.target.closest('[data-go]'); if (!b) return; e.preventDefault();
    var d = document.getElementById(b.getAttribute('data-go')); if (!d) return;
    if (d.hidden){ prio = ''; [].forEach.call(pr.children, function(c, i){ c.setAttribute('aria-pressed', i === 0 ? 'true' : 'false') }); ['sta','dom','gate','repo','q'].forEach(function(id){ document.getElementById(id).value = '' }); render() }
    d.open = true; d.scrollIntoView({block:'start', behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth'});
    d.classList.add('flash'); setTimeout(function(){ d.classList.remove('flash') }, 1600) });

  function v(x){ var k = String(x || '').split(/[（(\s]/)[0].toLowerCase(); return '<span class="v ' + esc(k) + '">' + esc(x) + '</span>' }
  var cv = document.querySelector('#cov tbody');
  D.coverage.forEach(function(c){ cv.appendChild(el('tr', null, '<td class="c">' + md(c[0]) + '</td><td>' + v(c[1]) + '</td><td>' + md(c[2]) + '</td><td>' + md(c[3]) + '</td>')) });
  document.getElementById('rat-sum').textContent = '全部 ' + D.ratchets.length + ' 条现有防线 · ' + D.ratchet_plan.length + ' 条待建（' + D.ratchet_plan.join('；') + '）';
  var rt = document.querySelector('#rat tbody');
  D.ratchets.forEach(function(c){ rt.appendChild(el('tr', null, '<td class="c">' + md(c[0]) + '</td><td>' + md(c[1]) + '</td><td>' + md(c[2]) + '</td><td>' + v(c[3]) + '</td><td>' + md(c[4]) + '</td>')) });

  var gp = document.getElementById('gaps');
  D.gaps.forEach(function(g){ gp.appendChild(el('li', null, md(g))) });
  document.getElementById('method').innerHTML = D.method.split(/\n\s*\n|\n/).filter(Boolean).map(function(p){ return '<p>' + md(p) + '</p>' }).join('');
})();
</script>
</body>
</html>
"""


def behind_origin() -> list[str]:
    """Commits on origin/main that touch the two files and are not in this checkout.

    The page is published by whoever renders it; a render from a stale checkout sends the
    page back in time (10-06: a render from ab2c086 replaced one from deeea31's parent).
    """
    root = HERE.parent
    subprocess.run(["git", "-C", str(root), "fetch", "-q", "origin", "main"], capture_output=True)
    r = subprocess.run(["git", "-C", str(root), "log", "--format=%h %s", "HEAD..origin/main", "--",
                        "agent-config/TECH_DEBT.md", "agent-config/RATCHETS.md"], capture_output=True, text=True)
    return [ln for ln in r.stdout.split("\n") if ln.strip()] if r.returncode == 0 else []


def main() -> int:
    stale = behind_origin()
    if stale and "--allow-stale" not in sys.argv:
        print("refusing to render: this checkout is behind origin/main for TECH_DEBT.md / RATCHETS.md:", file=sys.stderr)
        for ln in stale:
            print("  " + ln, file=sys.stderr)
        print("rebase onto origin/main (or render from a fresh worktree), or pass --allow-stale", file=sys.stderr)
        return 2
    debt = DEBT.read_text(encoding="utf-8")
    ratchets = RATCHETS.read_text(encoding="utf-8")
    data = parse(debt, ratchets)
    data["since"] = since_last(data["seen"]["sha"], debt, ratchets) if data["seen"] else None
    sha = subprocess.run(["git", "-C", str(HERE), "log", "-1", "--format=%h %cs", "--", str(DEBT), str(RATCHETS)],
                         capture_output=True, text=True).stdout.strip() or "uncommitted"
    data["src"] = f"source: bifrost-trade-infra/agent-config/TECH_DEBT.md + RATCHETS.md @ {sha}"
    missing = [w for w in data["waves"] for i in w["ids"] if i not in {x["id"] for x in data["items"]}]
    if missing:
        print(f"warning: wave ids not in 条目: {missing}", file=sys.stderr)
    blob = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    sys.stdout.write(PAGE.replace("__DATA__", blob))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
