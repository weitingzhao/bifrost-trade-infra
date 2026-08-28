#!/usr/bin/env bash
# Bifrost — Cursor ↔ Claude 治理配置一致性校验
#
# 双轨维护（CLAUDE.md §7）下，两侧规则必须同步。本脚本机械校验：
#   1. parity-id 双向覆盖 + 版本一致
#   2. skill 名称集合一致
#   3. 活跃治理文件不引用已退役实体
#   4. D10 表述与 spine 一致
#   5. 硬边界 hook 两侧都已接线
#
# 用法: bash scripts/check-agent-config-parity.sh
# 退出码: 0 = 一致 · 1 = 存在漂移

set -uo pipefail

# 向上查找工作区根（标记：bifrost-platform/config/ops-context.yaml），
# 使脚本无论放在工作区根的 scripts/ 还是 bifrost-trade-infra/agent-config/scripts/ 都能工作。
dir="$(cd "$(dirname "$0")" && pwd)"
root=""
for _ in 1 2 3 4 5 6 7 8; do
  if [ -f "$dir/bifrost-platform/config/ops-context.yaml" ]; then root="$dir"; break; fi
  parent="$(dirname "$dir")"
  [ "$parent" = "$dir" ] && break
  dir="$parent"
done
if [ -z "$root" ]; then
  echo "✗ 找不到工作区根（缺 bifrost-platform/config/ops-context.yaml）" >&2
  exit 1
fi
cd "$root" || exit 1

exec python3 - "$root" <<'PY'
import sys, re, pathlib, json

ROOT = pathlib.Path(sys.argv[1])
fails, warns = [], []

def rel(p): return str(p.relative_to(ROOT))

# ─────────── 1. parity-id 双向覆盖 ───────────
cursor_ids = {}   # id -> [file]
for p in list(ROOT.glob('.cursor/rules/*.mdc')) + list(ROOT.glob('*/.cursor/rules/*.mdc')):
    for m in re.finditer(r'^parity-id:\s*(\S+)', p.read_text(), re.M):
        cursor_ids.setdefault(m.group(1), []).append(rel(p))

claude_ids = {}
for p in list(ROOT.glob('.claude/skills/*/SKILL.md')) + list(ROOT.glob('*/.claude/skills/*/SKILL.md')):
    for m in re.finditer(r'^parity-id:\s*(\S+)', p.read_text(), re.M):
        claude_ids.setdefault(m.group(1), []).append(rel(p))
for p in [ROOT / 'CLAUDE.md'] + sorted(ROOT.glob('*/CLAUDE.md')):
    if not p.exists(): continue
    for m in re.finditer(r'^parity-ids:\s*(.+)$', p.read_text(), re.M):
        for i in [x.strip() for x in m.group(1).split(',') if x.strip()]:
            claude_ids.setdefault(i, []).append(rel(p))

def base(i):
    m = re.match(r'^(.*)-v\d+$', i)
    return m.group(1) if m else i

for i, files in sorted(cursor_ids.items()):
    if i in claude_ids: continue
    same = [c for c in claude_ids if base(c) == base(i)]
    if same:
        fails.append(f"版本漂移: Cursor `{i}` ({files[0]}) vs Claude `{same[0]}` — 两侧版本号不一致")
    else:
        fails.append(f"Claude 侧缺失 parity-id `{i}`（Cursor: {files[0]}）")

for i, files in sorted(claude_ids.items()):
    if i in cursor_ids: continue
    if not any(base(c) == base(i) for c in cursor_ids):
        fails.append(f"Cursor 侧缺失 parity-id `{i}`（Claude: {files[0]}）")

# ─────────── 2. skill 集合一致 ───────────
for scope, cdir, kdir in [
    ('workspace', ROOT / '.cursor/skills', ROOT / '.claude/skills'),
    ('frontend',  ROOT / 'bifrost-trade-frontend/.cursor/skills',
                  ROOT / 'bifrost-trade-frontend/.claude/skills'),
]:
    cs = {d.name for d in cdir.iterdir() if d.is_dir()} if cdir.is_dir() else set()
    ks = {d.name for d in kdir.iterdir() if d.is_dir()} if kdir.is_dir() else set()
    # Claude 侧可以多出由 .mdc 转写而来的 skill（规则→skill 的形态差异），只报 warn
    for s in sorted(cs - ks):
        fails.append(f"[{scope}] skill `{s}` 只存在于 Cursor 侧")
    for s in sorted(ks - cs):
        warns.append(f"[{scope}] skill `{s}` 只存在于 Claude 侧（若源自 .mdc 规则转写则属预期）")

