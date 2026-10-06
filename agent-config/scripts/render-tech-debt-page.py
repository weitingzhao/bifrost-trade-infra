#!/usr/bin/env python3
"""Render agent-config/TECH_DEBT.md and RATCHETS.md into one read-only HTML page.

The page is a view: the two Markdown files are the only source, and the page
embeds them verbatim and renders them in the browser (marked from cdnjs). Publish
the output to the "Trade 技术债台账" artifact after either file changes:

    python3 agent-config/scripts/render-tech-debt-page.py > /tmp/tech-debt.html
"""
from __future__ import annotations

import json
import pathlib
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent.parent
FILES = {"debt": HERE / "TECH_DEBT.md", "ratchets": HERE / "RATCHETS.md"}

PAGE = """<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Trade 技术债台账</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500&family=Noto+Sans+SC:wght@400;500;700&display=swap">
<style>
:root{--bg:#f4f6f8;--panel:#fff;--sunk:#eceff3;--ink:#18202a;--ink2:#4a5562;--mute:#7a8592;--rule:#d9dfe6;--accent:#1f5f8b;--accent-soft:#e3eef6;
  --sans:"IBM Plex Sans","Noto Sans SC",system-ui,-apple-system,"PingFang SC",sans-serif;--mono:"IBM Plex Mono",ui-monospace,"SF Mono",Menlo,monospace}
@media (prefers-color-scheme: dark){:root:not([data-theme="light"]){--bg:#11161c;--panel:#171e26;--sunk:#1d252f;--ink:#e4e9ef;--ink2:#b3bdc8;--mute:#7f8a96;--rule:#2a3440;--accent:#7db4dc;--accent-soft:#1b2c3b;color-scheme:dark}}
:root[data-theme="dark"]{--bg:#11161c;--panel:#171e26;--sunk:#1d252f;--ink:#e4e9ef;--ink2:#b3bdc8;--mute:#7f8a96;--rule:#2a3440;--accent:#7db4dc;--accent-soft:#1b2c3b;color-scheme:dark}
*{box-sizing:border-box}
body{background:var(--bg);color:var(--ink);font-family:var(--sans);font-size:14px;line-height:1.65;margin:0}
.wrap{max-width:1040px;margin:0 auto;padding:24px 16px 64px}
.bar{display:flex;flex-wrap:wrap;gap:10px;align-items:center;justify-content:space-between;margin-bottom:8px}
.src{color:var(--mute);font-family:var(--mono);font-size:12px}
.tabs{display:inline-flex;background:var(--sunk);border-radius:999px;padding:3px}
.tabs button{font:inherit;font-size:13px;border:0;background:none;color:var(--ink2);padding:4px 14px;border-radius:999px;cursor:pointer}
.tabs button[aria-pressed="true"]{background:var(--panel);color:var(--ink);box-shadow:0 0 0 1px var(--rule)}
.tabs button:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
article{background:var(--panel);border:1px solid var(--rule);border-radius:10px;padding:8px 24px 24px}
article h1{font-size:26px;line-height:1.25;margin:18px 0 10px;text-wrap:balance}
article h2{font-size:18px;margin:34px 0 10px;padding-top:12px;border-top:1px solid var(--rule)}
article h3{font-size:14px;font-family:var(--mono);color:var(--accent);margin:28px 0 4px;scroll-margin-top:12px}
article p,article li{max-width:92ch}
article blockquote{margin:12px 0;padding:8px 14px;background:var(--accent-soft);border-radius:8px;color:var(--ink)}
article blockquote p{margin:4px 0}
article code{font-family:var(--mono);font-size:.9em;background:var(--sunk);padding:1px 5px;border-radius:4px;word-break:break-word}
article a{color:var(--accent)}
article ul{padding-left:20px}
.tw{overflow-x:auto;margin:10px 0}
article table{border-collapse:collapse;font-size:12.5px;width:100%;min-width:640px}
article th,article td{border-bottom:1px solid var(--rule);padding:6px 8px;text-align:left;vertical-align:top}
article th{background:var(--sunk);color:var(--mute);font-weight:600;font-size:11.5px}
article td{font-variant-numeric:tabular-nums}
[hidden]{display:none!important}
@media (max-width:640px){article{padding:4px 14px 18px}article h1{font-size:22px}}
</style>
</head>
<body>
<div class="wrap">
  <div class="bar">
    <div class="tabs" role="group" aria-label="View">
      <button type="button" data-v="debt" aria-pressed="true">未结的债</button>
      <button type="button" data-v="ratchets" aria-pressed="false">防线</button>
    </div>
    <span class="src">__SRC__</span>
  </div>
  <article id="debt"></article>
  <article id="ratchets" hidden></article>
</div>
<script id="md" type="application/json">__MD__</script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/marked/12.0.2/marked.min.js"></script>
<script>
(function(){
  var M = JSON.parse(document.getElementById('md').textContent);
  function slug(t){ return t.trim().toLowerCase() }
  Object.keys(M).forEach(function(k){
    var el = document.getElementById(k);
    el.innerHTML = window.marked ? marked.parse(M[k]) : '<pre>' + M[k].replace(/[&<]/g, function(c){ return c === '&' ? '&amp;' : '&lt;' }) + '</pre>';
    el.querySelectorAll('table').forEach(function(t){ var w = document.createElement('div'); w.className = 'tw'; t.parentNode.insertBefore(w, t); w.appendChild(t) });
    el.querySelectorAll('h3').forEach(function(h){ h.id = slug(h.textContent) });
    el.querySelectorAll('a[href$=".md"]').forEach(function(a){ a.removeAttribute('href') });
  });
  var tabs = document.querySelectorAll('.tabs button');
  tabs.forEach(function(b){ b.onclick = function(){ tabs.forEach(function(x){ x.setAttribute('aria-pressed', x === b ? 'true' : 'false') });
    Object.keys(M).forEach(function(k){ document.getElementById(k).hidden = k !== b.dataset.v }) } });
})();
</script>
</body>
</html>
"""


def main() -> int:
    md = {k: p.read_text(encoding="utf-8") for k, p in FILES.items()}
    sha = subprocess.run(["git", "-C", str(HERE), "log", "-1", "--format=%h %cs", "--", *map(str, FILES.values())],
                         capture_output=True, text=True).stdout.strip() or "uncommitted"
    src = f"bifrost-trade-infra/agent-config · TECH_DEBT.md + RATCHETS.md @ {sha}"
    data = json.dumps(md, ensure_ascii=False).replace("</", "<\\/")
    sys.stdout.write(PAGE.replace("__SRC__", src).replace("__MD__", data))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
