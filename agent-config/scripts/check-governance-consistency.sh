#!/usr/bin/env bash
# Bifrost — 治理一致性检查
#
# 工作区级的 Cursor 一侧已在清理第 2 波（2026-11-12）删除，不再双轨维护，也不再有 parity-id。
# 本脚本机械校验（节号沿用旧版，1、2 两节随 Cursor 一侧删除）：
#   3. 活跃治理文件不引用已退役实体
#   4. D10 表述与 spine 一致
#   5. 硬边界 hook（preflight.js）已接到 Claude PreToolUse，会话心跳钩子也接上；本机装了 codex 时查 Codex 闸门
#   6. 各 repo 本地 HEAD 相对 origin/main 的新鲜度（Agent 认知是否过期）
#   7. 家目录路径棘轮：各仓库 origin/main 不新增写死的 /Users/<name>/（基线内放行）
#
# 用法: bash scripts/check-governance-consistency.sh [--static-tree <候选工作区>]
#   --static-tree 只跑 3、4 两节，只读候选树（ci-infra 的 parity-static 阶段）
# 退出码: 0 = 一致 · 1 = 存在漂移

set -uo pipefail

# S6: explicit candidate-tree mode, before any host/hook/ref inspection.
static_tree=''
if [ "${1-}" = --static-tree ]; then
  [ "$#" -eq 2 ] && [ -d "$2" ] || { echo 'invalid --static-tree' >&2; exit 2; }
  static_tree="$(cd "$2" && pwd -P)"
elif [ "$#" -ne 0 ]; then
  echo 'unknown governance-check argument' >&2; exit 2
fi

# 向上查找工作区根（标记：bifrost-platform/config/ops-context.yaml），
# 使脚本无论放在工作区根的 scripts/ 还是 bifrost-trade-infra/agent-config/scripts/ 都能工作。
dir="$(cd "$(dirname "$0")" && pwd)"
root=""
if [ -n "$static_tree" ]; then root="$static_tree"; fi
for _ in 1 2 3 4 5 6 7 8; do
  [ -n "$root" ] && break
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

exec python3 - "$root" "$static_tree" <<'PY'
import sys, re, pathlib, json

ROOT = pathlib.Path(sys.argv[1])
STATIC = bool(sys.argv[2])
fails, warns = [], []

if STATIC:
    for name in ('CLAUDE.md', 'AGENT_FACTS.md', 'bifrost-platform/config/ops-context.yaml'):
        path = ROOT / name
        if not path.exists() or not path.resolve().is_relative_to(ROOT):
            print(f'FAIL parity-static missing/outside candidate: {name}')
            sys.exit(1)
    # Follow only workspace links which resolve into this candidate tree.
    for pattern in ('.claude/skills/*/SKILL.md',):
        for path in ROOT.glob(pattern):
            if not path.resolve().is_relative_to(ROOT):
                print(f'FAIL parity-static outside candidate: {path}')
                sys.exit(1)

def rel(p): return str(p.relative_to(ROOT))

# ─────────── 3. 已退役实体引用 ───────────
# 名字 -> (匹配式, 原因)。socket 也认 `bifrost-trade-{core,socket,...}` 这种花括号写法。
DEAD = {
    'bifrost-trader-engine': (r'bifrost-trader-engine', 'spine D8 已归档移出工作区'),
    'bifrost-trade-ib-edge': (r'bifrost-trade-ib-edge', '已被 bifrost-trade-socket 取代'),
    'bifrost-ib-edge':       (r'bifrost-ib-edge', '已被 bifrost-trade-socket 取代'),
    'bifrost-trade-socket':  (r'bifrost-trade-socket|bifrost-trade-\{[^}]*\bsocket\b', 'Wave 14G-F 已归档移出工作区（2026-08-31）'),
    'Celery':                (r'\b[Cc]elery\b', 'Trade Celery 已退役（D-Wave-6.1 / 6.2）'),
}
ACTIVE = ([ROOT / 'CLAUDE.md', ROOT / 'AGENT_FACTS.md']
          + sorted(ROOT.glob('*/CLAUDE.md'))
          + sorted(ROOT.glob('.claude/skills/*/SKILL.md'))
          + sorted(ROOT.glob('*/.claude/skills/*/SKILL.md')))
# 允许在解释「已退役」或「不用它」的上下文里出现（例如「无 Celery」「不引入 Celery」）
RETIRED_CONTEXT = re.compile(r'D8|已归档|退役|已停用|取代|替代|勿启动|archiv|retired|legacy|归档|superseded|D-Wave-6'
                             r'|无 ?Celery|没有 ?Celery|不引入|remov|dropped', re.I)
for p in ACTIVE:
    if not p.exists(): continue
    for n, line in enumerate(p.read_text().splitlines(), 1):
        for dead, (pattern, why) in DEAD.items():
            if re.search(pattern, line) and not RETIRED_CONTEXT.search(line):
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
        for f in [ROOT / 'CLAUDE.md', ROOT / 'AGENT_FACTS.md']:
            if not f.exists():
                fails.append(f"缺少 D10 规则文件 {rel(f)}"); continue
            t = f.read_text()
            if status == 'BLOCKED' and 'BLOCKED' not in t:
                fails.append(f"{rel(f)} 未标注 D10 BLOCKED，但 spine 是 BLOCKED")
            if status == 'UNLOCKED' and 'BLOCKED' in t:
                fails.append(f"{rel(f)} 仍写 D10 BLOCKED，但 spine 已 UNLOCKED — 需同步解冻文档")
        print(f"  spine D10 = {status}")

