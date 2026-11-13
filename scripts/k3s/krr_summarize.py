#!/usr/bin/env python3
"""Turn KRR JSON output into one drift table (markdown).

Usage: krr_summarize.py <out.md> <krr.json>...   (called by scripts/k3s/krr-report.sh)
"""
import json, sys, collections

def cpu(v): return "—" if v is None else ("?" if v == "?" else f"{float(v):.3f}")
def mem(v): return "—" if v is None else ("?" if v == "?" else f"{float(v)/2**20:.0f}")

out, files = sys.argv[1], sys.argv[2:]
rows = []
for f in files:
    for s in json.load(open(f))["scans"]:
        o, r = s["object"], s["recommended"]
        a = o["allocations"]
        rows.append(dict(ns=o["namespace"], kind=o["kind"], name=o["name"], c=o["container"],
                         cr=a["requests"].get("cpu"), cl=a["limits"].get("cpu"),
                         mr=a["requests"].get("memory"), ml=a["limits"].get("memory"),
                         rc=r["requests"]["cpu"]["value"], rm=r["requests"]["memory"]["value"],
                         sev=s["severity"], pods=len(o["pods"])))
def ratio(cur, rec):
    try:
        cur, rec = float(cur), float(rec)
        return cur / rec if rec > 0 else None
    except (TypeError, ValueError):
        return None
steady = [r for r in rows if r["kind"] in ("Deployment", "StatefulSet", "DaemonSet")]
batch = [r for r in rows if r["kind"] in ("Job", "CronJob")]
def band(rs, cur, rec):
    n = collections.Counter()
    for r in rs:
        q = ratio(r[cur], r[rec])
        n["没写申请量" if r[cur] is None else "没有建议" if q is None else "0.7–1.5 内" if 0.7 <= q <= 1.5 else "写少了(<0.7)" if q < 0.7 else "写多了(>1.5)"] += 1
    return dict(n)
L = []
L.append(f"常驻（Deployment/StatefulSet/DaemonSet）{len(steady)} 个容器；跑完就走的（Job/CronJob）{len(batch)} 个。\n")
L.append(f"- 常驻 CPU 申请量 ÷ KRR 建议：{band(steady,'cr','rc')}")
L.append(f"- 常驻 内存申请量 ÷ KRR 建议：{band(steady,'mr','rm')}")
L.append(f"- 严重度：{dict(collections.Counter(r['sev'] for r in rows))}\n")
def table(rs, title):
    L.append(f"### {title}\n")
    L.append("| 命名空间 | 种类 | 名字 / 容器 | CPU 申请 → 建议（核） | CPU 上限 | 内存申请 → 建议（MiB） | 内存上限 | 严重度 |")
    L.append("|---|---|---|---|---|---|---|---|")
    for r in rs:
        nm = r["name"] if r["name"] == r["c"] else f'{r["name"]} / {r["c"]}'
        L.append(f'| {r["ns"]} | {r["kind"]} | {nm} | {cpu(r["cr"])} → {cpu(r["rc"])} | {cpu(r["cl"])} | {mem(r["mr"])} → {mem(r["rm"])} | {mem(r["ml"])} | {r["sev"]} |')
    L.append("")
def gap(r):
    try: return -abs(float(r["rc"]) - float(r["cr"] or 0))
    except (TypeError, ValueError): return 0
table(sorted(steady, key=gap), "常驻，按 CPU 申请量和建议的差从大到小")
table(sorted(batch, key=lambda r: (r["ns"], r["name"])), "跑完就走的")
open(out, "w").write("\n".join(L) + "\n")
print(L[0]); print("\n".join(L[1:4]))
