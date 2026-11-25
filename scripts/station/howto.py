#!/usr/bin/env python3
"""What do I need to bring to do X? (Station, 2026-11-22; format station.requires/v1, see README.md)

Usage: howto.py            lists what can be looked up, by task
       howto.py <tool>     prints what that tool needs, where to get it, and how to check before going
       howto.py find <word> searches the capability directory (agent-config/CAPABILITIES.md) for a task:
                           who owns it, how to do it, what to bring (Station, 2026-11-24)
"""
import pathlib
import sys

import yaml

INFRA = pathlib.Path(__file__).resolve().parents[2]
# Each domain's self-description sits beside the code it describes, named admission.yaml (LAW-10, map line's
# default with Station, 2026-11-22); platform's come through the map's /catalog/domain?task=.
SELF = sorted(INFRA.glob('scripts/**/admission.yaml'))


def load():
    return {d['tool']: dict(d, _path=str(p.relative_to(INFRA))) for p in SELF for d in [yaml.safe_load(p.read_text())]}


def show(d):
    lines = [f"# {d['task']}（{d['tool']}，归 {d['owner']}）", d['how']]
    if d.get('precheck'):
        lines.append(f"办之前自查：{d['precheck']}")
    lines.append('要带：')
    for b in d['bring']:
        lines.append(f"- {b['id']}：{b['what']}")
        if b.get('command'):
            lines.append(f"  命令：{b['command']}")
        if b.get('get_from'):
            lines.append(f"  缺了去哪拿：{b['get_from']}")
    if d.get('ci_red'):
        lines.append('检查红了：')
        lines += [f"- {c['task']}：{c['means']}。{c['do']}" for c in d['ci_red']]
    if d.get('must_answer'):
        lines.append('找这条线它必须答：')
        lines += [f'- {m}' for m in d['must_answer']]
    lines.append(f"被拒的每一句话和该做什么：{d['_path']} 的 refusals")
    return '\n'.join(lines)


CAPS = INFRA / 'agent-config' / 'CAPABILITIES.md'


def find(words):
    """Rows of the capability directory whose text holds every word, each under its section heading."""
    hits, section = [], ''
    for line in CAPS.read_text().splitlines():
        if line.startswith('#'):
            section = line.lstrip('#').strip()
        elif line.startswith(('|', '- ', '1', '2', '3', '4', '5', '6', '7', '8', '9')) and not line.startswith('|---'):
            low = f"{section} {line}".lower()  # a heading like 「找 Owner」 names every row under it
            if all(w.lower() in low for w in words):
                hits.append(f'[{section}] {line}')
    return hits


def main(argv):
    if argv[:1] == ['find']:
        if len(argv) < 2:
            print('howto.py find <关键词>…', file=sys.stderr)
            return 2
        hits = find(argv[1:])
        print('\n'.join(hits) if hits else f"能力目录里没有「{' '.join(argv[1:])}」；目录第 4 节是已知空白，找工坊（11-station）补。")
        return 0 if hits else 1
    docs = load()
    if not argv:
        for name, d in docs.items():
            print(f"{name}\t{d['task']}（归 {d['owner']}）")
        return 0
    if argv[0] not in docs:
        print(f"没有 {argv[0]}；能查的：{', '.join(docs)}", file=sys.stderr)
        return 1
    print(show(docs[argv[0]]))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