# ─────────── 3. 已退役实体引用 ───────────
DEAD = {
    'bifrost-trader-engine': 'spine D8 已归档移出工作区',
    'bifrost-trade-ib-edge': '已被 bifrost-trade-socket 取代',
    'bifrost-ib-edge':       '已被 bifrost-trade-socket 取代',
}
ACTIVE = ([ROOT / 'CLAUDE.md', ROOT / 'AGENT_FACTS.md']
          + sorted(ROOT.glob('*/CLAUDE.md'))
          + sorted(ROOT.glob('.cursor/rules/*.mdc'))
          + sorted(ROOT.glob('*/.cursor/rules/*.mdc'))
          + sorted(ROOT.glob('.claude/skills/*/SKILL.md'))
          + sorted(ROOT.glob('*/.claude/skills/*/SKILL.md')))
for p in ACTIVE:
    if not p.exists(): continue
    for n, line in enumerate(p.read_text().splitlines(), 1):
        for dead, why in DEAD.items():
            # 允许在解释「已退役」的上下文里出现
            ok = re.search(r'D8|已归档|已退役|已停用|取代|替代|archiv|retired|Legacy|归档|superseded', line)
            if dead in line and not ok:
                fails.append(f"{rel(p)}:{n} 引用已退役实体 `{dead}`（{why}）")

# ─────────── 4. D10 与 spine 一致 ───────────
spine = ROOT / 'bifrost-platform/config/ops-context.yaml'
if spine.exists():
    y = spine.read_text(); at = y.find('- id: D10')
    m = re.search(r'^\s*status:\s*(\S+)', y[at:at+400], re.M) if at >= 0 else None
    status = m.group(1).upper() if m else None
    if status is None:
        fails.append("spine 中找不到 decisions[id=D10].status")
    else:
        for f in [ROOT / 'CLAUDE.md', ROOT / '.cursor/rules/trade-execution-freeze.mdc']:
            if not f.exists():
                fails.append(f"缺少 D10 规则文件 {rel(f)}"); continue
            t = f.read_text()
            if status == 'BLOCKED' and 'BLOCKED' not in t:
                fails.append(f"{rel(f)} 未标注 D10 BLOCKED，但 spine 是 BLOCKED")
            if status == 'UNLOCKED' and 'BLOCKED' in t:
                fails.append(f"{rel(f)} 仍写 D10 BLOCKED，但 spine 已 UNLOCKED — 需同步解冻文档")
        print(f"  spine D10 = {status}")

# ─────────── 5. 硬边界 hook 接线 ───────────
guard = ROOT / 'scripts/agent-guard/preflight.js'
if not guard.exists():
    fails.append("缺少 scripts/agent-guard/preflight.js")
else:
    ch = ROOT / '.cursor/hooks.json'
    if ch.exists():
        h = json.loads(ch.read_text()).get('hooks', {})
        for ev in ('beforeShellExecution', 'beforeMCPExecution'):
            if not any('preflight.js' in x.get('command', '') for x in h.get(ev, [])):
                fails.append(f".cursor/hooks.json 未接线 preflight.js 到 {ev}")
    else:
        fails.append("缺少 .cursor/hooks.json")

    cs = ROOT / '.claude/settings.json'
    if cs.exists():
        pre = json.loads(cs.read_text()).get('hooks', {}).get('PreToolUse', [])
        wired = [e for e in pre
                 if any('preflight.js' in hh.get('command', '') for hh in e.get('hooks', []))]
        if not wired:
            fails.append(".claude/settings.json 未接线 preflight.js 到 PreToolUse")
        elif not any('mcp__' in str(e.get('matcher', '')) for e in wired):
            warns.append(".claude/settings.json 的 preflight 未覆盖 mcp__* 工具")
    else:
        fails.append("缺少 .claude/settings.json")

# ─────────── 结果 ───────────
print(f"  parity-id: Cursor {len(cursor_ids)} 条 · Claude {len(claude_ids)} 条")
for w in warns: print(f"  ⚠ {w}")
if fails:
    print(f"\n✗ 发现 {len(fails)} 处漂移：")
    for f in fails: print(f"  - {f}")
    sys.exit(1)
print("\n✓ Cursor ↔ Claude 治理配置一致")
PY