if STATIC:
    for failure in fails:
        print(f'FAIL parity-static {failure}')
    print(f'parity-static: governance consistency; failures={len(fails)}')
    sys.exit(bool(fails))

# ─────────── 5. 硬边界 hook 接线 ───────────
guard = ROOT / 'scripts/agent-guard/preflight.js'
if not guard.exists():
    fails.append("缺少 scripts/agent-guard/preflight.js")
else:
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

    # 会话钩子接心跳（R5:5.5-12 §4.3）：规则在 check_session_hooks.py（有自己的单元测试）。
    sh = ROOT / 'bifrost-trade-infra/agent-config/scripts/check_session_hooks.py'
    if not sh.exists():
        fails.append("缺少 bifrost-trade-infra/agent-config/scripts/check_session_hooks.py")
    else:
        import importlib.util
        spec = importlib.util.spec_from_file_location('check_session_hooks', sh)
        session_hooks = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(session_hooks)
        read = lambda p: json.loads(p.read_text()) if p.exists() else {}
        fails.extend(session_hooks.problems(read(cs)))

    # Codex 的接线在用户级 ~/.codex，不进仓库；本机装了 codex 才查（W-35）。
    # 没有 trust 的 hook 会被 Codex 无声跳过，所以问 Codex 自己，不只看文件在不在。
    import os, shutil, subprocess
    cg = ROOT / 'bifrost-trade-infra/agent-config/codex/check-codex-guard.py'
    if shutil.which('codex') and cg.exists():
        try:
            r = subprocess.run([sys.executable, str(cg)], capture_output=True, text=True, timeout=60,
                               env={**os.environ, 'BIFROST_WORKSPACE': str(ROOT)})
            if r.returncode != 0:
                fails.append("Codex preflight 验证未通过（配置不符或检查未完成）：" + (r.stdout.strip() or r.stderr.strip())[:1500])
        except Exception as e:
            fails.append(f"Codex 闸门检查没跑完：{e}")

# ─────────── 7. 家目录路径棘轮（W-36 防线，Owner 2026-10-10 卡 7）───────────
# 只拦新增：比基线多的文件或计数才算漂移，基线可以调低时只提示。读 origin/main 而不是 HEAD：
# 共享 checkout 可能因为别的会话的在制品快进不了，旧 HEAD 不是新增。不联网，用上次 fetch 的结果。
hp = ROOT / 'bifrost-trade-infra/agent-config/scripts/check_hardcoded_paths.py'
if hp.exists():
    import os as _os, subprocess as _sp
    try:
        r = _sp.run([sys.executable, str(hp), '--ref', 'origin/main', '--new-only'],
                    capture_output=True, text=True, timeout=120,
                    env={**_os.environ, 'BIFROST_WORKSPACE': str(ROOT)})
        out = (r.stdout.strip() or r.stderr.strip())
        if r.returncode != 0:
            fails.append("新增了写死的家目录路径（先 git fetch 再确认）：\n" + out[:1500])
        elif 'can be lowered' in out:
            warns.append("家目录路径基线可以调低：python3 bifrost-trade-infra/agent-config/scripts/check_hardcoded_paths.py --ref origin/main --update")
    except Exception as e:
        fails.append(f"家目录路径检查没跑完：{e}")
else:
    fails.append("缺少 bifrost-trade-infra/agent-config/scripts/check_hardcoded_paths.py")

# ─────────── 6. 认知新鲜度 ───────────
# 规则本身对了，不代表 Agent 手里的认知是对的。隔几天回来，记忆里的镜像版本、
# replicas、目录结构可能已全部失效，而这种失效是无声的。
#
# 不联网：只读已有的 origin/main 与上次 fetch 时间。治理检查不该改状态或卡在网络上。
import subprocess, time

def git(repo, *args):
    try:
        r = subprocess.run(['git', '-C', str(repo), *args],
                           capture_output=True, text=True, timeout=10)
        return r.stdout.strip() if r.returncode == 0 else None
    except Exception:
        return None

STALE_FETCH_SEC = 24 * 3600
stale_notes = []
for repo in sorted(ROOT.glob('bifrost-*')):
    if not (repo / '.git').exists():
        continue
    behind = git(repo, 'rev-list', '--count', 'HEAD..origin/main')
    if behind is None:
        continue
    fetch_head = repo / '.git' / 'FETCH_HEAD'
    age = time.time() - fetch_head.stat().st_mtime if fetch_head.exists() else None

    if behind.isdigit() and int(behind) > 0:
        stale_notes.append(f"{repo.name}: 落后 origin/main {behind} 个 commit — 先 git pull 再下结论")
    elif age is None:
        stale_notes.append(f"{repo.name}: 从未 fetch — origin/main 不可信，无法判断是否落后")
    elif age > STALE_FETCH_SEC:
        stale_notes.append(f"{repo.name}: 上次 fetch 在 {int(age // 3600)}h 前 — origin/main 本身已陈旧")

if stale_notes:
    print("  认知新鲜度：")
    for n in stale_notes:
        print(f"    ⚠ {n}")
else:
    print("  认知新鲜度：各 repo 与 origin/main 同步且 fetch 在 24h 内")

# ─────────── 结果 ───────────
for w in warns: print(f"  ⚠ {w}")
if fails:
    print(f"\n✗ 发现 {len(fails)} 处漂移：")
    for f in fails: print(f"  - {f}")
    sys.exit(1)
print("\n✓ 治理配置一致")
PY
